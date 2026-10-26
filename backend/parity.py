"""VoxLab parity scaffold — Voicebox-style features, honestly labelled.

This module is a SCAFFOLD, not a finished release. Nothing here downloads
a model at import time, and nothing here claims a feature works until it
has actually been tested with that model/engine on this machine.

Features scaffolded:
- Record: upload handling for a recorded clip (browser MediaRecorder or
  any file). The browser-side recorder is UI only until tested.
- System capture: OS-specific, honest note only — no capture is performed
  here, because loopback capture needs OS setup (see capture_info()).
- Dictation: faster-whisper "large-v3-turbo" (Whisper Turbo) first,
  with an honest fallback to "small" if Turbo fails to load or
  transcribe; otherwise a clear not-available error. The response
  always names the model actually used. No fake transcript is ever
  returned.
- MCP agent voice: POST /api/mcp/speak with per-agent voice mapping.
  This returns the resolved voice/text payload; actual synthesis is
  wired to /api/generate only when a TTS engine is loaded, and the
  response says so explicitly (synthesized: false until then).
- Personalities Rewrite/Compose: TEMPLATE-based transforms only, unless
  a Qwen3 LLM is actually loaded (it is not loaded here). The response
  always says which path was used.
- Multi-voice stories: ffmpeg concatenation of existing WAV files in
  the output/ directory only (no absolute paths, no traversal).
- Audio effects: ffmpeg filters only (speed via atempo, volume,
  echo via aecho). No effect is claimed if ffmpeg is missing.

Parity models (Chatterbox Turbo, LuxTTS, TADA, Qwen CustomVoice,
Whisper Turbo, Qwen3 LLM) are listed in PARITY_MODELS with status
"needs_download" — they are NOT imported, downloaded, or claimed here.
"""
import os
import json
import shutil
import subprocess

from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import JSONResponse, FileResponse

router = APIRouter()

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "output")
UPLOAD_DIR = os.path.join(OUT, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTS = {".wav", ".mp3", ".flac", ".webm", ".ogg", ".m4a"}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024

# Per-agent voice mapping (MCP-style). These are voice IDs from
# server.py VOICES / clone profiles, not real agent identities.
AGENT_VOICES = {
    "default": "af_heart",
    "claude": "af_bella",
    "cursor": "am_adam",
    "cline": "bf_emma",
}

# Parity models: status is honest, never "ready" without a test.
PARITY_MODELS = [
    {"id": "chatterbox-turbo", "job": "Fast cloning, paralinguistic tags", "status": "tested — ResembleAI/chatterbox-turbo, 4.0 GB, 3.80 s clone, exact transcript (see PARITY.md); paralinguistic tags not yet tested"},
    {"id": "luxtts", "job": "Fast CPU cloning, 48 kHz", "status": "tested — EXACT with full 8s reference + steps=8 + speed=0.7 (5.37 s, verified by faster-whisper small AND large-v3-turbo); baseline 5s ref drops the opening words (see PARITY.md)"},
    {"id": "tada", "job": "Long-form generation 700s+", "status": "tested DONE 2026-10-26 — 4.04 s, exact transcript by both small and large-v3-turbo; low-RAM load needs dtype=bfloat16 + low_cpu_mem_usage for the LM only, NOT a global BF16 default (see PARITY.md top section)"},
    {"id": "qwen-customvoice", "job": "Preset speakers, style control", "status": "tested — Qwen3-TTS-12Hz-0.6B-CustomVoice, Ryan, 5.04 s, exact transcript (see PARITY.md); other 8 speakers not individually generated"},
    {"id": "whisper-turbo", "job": "Faster transcription", "status": "WIRED as the dictation engine 2026-10-27 — transcribe() tries large-v3-turbo first, falls back to small on failure (see PARITY.md); Turbo tested exact on the Kokoro sample, 1.6 GB"},
    {"id": "qwen3-llm", "job": "Transcript refinement, persona replies", "status": "tested — Qwen/Qwen3-0.6B downloaded, Rewrite/Compose via llm_used=true (rewrite is minimal at 0.6B, sometimes verbatim; see PARITY.md)"},
]


def _ffmpeg_available():
    return shutil.which("ffmpeg") is not None


def _safe_output_path(name):
    """Resolve a filename inside OUT only; reject traversal/absolute."""
    base = os.path.abspath(OUT)
    path = os.path.abspath(os.path.join(base, os.path.basename(str(name))))
    if not path.startswith(base + os.sep):
        raise ValueError("path outside output directory")
    return path


def _monitor_sources():
    """Detect real audio monitor sources. Returns (list, method, error)."""
    sources = []
    method = None
    error = None
    # PulseAudio: pactl list sources, keep *.monitor entries.
    if shutil.which("pactl"):
        try:
            proc = subprocess.run(["pactl", "list", "sources", "short"],
                                  capture_output=True, text=True, timeout=15)
            if proc.returncode == 0:
                for line in proc.stdout.splitlines():
                    parts = line.split()
                    if len(parts) >= 2 and parts[1].endswith(".monitor"):
                        sources.append(parts[1])
                method = "pactl"
            else:
                error = proc.stderr.strip() or "pactl list sources failed"
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
    if not sources and shutil.which("wpctl"):
        # PipeWire: wpctl status lists nodes; monitor nodes are named
        # "*.monitor" in the audio tree, but parsing is fragile, so
        # only report wpctl presence, not a fabricated source list.
        method = method or "wpctl"
        error = error or "wpctl present but no monitor source parsed"
    if not sources and error is None:
        error = "pactl not installed and no monitor source found"
    return sources, method, error


def capture_info():
    """Honest OS-specific system-capture note, with real detection.

    available=True ONLY if a monitor source was actually detected.
    On Windows/macOS the steps are documented, not claimed as done.
    """
    import platform
    system = platform.system()
    sources, method, error = _monitor_sources() if system == "Linux" else ([], None, None)
    notes = {
        "Windows": "Needs WASAPI loopback (ffmpeg dshow 'Stereo Mix' or a virtual cable). Steps: enable Stereo Mix in Sound settings, then run ffmpeg -f dshow -i audio='Stereo Mix'. Not bundled or tested here.",
        "Darwin": "Needs a virtual audio driver (e.g. BlackHole): set BlackHole as system output, then capture it with ffmpeg -f avfoundation -i ':BlackHole'. Not bundled or tested here.",
        "Linux": "Needs a PulseAudio/PipeWire monitor source (ffmpeg -f pulse -i <monitor>). Detected sources are listed in monitor_sources; if empty, no capture is possible on this machine until PulseAudio/PipeWire runs with a monitor source.",
    }
    return {
        "platform": system,
        "status": "available" if sources else "needs_os_setup",
        "available": bool(sources),
        "monitor_sources": sources,
        "detection_method": method,
        "detection_error": error,
        "note": notes.get(system, "OS-specific loopback setup required. Not bundled or tested here."),
        "capture_performed": False,
    }


def capture_system_audio(duration=5, out_name="capture.wav"):
    """Real Linux PulseAudio monitor capture via ffmpeg.

    duration is clamped to 1-60 s. Returns {"ok": True, ...} only if
    ffmpeg actually wrote a non-empty file; otherwise {"ok": False,
    "error": <real ffmpeg/pactl error>}. Windows/macOS are NOT faked:
    they return ok=False with the documented setup step.
    """
    import platform
    if platform.system() != "Linux":
        return {"ok": False, "error": f"System capture on {platform.system()} needs OS setup (see /api/parity/capture-info); not implemented on this machine."}
    if not _ffmpeg_available():
        return {"ok": False, "error": "ffmpeg not available"}
    try:
        duration = max(1, min(60, float(duration)))
    except Exception:
        return {"ok": False, "error": "duration must be a number of seconds (1-60)"}
    sources, _method, det_err = _monitor_sources()
    if not sources:
        return {"ok": False, "error": f"no PulseAudio monitor source found: {det_err}"}
    out_path = _safe_output_path(out_name)
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "pulse", "-i", sources[0],
           "-t", str(duration), out_path]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=int(duration) + 30)
    if proc.returncode != 0 or not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        return {"ok": False, "error": proc.stderr.strip() or "ffmpeg pulse capture failed"}
    return {"ok": True, "output": os.path.basename(out_path),
            "bytes": os.path.getsize(out_path), "seconds": duration,
            "source": sources[0]}


def transcribe(audio_path, model_size="large-v3-turbo"):
    """Dictation via faster-whisper, decoded with librosa first.

    Proven in AUDIT.md / audit_transcribe.py: passing a file path to
    faster-whisper fails in this venv with av's
    "open() got an unexpected keyword argument 'metadata_errors'".
    Decoding with librosa to a 16 kHz mono ndarray and passing the
    array to model.transcribe() avoids av entirely and returns a real
    transcript. Default model is Whisper Turbo ("large-v3-turbo",
    tested exact on the Kokoro sample); if Turbo fails to load or
    transcribe, "small" is tried honestly and the response names the
    model actually used plus the Turbo error in "fallback_from".
    If both fail, the real errors are returned and no transcript is
    ever invented. Callers may pass model_size="small" explicitly to
    skip Turbo.
    """
    try:
        import librosa
    except Exception as exc:  # noqa: BLE001 - report the real reason
        return {"available": False, "transcript": None,
                "error": f"librosa not available: {exc}"}
    try:
        from faster_whisper import WhisperModel
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "transcript": None,
                "error": f"faster-whisper not available: {exc}"}
    try:
        samples, _sr = librosa.load(audio_path, sr=16000, mono=True)
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "transcript": None,
                "error": f"librosa decode failed: {exc}"}
    attempts = [model_size]
    if model_size != "small":
        attempts.append("small")
    errors = []
    for attempt in attempts:
        try:
            model = WhisperModel(attempt, device="cpu", compute_type="int8")
            segments, info = model.transcribe(samples, beam_size=5)
            text = " ".join(s.text.strip() for s in segments).strip()
            result = {"available": True, "transcript": text, "model": attempt,
                      "detected_language": getattr(info, "language", None)}
            if attempt != model_size:
                result["fallback_from"] = model_size
                result["fallback_error"] = errors[0] if errors else None
            return result
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
    return {"available": False, "transcript": None,
            "error": f"all dictation models failed: {'; '.join(errors)}"}


# --- Kokoro ONNX synthesis for MCP (proven route: test_kokoro_onnx.py) ---
_kokoro_onnx = None
_kokoro_onnx_error = None

# Kokoro preset voice id -> ONNX lang tag. Parler/Edge voice ids are
# deliberately absent: they need their own engines, not Kokoro.
_KOKORO_LANGS = {
    "af": "en-us", "am": "en-us", "bf": "en-gb", "bm": "en-gb",
    "hf": "hi", "hm": "hi",
}


def _get_kokoro_onnx():
    """Lazily load Kokoro ONNX (model files already in output/)."""
    global _kokoro_onnx, _kokoro_onnx_error
    if _kokoro_onnx is not None:
        return _kokoro_onnx, None
    if _kokoro_onnx_error is not None:
        return None, _kokoro_onnx_error
    try:
        from kokoro_onnx import Kokoro
        model_path = os.path.join(OUT, "kokoro-v1.0.onnx")
        voices_path = os.path.join(OUT, "voices-v1.0.bin")
        if not os.path.exists(model_path) or not os.path.exists(voices_path):
            raise FileNotFoundError("Kokoro ONNX model/voices files missing from output/")
        _kokoro_onnx = Kokoro(model_path, voices_path)
        return _kokoro_onnx, None
    except Exception as exc:  # noqa: BLE001
        _kokoro_onnx_error = str(exc)
        return None, _kokoro_onnx_error


def synthesize_kokoro(text, voice, out_name="mcp_speak.wav"):
    """Synthesize with Kokoro ONNX for a Kokoro preset voice only.

    Returns {"ok": True, "output": filename, "seconds": float} on success,
    or {"ok": False, "error": str} — never a claim of audio that was
    not actually written to output/.
    """
    if not text or not text.strip():
        return {"ok": False, "error": "empty text"}
    prefix = str(voice)[:2]
    lang = _KOKORO_LANGS.get(prefix)
    if lang is None:
        return {"ok": False,
                "error": f"voice {voice} is not a Kokoro preset voice; "
                         "Parler/Edge/clone voices need their own engine"}
    kokoro, err = _get_kokoro_onnx()
    if kokoro is None:
        return {"ok": False, "error": f"Kokoro ONNX unavailable: {err}"}
    try:
        import soundfile as sf
        samples, sr = kokoro.create(text, voice=voice, speed=1.0, lang=lang)
        out_path = _safe_output_path(out_name)
        sf.write(out_path, samples, sr)
        seconds = round(len(samples) / sr, 3) if sr else 0
        return {"ok": True, "output": os.path.basename(out_path),
                "seconds": seconds, "sample_rate": sr, "voice": voice}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def rewrite_text(text, persona):
    """Persona Rewrite: real Qwen3 LLM if loaded, else template fallback.

    llm_used=True ONLY when the LLM actually generated the text.
    Any LLM failure returns the template with the real error in note —
    never a fabricated 'LLM' output.
    """
    persona = (persona or "neutral").strip()
    try:
        from llm import rewrite_llm  # noqa: F401  (backend/ is on sys.path via server.py)
        rewritten = rewrite_llm(text, persona)
        if rewritten:
            return {"method": "qwen3-llm", "llm_used": True, "persona": persona,
                    "original": text, "rewritten": rewritten, "model": "Qwen/Qwen3-0.6B"}
    except Exception as exc:  # noqa: BLE001 - fall back honestly
        fallback_note = f"LLM unavailable ({exc}); template fallback used."
    else:
        fallback_note = "LLM returned empty output; template fallback used."
    return {
        "method": "template",
        "llm_used": False,
        "persona": persona,
        "original": text,
        # Framing only: the user's words are preserved verbatim inside.
        "rewritten": f"[{persona}] {text}",
        "note": fallback_note,
    }


def compose_text(persona, topic=""):
    """Persona Compose: real Qwen3 LLM if loaded, else template fallback."""
    persona = (persona or "neutral").strip()
    topic = (topic or "this").strip()
    try:
        from llm import compose_llm  # noqa: F401
        composed = compose_llm(persona, topic)
        if composed:
            return {"method": "qwen3-llm", "llm_used": True, "persona": persona,
                    "composed": composed, "model": "Qwen/Qwen3-0.6B"}
    except Exception as exc:  # noqa: BLE001
        fallback_note = f"LLM unavailable ({exc}); template fallback used."
    else:
        fallback_note = "LLM returned empty output; template fallback used."
    return {
        "method": "template",
        "llm_used": False,
        "persona": persona,
        "composed": f"[{persona}] Here is a line about {topic}, spoken in character.",
        "note": fallback_note,
    }


def synthesize_bengali(text, voice, out_name):
    """MCP synthesis for Parler/Edge voices via backend/bengali.py.

    Returns {"ok": True, "output", "seconds", "engine"} only when audio
    was actually written; on failure {"ok": False, "error": real error}
    — no silent Edge fallback for a requested Parler voice here, so a
    Parler MCP result is never mistaken for Edge audio.
    """
    if not text or not text.strip():
        return {"ok": False, "error": "empty text"}
    try:
        if voice.startswith("parler_"):
            from bengali import generate_parler
            import soundfile as sf
            audio, sr = generate_parler(text, voice[len("parler_"):])
            out_path = _safe_output_path(out_name)
            sf.write(out_path, audio, sr)
            seconds = round(len(audio) / sr, 3) if sr else 0
            return {"ok": True, "output": os.path.basename(out_path),
                    "seconds": seconds, "engine": "parler", "voice": voice}
        if voice.startswith("edge_"):
            from bengali import generate_edge
            data = generate_edge(text, voice)
            out_path = _safe_output_path(out_name)
            with open(out_path, "wb") as fh:
                fh.write(data)
            seconds = None
            if shutil.which("ffprobe"):
                proc = subprocess.run(["ffprobe", "-v", "error",
                                       "-show_entries", "format=duration",
                                       "-of", "default=noprint_wrappers=1:nokey=1",
                                       out_path], capture_output=True, text=True)
                try:
                    seconds = round(float(proc.stdout.strip()), 3)
                except Exception:
                    seconds = None
            return {"ok": True, "output": os.path.basename(out_path),
                    "bytes": len(data), "seconds": seconds,
                    "engine": "edge", "voice": voice}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    return {"ok": False, "error": f"voice {voice} is not a Parler/Edge voice"}


def synthesize_clone(text, voice, ref_wav=None, out_name="mcp_clone.wav"):
    """MCP synthesis for a clone voice via backend/clone.py (Chatterbox).

    Voice naming: "clone_<reference-basename>" (e.g. clone_kokoro_af_heart.wav),
    or voice="clone" with an explicit ref_wav payload field. The reference
    must resolve inside output/ or output/uploads/ — traversal/absolute
    paths are rejected by _safe_output_path / the uploads check below.
    Returns {"ok": True, "output", "seconds", "engine": "chatterbox-clone"}
    only when audio was actually written; otherwise {"ok": False, "error"}.
    Chatterbox model load on CPU is slow on first run (model download
    on first use); that cost is real and is not hidden here.
    """
    if not text or not text.strip():
        return {"ok": False, "error": "empty text"}
    ref_name = ref_wav or (voice[len("clone_"):] if voice.startswith("clone_") else "")
    if not ref_name:
        return {"ok": False,
                "error": "clone voice needs a reference: voice 'clone_<file.wav>' or a ref_wav field"}
    ref_base = os.path.basename(str(ref_name))
    candidates = [os.path.join(OUT, ref_base), os.path.join(UPLOAD_DIR, ref_base)]
    ref_path = next((p for p in candidates if os.path.exists(p)), None)
    if ref_path is None:
        return {"ok": False,
                "error": f"reference clip not found in output/ or output/uploads/: {ref_base}"}
    try:
        from clone import generate_clone
        import soundfile as sf
        wav, sr = generate_clone(text, ref_path)
        # Chatterbox returns a torch tensor, not a numpy array:
        # soundfile cannot write a tensor ("Format not recognised" if
        # passed raw). Convert, and transpose a (1, N) mono tensor to
        # (N,) so soundfile does not read it as 1 sample / N channels.
        try:
            import torch
            if isinstance(wav, torch.Tensor):
                wav = wav.detach().cpu().numpy()
        except ImportError:
            pass
        try:
            import numpy as np
            wav = np.asarray(wav)
            if wav.ndim == 2 and wav.shape[0] == 1:
                wav = wav[0]
            n_samples = int(wav.shape[-1])
        except Exception:
            n_samples = 0
        out_path = _safe_output_path(out_name)
        sf.write(out_path, wav, sr)
        seconds = round(float(n_samples) / sr, 3) if sr and n_samples else 0
        return {"ok": True, "output": os.path.basename(out_path),
                "seconds": seconds, "sample_rate": sr,
                "engine": "chatterbox-clone", "voice": voice, "reference": ref_base}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def concat_story(wav_names, out_name="story.wav"):
    """Concatenate WAV files (inside output/) with ffmpeg."""
    if not _ffmpeg_available():
        return {"ok": False, "error": "ffmpeg not available"}
    paths = []
    for name in wav_names:
        path = _safe_output_path(name)
        if not os.path.exists(path):
            return {"ok": False, "error": f"missing file: {name}"}
        paths.append(path)
    out_path = _safe_output_path(out_name)
    list_path = out_path + ".txt"
    with open(list_path, "w", encoding="utf-8") as fh:
        for path in paths:
            fh.write(f"file '{path}'\n")
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
           "-i", list_path, "-c", "copy", out_path]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not os.path.exists(out_path):
        return {"ok": False, "error": proc.stderr.strip() or "ffmpeg concat failed"}
    return {"ok": True, "output": os.path.basename(out_path),
            "segments": len(paths)}


def apply_effect(input_name, speed=1.0, volume=1.0, echo=False, out_name="effect.wav"):
    """ffmpeg speed/volume/echo. Validates ranges; no effect if ffmpeg missing."""
    if not _ffmpeg_available():
        return {"ok": False, "error": "ffmpeg not available"}
    if not (0.5 <= float(speed) <= 2.0):
        return {"ok": False, "error": "speed must be between 0.5 and 2.0"}
    if not (0.1 <= float(volume) <= 3.0):
        return {"ok": False, "error": "volume must be between 0.1 and 3.0"}
    in_path = _safe_output_path(input_name)
    if not os.path.exists(in_path):
        return {"ok": False, "error": f"missing file: {input_name}"}
    filters = [f"atempo={float(speed)}", f"volume={float(volume)}"]
    if echo:
        filters.append("aecho=0.8:0.7:60:0.3")
    out_path = _safe_output_path(out_name)
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", in_path,
           "-af", ",".join(filters), out_path]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not os.path.exists(out_path):
        return {"ok": False, "error": proc.stderr.strip() or "ffmpeg effect failed"}
    return {"ok": True, "output": os.path.basename(out_path),
            "filters": ",".join(filters)}


@router.get("/api/parity/status")
def parity_status():
    return {
        "record_upload": "scaffold",
        "system_capture": capture_info(),
        "dictation": "faster-whisper large-v3-turbo first, small on failure, via librosa decode (av path avoided), checked at request time, not at import; response names the model actually used",
        "mcp_speak": "voice mapping + synthesis: Kokoro ONNX for Kokoro presets, Parler via venv_parler, Edge via Deno server, clone_ voices via Chatterbox (backend/clone.py) with a reference clip in output/; a failed voice returns synthesized: false with the real error, no silent fallback",
        "personalities": "qwen3-llm if loaded, else template with llm_used=false (see /api/parity/rewrite response)",
        "stories": "scaffold — ffmpeg concat, tested only if ffmpeg present",
        "effects": "scaffold — ffmpeg filters, tested only if ffmpeg present",
        "parity_models": PARITY_MODELS,
        "ffmpeg_available": _ffmpeg_available(),
    }


@router.post("/api/parity/upload")
async def parity_upload(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTS:
        return JSONResponse({"ok": False, "error": f"unsupported extension: {ext}"}, status_code=400)
    dest = os.path.join(UPLOAD_DIR, os.path.basename(file.filename))
    size = 0
    with open(dest, "wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                os.remove(dest)
                return JSONResponse({"ok": False, "error": "file over 50 MB limit"}, status_code=400)
            out.write(chunk)
    return {"ok": True, "filename": os.path.basename(dest), "bytes": size,
            "note": "Saved as a reference clip. Cloning from it needs the Chatterbox engine (see /api/clone path in README, not yet wired to this upload). "}


@router.get("/api/parity/capture-info")
def parity_capture_info():
    return capture_info()


@router.post("/api/parity/capture")
def parity_capture(payload: dict):
    """Real system-audio capture (Linux PulseAudio monitor only).

    duration: seconds, clamped 1-60. On success returns the captured
    file; on failure (no monitor source, no PulseAudio, ffmpeg error)
    returns the real error with HTTP 503 — never a fake capture.
    """
    result = capture_system_audio(
        payload.get("duration", 5),
        payload.get("out_name", "capture.wav"))
    if not result.get("ok"):
        return JSONResponse(result, status_code=503)
    return result


@router.post("/api/parity/dictate")
async def parity_dictate(file: UploadFile = File(...)):
    dest = os.path.join(UPLOAD_DIR, os.path.basename(file.filename or "dictate.wav"))
    with open(dest, "wb") as out:
        out.write(await file.read())
    result = transcribe(dest)
    if not result.get("available"):
        return JSONResponse(result, status_code=503)
    return result


@router.get("/api/parity/audio/{filename}")
def parity_audio(filename: str):
    """Serve a synthesized/story/effect file from output/ only."""
    try:
        path = _safe_output_path(filename)
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    if not os.path.exists(path):
        return JSONResponse({"ok": False, "error": f"missing file: {filename}"}, status_code=404)
    return FileResponse(path, filename=os.path.basename(path))


@router.post("/api/mcp/speak")
def mcp_speak(payload: dict):
    agent = str(payload.get("agent", "default")).lower()
    text = str(payload.get("text", ""))
    voice = payload.get("voice") or AGENT_VOICES.get(agent, AGENT_VOICES["default"])
    if voice.startswith("clone") or payload.get("ref_wav"):
        result = synthesize_clone(text, voice, ref_wav=payload.get("ref_wav"),
                                  out_name=f"mcp_{agent}_clone.wav")
        if result.get("ok"):
            return {
                "agent": agent, "voice": voice, "text": text,
                "synthesized": True, "audio": result["output"],
                "audio_url": f"/api/parity/audio/{result['output']}",
                "seconds": result.get("seconds"), "engine": result["engine"],
                "reference": result.get("reference"),
            }
        return {
            "agent": agent, "voice": voice, "text": text,
            "synthesized": False, "audio": None, "error": result.get("error"),
            "note": "Clone MCP synthesis failed with the real error above; no audio was synthesized and no fallback voice was substituted.",
        }
    if voice.startswith(("parler_", "edge_")):
        ext = "mp3" if voice.startswith("edge_") else "wav"
        result = synthesize_bengali(text, voice, out_name=f"mcp_{agent}.{ext}")
        if result.get("ok"):
            return {
                "agent": agent, "voice": voice, "text": text,
                "synthesized": True, "audio": result["output"],
                "audio_url": f"/api/parity/audio/{result['output']}",
                "seconds": result.get("seconds"), "bytes": result.get("bytes"),
                "engine": result["engine"],
            }
        return {
            "agent": agent, "voice": voice, "text": text,
            "synthesized": False, "audio": None, "error": result.get("error"),
            "note": "Parler/Edge MCP synthesis failed with the real error above; no audio was synthesized and no fallback voice was substituted.",
        }
    result = synthesize_kokoro(text, voice, out_name=f"mcp_{agent}.wav")
    if result.get("ok"):
        return {
            "agent": agent,
            "voice": voice,
            "text": text,
            "synthesized": True,
            "audio": result["output"],
            "audio_url": f"/api/parity/audio/{result['output']}",
            "seconds": result["seconds"],
            "engine": "kokoro-onnx",
        }
    return {
        "agent": agent,
        "voice": voice,
        "text": text,
        "synthesized": False,
        "audio": None,
        "error": result.get("error"),
        "note": "Voice resolved, but no audio was synthesized: see error. "
                "Non-Kokoro voices need their own engine.",
    }


@router.post("/api/parity/rewrite")
def parity_rewrite(payload: dict):
    return rewrite_text(str(payload.get("text", "")), str(payload.get("persona", "neutral")))


@router.post("/api/parity/compose")
def parity_compose(payload: dict):
    return compose_text(str(payload.get("persona", "neutral")), str(payload.get("topic", "")))


@router.post("/api/parity/story")
def parity_story(payload: dict):
    segments = payload.get("segments") or []
    if not isinstance(segments, list) or not segments:
        return JSONResponse({"ok": False, "error": "segments must be a non-empty list"}, status_code=400)
    result = concat_story(segments, payload.get("out_name", "story.wav"))
    if not result.get("ok"):
        return JSONResponse(result, status_code=400)
    return result


@router.post("/api/parity/effect")
def parity_effect(payload: dict):
    result = apply_effect(
        payload.get("input", ""),
        speed=float(payload.get("speed", 1.0)),
        volume=float(payload.get("volume", 1.0)),
        echo=bool(payload.get("echo", False)),
        out_name=payload.get("out_name", "effect.wav"),
    )
    if not result.get("ok"):
        return JSONResponse(result, status_code=400)
    return result
