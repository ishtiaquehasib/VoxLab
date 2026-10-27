"""VoxLab parity scaffold — Voicebox-style features, honestly labelled.

This module is a SCAFFOLD, not a finished release. Nothing here downloads
a model at import time, and nothing here claims a feature works until it
has actually been tested with that model/engine on this machine.

Features scaffolded:
- Record: upload handling for a recorded clip (browser MediaRecorder or
  any file). The browser-side recorder is UI only until tested.
- System capture: OS-specific, honest note only — no capture is performed
  here, because loopback capture needs OS setup (see capture_info()).
- Dictation: faster-whisper "large-v3-turbo" (Whisper Turbo) only
  when requested; no automatic substitution with "small" (removed
  2026-10-27 no-fallback limit) — on failure a clear error plus the
  download action is returned. No fake transcript is ever returned.
- MCP agent voice: POST /api/mcp/speak with per-agent voice mapping.
  This returns the resolved voice/text payload; actual synthesis is
  wired to /api/generate only when a TTS engine is loaded, and the
  response says so explicitly (synthesized: false until then).
- Personalities Rewrite/Compose: real Qwen3-0.6B LLM if it loads,
  with persona presets (traits) and a verbatim retry + verbatim flag;
  otherwise TEMPLATE transforms with llm_used=False. 0.6B rewriting
  is minimal and sometimes verbatim — never claimed as strong.
- Transcript refinement: POST /api/parity/refine-transcript with a
  refine toggle. refine=false returns the original unchanged;
  refine=true uses Qwen3-0.6B to clean fillers/self-corrections/
  punctuation only. If the LLM is unavailable, the original is
  returned with refined=False and the real error — never a fake
  "refined" transcript.
- Remote mode: GET /api/parity/remote-config, POST
  /api/parity/remote/start (one-click local server), GET
  /api/parity/remote/health. See backend/remote.py for limits:
  no auth/encryption, no auto-discovery, remote GPU only if the
  remote machine itself detects one.
- Multi-voice stories: multi-track timeline (trim, start offset,
  per-track volume, parallel mix) or sequential assembly with
  crossfade, plus ffmpeg concatenation for the plain case. Files
  must live in output/ (no absolute paths, no traversal).
- Audio effects: ffmpeg filters (speed, volume, pitch, delay,
  chorus, compressor, low/high-pass, equalizer) PLUS real
  convolution reverb (see _apply_convolution_reverb): a synthetic
  exponential-decay impulse response convolved with the audio
  via scipy FFT convolution, else numpy FFT convolution.
  Pedalboard is NOT installed and NOT required; it is only a
  commented optional dependency in requirements.txt. The old
  No aecho approximation is substituted for convolution reverb:
  if numpy is unavailable, reverb returns an error (2026-10-27
  no-fallback limit). numpy is a required dependency, so that
  error path is not expected to run.
  No effect is claimed if ffmpeg is missing.
- Auto-chunking: long text is split at sentence boundaries into
  chunks <= max_chars; each chunk is synthesized separately and
  the clips are assembled with the story builder (crossfade
  optional). Chunking itself synthesizes nothing.

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

# Same frozen-exe fix as server.py: PyInstaller onedir puts --add-data
# in _internal/ (sys._MEIPASS), NOT beside the exe, so the previous
# fix (BASE = exe dir) pointed at a nonexistent data dir. Split it:
# bundled data from _MEIPASS, writable output beside the exe.
# Unfrozen logic unchanged.
import sys as _sys
if getattr(_sys, "frozen", False):
    DATA_DIR = getattr(_sys, "_MEIPASS", os.path.dirname(os.path.abspath(_sys.executable)))
    BASE = DATA_DIR
    OUT = os.path.join(os.path.dirname(os.path.abspath(_sys.executable)), "output")
else:
    BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATA_DIR = BASE
    OUT = os.path.join(BASE, "output")
UPLOAD_DIR = os.path.join(OUT, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTS = {".wav", ".mp3", ".flac", ".webm", ".ogg", ".m4a"}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_MIC_SECONDS = 30
MIC_SECONDS_TOLERANCE = 0.5  # container overhead on a 30 s MediaRecorder clip

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
    {"id": "qwen-voicedesign", "job": "Design a voice from a text description, no reference audio", "status": "needs_download — SKELETON ONLY 2026-10-27: POST /api/parity/voice-design exists but returns needs_download=true until a real generation passes. Model Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign (~4.54 GB, 1.7B only, 10 languages, NO Bengali). Licence NOT verified on the HF card text itself (106-line fetch, no licence field); secondary sources quote Apache 2.0 but that does NOT satisfy the HF-field check, so do not ship as Apache-verified. Torch conflict: qwen-tts needs torch>=2.9.1 / transformers>=4.57.3 per its pyproject, VoxLab ships torch==2.6.0 for chatterbox-tts — a shared env cannot hold both; VoiceDesign needs an isolated env or a torch upgrade that re-proves chatterbox. NOT tested, NOT bundled."},
]


def _ffmpeg_path():
    """ffmpeg exe: bundled imageio-ffmpeg first, else system PATH.

    imageio-ffmpeg ships a static ffmpeg binary; PyInstaller bundles
    it only with --collect-all imageio_ffmpeg (see workflows). Without
    it, a user PC with no ffmpeg on PATH previously got
    "ffmpeg not available" for every effect/story/concat call.
    """
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.exists(exe):
            return exe
    except Exception:
        pass
    return shutil.which("ffmpeg")


def _ffmpeg_available():
    return _ffmpeg_path() is not None


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
        "Windows": "Code path: capture_windows_audio() in backend/parity.py uses sounddevice WasapiSettings(loopback=True) if sounddevice is installed; otherwise it returns an honest unavailable error. NOT live-tested on Windows — the first real Windows run is the proof.",
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
        "windows_wasapi_code": {
            "implemented": True,
            "method": "sounddevice WasapiSettings(loopback=True) in capture_windows_audio()",
            "requires": "sounddevice on Windows",
            "live_windows_test_pending": True,
        },
    }


def capture_system_audio(duration=5, out_name="capture.wav"):
    """Real Linux PulseAudio monitor capture via ffmpeg.

    duration is clamped to 1-60 s. Returns {"ok": True, ...} only if
    ffmpeg actually wrote a non-empty file; otherwise {"ok": False,
    "error": <real ffmpeg/pactl error>}. Windows/macOS are NOT faked:
    they return ok=False with the documented setup step.
    """
    import platform
    if platform.system() == "Windows":
        return capture_windows_audio(duration, out_name)
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
    cmd = [_ffmpeg_path(), "-y", "-v", "error", "-f", "pulse", "-i", sources[0],
           "-t", str(duration), out_path]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=int(duration) + 30)
    if proc.returncode != 0 or not os.path.exists(out_path) or os.path.getsize(out_path) <= 44:
        return {"ok": False, "error": proc.stderr.strip() or "ffmpeg pulse capture wrote an empty file (header only) — no audio was playing on the monitor source"}
    _meta = _wav_waveform_metadata(out_path)
    if _meta.get("peak", 1) == 0:
        return {"ok": False, "error": "system capture is silent (peak 0) — no audio was playing on the monitor source"}
    return {"ok": True, "output": os.path.basename(out_path),
            "bytes": os.path.getsize(out_path), "seconds": duration,
            "source": sources[0]}


def capture_windows_audio(duration=5, out_name="capture_wasapi.wav"):
    """Windows WASAPI loopback capture via sounddevice, if available.

    Implemented path ONLY: sounddevice with WasapiSettings(loopback=True),
    which records the system mix without a virtual cable or Stereo Mix.
    pyaudiowasapi is NOT used: its loopback API differs and is untested
    here, so claiming it would be a guess. Returns {"ok": False, ...}
    with the real reason on non-Windows machines, when sounddevice is
    missing, when no loopback device is available, or when recording
    fails — never a fake capture. LIVE WINDOWS TEST PENDING: this code
    has never run on a Windows machine (this VM is Linux); the first
    real Windows run is the proof, not this docstring.
    """
    import platform
    system = platform.system()
    if system != "Windows":
        return {"ok": False, "platform": system,
                "error": f"WASAPI loopback capture only runs on Windows; this machine is {system}",
                "live_windows_test_pending": True}
    try:
        duration = max(1, min(60, float(duration)))
    except Exception:
        return {"ok": False, "error": "duration must be a number of seconds (1-60)"}
    try:
        import sounddevice as sd
    except Exception as exc:  # noqa: BLE001
        return {"ok": False,
                "error": f"sounddevice not available on this Windows machine: {exc}. "
                         "Install it (pip install sounddevice) and retry; no capture was performed.",
                "live_windows_test_pending": True}
    try:
        import soundfile as sf
        samplerate = 48000
        frames = int(samplerate * duration)
        recording = sd.rec(frames, samplerate=samplerate, channels=2, dtype="int16",
                           extra_settings=sd.WasapiSettings(loopback=True))
        sd.wait()
        out_path = _safe_output_path(out_name)
        sf.write(out_path, recording, samplerate)
        if not os.path.exists(out_path) or os.path.getsize(out_path) <= 44:
            return {"ok": False, "error": "sounddevice loopback wrote an empty file (header only) — no system audio was playing during the capture; play audio and retry"}
        _meta = _wav_waveform_metadata(out_path)
        if _meta.get("waveform_error") or not _meta.get("seconds"):
            return {"ok": False, "error": f"sounddevice loopback capture has no audio: {_meta.get('waveform_error') or '0 seconds'}"}
        if _meta.get("peak", 0) == 0:
            return {"ok": False, "error": "system capture is silent (peak 0) — no system audio was playing, or the loopback device captured silence; play audio during the capture and retry"}
        return {"ok": True, "output": os.path.basename(out_path),
                "bytes": os.path.getsize(out_path), "seconds": duration,
                "method": "sounddevice WASAPI loopback",
                "live_windows_test_pending": True}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"WASAPI loopback capture failed: {exc}",
                "live_windows_test_pending": True}


def _wav_waveform_metadata(path, buckets=100):
    """Waveform peaks for a WAV file (stdlib wave module only).

    Returns {sample_rate, channels, seconds, peak, rms, peaks[]} where
    peaks are per-bucket max |sample| normalised to 0..1. Non-WAV files
    return waveform=None with a note (ffprobe gives duration only).
    """
    import array
    import wave
    try:
        with wave.open(path, "rb") as wf:
            channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            sample_rate = wf.getframerate()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)
    except Exception as exc:  # noqa: BLE001
        return {"waveform": None, "waveform_error": f"wave decode failed: {exc}"}
    if sampwidth == 2:
        samples = array.array("h")
        scale = 32768.0
    elif sampwidth == 4:
        samples = array.array("i")
        scale = 2147483648.0
    elif sampwidth == 1:
        samples = array.array("B")
        samples = array.array("h", [(s - 128) * 256 for s in samples])
        scale = 32768.0
    else:
        return {"waveform": None, "waveform_error": f"unsupported sample width: {sampwidth}"}
    samples.frombytes(raw)
    if len(samples) == 0:
        return {"waveform": None, "waveform_error": "empty audio"}
    if channels > 1:
        samples = samples[0::channels]
    seconds = round(n_frames / sample_rate, 3) if sample_rate else 0
    peak = max(abs(int(s)) for s in samples) / scale
    rms = (sum(int(s) ** 2 for s in samples) / len(samples)) ** 0.5 / scale
    peaks = []
    bucket_size = max(1, len(samples) // buckets)
    for i in range(0, len(samples), bucket_size):
        chunk = samples[i:i + bucket_size]
        peaks.append(round(max(abs(int(s)) for s in chunk) / scale, 3))
    return {"sample_rate": sample_rate, "channels": channels, "seconds": seconds,
            "peak": round(peak, 3), "rms": round(rms, 3), "peaks": peaks[:buckets]}


def _audio_duration_seconds(path):
    """Duration via ffprobe, falling back to the WAV header."""
    seconds = _ffprobe_seconds(path)
    if seconds is not None:
        return seconds
    meta = _wav_waveform_metadata(path)
    return meta.get("seconds")


def _validate_audio_file(path):
    """Reject header-only / empty / silent clips (the user's 44-byte WAV bug).

    A 44-byte WAV is just a RIFF header with 0 frames: a recorder that
    was stopped instantly, a mic that never delivered samples, or a
    system capture with nothing playing. Such a file must NEVER be
    saved as ok=True and must NEVER reach a clone engine (Chatterbox
    would fail or produce nothing, and the user would see "clone
    doesn't work" with no reason). WAV is checked with the stdlib
    wave module (frames + peak); other containers via ffprobe
    duration + file size. Silence (peak == 0) is also rejected:
    a WASAPI loopback capture with no audio playing writes frames
    of zeros, which is not a usable voice reference.
    Returns {"ok": True, "seconds", "peak", "frames"} or
    {"ok": False, "error": <plain-language reason>}.
    """
    size = os.path.getsize(path) if os.path.exists(path) else 0
    if size == 0:
        return {"ok": False, "error": "uploaded clip is empty (0 bytes) — nothing was recorded; record again while speaking / while system audio is playing"}
    ext = os.path.splitext(path)[1].lower()
    if ext == ".wav":
        if size <= 44:
            return {"ok": False, "error": "uploaded clip is empty (only a 44-byte WAV header, 0 audio frames) — the recorder captured no audio; check mic permission, speak during recording, and for system capture make sure audio is actually playing"}
        meta = _wav_waveform_metadata(path)
        if meta.get("waveform_error"):
            return {"ok": False, "error": f"uploaded WAV could not be decoded: {meta['waveform_error']}"}
        if not meta.get("seconds"):
            return {"ok": False, "error": "uploaded WAV has 0 seconds of audio — the recorder captured no audio"}
        if meta.get("peak", 0) == 0:
            return {"ok": False, "error": "uploaded clip is silent (peak 0) — no voice/system audio was captured; speak during recording, or play audio during a system capture, then retry"}
        return {"ok": True, "seconds": meta["seconds"], "peak": meta["peak"],
                "frames": meta.get("seconds", 0) * meta.get("sample_rate", 0)}
    seconds = _audio_duration_seconds(path)
    if seconds is not None and seconds <= 0:
        return {"ok": False, "error": "uploaded clip has 0 seconds of audio — nothing was recorded"}
    if seconds is None and size < 1024:
        return {"ok": False, "error": f"uploaded clip is only {size} bytes and its duration could not be measured — nothing usable was recorded"}
    return {"ok": True, "seconds": seconds, "peak": None, "frames": None}


PROFILES_DIR = os.path.join(OUT, "profiles")
os.makedirs(PROFILES_DIR, exist_ok=True)


def _save_profile(name, ref_filename, engine):
    """Persist a voice profile: a named reference clip for cloning.

    This is what "Create Voice" was missing: previously a clone
    generation left no profile behind, so the Generate voice list
    never gained the user's voice. Profiles are JSON files in
    output/profiles/ (name, reference basename, engine, timestamp).
    The reference audio itself stays in output/uploads/.
    """
    import re as _re
    import time as _time
    safe = _re.sub(r"[^A-Za-z0-9_.-]", "_", str(name or "voice").strip()) or "voice"
    profile = {"name": safe, "ref_wav": os.path.basename(ref_filename),
               "engine": engine, "created": int(_time.time()),
               "clone_endpoint": "/api/parity/clone"}
    with open(os.path.join(PROFILES_DIR, safe + ".json"), "w") as fh:
        json.dump(profile, fh, indent=2)
    return profile


def _list_profiles():
    out = []
    try:
        for fn in sorted(os.listdir(PROFILES_DIR)):
            if fn.endswith(".json"):
                with open(os.path.join(PROFILES_DIR, fn)) as fh:
                    out.append(json.load(fh))
    except Exception:
        pass
    return out


def _clone_with_engine(text, ref_path, engine, out_name):
    """Run one clone generation. Turbo is the default in-app engine;
    "chatterbox" is the full Chatterbox model via backend/clone.py.
    Returns the generate_* result dict (ok False carries the real error).
    """
    if engine == "chatterbox":
        try:
            import sys as _s
            _here = os.path.dirname(os.path.abspath(__file__))
            if _here not in _s.path:
                _s.path.insert(0, _here)
            from clone import generate_clone
            wav, sr = generate_clone(text, ref_path)
            res = _write_wav_array(wav, sr, out_name)
            res.update({"model": "chatterbox", "engine": "ResembleAI/chatterbox"})
            return res
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "model": "chatterbox", "error": str(exc)}
    return generate_turbo(text, ref_path, out_name)


def _do_clone(text, ref_wav, engine, profile_name, out_name):
    """Shared clone flow for /api/parity/clone and clone-from-upload:
    resolve + validate the reference, save a profile, generate.
    """
    if not (text or "").strip():
        return {"ok": False, "error": "text is required"}
    ref, err = _resolve_ref(ref_wav)
    if err:
        return {"ok": False, "error": err}
    valid = _validate_audio_file(ref)
    if not valid.get("ok"):
        return {"ok": False, "error": valid["error"], "ref_wav": os.path.basename(ref)}
    profile = None
    if profile_name:
        profile = _save_profile(profile_name, ref, engine)
    result = _clone_with_engine(text, ref, engine, out_name)
    if not result.get("ok"):
        return result
    result["ref_wav"] = os.path.basename(ref)
    result["ref_seconds"] = valid.get("seconds")
    result["ref_peak"] = valid.get("peak")
    if valid.get("seconds") and valid["seconds"] < 5:
        result["warning"] = (f"reference is only {valid['seconds']} s; "
                             "Chatterbox Turbo works best with 5+ s of reference audio")
    if profile:
        result["profile"] = profile
    return result


def save_mic_upload(data, filename):
    """Save a mic-recorder (MediaRecorder, max 30 s) upload.

    Plain function behind POST /api/parity/mic-upload so it is testable
    without FastAPI. Enforces the same 50 MB cap as /api/parity/upload
    plus the 30 s recorder cap (0.5 s container tolerance). Returns
    ok/filename/bytes/seconds/waveform metadata, or ok=False with the
    real reason — never a duration or waveform that was not measured.
    """
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in ALLOWED_EXTS:
        return {"ok": False, "error": f"unsupported extension: {ext}"}
    if len(data) > MAX_UPLOAD_BYTES:
        return {"ok": False, "error": "file over 50 MB limit"}
    dest_name = "mic_" + os.path.basename(filename)
    dest = os.path.join(UPLOAD_DIR, dest_name)
    with open(dest, "wb") as out:
        out.write(data)
    # 2026-10-27 clone fix: a 44-byte WAV (header only) used to be
    # saved as ok=True, so the user believed the recording worked
    # and cloning then failed with no reason. Validate first.
    valid = _validate_audio_file(dest)
    if not valid.get("ok"):
        try:
            os.remove(dest)
        except OSError:
            pass
        return {"ok": False, "error": valid["error"], "bytes": len(data)}
    seconds = _audio_duration_seconds(dest)
    if seconds is not None and seconds > MAX_MIC_SECONDS + MIC_SECONDS_TOLERANCE:
        os.remove(dest)
        return {"ok": False, "error": f"mic clip is {seconds} s, over the 30 s recorder limit",
                "seconds": seconds, "max_seconds": MAX_MIC_SECONDS}
    result = {"ok": True, "filename": dest_name, "bytes": len(data),
              "seconds": seconds, "max_seconds": MAX_MIC_SECONDS}
    if ext == ".wav":
        result.update(_wav_waveform_metadata(dest))
        result["waveform_buckets"] = len(result.get("peaks") or [])
    else:
        result["waveform"] = None
        result["waveform_note"] = "waveform peaks are computed for WAV only; duration is from ffprobe"
    return result


def dictate_shortcut(audio_file, paste=False):
    """Shortcut-triggered dictation: transcribe + clipboard (+ paste).

    Wires backend/global_shortcut.py to the same transcribe() used by
    POST /api/parity/dictate: the audio file must already be inside
    output/ or output/uploads/ (e.g. a mic upload). The transcript is
    copied to the clipboard via pyperclip/native tool, and pasted into
    the focused app ONLY if paste=True and a GUI session exists.
    Returns the trigger result plus hotkey info and
    live_windows_test_pending=True — the Windows hotkey + paste run
    has NOT been live-tested on a Windows machine, and is never
    claimed here. A clipboard/paste failure is reported, not hidden.
    """
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from global_shortcut import trigger_dictation, default_hotkey
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"shortcut handler unavailable: {exc}",
                "live_windows_test_pending": True}
    base = os.path.basename(str(audio_file or ""))
    candidates = [os.path.join(OUT, base), os.path.join(UPLOAD_DIR, base)]
    path = next((p for p in candidates if os.path.exists(p)), None)
    if path is None:
        return {"ok": False, "error": f"audio file not found in output/ or output/uploads/: {base}",
                "live_windows_test_pending": True}
    result = trigger_dictation(path, transcribe_fn=transcribe, paste=bool(paste))
    result["hotkey"] = default_hotkey()
    result["live_windows_test_pending"] = True
    return result


def transcribe(audio_path, model_size="large-v3-turbo"):
    """Dictation via faster-whisper, decoded with librosa first.

    Proven in AUDIT.md / audit_transcribe.py: passing a file path to
    faster-whisper fails in this venv with av's
    "open() got an unexpected keyword argument 'metadata_errors'".
    Decoding with librosa to a 16 kHz mono ndarray and passing the
    array to model.transcribe() avoids av entirely and returns a real
    transcript. Default model is Whisper Turbo ("large-v3-turbo",
    tested exact on the Kokoro sample).
    NO-FALLBACK LIMIT (set 2026-10-27, user: "limit tumi thik kore
    daw"): only the REQUESTED model is tried. The old automatic
    Turbo->small substitution is REMOVED — a different model would
    return a different-quality transcript under the requested model's
    name. On failure the response is available=False with the real
    error plus the download action; callers may pass model_size=
    "small" explicitly to request small. A CUDA->CPU retry of the SAME
    model on OOM is kept: same model, same output, different device.
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
    errors = []
    # Whisper device: CUDA float16, else CPU int8 (CTranslate2 has no
    # MPS backend, so MPS machines use CPU here — see device.py).
    # An OOM on CUDA retries the SAME model once on CPU.
    from device import is_oom_error, whisper_device
    _w_device, _w_compute = whisper_device()
    try:
        model = WhisperModel(model_size, device=_w_device, compute_type=_w_compute)
        segments, info = model.transcribe(samples, beam_size=5)
        text = " ".join(s.text.strip() for s in segments).strip()
        return {"available": True, "transcript": text, "model": model_size,
                "detected_language": getattr(info, "language", None)}
    except Exception as exc:  # noqa: BLE001
        if _w_device != "cpu" and is_oom_error(exc):
            try:
                model = WhisperModel(model_size, device="cpu", compute_type="int8")
                segments, info = model.transcribe(samples, beam_size=5)
                text = " ".join(s.text.strip() for s in segments).strip()
                return {"available": True, "transcript": text, "model": model_size,
                        "detected_language": getattr(info, "language", None),
                        "device": "cpu"}
            except Exception as exc2:  # noqa: BLE001
                errors.append(f"{exc}; cpu retry: {exc2}")
        else:
            errors.append(str(exc))
    return {"available": False, "transcript": None, "model": model_size,
            "error": f"dictation model {model_size} failed: {'; '.join(errors)}",
            "download_action": "Download the requested Whisper model on "
                               "the Models page (Turbo: mobiuslabsgmbh/"
                               "faster-whisper-large-v3-turbo), or call "
                               "with model_size='small' explicitly."}


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


# Persona presets: a preset name maps to a trait description used in
# the LLM prompt. Free-form persona names still work — they just get
# no preset trait. Presets are prompt text only, never a copied voice.
PERSONA_PRESETS = {
    "neutral": "clear, neutral narrator voice",
    "warm narrator": "warm, confident narrator in her 30s, friendly and steady",
    "noir detective": "1940s noir detective, dry, terse, world-weary",
    "news anchor": "professional news anchor, crisp, formal, measured pace",
    "friendly teacher": "friendly teacher, patient, clear, encouraging",
    "calm guide": "calm guide, slow, gentle, reassuring",
}


def _resolve_persona(persona):
    """Return (display_name, trait_or_None) for a persona input."""
    name = (persona or "neutral").strip()
    return name, PERSONA_PRESETS.get(name.lower())


_LLM_QUALITY_NOTE = ("Qwen3-0.6B rewriting is minimal and sometimes "
                      "verbatim — this is not strong rewriting. A larger "
                      "persona LLM would be needed to claim strong rewrites.")


def rewrite_text(text, persona):
    """Persona Rewrite: real Qwen3 LLM, or an honest unavailable error.

    llm_used=True ONLY when the LLM actually generated the text.
    verbatim=True means the LLM output matched the input even after
    the retry — it is reported, never hidden. No template substitute.
    """
    persona, trait = _resolve_persona(persona)
    try:
        from llm import rewrite_llm  # noqa: F401  (backend/ is on sys.path via server.py)
        rewritten, verbatim = rewrite_llm(text, persona, persona_trait=trait)
        if rewritten:
            return {"method": "qwen3-llm", "llm_used": True, "persona": persona,
                    "persona_trait": trait, "verbatim": verbatim,
                    "original": text, "rewritten": rewritten,
                    "model": "Qwen/Qwen3-0.6B", "quality_note": _LLM_QUALITY_NOTE}
    except Exception as exc:  # noqa: BLE001
        err = str(exc)
    else:
        err = "LLM returned empty output"
    # NO-FALLBACK LIMIT (2026-10-27): template output removed — it is
    # not a rewrite. Return unavailable + download action instead.
    return {
        "method": "unavailable",
        "llm_used": False,
        "persona": persona,
        "persona_trait": trait,
        "verbatim": False,
        "original": text,
        "rewritten": None,
        "error": err,
        "download_action": "Download Qwen3 0.6B on the Models page (Qwen/Qwen3-0.6B), then retry.",
    }


def compose_text(persona, topic=""):
    """Persona Compose: real Qwen3 LLM, or an honest unavailable error."""
    persona, trait = _resolve_persona(persona)
    topic = (topic or "this").strip()
    try:
        from llm import compose_llm  # noqa: F401
        composed = compose_llm(persona, topic, persona_trait=trait)
        if composed:
            return {"method": "qwen3-llm", "llm_used": True, "persona": persona,
                    "persona_trait": trait,
                    "composed": composed, "model": "Qwen/Qwen3-0.6B",
                    "quality_note": _LLM_QUALITY_NOTE}
    except Exception as exc:  # noqa: BLE001
        err = str(exc)
    else:
        err = "LLM returned empty output"
    # NO-FALLBACK LIMIT (2026-10-27): template sentence removed — it
    # is not a composed persona line. Return unavailable instead.
    return {
        "method": "unavailable",
        "llm_used": False,
        "persona": persona,
        "persona_trait": trait,
        "composed": None,
        "error": err,
        "download_action": "Download Qwen3 0.6B on the Models page (Qwen/Qwen3-0.6B), then retry.",
    }


def refine_transcript(text, refine=False):
    """Transcript refinement with an explicit toggle.

    refine=False: the original is returned unchanged, refined=False.
    refine=True: Qwen3-0.6B cleans fillers/self-corrections/punctuation
    only. If the LLM is unavailable or returns empty, the original is
    returned with refined=False and the real error — a "refined"
    transcript is never invented.
    """
    text = text or ""
    if not refine:
        return {"refined": False, "original": text, "refined_text": text,
                "method": "none", "llm_used": False,
                "note": "Refinement toggle is off; original returned unchanged."}
    try:
        from llm import refine_transcript_llm  # noqa: F401
        cleaned = refine_transcript_llm(text)
        if cleaned:
            return {"refined": True, "original": text, "refined_text": cleaned,
                    "method": "qwen3-llm", "llm_used": True,
                    "model": "Qwen/Qwen3-0.6B",
                    "note": "Fillers/self-corrections/punctuation cleaned only; meaning, names and facts preserved as instructed."}
    except Exception as exc:  # noqa: BLE001
        return {"refined": False, "original": text, "refined_text": text,
                "method": "none", "llm_used": False,
                "error": f"LLM refinement unavailable: {exc}",
                "note": "Original returned unchanged; no refined transcript was invented."}
    return {"refined": False, "original": text, "refined_text": text,
            "method": "none", "llm_used": False,
            "note": "LLM returned empty output; original returned unchanged."}


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


def concat_story(wav_names, out_name="story.wav", crossfade_ms=0):
    """Concatenate WAV files (inside output/) with ffmpeg.

    FIX (2026-10-27, mixed-rate bug): the old implementation used the
    ffmpeg concat demuxer with ``-c copy``, which keeps each segment's
    raw samples but declares the FIRST segment's sample rate for the
    whole file. A 44.1 kHz segment in a 24 kHz container therefore
    played back stretched (e.g. kokoro 24 kHz + mcp_default 44.1 kHz +
    mcp_claude 24 kHz produced 14.74 s instead of the true 12.26 s),
    and a crossfade_ms passed to /api/parity/story was silently
    dropped in legacy mode. Legacy concat now routes through
    build_story_timeline(), which re-encodes every segment to a
    common 24 kHz rate (see _trim_filter's aresample) and honours
    crossfade_ms in sequence mode. Legacy signature/behaviour
    (segments list, output name) is unchanged apart from the added
    crossfade_ms parameter and extra mode/seconds/sample_rate keys.
    """
    if not _ffmpeg_available():
        return {"ok": False, "error": "ffmpeg not available"}
    if not isinstance(wav_names, list) or not wav_names:
        return {"ok": False, "error": "segments must be a non-empty list"}
    result = build_story_timeline(
        [{"file": name} for name in wav_names],
        out_name=out_name, crossfade_ms=crossfade_ms)
    if not result.get("ok"):
        return result
    result["segments"] = len(wav_names)
    result["sample_rate"] = _ffprobe_sample_rate(
        _safe_output_path(out_name))
    return result


def _generate_reverb_ir(sr, decay_s, channels):
    """Deterministic synthetic impulse response: seeded noise with
    exponential decay reaching -60 dB at decay_s (RT60-style).
    Returns float64 array shape (ir_len, channels)."""
    import numpy as np
    ir_len = max(1, int(round(float(sr) * float(decay_s))))
    t = np.arange(ir_len, dtype=np.float64) / float(sr)
    decay = np.exp(-6.91 * t / float(decay_s))
    rng = np.random.default_rng(42)
    mono = rng.standard_normal(ir_len) * decay
    mono = mono / max(float(np.max(np.abs(mono))), 1e-12)
    if channels <= 1:
        return mono.reshape(-1, 1)
    # Decorrelated stereo: independent seeded noise per channel.
    out = np.empty((ir_len, channels), dtype=np.float64)
    for ch in range(channels):
        r = np.random.default_rng(42 + ch)
        col = r.standard_normal(ir_len) * decay
        out[:, ch] = col / max(float(np.max(np.abs(col))), 1e-12)
    return out


def _fft_convolve_channel(data, ir):
    """FFT convolution via scipy if present, else numpy FFT.
    data, ir: 1-D float64 arrays. Returns full-length convolution."""
    try:
        from scipy.signal import fftconvolve
        return fftconvolve(data, ir, mode="full"), "convolution_scipy_fft"
    except Exception:  # noqa: BLE001 - scipy is optional, numpy is required
        import numpy as np
        n = len(data) + len(ir) - 1
        nfft = 1 << (n - 1).bit_length()
        spec = np.fft.rfft(data, nfft) * np.fft.rfft(ir, nfft)
        return np.fft.irfft(spec, nfft)[:n], "convolution_numpy_fft"


def _apply_convolution_reverb(in_path, out_path, decay_s=1.2, mix=0.3):
    """Real convolution reverb. Returns (ok, engine, error).
    Reads WAV via soundfile if installed (shipped env has it), else
    stdlib wave + numpy. Output is dry + mix*wet, peak-normalised
    to <= 0.99, and LONGER than the input by the IR tail (full
    convolution, not trimmed). Raises nothing; errors are returned.
    Requires numpy: if numpy is missing, returns ok=False; the
    caller returns an error (no approximation is substituted)."""
    try:
        import numpy as np
    except Exception as exc:  # noqa: BLE001
        return False, "none", f"numpy unavailable: {exc}"
    try:
        try:
            import soundfile as sf
            data, sr = sf.read(in_path, always_2d=True)
            data = np.asarray(data, dtype=np.float64)
            write = "soundfile"
        except Exception:  # noqa: BLE001 - soundfile optional on this VM
            import wave
            with wave.open(in_path, "rb") as wf:
                sr, ch, sw = wf.getframerate(), wf.getnchannels(), wf.getsampwidth()
                frames = wf.readframes(wf.getnframes())
            if sw == 2:
                raw = np.frombuffer(frames, dtype=np.int16).astype(np.float64) / 32768.0
            elif sw == 4:
                raw = np.frombuffer(frames, dtype=np.int32).astype(np.float64) / 2147483648.0
            elif sw == 1:
                raw = (np.frombuffer(frames, dtype=np.uint8).astype(np.float64) - 128.0) / 128.0
            else:
                return False, "none", f"unsupported sample width {sw}"
            data = raw.reshape(-1, ch)
            write = "wave"
        ir = _generate_reverb_ir(sr, decay_s, data.shape[1])
        wet = np.empty((len(data) + len(ir) - 1, data.shape[1]), dtype=np.float64)
        engine = None
        for ch in range(data.shape[1]):
            wet[:, ch], engine = _fft_convolve_channel(data[:, ch], ir[:, ch])
        dry = np.zeros_like(wet)
        dry[: len(data)] = data
        out = dry + float(mix) * wet
        peak = float(np.max(np.abs(out))) if out.size else 0.0
        if peak > 0.99:
            out = out * (0.99 / peak)
        if write == "soundfile":
            import soundfile as sf
            sf.write(out_path, out, sr, subtype="PCM_16")
        else:
            import wave
            pcm = np.clip(out * 32767.0, -32768, 32767).astype(np.int16)
            with wave.open(out_path, "wb") as wf:
                wf.setnchannels(data.shape[1])
                wf.setsampwidth(2)
                wf.setframerate(sr)
                wf.writeframes(pcm.tobytes())
        return True, engine, None
    except Exception as exc:  # noqa: BLE001
        return False, "none", str(exc)


def apply_effect(input_name, speed=1.0, volume=1.0, echo=False, out_name="effect.wav",
                   pitch_semitones=0, reverb=False, delay_ms=0, chorus=False,
                   compressor=False, lowpass=None, highpass=None,
                   preview_seconds=None, reverb_decay_s=1.2, reverb_mix=0.3):
    """ffmpeg effects + real convolution reverb. Legacy
    speed/volume/echo args still work.

    New params (all optional):
    - pitch_semitones (-12..12): asetrate + atempo, duration preserved.
    - reverb: REAL convolution reverb (synthetic exponential-decay
      IR, scipy FFT else numpy FFT; see _apply_convolution_reverb).
      reverb_decay_s (0.2-3.0, default 1.2), reverb_mix (0-0.8,
      default 0.3). If convolution fails (numpy unavailable), the
      effect returns an error — no approximation is substituted.
    - delay_ms: single echo tap at that delay.
    - chorus: ffmpeg chorus filter. compressor: acompressor.
    - lowpass/highpass: Hz cutoffs. preview_seconds: trim output
      to the first N seconds (live-preview parameters, same chain;
      a convolution tail is added after the trim).
    Returns ok/output/filters/applied, or ok=False with the error.
    """
    if not _ffmpeg_available():
        return {"ok": False, "error": "ffmpeg not available"}
    if not (0.5 <= float(speed) <= 2.0):
        return {"ok": False, "error": "speed must be between 0.5 and 2.0"}
    if not (0.1 <= float(volume) <= 3.0):
        return {"ok": False, "error": "volume must be between 0.1 and 3.0"}
    pitch_semitones = float(pitch_semitones or 0)
    if not (-12 <= pitch_semitones <= 12):
        return {"ok": False, "error": "pitch_semitones must be between -12 and 12"}
    delay_ms = int(delay_ms or 0)
    if not (0 <= delay_ms <= 2000):
        return {"ok": False, "error": "delay_ms must be between 0 and 2000"}
    if preview_seconds is not None and not (0 < float(preview_seconds) <= 60):
        return {"ok": False, "error": "preview_seconds must be between 0 and 60"}
    reverb_decay_s = float(reverb_decay_s or 1.2)
    if not (0.2 <= reverb_decay_s <= 3.0):
        return {"ok": False, "error": "reverb_decay_s must be between 0.2 and 3.0"}
    reverb_mix = float(reverb_mix or 0.3)
    if not (0.0 <= reverb_mix <= 0.8):
        return {"ok": False, "error": "reverb_mix must be between 0.0 and 0.8"}
    in_path = _safe_output_path(input_name)
    if not os.path.exists(in_path):
        return {"ok": False, "error": f"missing file: {input_name}"}
    filters, applied = [], []
    if pitch_semitones != 0:
        sr = _ffprobe_sample_rate(in_path) or 24000
        factor = 2 ** (pitch_semitones / 12.0)
        filters.append(f"asetrate={sr * factor:.1f},aresample={sr},atempo={1.0 / factor:.4f}")
        applied.append(f"pitch_{pitch_semitones:+g}st")
    if lowpass is not None:
        filters.append(f"lowpass=f={float(lowpass)}")
        applied.append(f"lowpass_{lowpass}Hz")
    if highpass is not None:
        filters.append(f"highpass=f={float(highpass)}")
        applied.append(f"highpass_{highpass}Hz")
    if chorus:
        filters.append("chorus=0.5:0.9:50|60|40:0.4|0.32|0.3:0.25|0.4|0.3:2|1.3|0.3")
        applied.append("chorus")
    if delay_ms:
        filters.append(f"aecho=0.8:0.5:{delay_ms}:0.3")
        applied.append(f"delay_{delay_ms}ms")
    # Reverb is NOT an ffmpeg filter: it is applied after the ffmpeg
    # chain by _apply_convolution_reverb(). If that step fails, the
    # effect returns an error — no aecho approximation is substituted.
    if compressor:
        filters.append("acompressor=threshold=-18dB:ratio=3:attack=20:release=200")
        applied.append("compressor")
    filters.append(f"atempo={float(speed)}")
    applied.append(f"speed_{speed}")
    filters.append(f"volume={float(volume)}")
    applied.append(f"volume_{volume}")
    if echo:
        filters.append("aecho=0.8:0.7:60:0.3")
        applied.append("echo_legacy")
    out_path = _safe_output_path(out_name)
    # When reverb is on, ffmpeg writes to a temp file first so the
    # convolution step can read the fully filtered audio.
    ffmpeg_target = out_path
    if reverb:
        stem = os.path.splitext(os.path.basename(out_path))[0]
        ffmpeg_target = _safe_output_path(f"{stem}.noreverb.wav")
    cmd = [_ffmpeg_path(), "-y", "-v", "error"]
    if preview_seconds is not None:
        cmd += ["-t", str(float(preview_seconds))]
    cmd += ["-i", in_path, "-af", ",".join(filters), ffmpeg_target]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not os.path.exists(ffmpeg_target):
        return {"ok": False, "error": proc.stderr.strip() or "ffmpeg effect failed"}
    if reverb:
        ok, engine, err = _apply_convolution_reverb(
            ffmpeg_target, out_path, decay_s=reverb_decay_s, mix=reverb_mix)
        try:
            os.remove(ffmpeg_target)
        except OSError:
            pass
        if not ok:
            # NO-FALLBACK LIMIT (2026-10-27): the old aecho multi-tap
            # approximation is REMOVED — it is not convolution reverb.
            # Requesting reverb and failing convolution is an error.
            return {"ok": False,
                    "error": f"convolution reverb failed ({err}); "
                             "reverb requires numpy/scipy — no echo "
                             "approximation is substituted."}
        applied.append(f"reverb_convolution_decay{reverb_decay_s:g}s_mix{reverb_mix:g}")
        return {"ok": True, "output": os.path.basename(out_path),
                "filters": ",".join(filters), "applied": applied,
                "preview": preview_seconds is not None,
                "reverb_engine": engine}
    return {"ok": True, "output": os.path.basename(out_path),
            "filters": ",".join(filters), "applied": applied,
            "preview": preview_seconds is not None}



def _ffprobe_seconds(path):
    """Duration in seconds via ffprobe, or None on failure."""
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=30)
        return float(proc.stdout.strip()) if proc.returncode == 0 else None
    except Exception:  # noqa: BLE001
        return None


def _ffprobe_sample_rate(path):
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=sample_rate",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=30)
        return int(proc.stdout.strip()) if proc.returncode == 0 else None
    except Exception:  # noqa: BLE001
        return None


def split_text_chunks(text, max_chars=2000):
    """Split text at sentence boundaries into chunks <= max_chars.

    Sentences end on . ! ? … or the Bengali danda (।), even with NO
    space after the danda (e.g. "।আধুনিক") and even across newlines.
    Hard guarantee: no returned chunk exceeds max_chars — any
    oversized chunk is word-split, and a single over-long word is
    hard-split by characters. Returns []; empty text returns [].
    """
    import re
    text = (text or "").strip()
    if not text:
        return []
    max_chars = int(max_chars)
    if max_chars < 100:
        raise ValueError("max_chars must be at least 100")
    # Normalise no-space danda: "।X" -> "। X" so the sentence split
    # below works; other punctuation keeps its existing rule.
    text = re.sub(r"(\u0964)(?=\S)", r"\1 ", text)
    sentences = re.split(r"(?<=[.!?\u2026\u0964])\s+", text)
    chunks, current = [], ""
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        if len(sent) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            words, buf = sent.split(), ""
            for word in words:
                piece = (buf + " " + word).strip()
                if len(piece) > max_chars and buf:
                    chunks.append(buf)
                    buf = word
                else:
                    buf = piece
            if buf:
                chunks.append(buf)
            continue
        candidate = (current + " " + sent).strip()
        if len(candidate) > max_chars and current:
            chunks.append(current)
            current = sent
        else:
            current = candidate
    if current:
        chunks.append(current)
    # Final hard enforcement (belt-and-braces): split any chunk that
    # still exceeds max_chars by words, then by characters.
    enforced = []
    for ch in chunks:
        if len(ch) <= max_chars:
            enforced.append(ch)
            continue
        buf = ""
        for word in ch.split():
            if len(word) > max_chars:
                if buf:
                    enforced.append(buf); buf = ""
                for i in range(0, len(word), max_chars):
                    enforced.append(word[i:i + max_chars])
                continue
            piece = (buf + " " + word).strip()
            if len(piece) > max_chars and buf:
                enforced.append(buf); buf = word
            else:
                buf = piece
        if buf:
            enforced.append(buf)
    return enforced


def auto_chunk_text(text, max_chars=2000):
    """Text-level auto-chunking. Synthesizes nothing; see split_text_chunks."""
    chunks = split_text_chunks(text, max_chars=max_chars)
    return {"ok": True, "chunks": chunks, "count": len(chunks),
            "total_chars": len(text or ""), "max_chars": int(max_chars)}


def build_story_timeline(tracks, out_name="story_timeline.wav", crossfade_ms=0):
    """Multi-track story builder (ffmpeg, files inside output/ only).

    tracks: list of dicts {file, start, trim_start, trim_end, volume}.
    - Timeline mode: any track with an explicit "start" (seconds) is
      placed at that offset; tracks without one default to start=0.
      All tracks are mixed in parallel (adelay + amix).
    - Sequence mode: no track has "start". Clips play one after
      another in list order; crossfade_ms>0 joins them with an
      acrossfade (triangular), crossfade_ms=0 places them back to
      back (still re-encoded, so trim/volume apply).
    Returns ok/output/mode/tracks/seconds, or ok=False with the error.
    """
    if not _ffmpeg_available():
        return {"ok": False, "error": "ffmpeg not available"}
    if not isinstance(tracks, list) or not tracks:
        return {"ok": False, "error": "tracks must be a non-empty list"}
    crossfade_ms = int(crossfade_ms or 0)
    if crossfade_ms < 0 or crossfade_ms > 5000:
        return {"ok": False, "error": "crossfade_ms must be between 0 and 5000"}
    parsed = []
    for track in tracks:
        if not isinstance(track, dict) or not track.get("file"):
            return {"ok": False, "error": "each track needs a file"}
        path = _safe_output_path(track["file"])
        if not os.path.exists(path):
            return {"ok": False, "error": f"missing file: {track['file']}"}
        dur = _ffprobe_seconds(path)
        if dur is None:
            return {"ok": False, "error": f"cannot read duration: {track['file']}"}
        trim_start = float(track.get("trim_start", 0) or 0)
        trim_end = track.get("trim_end")
        trim_end = float(trim_end) if trim_end is not None else dur
        if trim_start < 0 or trim_end <= trim_start or trim_start >= dur:
            return {"ok": False, "error": f"bad trim for {track['file']}"}
        trim_end = min(trim_end, dur)
        volume = float(track.get("volume", 1.0) or 1.0)
        if not (0.0 <= volume <= 3.0):
            return {"ok": False, "error": f"volume must be 0-3 for {track['file']}"}
        start = track.get("start")
        start = float(start) if start is not None else None
        if start is not None and start < 0:
            return {"ok": False, "error": f"start must be >= 0 for {track['file']}"}
        parsed.append({"file": os.path.basename(track["file"]), "path": path,
                       "start": start, "trim_start": trim_start,
                       "trim_end": trim_end, "volume": volume,
                       "duration": round(trim_end - trim_start, 3),
                       "full_duration": dur})
    out_path = _safe_output_path(out_name)
    inputs = []
    for item in parsed:
        inputs += ["-i", item["path"]]

    def _trim_filter(item, label):
        parts = []
        if item["trim_start"] != 0 or item["trim_end"] != item["full_duration"]:
            parts.append(f"atrim=start={item['trim_start']}:end={item['trim_end']}")
        # Common rate for every track: without this, a 44.1 kHz clip
        # mixed/crossfaded with 24 kHz clips plays back stretched or
        # fails acrossfade/amix rate negotiation. 24 kHz is VoxLab's
        # native rate (Kokoro/TADA outputs); 44.1 kHz inputs are
        # resampled down, never stretched.
        parts.append("aresample=24000")
        parts.append("asetpts=PTS-STARTPTS")
        if item["volume"] != 1.0:
            parts.append(f"volume={item['volume']}")
        return f"[{label}]" + ",".join(parts) + f"[t{label}]"

    if any(item["start"] is not None for item in parsed):
        mode = "timeline"
        filters = []
        mix_inputs = []
        for idx, item in enumerate(parsed):
            filters.append(_trim_filter(item, idx))
            delay_ms = int(round((item["start"] or 0) * 1000))
            filters.append(f"[t{idx}]adelay={delay_ms}|{delay_ms}[d{idx}]")
            mix_inputs.append(f"[d{idx}]")
        filters.append(f"{''.join(mix_inputs)}amix=inputs={len(parsed)}:normalize=0:duration=longest[out]")
        filter_complex = ";".join(filters)
        cmd = [_ffmpeg_path(), "-y", "-v", "error"] + inputs + [
            "-filter_complex", filter_complex, "-map", "[out]", out_path]
    elif crossfade_ms > 0 and len(parsed) > 1:
        mode = "sequence-crossfade"
        filters = []
        for idx, item in enumerate(parsed):
            filters.append(_trim_filter(item, idx))
        prev = "t0"
        for idx in range(1, len(parsed)):
            out_label = f"x{idx}"
            filters.append(f"[{prev}][t{idx}]acrossfade=d={crossfade_ms / 1000.0}:c1=tri:c2=tri[{out_label}]")
            prev = out_label
        cmd = [_ffmpeg_path(), "-y", "-v", "error"] + inputs + [
            "-filter_complex", ";".join(filters), "-map", f"[{prev}]", out_path]
    else:
        mode = "sequence" if len(parsed) > 1 else "single"
        if len(parsed) == 1:
            item = parsed[0]
            filters = _trim_filter(item, 0).split("]", 1)[1].rsplit("[", 1)[0]
            cmd = [_ffmpeg_path(), "-y", "-v", "error"] + inputs + ["-af", filters, out_path]
        else:
            filters = []
            mix_inputs = []
            offset = 0.0
            for idx, item in enumerate(parsed):
                filters.append(_trim_filter(item, idx))
                delay_ms = int(round(offset * 1000))
                filters.append(f"[t{idx}]adelay={delay_ms}|{delay_ms}[d{idx}]")
                mix_inputs.append(f"[d{idx}]")
                offset += item["duration"]
            filters.append(f"{''.join(mix_inputs)}amix=inputs={len(parsed)}:normalize=0:duration=longest[out]")
            cmd = [_ffmpeg_path(), "-y", "-v", "error"] + inputs + [
                "-filter_complex", ";".join(filters), "-map", "[out]", out_path]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not os.path.exists(out_path):
        return {"ok": False, "error": proc.stderr.strip() or "ffmpeg story build failed"}
    seconds = _ffprobe_seconds(out_path)
    return {"ok": True, "output": os.path.basename(out_path), "mode": mode,
            "tracks": len(parsed), "seconds": seconds,
            "crossfade_ms": crossfade_ms}



# ---------------------------------------------------------------------------
# In-app parity model endpoints (2026-10-27, NOT pushed, NO release)
# Reuses the exact lab code paths in test_chatterbox_turbo.py,
# test_luxtts_retest.py (variant E), tmp/run_tada_bf16.py,
# test_qwen_customvoice.py and transcribe() (Whisper Turbo dictation).
# Nothing loads at import: every engine is lazy, cached in a module
# global after its first successful load, and every failure returns the
# real error with synthesized/generated=false -- never a fake file.
# Honest shipped-install limit: luxtts_src/ and tada_src/ are gitignored
# test copies on this dev machine, NOT in the repo, so on a fresh
# install those two endpoints return 503 "source not bundled" until the
# sources are vendored or the engines are packaged. The status endpoint
# says so explicitly; it never claims they are bundled.
# ---------------------------------------------------------------------------

def _hf_cache_dir():
    return os.environ.get("HF_HOME") or os.path.join(
        os.path.expanduser("~"), ".cache", "huggingface", "hub")

def _cache_present(repo):
    return os.path.isdir(os.path.join(_hf_cache_dir(), "models--" + repo.replace("/", "--")))

MODEL_ENDPOINTS = {
    "chatterbox-turbo": {
        "endpoint": "POST /api/parity/generate-chatterbox-turbo",
        "repos": ["ResembleAI/chatterbox-turbo"],
        "lab_result": "3.80 s / 182,444 B, exact transcript (lab, kokoro_af_heart.wav ref)",
        "needs_src": None,
    },
    "luxtts": {
        "endpoint": "POST /api/parity/generate-luxtts",
        "repos": ["YatharthS/LuxTTS"],
        "lab_result": "5.37 s / 515,116 B, exact (lab, full 8 s ref, steps=8, speed=0.7)",
        "needs_src": "luxtts_src",
    },
    "tada": {
        "endpoint": "POST /api/parity/generate-tada",
        "repos": ["HumeAI/tada-1b", "HumeAI/tada-codec"],
        "lab_result": "4.04 s / 387,896 B, exact by small AND large-v3-turbo (lab; CPU generate took 928.5 s)",
        "needs_src": "tada_src",
    },
    "qwen-customvoice": {
        "endpoint": "POST /api/parity/generate-qwen-customvoice",
        "repos": ["Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"],
        "lab_result": "Ryan 5.04 s / 241,964 B, exact (lab; other 8 speakers untested)",
        "needs_src": None,
    },
    "whisper-turbo": {
        "endpoint": "POST /api/parity/dictate-whisper-turbo (alias POST /api/parity/generate-whisper-turbo)",
        "repos": ["mobiuslabsgmbh/faster-whisper-large-v3-turbo"],
        "lab_result": "exact transcript of the Kokoro sample, model large-v3-turbo, ~31.5 s wall incl. load (lab)",
        "needs_src": None,
    },
}

def parity_model_status():
    out = []
    for m in PARITY_MODELS:
        ep = MODEL_ENDPOINTS.get(m["id"])
        if not ep:
            continue
        downloaded = all(_cache_present(r) for r in ep["repos"])
        src_ok = True
        if ep["needs_src"]:
            src_ok = os.path.isdir(os.path.join(BASE, ep["needs_src"]))
        out.append({
            "id": m["id"], "job": m["job"], "status": m["status"],
            "endpoint": ep["endpoint"], "lab_result": ep["lab_result"],
            "downloaded": downloaded, "needs_download": not downloaded,
            "bundled": src_ok,
            "note": ("" if src_ok else
                     f"{ep['needs_src']}/ is a gitignored test copy, not bundled in the installer; "
                     "endpoint returns 503 on a fresh install until it is vendored."),
        })
    return out

def _resolve_ref(ref_wav):
    """Reference clip: basename only, searched in output/ then output/uploads/."""
    if not ref_wav:
        return None, "ref_wav is required"
    base = os.path.basename(str(ref_wav))
    for cand in (os.path.join(OUT, base), os.path.join(UPLOAD_DIR, base)):
        if os.path.isfile(cand):
            return cand, None
    return None, f"reference not found in output/: {base}"

def _write_wav_array(wav, sr, out_name):
    import numpy as np
    import soundfile as sf
    arr = np.asarray(wav)
    if arr.ndim == 2:
        arr = arr[0]
    arr = np.asarray(arr, dtype=np.float32).squeeze()
    path = _safe_output_path(out_name)
    sf.write(path, arr, int(sr))
    info = sf.info(path)
    return {"ok": True, "output": os.path.basename(path),
            "seconds": round(float(info.duration), 3),
            "sample_rate": int(info.samplerate),
            "bytes": os.path.getsize(path)}

_TURBO = None
_LUX = None
_TADA = None
_CUSTOMVOICE = None

def generate_turbo(text, ref_wav="kokoro_af_heart.wav", out_name="turbo_clone.wav"):
    if not (text or "").strip():
        return {"ok": False, "error": "text is required"}
    ref, err = _resolve_ref(ref_wav)
    if err:
        return {"ok": False, "error": err}
    global _TURBO
    try:
        if _TURBO is None:
            from chatterbox.tts_turbo import ChatterboxTurboTTS
            _TURBO = ChatterboxTurboTTS.from_pretrained(device="cpu")
        wav = _TURBO.generate(text=text, audio_prompt_path=ref)
        res = _write_wav_array(wav, _TURBO.sr, out_name)
        res.update({"model": "chatterbox-turbo", "engine": "ResembleAI/chatterbox-turbo"})
        return res
    except Exception as exc:  # noqa: BLE001 - return the real error
        return {"ok": False, "model": "chatterbox-turbo", "error": str(exc)}

def generate_luxtts(text, ref_wav="kokoro_af_heart.wav", out_name="luxtts_clone.wav"):
    if not (text or "").strip():
        return {"ok": False, "error": "text is required"}
    ref, err = _resolve_ref(ref_wav)
    if err:
        return {"ok": False, "error": err}
    src = os.path.join(BASE, "luxtts_src")
    if not os.path.isdir(src):
        return {"ok": False, "model": "luxtts",
                "error": "luxtts_src/ not bundled in this install (gitignored test copy); LuxTTS endpoint unavailable until vendored"}
    global _LUX
    try:
        import sys as _s
        if src not in _s.path:
            _s.path.insert(0, src)
        if _LUX is None:
            from zipvoice.luxvoice import LuxTTS
            _LUX = LuxTTS("YatharthS/LuxTTS", device="cpu", threads=2)
        import soundfile as sf
        ref_info = sf.info(ref)
        # Lab-exact variant E: full reference (capped at 8 s), steps=8, speed=0.7.
        enc = _LUX.encode_prompt(ref, rms=0.01, duration=min(8, ref_info.duration))
        wav = _LUX.generate_speech(text, enc, num_steps=8, speed=0.7)
        res = _write_wav_array(wav.numpy().squeeze(), 48000, out_name)
        res.update({"model": "luxtts", "engine": "YatharthS/LuxTTS",
                    "settings": "full-ref (<=8 s), rms=0.01, num_steps=8, speed=0.7"})
        return res
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "model": "luxtts", "error": str(exc)}

def generate_tada(text, ref_wav=None, prompt_text=None, out_name="tada_clone.wav"):
    if not (text or "").strip():
        return {"ok": False, "error": "text is required"}
    src = os.path.join(BASE, "tada_src")
    if not os.path.isdir(src):
        return {"ok": False, "model": "tada",
                "error": "tada_src/ not bundled in this install (gitignored test copy); TADA endpoint unavailable until vendored"}
    ref = os.path.join(src, "tada", "samples", "ljspeech.wav") if not ref_wav else None
    if ref_wav:
        ref, err = _resolve_ref(ref_wav)
        if err:
            return {"ok": False, "error": err}
    if not os.path.isfile(ref):
        return {"ok": False, "error": f"TADA reference not found: {ref}"}
    prompt = prompt_text or ("The examination and testimony of the experts, enabled the "
                             "commission to conclude that five shots may have been fired.")
    global _TADA
    try:
        import sys as _s
        if src not in _s.path:
            _s.path.insert(0, src)
        import torch, torchaudio
        if _TADA is None:
            from tada.modules.encoder import Encoder
            from tada.modules.tada import TadaForCausalLM
            try:
                encoder = Encoder.from_pretrained("HumeAI/tada-codec", subfolder="encoder",
                                                  low_cpu_mem_usage=True).to("cpu")
                # BF16 on the LM load ONLY (lab finding): a global BF16 default
                # breaks the float32 encoder; float32 LM init OOM-kills this VM.
                model = TadaForCausalLM.from_pretrained("HumeAI/tada-1b", low_cpu_mem_usage=True,
                                                        dtype=torch.bfloat16).to("cpu")
            except Exception as load_exc:  # noqa: BLE001
                # The Llama tokenizer load hits the gated HF repo and 401s
                # when no HF token is configured, even though the tokenizer
                # files are already in the local HF cache (that is how the
                # lab run succeeded). Retry once with offline mode, which
                # forces local-cache resolution; if the cache is absent
                # this fails honestly instead of pretending to download.
                if "gated" not in str(load_exc) and "401" not in str(load_exc):
                    raise
                # NOTE: HF_HUB_OFFLINE is read by huggingface_hub at import
                # time, so setting the env var alone after import does NOT
                # stop the HTTP check -- the in-process constant must be
                # flipped as well, then restored.
                _prev_offline = os.environ.get("HF_HUB_OFFLINE")
                os.environ["HF_HUB_OFFLINE"] = "1"
                os.environ["TRANSFORMERS_OFFLINE"] = "1"
                _hub_constants = None
                try:
                    import huggingface_hub.constants as _hub_constants
                    _prev_const = _hub_constants.HF_HUB_OFFLINE
                    _hub_constants.HF_HUB_OFFLINE = True
                except Exception:
                    _prev_const = None
                try:
                    encoder = Encoder.from_pretrained("HumeAI/tada-codec", subfolder="encoder",
                                                      low_cpu_mem_usage=True).to("cpu")
                    model = TadaForCausalLM.from_pretrained("HumeAI/tada-1b", low_cpu_mem_usage=True,
                                                            dtype=torch.bfloat16).to("cpu")
                finally:
                    if _prev_offline is None:
                        os.environ.pop("HF_HUB_OFFLINE", None)
                    else:
                        os.environ["HF_HUB_OFFLINE"] = _prev_offline
                    os.environ.pop("TRANSFORMERS_OFFLINE", None)
                    if _hub_constants is not None and _prev_const is not None:
                        _hub_constants.HF_HUB_OFFLINE = _prev_const
            encoder.eval(); model.eval()
            _TADA = (encoder, model)
        encoder, model = _TADA
        audio, sr = torchaudio.load(ref)
        prompt_obj = encoder(audio.to("cpu"), text=[prompt], sample_rate=sr)
        with torch.inference_mode():
            output = model.generate(prompt=prompt_obj, text=text)
        wav = output.audio[0].detach().cpu()
        import soundfile as sf
        path = _safe_output_path(out_name)
        sf.write(path, wav.numpy() if hasattr(wav, "numpy") else wav, 24000)
        info = sf.info(path)
        return {"ok": True, "output": os.path.basename(path),
                "seconds": round(float(info.duration), 3), "sample_rate": 24000,
                "bytes": os.path.getsize(path), "model": "tada",
                "engine": "HumeAI/tada-1b",
                "note": "CPU generation is very slow (lab: 928.5 s for one sentence); do not expect a fast reply on CPU."}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "model": "tada", "error": str(exc)}

def generate_customvoice(text, speaker="Ryan", language="English", out_name="customvoice.wav",
                         instruct=None, model_repo="Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
                         model_id="qwen-customvoice"):
    """Qwen CustomVoice preset speaker. instruct = style instruction
    (e.g. 'Speak slowly and warmly') passed to generate_custom_voice;
    None means the model's default style. model_repo/model_id let the
    main /api/generate reuse this for the 1.7B CustomVoice repo when
    (and only when) that cache is present — otherwise the caller must
    return needs_download, never a fake file."""
    if not (text or "").strip():
        return {"ok": False, "error": "text is required"}
    global _CUSTOMVOICE
    try:
        import torch
        if _CUSTOMVOICE is None or getattr(_CUSTOMVOICE, "_voxlab_repo", None) != model_repo:
            from qwen_tts import Qwen3TTSModel
            _CUSTOMVOICE = Qwen3TTSModel.from_pretrained(
                model_repo, device_map="cpu", dtype=torch.float32)
            _CUSTOMVOICE._voxlab_repo = model_repo
        kwargs = {"text": text, "language": language, "speaker": speaker}
        if instruct:
            kwargs["instruct"] = instruct
        wavs, sr = _CUSTOMVOICE.generate_custom_voice(**kwargs)
        res = _write_wav_array(wavs[0], sr, out_name)
        res.update({"model": model_id, "engine": model_repo,
                    "speaker": speaker, "language": language,
                    "instruct": instruct or ""})
        return res
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "model": model_id, "error": str(exc)}

@router.get("/api/parity/startup-status")
def startup_status():
    """Real startup checks only: parity router loaded, ffmpeg path,
    model endpoint list. Voice count comes from /api/voices (server.py);
    model downloads are NOT claimed here — see /api/parity/models."""
    try:
        models = parity_model_status()
    except Exception as exc:  # noqa: BLE001
        models = {"ok": False, "error": str(exc)}
    return {"ok": True, "parity_router": "loaded",
            "ffmpeg_available": _ffmpeg_available(),
            "ffmpeg_path": _ffmpeg_path() or "",
            "parity_model_endpoints": models,
            "note": "Models are lazy-loaded on first use; this endpoint does not "
                    "claim any model is downloaded. See /api/parity/models."}


@router.get("/api/parity/status")
def parity_status():
    return {
        "record_upload": "scaffold",
        "mic_upload": "POST /api/parity/mic-upload: max 30 s + 50 MB, WAV waveform peaks (sample_rate/channels/peak/rms/peaks[]) measured from the file; non-WAV duration via ffprobe, waveform None with a note",
        "system_capture": capture_info(),
        "windows_wasapi_capture": "capture_windows_audio() via sounddevice WASAPI loopback if installed on Windows, honest unavailable error otherwise; LIVE WINDOWS TEST PENDING, never claimed",
        "dictation_shortcut": "POST /api/parity/dictate-shortcut: global_shortcut.trigger_dictation() wired to transcribe() (same engine as /api/parity/dictate) + clipboard copy + optional paste; GET /api/parity/shortcut-info; LIVE WINDOWS HOTKEY/PASTE TEST PENDING",
        "dictation": "faster-whisper large-v3-turbo first, small on failure, via librosa decode (av path avoided), checked at request time, not at import; response names the model actually used",
        "mcp_speak": "voice mapping + synthesis: Kokoro ONNX for Kokoro presets, Parler via venv_parler, Edge via Deno server, clone_ voices via Chatterbox (backend/clone.py) with a reference clip in output/; a failed voice returns synthesized: false with the real error, no silent fallback",
        "personalities": "qwen3-llm if loaded (presets + verbatim flag + quality note), else template with llm_used=false (see /api/parity/rewrite response); 0.6B is minimal, not strong rewriting",
        "transcript_refinement": "POST /api/parity/refine-transcript with refine toggle; refine=true uses qwen3-llm to clean fillers/self-corrections/punctuation only, else original unchanged",
        "remote": "GET /api/parity/remote-config, POST /api/parity/remote/start, GET /api/parity/remote/health — local or remote base URL, no auth/encryption, no auto-discovery (see backend/remote.py)",
        "stories": "timeline (trim/start/volume/mix), sequence with crossfade, and plain concat — see PARITY.md test results",
        "effects": "ffmpeg filters: speed, volume, pitch, delay, chorus, compressor, low/high-pass, preview + real convolution reverb (scipy FFT else numpy FFT; convolution failure is an error, no echo approximation) — see PARITY.md test results",
        "parity_models": PARITY_MODELS,
        "parity_model_endpoints": parity_model_status(),
        "ffmpeg_available": _ffmpeg_available(),
            "ffmpeg_path": _ffmpeg_path() or "",
    }


@router.post("/api/parity/upload")
async def parity_upload(file: UploadFile = File(...), clone_text: str = Form(""),
                        profile_name: str = Form(""), engine: str = Form("chatterbox-turbo")):
    """File upload AND clone wiring (2026-10-27 fix).

    Previously this returned ok=True with the note that cloning was
    "not yet wired", so a user who uploaded a voice and pressed
    Create Voice got nothing. Now: the clip is validated (empty /
    silent clips are rejected with the real reason, not saved), and
    with clone_text set the same request creates a voice profile
    and generates with it — upload -> profile -> clone, no README
    detour. Without clone_text it returns the saved clip plus the
    exact clone call to make next.
    """
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
    valid = _validate_audio_file(dest)
    if not valid.get("ok"):
        os.remove(dest)
        return JSONResponse({"ok": False, "error": valid["error"], "bytes": size}, status_code=400)
    result = {"ok": True, "filename": os.path.basename(dest), "bytes": size,
              "seconds": valid.get("seconds"), "peak": valid.get("peak"),
              "clone": {"endpoint": "POST /api/parity/clone",
                        "example": {"text": "Hello, this is my cloned voice.",
                                    "ref_wav": os.path.basename(dest),
                                    "engine": "chatterbox-turbo"}}}
    if (clone_text or "").strip():
        clone = _do_clone(clone_text, os.path.basename(dest), engine,
                          profile_name or None, "upload_clone.wav")
        result["clone_result"] = clone
        if not clone.get("ok"):
            return JSONResponse(result, status_code=503)
    return result


@router.post("/api/parity/mic-upload")
async def parity_mic_upload(file: UploadFile = File(...), clone_text: str = Form(""),
                            profile_name: str = Form(""), engine: str = Form("chatterbox-turbo")):
    """Mic-recorder upload: max 30 s, 50 MB, waveform metadata for WAV.
    Empty/silent clips are rejected (see _validate_audio_file). With
    clone_text set, the same request creates a profile and clones —
    the Record page's Upload button now feeds Clone directly."""
    data = await file.read()
    result = save_mic_upload(data, file.filename or "recording.wav")
    if not result.get("ok"):
        return JSONResponse(result, status_code=400)
    result["clone"] = {"endpoint": "POST /api/parity/clone",
                       "example": {"text": "Hello, this is my cloned voice.",
                                   "ref_wav": result["filename"],
                                   "engine": "chatterbox-turbo"}}
    if (clone_text or "").strip():
        clone = _do_clone(clone_text, result["filename"], engine,
                          profile_name or None, "mic_clone.wav")
        result["clone_result"] = clone
        if not clone.get("ok"):
            return JSONResponse(result, status_code=503)
    return result


@router.get("/api/parity/capture-info")
def parity_capture_info():
    return capture_info()


@router.post("/api/parity/capture")
def parity_capture(payload: dict):
    """Real system-audio capture: Windows WASAPI loopback via
    sounddevice (capture_windows_audio) or Linux PulseAudio monitor.

    duration: seconds, clamped 1-60. On success returns the captured
    file; on failure returns the real error with HTTP 503 — never a
    fake capture. LIVE WINDOWS TEST PENDING for the WASAPI path.
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
    try:
        import datetime as _dt
        _cd = os.path.join(OUT, "captures"); os.makedirs(_cd, exist_ok=True)
        _fn = "capture_" + _dt.datetime.now().strftime("%Y%m%d_%H%M%S") + ".txt"
        with open(os.path.join(_cd, _fn), "w", encoding="utf-8") as _fh:
            _fh.write(result.get("transcript") or "")
        result["capture_file"] = _fn
    except Exception:
        pass
    return result


@router.post("/api/parity/dictate-shortcut")
def parity_dictate_shortcut(payload: dict):
    """Shortcut dictation: transcribe a saved clip, copy, optionally paste.

    Payload: {audio_file (in output/ or output/uploads/), paste: bool}.
    The Windows hotkey + paste run is NOT live-tested; the response
    always carries live_windows_test_pending=True.
    """
    result = dictate_shortcut(payload.get("audio_file", ""), paste=bool(payload.get("paste", False)))
    if not result.get("ok"):
        return JSONResponse(result, status_code=503)
    return result


@router.get("/api/parity/shortcut-info")
def parity_shortcut_info():
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from global_shortcut import default_hotkey, is_headless
        return {"hotkey": default_hotkey(), "platform": __import__("platform").system(),
                "headless": is_headless(), "paste_requires_gui": True,
                "endpoint": "POST /api/parity/dictate-shortcut",
                "live_windows_test_pending": True,
                "note": "Hotkey listener (Ctrl+Alt+V Windows/Linux, Cmd+Option+V macOS) is in backend/global_shortcut.py; a live Windows hotkey + paste test on a real Windows PC is still pending and is never claimed here."}
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc), "live_windows_test_pending": True}, status_code=503)




# --- Settings + Models catalog (2026-10-27) ---
# Settings are honest about what is live vs restart-only:
# - keep_alive: applies to a server started via remote/start (a
#   detached subprocess). The frozen exe IS its own server process,
#   so closing that exe's window still ends that process; keep_alive
#   cannot keep a frozen exe alive after its window closes.
# - network_access / host: stored in output/voxlab-settings.json and
#   read by remote/start; changing the RUNNING server's bind host
#   requires a restart, so POST returns restart_required=true.
# - language/theme: client-side only (localStorage + CSS), the server
#   stores nothing for them; theme actually switches CSS in the UI.
SETTINGS_FILE = os.path.join(OUT, "voxlab-settings.json")


def _read_settings():
    defaults = {"keep_alive": False, "network_access": False,
                "host": os.environ.get("VOXLAB_SERVER_HOST", "127.0.0.1"),
                "port": int(os.environ.get("VOXLAB_SERVER_PORT", "8000")),
                "auto_chunk_limit": 800, "chunk_crossfade_ms": 50,
                "normalize_audio": True, "autoplay_on_generate": True,
                "generations_folder": OUT,
                "push_to_talk_shortcut": "Ctrl+Alt+V",
                "toggle_shortcut": "Ctrl+Alt+V",
                "auto_paste": False,
                "transcription_model": "large-v3-turbo",
                "transcription_language": "auto",
                "refine_auto": True, "refinement_model": "Qwen3 0.6B",
                "smart_cleanup": True, "remove_self_corrections": True,
                "preserve_technical_terms": True,
                "mcp_default_voice": "af_heart", "mcp_bindings": [],
                "effect_presets": [], "cuda_backend_downloaded": False}
    try:
        if os.path.isfile(SETTINGS_FILE):
            with open(SETTINGS_FILE, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                _keys = ("keep_alive", "network_access", "host", "port",
                         "auto_chunk_limit", "chunk_crossfade_ms", "normalize_audio",
                         "autoplay_on_generate", "generations_folder",
                         "push_to_talk_shortcut", "toggle_shortcut", "auto_paste",
                         "transcription_model", "transcription_language",
                         "refine_auto", "refinement_model", "smart_cleanup",
                         "remove_self_corrections", "preserve_technical_terms",
                         "mcp_default_voice", "mcp_bindings", "effect_presets",
                         "cuda_backend_downloaded")
                defaults.update({k: data[k] for k in _keys if k in data})
    except Exception:
        pass
    return defaults


def _write_settings(data):
    try:
        os.makedirs(OUT, exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        return True
    except Exception:
        return False


@router.get("/api/parity/settings")
def parity_settings():
    cfg = _read_settings()
    cfg.update({"server_log": os.path.join(OUT, "voxlab-server.log"),
                "server_host_live": os.environ.get("VOXLAB_SERVER_HOST", "127.0.0.1"),
                "server_port_live": int(os.environ.get("VOXLAB_SERVER_PORT", "8000")),
                "restart_required_for_host_change": True,
                "keep_alive_note": "Applies to a server started via remote/start. Closing a frozen exe window still ends that exe's own server process.",
                "version": "see /api/parity/updates (GitHub releases, live check)"})
    return cfg


@router.post("/api/parity/settings")
def parity_settings_set(payload: dict):
    cfg = _read_settings()
    if "keep_alive" in payload:
        cfg["keep_alive"] = bool(payload["keep_alive"])
    if "network_access" in payload:
        cfg["network_access"] = bool(payload["network_access"])
        cfg["host"] = "0.0.0.0" if cfg["network_access"] else "127.0.0.1"
    if "host" in payload and payload["host"] in ("127.0.0.1", "0.0.0.0"):
        cfg["host"] = payload["host"]
        cfg["network_access"] = (payload["host"] == "0.0.0.0")
    for _k in ("auto_chunk_limit", "chunk_crossfade_ms", "normalize_audio",
               "autoplay_on_generate", "generations_folder",
               "push_to_talk_shortcut", "toggle_shortcut", "auto_paste",
               "transcription_model", "transcription_language",
               "refine_auto", "refinement_model", "smart_cleanup",
               "remove_self_corrections", "preserve_technical_terms",
               "mcp_default_voice", "mcp_bindings", "effect_presets",
               "cuda_backend_downloaded"):
        if _k in payload:
            cfg[_k] = payload[_k]
    try:
        cfg["auto_chunk_limit"] = max(100, min(2000, int(cfg["auto_chunk_limit"])))
        cfg["chunk_crossfade_ms"] = max(0, min(500, int(cfg["chunk_crossfade_ms"])))
    except Exception:
        pass
    saved = _write_settings(cfg)
    # Apply to this process env for remote/start callers in-process;
    # the running uvicorn bind host does NOT change without restart.
    os.environ["VOXLAB_SERVER_HOST"] = cfg["host"]
    return {"ok": saved, "settings": cfg, "restart_required": True,
            "note": "Restart the app for a host change to take effect. Keep-alive applies to remote/start servers, not to a frozen exe's own process."}


@router.get("/api/parity/updates")
def parity_updates():
    """Live GitHub releases check for ishtiaquehasib/VoxLab. No fake version."""
    import urllib.request
    try:
        req = urllib.request.Request(
            "https://api.github.com/repos/ishtiaquehasib/VoxLab/releases/latest",
            headers={"Accept": "application/vnd.github+json",
                     "User-Agent": "VoxLab"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
        return {"ok": True, "latest_tag": data.get("tag_name"),
                "latest_name": data.get("name"),
                "published_at": data.get("published_at"),
                "html_url": data.get("html_url"),
                "assets": [a.get("name") for a in data.get("assets", [])]}
    except Exception as exc:  # noqa: BLE001 - report the real reason
        return {"ok": False, "error": str(exc)}


# Model catalog: repos are only listed where they are known. TADA 3B's
# HF repo is NOT confirmed here, so its download is disabled rather
# than pointing at a guessed repo. Edge voices are a service, not a
# download. Parler is the public mirror used in lab tests.
MODEL_CATALOG = [
    {"category": "Voice Generation", "id": "qwen-tts-1.7b",
     "name": "Qwen TTS 1.7B", "repos": ["Qwen/Qwen3-TTS-12Hz-1.7B"]},
    {"category": "Voice Generation", "id": "qwen-tts-0.6b",
     "name": "Qwen TTS 0.6B", "repos": ["Qwen/Qwen3-TTS-12Hz-0.6B"]},
    {"category": "Voice Generation", "id": "qwen-customvoice-1.7b",
     "name": "Qwen CustomVoice 1.7B",
     "repos": ["Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"]},
    {"category": "Voice Generation", "id": "qwen-customvoice-0.6b",
     "name": "Qwen CustomVoice 0.6B",
     "repos": ["Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"]},
    {"category": "Voice Generation", "id": "luxtts",
     "name": "LuxTTS (Fast, CPU-friendly)", "repos": ["YatharthS/LuxTTS"],
     "note": "Source luxtts_src/ is not bundled; endpoint 503s on a fresh install until vendored."},
    {"category": "Voice Generation", "id": "chatterbox",
     "name": "Chatterbox TTS (Multilingual)", "repos": ["ResembleAI/chatterbox"]},
    {"category": "Voice Generation", "id": "chatterbox-turbo",
     "name": "Chatterbox Turbo (English, Tags)",
     "repos": ["ResembleAI/chatterbox-turbo"]},
    {"category": "Voice Generation", "id": "tada-1b",
     "name": "TADA 1B (English)",
     "repos": ["HumeAI/tada-1b", "HumeAI/tada-codec"],
     "note": "Source tada_src/ is not bundled; endpoint 503s on a fresh install until vendored."},
    {"category": "Voice Generation", "id": "tada-3b",
     "name": "TADA 3B Multilingual", "repos": [],
     "note": "HF repo not confirmed — download disabled, not guessed."},
    {"category": "Voice Generation", "id": "kokoro-82m",
     "name": "Kokoro 82M", "repos": ["hexgrad/Kokoro-82M"]},
    {"category": "Voice Generation", "id": "parler-bengali",
     "name": "Bengali Parler (extra)", "repos": ["RXD03/indic-parler-tts-pretrained"]},
    {"category": "Voice Generation", "id": "edge-bengali",
     "name": "Bengali Edge (extra)", "repos": [],
     "note": "Edge voices are a network service, not a download; availability is the edge-tts package + network."},
    {"category": "Transcription", "id": "whisper-base",
     "name": "Whisper Base", "repos": ["openai/whisper-base"]},
    {"category": "Transcription", "id": "whisper-small",
     "name": "Whisper Small", "repos": ["openai/whisper-small"]},
    {"category": "Transcription", "id": "whisper-medium",
     "name": "Whisper Medium", "repos": ["openai/whisper-medium"]},
    {"category": "Transcription", "id": "whisper-large",
     "name": "Whisper Large", "repos": ["openai/whisper-large"]},
    {"category": "Transcription", "id": "whisper-turbo",
     "name": "Whisper Turbo",
     "repos": ["mobiuslabsgmbh/faster-whisper-large-v3-turbo"]},
    {"category": "Language Models", "id": "qwen3-0.6b",
     "name": "Qwen3 0.6B", "repos": ["Qwen/Qwen3-0.6B"]},
    {"category": "Language Models", "id": "qwen3-1.7b",
     "name": "Qwen3 1.7B", "repos": ["Qwen/Qwen3-1.7B"]},
    {"category": "Language Models", "id": "qwen3-4b",
     "name": "Qwen3 4B", "repos": ["Qwen/Qwen3-4B"]},
]

_DOWNLOADS = {}


def _catalog_status():
    out = []
    for m in MODEL_CATALOG:
        dl = bool(m["repos"]) and all(_cache_present(r) for r in m["repos"])
        st = _DOWNLOADS.get(m["id"], {})
        out.append({"category": m["category"], "id": m["id"], "name": m["name"],
                    "repos": m["repos"], "downloaded": dl,
                    "needs_download": bool(m["repos"]) and not dl,
                    "downloadable": bool(m["repos"]),
                    "download_state": st.get("state", "idle"),
                    "download_error": st.get("error"),
                    "note": m.get("note", "")})
    return out


@router.get("/api/parity/model-catalog")
def parity_model_catalog():
    return {"storage_location": _hf_cache_dir(), "models": _catalog_status()}


def _download_worker(model_id, repos):
    try:
        from huggingface_hub import snapshot_download
        for repo in repos:
            snapshot_download(repo_id=repo)
        _DOWNLOADS[model_id] = {"state": "done", "error": None}
    except Exception as exc:  # noqa: BLE001 - real error, surfaced by status
        _DOWNLOADS[model_id] = {"state": "error", "error": str(exc)}


@router.post("/api/parity/download-model")
def parity_download_model(payload: dict):
    model_id = str(payload.get("id", ""))
    entry = next((m for m in MODEL_CATALOG if m["id"] == model_id), None)
    if entry is None:
        return JSONResponse({"ok": False, "error": f"unknown model: {model_id}"},
                            status_code=404)
    if not entry["repos"]:
        return JSONResponse({"ok": False, "error": entry.get("note", "not downloadable"),
                             "downloadable": False}, status_code=503)
    if all(_cache_present(r) for r in entry["repos"]):
        return {"ok": True, "already_downloaded": True, "id": model_id}
    if _DOWNLOADS.get(model_id, {}).get("state") == "downloading":
        return {"ok": True, "already_downloading": True, "id": model_id}
    import threading
    _DOWNLOADS[model_id] = {"state": "downloading", "error": None}
    threading.Thread(target=_download_worker, args=(model_id, entry["repos"]),
                     daemon=True).start()
    return {"ok": True, "downloading": True, "id": model_id,
            "note": "Download runs in the background; poll download status. Large models are several GB."}


@router.get("/api/parity/download-status/{model_id}")
def parity_download_status(model_id: str):
    entry = next((m for m in MODEL_CATALOG if m["id"] == model_id), None)
    if entry is None:
        return JSONResponse({"ok": False, "error": f"unknown model: {model_id}"},
                            status_code=404)
    return {"ok": True, "id": model_id,
            "downloaded": bool(entry["repos"]) and all(_cache_present(r) for r in entry["repos"]),
            "state": _DOWNLOADS.get(model_id, {}).get("state", "idle"),
            "error": _DOWNLOADS.get(model_id, {}).get("error")}


# --- On-demand Parler install (NO-FALLBACK RULE, 2026-10-27) ---
# The isolated Parler venv (~1.7 GB installed + ~3.6 GB model) is NOT
# bundled in the installer. This endpoint creates output/parler-env
# with a host Python and pip-installs parler-tts 0.2.2 (which pins
# transformers 4.46.1) + CPU torch + soundfile, in a background
# thread; poll GET /api/parity/install-parler-status. The model itself
# is downloaded separately via POST /api/parity/download-model
# id=parler-bengali (RXD03/indic-parler-tts-pretrained).
# FROZEN LIMIT, honest: a frozen exe has no Python interpreter of its
# own, so if no `python`/`python3` is on PATH the install cannot start
# and the endpoint returns needs_python with the exact step (install
# Python 3.12 from python.org, tick Add to PATH, restart VoxLab, press
# Install Parler again). The Windows embeddable-Python download path
# is NOT coded — it would be untested on this Linux VM and must not be
# claimed until a Windows run proves it.
_PARLER_INSTALL = {"state": "idle", "error": None, "log": []}


def _parler_install_python():
    """Host interpreter for venv creation, or None (frozen, no PATH python)."""
    import sys as _sys
    if not getattr(_sys, "frozen", False):
        return _sys.executable
    for name in ("python", "python3"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _parler_install_worker():
    _PARLER_INSTALL["state"] = "installing"
    _PARLER_INSTALL["error"] = None
    try:
        import sys as _sys
        _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from bengali import _parler_install_dir, _parler_model_cached
        install_dir = _parler_install_dir()
        host_python = _parler_install_python()
        if not host_python:
            raise RuntimeError(
                "No Python interpreter found: a frozen VoxLab has no "
                "Python of its own. Install Python 3.12 from python.org "
                "(tick 'Add python.exe to PATH'), restart VoxLab, then "
                "press Install Parler again.")
        _PARLER_INSTALL["log"].append(f"creating venv at {install_dir}")
        proc = subprocess.run([host_python, "-m", "venv", install_dir],
                              capture_output=True, text=True, timeout=600)
        if proc.returncode != 0:
            raise RuntimeError(f"venv creation failed: {(proc.stderr or proc.stdout)[-500:]}")
        if os.name == "nt":
            venv_python = os.path.join(install_dir, "Scripts", "python.exe")
        else:
            venv_python = os.path.join(install_dir, "bin", "python")
        _PARLER_INSTALL["log"].append("installing CPU torch")
        proc = subprocess.run(
            [venv_python, "-m", "pip", "install", "--no-cache-dir",
             "torch", "--index-url", "https://download.pytorch.org/whl/cpu"],
            capture_output=True, text=True, timeout=1800)
        if proc.returncode != 0:
            raise RuntimeError(f"torch install failed: {(proc.stderr or proc.stdout)[-500:]}")
        _PARLER_INSTALL["log"].append("installing parler-tts 0.2.2 + soundfile")
        proc = subprocess.run(
            [venv_python, "-m", "pip", "install", "--no-cache-dir",
             "parler-tts==0.2.2", "soundfile"],
            capture_output=True, text=True, timeout=1800)
        if proc.returncode != 0:
            raise RuntimeError(f"parler-tts install failed: {(proc.stderr or proc.stdout)[-500:]}")
        _PARLER_INSTALL["log"].append("install complete")
        _PARLER_INSTALL["state"] = "done"
    except Exception as exc:  # noqa: BLE001 - surfaced by status endpoint
        _PARLER_INSTALL["state"] = "error"
        _PARLER_INSTALL["error"] = str(exc)


@router.get("/api/parity/install-parler-status")
def parity_install_parler_status():
    try:
        import sys as _sys
        _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from bengali import parler_env_status
        env = parler_env_status()
    except Exception as exc:  # noqa: BLE001
        env = {"ready": False, "error": str(exc)}
    env = dict(env)
    env.update({"install_state": _PARLER_INSTALL["state"],
                "install_error": _PARLER_INSTALL["error"],
                "install_log_tail": _PARLER_INSTALL["log"][-5:]})
    return {"ok": True, "parler": env}


@router.post("/api/parity/install-parler")
def parity_install_parler(payload: dict = None):
    try:
        import sys as _sys
        _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from bengali import parler_env_status
        env = parler_env_status()
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    if env.get("venv_installed"):
        return {"ok": True, "already_installed": True,
                "venv_python": env.get("venv_python"),
                "model_cached": env.get("model_cached"),
                "note": "Parler venv already installed. If the model is not "
                        "cached, download 'Bengali Parler (extra)' on the "
                        "Models page, then generate with a Parler voice."}
    if _PARLER_INSTALL["state"] == "installing":
        return {"ok": True, "already_installing": True}
    if _parler_install_python() is None:
        return JSONResponse(
            {"ok": False, "needs_python": True,
             "error": "No Python interpreter found: a frozen VoxLab has no "
                      "Python of its own. Install Python 3.12 from "
                      "python.org (tick 'Add python.exe to PATH'), restart "
                      "VoxLab, then press Install Parler again."},
            status_code=503)
    import threading
    _PARLER_INSTALL["state"] = "installing"
    _PARLER_INSTALL["error"] = None
    _PARLER_INSTALL["log"] = []
    threading.Thread(target=_parler_install_worker, daemon=True).start()
    return {"ok": True, "installing": True,
            "venv_dir": env.get("venv_dir"),
            "note": "Parler venv install runs in the background (CPU torch "
                    "+ parler-tts 0.2.2, several hundred MB); poll "
                    "GET /api/parity/install-parler-status. Then download "
                    "the Parler model on the Models page if not cached."}


@router.get("/api/parity/models")
def parity_models():
    return {"models": parity_model_status()}


def _model_endpoint_result(result):
    if not result.get("ok"):
        return JSONResponse(result, status_code=503)
    return result


@router.get("/api/parity/profiles")
def parity_profiles():
    """Saved voice profiles (Create Voice): name -> reference clip."""
    return {"ok": True, "profiles": _list_profiles()}


@router.post("/api/parity/profiles")
def parity_create_profile(payload: dict):
    """Create a voice profile from a clip already in output/uploads/."""
    ref, err = _resolve_ref(payload.get("ref_wav", ""))
    if err:
        return JSONResponse({"ok": False, "error": err}, status_code=400)
    valid = _validate_audio_file(ref)
    if not valid.get("ok"):
        return JSONResponse({"ok": False, "error": valid["error"]}, status_code=400)
    profile = _save_profile(payload.get("name", "voice"), ref,
                            payload.get("engine", "chatterbox-turbo"))
    profile["ref_seconds"] = valid.get("seconds")
    return {"ok": True, "profile": profile}


@router.post("/api/parity/clone")
def parity_clone(payload: dict):
    """Clone a voice: the missing /api/clone path.

    Body: {text, ref_wav (basename in output/ or output/uploads/) or
    profile (profile name), engine "chatterbox-turbo" (default) or
    "chatterbox", profile_name (optional, saves a profile),
    out_name}. Validates the reference first (empty/silent rejected),
    then generates. Returns the clone file + seconds/bytes.
    """
    ref_wav = payload.get("ref_wav", "")
    if not ref_wav and payload.get("profile"):
        for prof in _list_profiles():
            if prof.get("name") == payload["profile"]:
                ref_wav = prof["ref_wav"]
                break
        if not ref_wav:
            return JSONResponse({"ok": False, "error": f"profile not found: {payload['profile']}"}, status_code=404)
    result = _do_clone(payload.get("text", ""), ref_wav,
                       payload.get("engine", "chatterbox-turbo"),
                       payload.get("profile_name"),
                       payload.get("out_name", "clone.wav"))
    if not result.get("ok"):
        return JSONResponse(result, status_code=503)
    return result


@router.post("/api/parity/clone-from-upload")
async def parity_clone_from_upload(file: UploadFile = File(...), text: str = Form(""),
                                   profile_name: str = Form(""), engine: str = Form("chatterbox-turbo")):
    """One-call upload -> profile -> clone (Clone view file picker).

    Previously the Clone view's file picker was ignored entirely:
    modelGenerate() sent only a ref_wav name string, so uploading
    your own voice and pressing Generate cloned the Kokoro sample
    instead. This endpoint takes the file itself, validates it
    (empty/silent rejected), saves a profile, and clones from it.
    """
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
    valid = _validate_audio_file(dest)
    if not valid.get("ok"):
        os.remove(dest)
        return JSONResponse({"ok": False, "error": valid["error"], "bytes": size}, status_code=400)
    result = _do_clone(text, os.path.basename(dest), engine,
                       profile_name or None, "clone_from_upload.wav")
    result["uploaded"] = {"filename": os.path.basename(dest), "bytes": size,
                          "seconds": valid.get("seconds"), "peak": valid.get("peak")}
    if not result.get("ok"):
        return JSONResponse(result, status_code=503)
    return result


@router.post("/api/parity/generate-chatterbox-turbo")
def parity_generate_turbo(payload: dict):
    return _model_endpoint_result(generate_turbo(
        payload.get("text", ""), payload.get("ref_wav", "kokoro_af_heart.wav"),
        payload.get("out_name", "turbo_clone.wav")))


@router.post("/api/parity/generate-luxtts")
def parity_generate_luxtts(payload: dict):
    return _model_endpoint_result(generate_luxtts(
        payload.get("text", ""), payload.get("ref_wav", "kokoro_af_heart.wav"),
        payload.get("out_name", "luxtts_clone.wav")))


@router.post("/api/parity/generate-tada")
def parity_generate_tada(payload: dict):
    return _model_endpoint_result(generate_tada(
        payload.get("text", ""), payload.get("ref_wav"),
        payload.get("prompt_text"), payload.get("out_name", "tada_clone.wav")))


@router.post("/api/parity/generate-qwen-customvoice")
def parity_generate_customvoice(payload: dict):
    return _model_endpoint_result(generate_customvoice(
        payload.get("text", ""), payload.get("speaker", "Ryan"),
        payload.get("language", "English"),
        payload.get("out_name", "customvoice.wav"),
        instruct=payload.get("instruct") or payload.get("style") or None))


@router.post("/api/parity/dictate-whisper-turbo")
async def parity_dictate_whisper_turbo(file: UploadFile = File(...)):
    dest = os.path.join(UPLOAD_DIR, os.path.basename(file.filename or "dictate.wav"))
    with open(dest, "wb") as out:
        out.write(await file.read())
    result = transcribe(dest, model_size="large-v3-turbo")
    if not result.get("available"):
        return JSONResponse(result, status_code=503)
    result["endpoint"] = "POST /api/parity/dictate-whisper-turbo"
    return result


@router.post("/api/parity/generate-whisper-turbo")
async def parity_generate_whisper_turbo(file: UploadFile = File(...)):
    """Alias of dictate-whisper-turbo, kept so the model list has one
    generate-style route per model; dictation is the honest name."""
    return await parity_dictate_whisper_turbo(file)


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
    _bind_voice = None
    try:
        for _b in _read_settings().get("mcp_bindings", []) or []:
            if str(_b.get("client_id", "")).lower() == agent:
                _bind_voice = _b.get("voice"); break
    except Exception:
        pass
    voice = payload.get("voice") or _bind_voice or AGENT_VOICES.get(agent, AGENT_VOICES["default"])
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
    result = rewrite_text(str(payload.get("text", "")), str(payload.get("persona", "neutral")))
    if result.get("method") == "unavailable":
        return JSONResponse(result, status_code=503)
    return result


@router.post("/api/parity/compose")
def parity_compose(payload: dict):
    result = compose_text(str(payload.get("persona", "neutral")), str(payload.get("topic", "")))
    if result.get("method") == "unavailable":
        return JSONResponse(result, status_code=503)
    return result


@router.get("/api/parity/personas")
def parity_personas():
    return {"personas": PERSONA_PRESETS,
            "note": "Preset names add a trait to the LLM prompt; any free-form persona name also works (no preset trait). 0.6B quality note applies."}


@router.post("/api/parity/refine-transcript")
def parity_refine_transcript(payload: dict):
    _cfg = _read_settings()
    _refine = bool(payload.get("refine", _cfg.get("refine_auto", True)))
    _res = refine_transcript(str(payload.get("transcript", "")), refine=_refine)
    # Stored toggles, applied as deterministic post-processing where coded:
    # smart_cleanup removes standalone um/uh fillers; remove_self_corrections
    # drops the clause before a retraction marker in the same sentence;
    # preserve_technical_terms keeps the text unchanged for technical terms
    # (no term rewriting is coded, so this toggle is a no-op by design).
    _txt = _res.get("refined_text", "")
    _applied = []
    if _refine and _cfg.get("smart_cleanup", True):
        import re as _re
        _txt2 = _re.sub(r"\b(um|uh)\b[,\s]*", " ", _txt, flags=_re.I)
        _txt = " ".join(_txt2.split()); _applied.append("smart_cleanup")
    if _refine and _cfg.get("remove_self_corrections", True):
        import re as _re
        _txt = _re.sub(r"[^.!?]*\b(actually,? no|wait,? I meant)\b\s*", "", _txt, flags=_re.I)
        _txt = " ".join(_txt.split()); _applied.append("remove_self_corrections")
    if _cfg.get("preserve_technical_terms", True):
        _applied.append("preserve_technical_terms(no-op: no term rewriting coded)")
    _res["refined_text"] = _txt
    _res["settings_applied"] = _applied
    _res["settings_note"] = "Toggles come from voxlab-settings.json (Captures tab). LLM cleaning is Qwen3 0.6B; smart_cleanup/remove_self_corrections above are post-processing only, not a second LLM pass."
    return _res


@router.get("/api/parity/remote-config")
def parity_remote_config():
    from remote import get_remote_config, is_local_server_running
    cfg = get_remote_config()
    cfg["local_server_running"] = is_local_server_running()
    return cfg


@router.post("/api/parity/remote/start")
def parity_remote_start(payload: dict):
    from remote import start_local_server
    result = start_local_server(payload.get("host"), payload.get("port"))
    if not result.get("ok"):
        return JSONResponse(result, status_code=503)
    return result


@router.get("/api/parity/remote/health")
def parity_remote_health(base_url: str = ""):
    from remote import check_server, get_remote_config
    cfg = get_remote_config()
    target = base_url or cfg.get("base_url") or ""
    result = check_server(target)
    result["mode"] = cfg["mode"]
    return result


@router.post("/api/parity/story")
def parity_story(payload: dict):
    # New: tracks [{file, start, trim_start, trim_end, volume}] with
    # optional crossfade_ms. Legacy: segments [filenames] -> concat
    # routed through the timeline builder (common 24 kHz resample +
    # crossfade honoured), NOT the old -c copy concat demuxer.
    _xf = payload.get("crossfade_ms")
    if _xf is None:
        _xf = _read_settings().get("chunk_crossfade_ms", 50)
    tracks = payload.get("tracks")
    if isinstance(tracks, list) and tracks:
        result = build_story_timeline(
            tracks, payload.get("out_name", "story_timeline.wav"),
            crossfade_ms=_xf)
        if not result.get("ok"):
            return JSONResponse(result, status_code=400)
        return result
    segments = payload.get("segments") or []
    if not isinstance(segments, list) or not segments:
        return JSONResponse({"ok": False, "error": "segments (legacy) or tracks must be a non-empty list"}, status_code=400)
    result = concat_story(segments, payload.get("out_name", "story.wav"),
                          crossfade_ms=_xf)
    if not result.get("ok"):
        return JSONResponse(result, status_code=400)
    return result


@router.post("/api/parity/chunk-text")
def parity_chunk_text(payload: dict):
    try:
        _mc = payload.get("max_chars")
        if _mc is None:
            _mc = _read_settings().get("auto_chunk_limit", 800)
        result = auto_chunk_text(str(payload.get("text", "")), max_chars=_mc)
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    return result


# --- Qwen VoiceDesign: SKELETON ONLY, 2026-10-27, NOT tested ---
# Licence is NOT verified on the HF card itself, and qwen-tts wants
# torch>=2.9.1 while VoxLab ships torch==2.6.0, so this function must
# never silently import, download, or fake audio. It returns
# needs_download=true unless BOTH the qwen_tts package AND a local
# model directory are present; even then the load/generate path is
# unproven on CPU (upstream examples use cuda + flash_attention_2).
VOICEDESIGN_MODEL_ID = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
VOICEDESIGN_DIR = os.environ.get(
    "VOXLAB_QWEN_VOICEDESIGN_DIR",
    os.path.join(os.path.expanduser("~"), ".cache", "huggingface",
                  "hub", "models--Qwen--Qwen3-TTS-12Hz-1.7B-VoiceDesign"))


def voice_design_available():
    try:
        import importlib.util
        has_pkg = importlib.util.find_spec("qwen_tts") is not None
    except Exception:
        has_pkg = False
    return {"package": has_pkg, "model_dir": os.path.isdir(VOICEDESIGN_DIR)}


def generate_voice_design(text, language="English", instruct="", out_name="voicedesign.wav"):
    """Lazy-load VoiceDesign only if package + model are present.

    Returns needs_download=true (no audio, no fake) in every other case.
    The generate call itself is UNTESTED: method name and CPU load
    parameters come from the PARITY.md investigation, not a passing run.
    """
    avail = voice_design_available()
    if not (avail["package"] and avail["model_dir"]):
        return {"ok": False, "needs_download": True, "synthesized": False,
                "model": VOICEDESIGN_MODEL_ID,
                "licence_verified_on_hf_card": False,
                "licence_note": "HF card text fetch (106 lines) showed no licence field; secondary sources quote Apache 2.0 — NOT counted as HF-field verification.",
                "torch_conflict": "qwen-tts needs torch>=2.9.1, VoxLab ships torch==2.6.0 (chatterbox pin); needs an isolated env, not a shared install.",
                "error": "VoiceDesign model/package not present; download not attempted by this skeleton.",
                "package_present": avail["package"], "model_dir_present": avail["model_dir"]}
    try:
        import torch
        from qwen_tts import Qwen3TTSModel
        model = Qwen3TTSModel.from_pretrained(
            VOICEDESIGN_MODEL_ID, device_map="cpu", dtype=torch.bfloat16)
        if not hasattr(model, "generate_voice_design"):
            return {"ok": False, "synthesized": False,
                    "error": "loaded model has no generate_voice_design method; API differs from investigation"}
        wavs, sr = model.generate_voice_design(
            text=text, language=language, instruct=instruct)
        import soundfile as sf
        out_path = _safe_output_path(out_name)
        sf.write(out_path, wavs[0], sr)
        return {"ok": True, "synthesized": True, "output": os.path.basename(out_path),
                "sample_rate": int(sr), "model": VOICEDESIGN_MODEL_ID,
                "designed_voice_note": "Same description does NOT guarantee the identical voice every time; save the description for repeatability, do not promise identical voices.",
                "licence_verified_on_hf_card": False}
    except Exception as exc:  # noqa: BLE001 - return the real error, never fake audio
        return {"ok": False, "synthesized": False, "model": VOICEDESIGN_MODEL_ID,
                "error": str(exc)}


@router.post("/api/parity/voice-design")
def parity_voice_design(payload: dict):
    text = str(payload.get("text", "")).strip()
    if not text:
        return JSONResponse({"ok": False, "error": "text is required"}, status_code=400)
    result = generate_voice_design(
        text, language=str(payload.get("language", "English")),
        instruct=str(payload.get("instruct", "")),
        out_name=str(payload.get("out_name", "voicedesign.wav")))
    if not result.get("ok"):
        return JSONResponse(result, status_code=503 if result.get("needs_download") else 400)
    result["audio_url"] = f"/api/parity/audio/{result['output']}"
    return result


@router.post("/api/parity/effect")
def parity_effect(payload: dict):
    result = apply_effect(
        payload.get("input", ""),
        speed=float(payload.get("speed", 1.0)),
        volume=float(payload.get("volume", 1.0)),
        echo=bool(payload.get("echo", False)),
        out_name=payload.get("out_name", "effect.wav"),
        pitch_semitones=float(payload.get("pitch_semitones", 0) or 0),
        reverb=bool(payload.get("reverb", False)),
        reverb_decay_s=float(payload.get("reverb_decay_s", 1.2) or 1.2),
        reverb_mix=float(payload.get("reverb_mix", 0.3) or 0.3),
        delay_ms=int(payload.get("delay_ms", 0) or 0),
        chorus=bool(payload.get("chorus", False)),
        compressor=bool(payload.get("compressor", False)),
        lowpass=payload.get("lowpass"),
        highpass=payload.get("highpass"),
        preview_seconds=payload.get("preview_seconds"),
    )
    if not result.get("ok"):
        return JSONResponse(result, status_code=400)
    return result


# --- Settings full detail (2026-10-27): Generation / Captures / MCP / GPU /
# --- Logs / Changelog + Stories / Captures / Voices / Effect presets ---
# All VoxLab's own wording; no competitor text or design is copied.
EFFECT_PRESETS = {
    "robotic": {"name": "Robotic", "desc": "Metallic voice, chorus (flanger-style) only",
                "params": {"chorus": True, "speed": 1.0, "volume": 1.0}},
    "radio": {"name": "Radio", "desc": "Thin AM-radio voice, band-pass + compressor",
              "params": {"highpass": 300, "lowpass": 3400, "compressor": True, "speed": 1.0, "volume": 1.0}},
    "echo-chamber": {"name": "Echo Chamber", "desc": "Spacious convolution reverb + trailing delay",
                    "params": {"reverb": True, "reverb_decay_s": 1.8, "reverb_mix": 0.5, "delay_ms": 250, "speed": 1.0, "volume": 1.0}},
    "deep-voice": {"name": "Deep Voice", "desc": "Lower pitch with added warmth",
                 "params": {"pitch_semitones": -6, "lowpass": 800, "compressor": True, "speed": 1.0, "volume": 1.0}},
}


@router.get("/api/parity/logs")
def parity_logs(lines: int = 200):
    """Real server log lines from output/voxlab-server.log, else honest note."""
    path = os.path.join(OUT, "voxlab-server.log")
    if not os.path.isfile(path):
        return {"ok": False, "present": False, "lines": [],
                "note": "No voxlab-server.log yet — start the server (server.py writes it on startup) and check again."}
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            all_lines = fh.readlines()
        return {"ok": True, "present": True, "total_lines": len(all_lines),
                "lines": [l.rstrip("\n") for l in all_lines[-max(1, min(1000, int(lines))):]]}
    except Exception as exc:
        return {"ok": False, "present": True, "error": str(exc), "lines": []}


@router.get("/api/parity/releases")
def parity_releases():
    """Live GitHub releases list for ishtiaquehasib/VoxLab (Changelog tab)."""
    import urllib.request
    try:
        req = urllib.request.Request(
            "https://api.github.com/repos/ishtiaquehasib/VoxLab/releases?per_page=20",
            headers={"Accept": "application/vnd.github+json", "User-Agent": "VoxLab"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
        return {"ok": True, "releases": [{"tag": r.get("tag_name"), "name": r.get("name"),
                                          "published_at": r.get("published_at"),
                                          "html_url": r.get("html_url"),
                                          "body": (r.get("body") or "")[:500]} for r in data]}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "releases": []}


@router.get("/api/parity/mcp-snippets")
def parity_mcp_snippets():
    import sys
    """MCP install snippets for this machine's VoxLab server (no copy of
    any other app's config text; server URL and client-id header are VoxLab's own)."""
    import platform
    host = os.environ.get("VOXLAB_SERVER_HOST", "127.0.0.1")
    port = os.environ.get("VOXLAB_SERVER_PORT", "8000")
    url = f"http://{host}:{port}"
    exe = sys.executable if getattr(sys, "frozen", False) else os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py")
    cfg = _read_settings()
    return {"ok": True, "server_url": url, "mcp_url": url + "/api/mcp/speak",
            "default_voice": cfg.get("mcp_default_voice", "af_heart"),
            "http_snippet": {"mcpServers": {"voxlab": {"url": url + "/mcp",
                             "headers": {"X-VoxLab-Client-Id": "claude-code"}}}},
            "stdio_snippet": {"mcpServers": {"voxlab": {"command": exe,
                              "env": {"VOXLAB_CLIENT_ID": "claude-code"}}}},
            "note": "HTTP snippet is the recommended path; stdio falls back to the VoxLab exe / server.py on this machine. MCP speak honours per-agent bindings from settings (see /api/parity/mcp-bindings). Per-agent pill/ACP/A2A/WebSocket are not built."}


@router.get("/api/parity/mcp-bindings")
def parity_mcp_bindings():
    return {"bindings": _read_settings().get("mcp_bindings", []),
            "default_voice": _read_settings().get("mcp_default_voice", "af_heart")}


@router.post("/api/parity/mcp-bindings")
def parity_mcp_bindings_add(payload: dict):
    cfg = _read_settings()
    binds = list(cfg.get("mcp_bindings", []) or [])
    client_id = str(payload.get("client_id", "")).strip()
    voice = str(payload.get("voice", "")).strip()
    if not client_id or not voice:
        return JSONResponse({"ok": False, "error": "client_id and voice are required"}, status_code=400)
    binds = [b for b in binds if str(b.get("client_id", "")).lower() != client_id.lower()]
    binds.append({"client_id": client_id, "label": str(payload.get("label", "")), "voice": voice})
    cfg["mcp_bindings"] = binds
    _write_settings(cfg)
    return {"ok": True, "bindings": binds,
            "note": "POST /api/mcp/speak with agent == client_id now uses this voice (unless payload.voice overrides it)."}


@router.get("/api/parity/stories")
def parity_stories(q: str = ""):
    """Stories list from output/: story_* and story_timeline files only."""
    rows = []
    try:
        for name in sorted(os.listdir(OUT)):
            if not (name.startswith("story") and name.lower().endswith((".wav", ".mp3"))):
                continue
            if q and q.lower() not in name.lower():
                continue
            fp = os.path.join(OUT, name)
            rows.append({"name": name, "bytes": os.path.getsize(fp),
                         "mtime": os.path.getmtime(fp),
                         "audio_url": f"/api/parity/audio/{name}"})
    except Exception as exc:
        return {"ok": False, "error": str(exc), "stories": []}
    return {"ok": True, "stories": rows, "count": len(rows)}


@router.get("/api/parity/captures")
def parity_captures(q: str = ""):
    """Captures list: saved transcripts in output/captures/*.txt (dictate
    saves one per successful transcription). Search matches filename or
    transcript text. No captures yet = empty list, not invented rows."""
    rows = []
    cdir = os.path.join(OUT, "captures")
    try:
        if os.path.isdir(cdir):
            for name in sorted(os.listdir(cdir)):
                if not name.endswith(".txt"):
                    continue
                with open(os.path.join(cdir, name), encoding="utf-8", errors="replace") as fh:
                    txt = fh.read()
                if q and q.lower() not in name.lower() and q.lower() not in txt.lower():
                    continue
                rows.append({"file": name, "transcript": txt[:500], "chars": len(txt)})
    except Exception as exc:
        return {"ok": False, "error": str(exc), "captures": []}
    return {"ok": True, "captures": rows, "count": len(rows),
            "note": "Only successful dictate transcriptions saved since this change are listed; older dictations were not persisted."}


@router.get("/api/parity/effect-presets")
def parity_effect_presets():
    cfg = _read_settings()
    out = [{"id": k, "name": v["name"], "desc": v["desc"], "params": v["params"], "builtin": True}
           for k, v in EFFECT_PRESETS.items()]
    for c in cfg.get("effect_presets", []) or []:
        out.append({"id": c.get("id"), "name": c.get("name"), "desc": c.get("desc", "Custom preset"),
                    "params": c.get("params", {}), "builtin": False})
    return {"ok": True, "presets": out}


@router.post("/api/parity/effect-presets")
def parity_effect_presets_add(payload: dict):
    cfg = _read_settings()
    customs = list(cfg.get("effect_presets", []) or [])
    pid = str(payload.get("id", "")).strip() or ("custom-" + str(len(customs) + 1))
    params = payload.get("params", {}) if isinstance(payload.get("params", {}), dict) else {}
    customs = [c for c in customs if c.get("id") != pid]
    customs.append({"id": pid, "name": str(payload.get("name", pid)), "params": params})
    cfg["effect_presets"] = customs
    _write_settings(cfg)
    return {"ok": True, "presets": customs}


@router.post("/api/parity/effect-preset")
def parity_effect_preset(payload: dict):
    pid = str(payload.get("preset", ""))
    params = dict(EFFECT_PRESETS.get(pid, {}).get("params", {}))
    if not params:
        cfg = _read_settings()
        for c in cfg.get("effect_presets", []) or []:
            if c.get("id") == pid:
                params = dict(c.get("params", {})); break
    if not params:
        return JSONResponse({"ok": False, "error": f"unknown preset: {pid}"}, status_code=404)
    result = apply_effect(payload.get("input", ""), out_name=payload.get("out_name", "effect_preset.wav"), **params)
    if not result.get("ok"):
        return JSONResponse(result, status_code=400)
    result["preset"] = pid
    return result


@router.get("/api/parity/gpu")
def parity_gpu():
    """Detected device + CUDA backend download note (not downloaded by default)."""
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from device import get_device
        dev = get_device()
    except Exception as exc:
        dev = f"unknown ({exc})"
    return {"ok": True, "device": dev,
            "cuda_backend": {"downloaded": _read_settings().get("cuda_backend_downloaded", False),
                             "size_note": "~2.4 GB torch CUDA wheel, NVIDIA GPU only",
                             "note": "Not downloaded by default. VoxLab ships CPU torch; a CUDA backend is a separate first-use download and is not built as an auto-installer here."},
            "backends": "CUDA -> MPS -> DirectML -> CPU, OOM falls back to CPU"}
