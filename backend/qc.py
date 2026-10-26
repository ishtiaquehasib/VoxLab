"""VoxLab output QC + prosody helpers (2026-10-27, best-output work).

QC is never invented: qc_check() measures the actual WAV file
(peak/RMS in dBFS, duration, sample rate) and transcribes it with
faster-whisper (small by default, the cached model) via parity.transcribe().
If Whisper is unavailable the response says so (qc_available=false)
instead of returning a made-up transcript. qc_match is a normalised
exact match (lowercase, punctuation/whitespace collapsed); qc_word_match
is the word-overlap ratio, so a near-miss is visible, not hidden.

Prosody:
- rate (atempo, 0.5-2.0) and pitch (asetrate + compensating atempo,
  -12..+12 semitones, duration preserved approximately) use ffmpeg
  (imageio-ffmpeg binary first, else PATH ffmpeg). If ffmpeg is
  missing and rate/pitch is requested, the caller must fail honestly
  — prosody is never silently skipped.
- pause_ms is applied at generation time, not by guessing timings
  in a finished WAV: text is split into sentences, each sentence is
  generated separately, and pause_ms of silence is inserted between
  sentences. sentence_split() is shared so Kokoro and Qwen paths agree.
"""
import os
import re
import subprocess

_SENT_RE = re.compile(r"(?<=[.!?\u2026\u0964])\s*")


def sentence_split(text):
    """Split on . ! ? … and Bengali danda, with or without a space after."""
    text = (text or "").strip()
    if not text:
        return []
    parts = [p.strip() for p in _SENT_RE.split(text)]
    return [p for p in parts if p]


def join_with_pauses(chunks, sr, pause_ms):
    """chunks: list of (samples ndarray, sr). Returns (samples, sr)."""
    import numpy as np
    pause_n = int(round(sr * max(0, int(pause_ms)) / 1000.0)) if pause_ms else 0
    silence = np.zeros(pause_n, dtype=np.float32) if pause_n else None
    out = []
    for i, (arr, _sr) in enumerate(chunks):
        if i and silence is not None:
            out.append(silence)
        out.append(np.asarray(arr, dtype=np.float32).squeeze())
    if not out:
        return np.zeros(0, dtype=np.float32), sr
    return np.concatenate(out), sr


def measure_wav(path):
    """Peak/RMS/duration from the real file. WAV via soundfile;
    other formats (e.g. Edge MP3) via librosa decode — never estimated."""
    import math
    import numpy as np
    def _db(v):
        return round(20 * math.log10(v), 2) if v > 0 else None
    try:
        import soundfile as sf
        info = sf.info(path)
        audio, sr = sf.read(path, always_2d=False)
        arr = np.asarray(audio, dtype=np.float64).squeeze()
        return {"seconds": round(float(info.duration), 3),
                "sample_rate": int(info.samplerate),
                "peak": float(np.max(np.abs(arr))) if arr.size else 0.0,
                "peak_dbfs": _db(float(np.max(np.abs(arr))) if arr.size else 0.0),
                "rms": round(float(np.sqrt(np.mean(arr ** 2))) if arr.size else 0.0, 4),
                "rms_dbfs": _db(float(np.sqrt(np.mean(arr ** 2))) if arr.size else 0.0)}
    except Exception:
        import librosa
        audio, sr = librosa.load(path, sr=None, mono=True)
        arr = np.asarray(audio, dtype=np.float64).squeeze()
        peak = float(np.max(np.abs(arr))) if arr.size else 0.0
        rms = float(np.sqrt(np.mean(arr ** 2))) if arr.size else 0.0
        return {"seconds": round(float(arr.size / sr), 3) if sr else 0.0,
                "sample_rate": int(sr),
                "peak": peak, "peak_dbfs": _db(peak),
                "rms": round(rms, 4), "rms_dbfs": _db(rms)}


def _normalise(text):
    text = (text or "").lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def qc_check(wav_path, expected_text, model_size="small"):
    """Transcribe + measure. Returns a dict; qc_available=false on failure."""
    result = {"qc_available": False, "qc_transcript": None, "qc_match": False,
              "qc_word_match": None, "qc_model": None, "qc_error": None}
    try:
        result.update(measure_wav(wav_path))
    except Exception as exc:  # noqa: BLE001 - measure failure is reported, not hidden
        result["qc_error"] = f"measure failed: {exc}"
        return result
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from parity import transcribe
        tr = transcribe(wav_path, model_size=model_size)
    except Exception as exc:  # noqa: BLE001
        result["qc_error"] = f"transcribe failed: {exc}"
        return result
    if not tr.get("available"):
        result["qc_error"] = tr.get("error") or "whisper unavailable"
        return result
    transcript = tr.get("transcript") or ""
    exp_n, got_n = _normalise(expected_text), _normalise(transcript)
    exp_words, got_words = set(exp_n.split()), set(got_n.split())
    overlap = (len(exp_words & got_words) / len(exp_words)) if exp_words else 0.0
    result.update({"qc_available": True, "qc_transcript": transcript,
                   "qc_match": bool(exp_n and exp_n == got_n),
                   "qc_word_match": round(overlap, 3),
                   "qc_model": tr.get("model"),
                   "qc_detected_language": tr.get("detected_language")})
    return result


def ffmpeg_exe():
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.exists(exe):
            return exe
    except Exception:
        pass
    import shutil
    return shutil.which("ffmpeg")


def apply_rate_pitch(wav_path, out_path, rate=1.0, pitch_semitones=0):
    """ffmpeg rate/pitch on a WAV. Returns (ok, error). No-op if defaults."""
    rate = float(rate or 1.0)
    pitch = float(pitch_semitones or 0)
    if rate == 1.0 and pitch == 0:
        return True, None
    if not (0.5 <= rate <= 2.0):
        return False, "rate must be between 0.5 and 2.0"
    if not (-12 <= pitch <= 12):
        return False, "pitch_semitones must be between -12 and 12"
    exe = ffmpeg_exe()
    if not exe:
        return False, "ffmpeg not available for rate/pitch prosody"
    filters = []
    if pitch != 0:
        factor = 2 ** (pitch / 12.0)
        filters.append(f"asetrate=24000*{factor:.6f},aresample=24000,atempo={1.0 / factor:.6f}")
    if rate != 1.0:
        filters.append(f"atempo={rate:.4f}")
    proc = subprocess.run([exe, "-y", "-v", "error", "-i", wav_path,
                           "-af", ",".join(filters), out_path],
                          capture_output=True, text=True)
    if proc.returncode != 0 or not os.path.exists(out_path):
        return False, (proc.stderr.strip() or "ffmpeg prosody failed")
    return True, None


def normalize_audio_file(path, target_peak_db=-3.0):
    """Peak-normalize a WAV file in place to target_peak_db (default -3 dBFS).

    Returns (ok, peak_dbfs_before, peak_dbfs_after) or (False, error).
    Loudness is peak-based only, not LUFS — that limit is stated in the
    caller. MP3 inputs are not normalized here (WAV generate path only).
    """
    import math
    try:
        import numpy as np, soundfile as sf
        audio, sr = sf.read(path, always_2d=False)
        arr = np.asarray(audio, dtype=np.float64)
        if arr.size == 0:
            return False, "empty audio"
        peak = float(np.max(np.abs(arr)))
        if peak == 0:
            return False, "silent audio"
        before = round(20 * math.log10(peak), 2)
        target = 10 ** (target_peak_db / 20.0)
        sf.write(path, (arr * (target / peak)).astype(np.float32), sr, subtype="PCM_16")
        return True, before, target_peak_db
    except Exception as exc:
        return False, str(exc)
