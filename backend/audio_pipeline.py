"""VoxLab audio pipeline — chunking, trimming, runaway detection and
RMS loudness normalisation for TTS output.

Original VoxLab implementation (written for this project, not copied
from any other codebase). Parameter values follow the published
Voicebox pipeline, used here as reference only:

- ``_voicebox-source/backend/utils/chunked_tts.py`` — 800-char chunks,
  50 ms crossfade, sentence -> clause -> whitespace -> hard-cut split
  order, abbreviation handling, paralinguistic ``[tag]`` atomicity,
  halve-and-retry on runaway (max 2 retries).
- ``_voicebox-source/backend/utils/audio.py`` — RMS normalisation to
  -20 dBFS with peak limit 0.85; per-frame RMS trim (-40 dB threshold,
  20 ms frames, 200 ms minimum trailing silence, 30 ms fade, cut at
  internal silence >= 1000 ms); runaway = speech -> >= 2 s internal
  silence -> more output; reference validation min 2.0 s / max 30 s /
  min RMS 0.01.

Consistency with existing VoxLab code (``backend/qc.py``):
- ``sentence_split`` there splits on ``.!?`` + ellipsis + Bengali
  danda (U+0964); this module's chunker uses the same sentence-end
  set, extended with abbreviation/decimal/tag guards.
- ``qc.normalize_audio_file`` is peak-only (-3 dBFS); the functions
  here are RMS-based instead, which is what equalises perceived
  loudness across engines. The two are complementary, not duplicates.

Pure numpy/soundfile only — no torch, no model imports, no network.
All functions are deterministic and side-effect free, except
``validate_reference_audio`` which only *reads* the file given.
"""

import math
import re

import numpy as np
import soundfile as sf

__all__ = [
    "split_text_into_chunks",
    "trim_tts_output",
    "has_tts_runaway",
    "rms_normalize",
    "crossfade_concat",
    "validate_reference_audio",
    "normalize_reference_audio",
]

# Words whose trailing period is not a sentence end. Compared
# case-insensitively against the token before the period (dots kept, so
# "e.g." and "i.e." match as multi-part tokens).
_ABBREVIATIONS = frozenset({
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "ave", "blvd",
    "inc", "ltd", "corp", "dept", "est", "approx", "vs", "etc",
    "e.g", "i.e", "a.m", "p.m", "u.s", "u.s.a", "u.k",
})

_TAG_RE = re.compile(r"\[[^\]]*\]")
_SENTENCE_END_RE = re.compile(r"[.!?](?:\s|$)|[।\u3002\uff01\uff1f]")
_CLAUSE_RE = re.compile(r"[;:,\u2014](?:\s|$)")


def _tag_spans(text):
    """Return [(start, end), ...] for every ``[tag]`` in *text*."""
    return [(m.start(), m.end()) for m in _TAG_RE.finditer(text)]


def _inside_tag(spans, pos):
    return any(start < pos < end for start, end in spans)


def _token_before_period(text, pos):
    """Token ending just before the '.' at *pos* (letters/dots only)."""
    start = pos - 1
    while start >= 0 and (text[start].isalpha() or text[start] == "."):
        start -= 1
    return text[start + 1:pos].lower()


def _find_last_sentence_end(segment):
    """Index of the last genuine sentence-ending punctuation, or -1.

    Skips periods after abbreviations, decimal points (digit on both
    sides), and punctuation inside a ``[tag]``. Bengali danda
    (U+0964) and CJK ends count as sentence ends.
    """
    spans = _tag_spans(segment)
    best = -1
    for m in _SENTENCE_END_RE.finditer(segment):
        pos = m.start()
        ch = segment[pos]
        if _inside_tag(spans, pos):
            continue
        if ch == ".":
            if _token_before_period(segment, pos) in _ABBREVIATIONS:
                continue
            # Decimal: digit immediately before and after the point.
            if (pos > 0 and segment[pos - 1].isdigit()
                    and pos + 1 < len(segment) and segment[pos + 1].isdigit()):
                continue
        if pos > best:
            best = pos
    return best


def _find_last_clause_boundary(segment):
    """Index of the last clause punctuation (``; : ,`` or em dash), or -1."""
    spans = _tag_spans(segment)
    best = -1
    for m in _CLAUSE_RE.finditer(segment):
        pos = m.start()
        if _inside_tag(spans, pos):
            continue
        if pos > best:
            best = pos
    return best


def _safe_hard_cut(segment, max_chars):
    """Hard-cut position that never lands inside a ``[tag]``.

    Returns an index; the chunk is ``segment[:index + 1]``. If the cut
    would fall inside a tag that starts the segment, the whole tag is
    kept (chunk may exceed *max_chars* by the tag length — atomicity
    wins over the length cap).
    """
    cut = max_chars - 1
    for start, end in _tag_spans(segment):
        if start < cut < end:
            if start > 0:
                return start - 1
            return end  # tag at position 0: keep the whole tag
    return cut


def split_text_into_chunks(text, max_chars=800):
    """Split *text* into chunks of at most *max_chars* characters.

    Priority: sentence end (``.!?`` + Bengali danda, with abbreviation
    and decimal guards) -> clause boundary (``; : ,`` + em dash) ->
    whitespace -> hard cut. A paralinguistic ``[tag]`` is atomic and is
    never split across chunks.
    """
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    chunks = []
    remaining = text
    while remaining:
        remaining = remaining.lstrip()
        if not remaining:
            break
        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break

        segment = remaining[:max_chars]
        split_pos = _find_last_sentence_end(segment)
        if split_pos == -1:
            split_pos = _find_last_clause_boundary(segment)
        if split_pos == -1:
            split_pos = max(
                segment.rfind(" "), segment.rfind("\t"), segment.rfind("\n")
            )
        if split_pos == -1:
            split_pos = _safe_hard_cut(segment, max_chars)

        chunk = remaining[:split_pos + 1].strip()
        if chunk:
            chunks.append(chunk)
        # Guarantee progress even if split_pos landed at 0.
        remaining = remaining[max(split_pos + 1, 1):]

    return chunks


def _frame_rms(audio, frame_len):
    """Per-frame RMS for complete frames only (trailing partial dropped)."""
    n_frames = len(audio) // frame_len
    if n_frames == 0:
        return np.zeros(0, dtype=np.float64)
    framed = np.asarray(audio[:n_frames * frame_len], dtype=np.float64)
    framed = framed.reshape(n_frames, frame_len)
    return np.sqrt(np.mean(framed ** 2, axis=1))


def trim_tts_output(audio, sample_rate=24000, silence_threshold_db=-40.0,
                    min_silence_ms=200, max_internal_silence_ms=1000,
                    fade_ms=30):
    """Trim leading/trailing silence and cut hallucinated tails.

    Leading silence is removed (keeping one 20 ms frame of padding),
    the audio is cut at the start of the first internal silence gap of
    at least *max_internal_silence_ms*, up to *min_silence_ms* of
    trailing silence is kept, and a cosine fade-out of *fade_ms* is
    applied. Returns a float32 ndarray. All-silence input returns an
    empty array (no speech to keep).
    """
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    frame_len = int(sample_rate * 20 / 1000)
    if frame_len <= 0 or len(audio) < frame_len:
        return audio.copy()

    threshold = 10 ** (silence_threshold_db / 20.0)
    rms = _frame_rms(audio, frame_len)
    is_speech = rms >= threshold
    n_frames = len(is_speech)

    if not np.any(is_speech):
        return np.zeros(0, dtype=np.float32)

    first_speech = int(np.argmax(is_speech))
    first_speech = max(0, first_speech - 1)  # one frame of padding

    # Cut at the first internal silence gap >= max_internal_silence_ms.
    cut_frame = n_frames
    if max_internal_silence_ms is not None:
        max_silence_frames = int(max_internal_silence_ms / 20)
        consecutive = 0
        for i in range(first_speech, n_frames):
            if is_speech[i]:
                consecutive = 0
            else:
                consecutive += 1
                if consecutive >= max_silence_frames:
                    cut_frame = i - consecutive + 1
                    break

    # Trim trailing silence, keeping min_silence_ms of tail.
    min_silence_frames = int(min_silence_ms / 20)
    end_frame = cut_frame
    while end_frame > first_speech and not is_speech[end_frame - 1]:
        end_frame -= 1
    end_frame = min(end_frame + min_silence_frames, cut_frame)

    start_sample = first_speech * frame_len
    end_sample = min(end_frame * frame_len, len(audio))
    trimmed = audio[start_sample:end_sample].copy()

    fade_samples = int(sample_rate * fade_ms / 1000)
    if fade_samples > 0 and len(trimmed) > fade_samples:
        fade = np.cos(np.linspace(0, np.pi / 2, fade_samples)) ** 2
        trimmed[-fade_samples:] = trimmed[-fade_samples:] * fade.astype(np.float32)

    return trimmed.astype(np.float32, copy=False)


def has_tts_runaway(audio, sample_rate=24000, silence_threshold_db=-40.0,
                    max_internal_silence_ms=2000):
    """True if speech is followed by a long silence and then more output.

    That shape means the model missed end-of-speech and resumed with
    hallucinated speech or codec noise. Leading/trailing silence does
    not count — the silence must be bounded by speech on both sides.
    """
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    frame_len = int(sample_rate * 20 / 1000)
    if frame_len <= 0 or len(audio) < frame_len:
        return False

    threshold = 10 ** (silence_threshold_db / 20.0)
    rms = _frame_rms(audio, frame_len)
    is_speech = rms >= threshold
    max_silence_frames = int(max_internal_silence_ms / 20)

    seen_speech = False
    consecutive_silence = 0
    for speech in is_speech:
        if speech:
            if seen_speech and consecutive_silence >= max_silence_frames:
                return True
            seen_speech = True
            consecutive_silence = 0
        elif seen_speech:
            consecutive_silence += 1
    return False


def rms_normalize(audio, target_db=-20.0, peak_limit=0.85):
    """Scale audio so its RMS hits *target_db* dBFS, then peak-limit.

    Silent or empty input is returned unchanged (no division by zero,
    no NaN). Returns a float32 ndarray.
    """
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    if audio.size == 0:
        return audio.copy()
    rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
    if not math.isfinite(rms) or rms <= 0:
        return audio.copy()
    target_rms = 10 ** (target_db / 20.0)
    out = audio * (target_rms / rms)
    return np.clip(out, -peak_limit, peak_limit).astype(np.float32, copy=False)


def crossfade_concat(chunks, sample_rate=24000, crossfade_ms=50):
    """Concatenate float32 chunks with a linear crossfade.

    Output length is ``sum(lengths) - crossfade * (n - 1)`` (with the
    overlap clamped when a chunk is shorter than the crossfade).
    Empty input returns an empty array; a single chunk is returned
    unchanged (as a copy); empty chunks are skipped.
    """
    arrays = [np.asarray(c, dtype=np.float32).reshape(-1)
              for c in (chunks or [])]
    arrays = [a for a in arrays if a.size > 0]
    if not arrays:
        return np.zeros(0, dtype=np.float32)
    if len(arrays) == 1:
        return arrays[0].copy()

    crossfade_samples = int(sample_rate * crossfade_ms / 1000)
    result = arrays[0].copy()
    for chunk in arrays[1:]:
        overlap = min(crossfade_samples, len(result), len(chunk))
        if overlap > 0:
            fade_out = np.linspace(1.0, 0.0, overlap, dtype=np.float32)
            fade_in = np.linspace(0.0, 1.0, overlap, dtype=np.float32)
            result[-overlap:] = (result[-overlap:] * fade_out
                                 + chunk[:overlap] * fade_in)
            result = np.concatenate([result, chunk[overlap:]])
        else:
            result = np.concatenate([result, chunk])
    return result.astype(np.float32, copy=False)


def validate_reference_audio(path, min_duration=2.0, max_duration=30.0,
                            min_rms=0.01):
    """Validate a reference-audio file for voice cloning (read-only).

    Returns ``{ok, seconds, peak, rms, rms_dbfs, error}``. ``error`` is
    a plain-language message (or None when valid). Rejects missing /
    unreadable files, empty or silent audio, clips shorter than
    *min_duration* and clips longer than *max_duration*. The file is
    never modified.
    """
    result = {"ok": False, "seconds": 0.0, "peak": 0.0, "rms": 0.0,
              "rms_dbfs": None, "error": None}
    try:
        audio, sr = sf.read(path, always_2d=False)
    except Exception as exc:  # unreadable / missing / unsupported format
        result["error"] = f"Could not read audio file: {exc}"
        return result

    arr = np.asarray(audio, dtype=np.float64)
    if arr.ndim > 1:
        arr = arr.mean(axis=1)  # stereo -> mono for measurement
    arr = arr.reshape(-1)
    if sr <= 0:
        result["error"] = "Could not read audio file: unknown sample rate."
        return result

    seconds = float(arr.size / sr)
    peak = float(np.max(np.abs(arr))) if arr.size else 0.0
    rms = float(np.sqrt(np.mean(arr ** 2))) if arr.size else 0.0
    result.update({
        "seconds": round(seconds, 3),
        "peak": round(peak, 6),
        "rms": round(rms, 6),
        "rms_dbfs": round(20 * math.log10(rms), 2) if rms > 0 else None,
    })

    if arr.size == 0 or peak == 0:
        result["error"] = "Audio file is empty or completely silent."
        return result
    if seconds < min_duration:
        result["error"] = (
            f"Audio is too short — at least {min_duration} seconds is "
            f"needed, this clip is {seconds:.1f} seconds."
        )
        return result
    if seconds > max_duration:
        result["error"] = (
            f"Audio is too long — at most {max_duration} seconds is "
            f"allowed, this clip is {seconds:.1f} seconds."
        )
        return result
    if rms < min_rms:
        result["error"] = (
            "Audio is too quiet or silent — please record a louder, "
            "clearer sample."
        )
        return result

    result["ok"] = True
    return result


def normalize_reference_audio(audio, sample_rate=24000, target_db=-20.0,
                              peak_limit=0.95):
    """Prepare reference audio for cloning: remove DC offset, then RMS-normalise.

    Returns a float32 ndarray. Silent/empty input passes through
    unchanged (via ``rms_normalize``).
    """
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    if audio.size == 0:
        return audio.copy()
    audio = audio - float(np.mean(audio.astype(np.float64)))
    return rms_normalize(audio.astype(np.float32, copy=False),
                         target_db=target_db, peak_limit=peak_limit)
