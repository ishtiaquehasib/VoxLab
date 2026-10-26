"""VoxLab v1 backend: local FastAPI server, no cloud, no account.

Engines (audit 2026-10-26, see ../AUDIT.md):
- Kokoro-82M preset voices (fast CPU, English etc.)
- Chatterbox cloning in clone.py — primary cloning engine, audit winner
  over Qwen3-TTS. Qwen3-TTS is dropped from v1.

Run: python backend/server.py  ->  http://127.0.0.1:8000
"""
import os, io, sys, shutil, subprocess
def _ffmpeg_exe():
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.exists(exe):
            return exe
    except Exception:
        pass
    return shutil.which("ffmpeg")

def _to_mp3(wav_path, mp3_path):
    exe = _ffmpeg_exe()
    if not exe:
        return False
    try:
        rc = subprocess.run([exe, "-y", "-v", "error", "-i", wav_path,
                             "-c:a", "libmp3lame", "-q:a", "4", mp3_path]).returncode
    except Exception:
        return False
    return rc == 0 and os.path.exists(mp3_path)
from fastapi import FastAPI, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Frozen (PyInstaller onedir) layout — user screenshot proof:
# extracted folder = VoxLab.exe + _internal/ only, NO app/ beside exe.
# --add-data files land in _internal/ (sys._MEIPASS), NOT the exe dir,
# so the previous fix (BASE = exe dir) made StaticFiles look for
# dist/VoxLab/app, which does not exist, and the exe failed at startup.
# Correct split when frozen: read-only bundled data from _MEIPASS,
# writable output beside the exe. Unfrozen logic unchanged.
if getattr(sys, "frozen", False):
    DATA_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    BASE = DATA_DIR
    OUT = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "output")
else:
    BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATA_DIR = BASE
    OUT = os.path.join(BASE, "output")
os.makedirs(OUT, exist_ok=True)

app = FastAPI(title="Voice Studio")

# Kokoro preset voices shipped with Kokoro-82M (English + others).
# lang codes: a=American, b=British, e=Spanish, f=French, h=Hindi,
# i=Italian, j=Japanese, p=Portuguese, z=Chinese.
VOICES = [
    {"id": "af_heart", "name": "Heart (female, American)", "lang": "a"},
    {"id": "af_bella", "name": "Bella (female, American)", "lang": "a"},
    {"id": "af_sarah", "name": "Sarah (female, American)", "lang": "a"},
    {"id": "am_adam", "name": "Adam (male, American)", "lang": "a"},
    {"id": "am_michael", "name": "Michael (male, American)", "lang": "a"},
    {"id": "bf_emma", "name": "Emma (female, British)", "lang": "b"},
    {"id": "bf_isabella", "name": "Isabella (female, British)", "lang": "b"},
    {"id": "bm_george", "name": "George (male, British)", "lang": "b"},
    {"id": "bm_lewis", "name": "Lewis (male, British)", "lang": "b"},
    {"id": "hf_alpha", "name": "Alpha (female, Hindi)", "lang": "h"},
    {"id": "hm_omega", "name": "Omega (male, Hindi)", "lang": "h"},
    # Bengali, ElevenLabs-style filter: Parler speakers are real distinct
    # speakers; Edge entries are presets over the 4 Edge base voices.
    # ElevenLabs' own Bengali voices are NOT copied here.
    {"id": "parler_arjun", "name": "Arjun (male, Bengali, Parler)", "lang": "bn", "engine": "parler"},
    {"id": "parler_aditi", "name": "Aditi (female, Bengali, Parler)", "lang": "bn", "engine": "parler"},
    {"id": "parler_tapan", "name": "Tapan (male, Bengali, Parler)", "lang": "bn", "engine": "parler"},
    {"id": "parler_rashmi", "name": "Rashmi (female, Bengali, Parler)", "lang": "bn", "engine": "parler"},
    {"id": "parler_arnav", "name": "Arnav (male, Bengali, Parler)", "lang": "bn", "engine": "parler"},
    {"id": "parler_riya", "name": "Riya (female, Bengali, Parler)", "lang": "bn", "engine": "parler"},
    {"id": "edge_nabanita", "name": "Nabanita (female, Bengali, Edge)", "lang": "bn", "engine": "edge"},
    {"id": "edge_pradeep", "name": "Pradeep (male, Bengali, Edge)", "lang": "bn", "engine": "edge"},
]

_pipe = None

def get_pipe():
    global _pipe
    if _pipe is None:
        from kokoro import KPipeline
        _pipe = {}
    return _pipe

@app.get("/api/voices")
def voices():
    return {"voices": VOICES}

@app.post("/api/generate")
def generate(text: str = Form(...), voice: str = Form("af_heart"), lang: str = Form("a")):
    """Generate: Bengali voices dispatch to Parler/Edge (see bengali.py);
    all other voices use a Kokoro preset. Returns an MP3/WAV file."""
    # Bengali dispatch — the voice id, not the lang form field, decides.
    # (The UI historically sent lang = first letter of the voice id,
    # which is wrong for bn voices, so lang is ignored on this path.)
    if voice.startswith("edge_"):
        from bengali import generate_edge
        try:
            data = generate_edge(text, voice)
        except Exception as exc:
            return JSONResponse({"ok": False, "error": "Bengali generation failed",
                                 "voice": voice, "parler_error": None,
                                 "edge_error": str(exc)}, status_code=500)
        mp3_path = os.path.join(OUT, "last_bn.mp3")
        with open(mp3_path, "wb") as fh:
            fh.write(data)
        return FileResponse(mp3_path, filename="last_bn.mp3")
    if voice.startswith("parler_"):
        # Parler path: bengali.generate_parler() prefers the pinned
        # venv_parler subprocess (transformers 4.46.1, tested). If
        # Parler fails for any reason, fall back CLEARLY to Edge —
        # gender-matched (female speakers -> Nabanita, male -> Pradeep)
        # — and mark it with the X-VoxLab-Voice-Fallback header, so a
        # fallback is never mistaken for the requested Parler voice.
        from bengali import generate_parler, generate_edge
        import soundfile as sf
        try:
            audio, sr = generate_parler(text, voice[len("parler_"):])
        except Exception as exc:  # noqa: BLE001 - fallback is explicit
            print(f"[VoxLab] Parler failed ({exc}); falling back to Edge", file=sys.stderr)
            speaker = voice[len("parler_"):]
            edge_voice = "edge_nabanita" if speaker in ("aditi", "rashmi", "riya") else "edge_pradeep"
            try:
                data = generate_edge(text, edge_voice)
            except Exception as edge_exc:
                return JSONResponse({"ok": False, "error": "Bengali generation failed",
                                     "voice": voice, "parler_error": str(exc),
                                     "edge_error": str(edge_exc),
                                     "fallback_voice": edge_voice}, status_code=500)
            mp3_path = os.path.join(OUT, "last_bn.mp3")
            with open(mp3_path, "wb") as fh:
                fh.write(data)
            return FileResponse(mp3_path, filename="last_bn.mp3",
                                headers={"X-VoxLab-Voice-Fallback": edge_voice})
        wav_path = os.path.join(OUT, "last_bn.wav")
        sf.write(wav_path, audio, sr)
        mp3_path = os.path.join(OUT, "last_bn.mp3")
        out = mp3_path if _to_mp3(wav_path, mp3_path) else wav_path
        return FileResponse(out, filename=os.path.basename(out))
    from kokoro import KPipeline
    import soundfile as sf
    key = lang
    pipes = get_pipe()
    if key not in pipes:
        pipes[key] = KPipeline(lang_code=lang)
    audio_chunks = []
    for _, _, audio in pipes[key](text, voice=voice):
        audio_chunks.append(audio)
    import numpy as np
    merged = np.concatenate(audio_chunks) if audio_chunks else np.zeros(24000)
    wav_path = os.path.join(OUT, "last.wav")
    sf.write(wav_path, merged, 24000)
    # Convert to MP3 with ffmpeg if available, else return WAV.
    mp3_path = os.path.join(OUT, "last.mp3")
    out = mp3_path if _to_mp3(wav_path, mp3_path) else wav_path
    return FileResponse(out, filename=os.path.basename(out))

def _spec_present(name):
    """True if a package is importable, without importing/loading it."""
    try:
        import importlib.util
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def _pkg_version(name):
    try:
        from importlib.metadata import version as _ver
        return _ver(name)
    except Exception:
        return None


@app.get("/api/parity/startup-status")
def startup_status():
    """Real startup checks for the splash screen — nothing is faked.

    Each step reports what was actually checked on this machine:
    server reachability (this endpoint answering), the voice list
    count, ffmpeg availability, Bengali engine package availability,
    and per-model download/bundled status. Models are lazy-loaded:
    a model showing needs_download has NOT been downloaded or
    loaded by this check, and a green splash does NOT mean every
    model is ready to generate — it means the server, voices and
    audio tools checked out and the model list is honestly reported.
    """
    ffmpeg_exe = _ffmpeg_exe()
    models = []
    models_error = None
    if _parity_loaded:
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from parity import parity_model_status
            models = parity_model_status()
        except Exception as exc:  # noqa: BLE001 - report, don't crash
            models_error = str(exc)
    else:
        models_error = _parity_error or "parity routes disabled"
    # Parler model cache presence only — no download, no model load.
    _hf = os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub")
    parler_cache = os.path.isdir(os.path.join(_hf, "models--RXD03--indic-parler-tts-pretrained"))
    steps = [
        {"id": "server", "label": "Local server running",
         "status": "ok", "detail": "Startup check answered on this machine."},
        {"id": "voices", "label": "Voice list loaded",
         "status": "ok" if len(VOICES) == 19 else "warning",
         "detail": f"{len(VOICES)} voices (11 Kokoro + 8 Bengali) — expected 19."},
        {"id": "ffmpeg", "label": "Audio tools ready",
         "status": "ok" if ffmpeg_exe else "unavailable",
         "detail": ("ffmpeg found: " + ffmpeg_exe) if ffmpeg_exe else
                    "ffmpeg not found (no bundled imageio-ffmpeg, none on PATH) — effects, stories and MP3 conversion will fail until it is available."},
        {"id": "bengali_edge", "label": "Bengali Edge voices",
         "status": "ok" if _spec_present("edge_tts") else "unavailable",
         "detail": ("edge-tts package installed — Edge Bengali voices can be tried (they still need network access to the Edge service)."
                     if _spec_present("edge_tts") else
                     "edge-tts package not installed — Edge Bengali voices are unavailable in this build.")},
        {"id": "bengali_parler", "label": "Bengali Parler voices",
         "status": "ok" if _spec_present("parler_tts") else "unavailable",
         "detail": (f"parler-tts package installed; model cache present: {parler_cache}; transformers {_pkg_version('transformers')}."
                     if _spec_present("parler_tts") else
                     "parler-tts package not installed in this build (it pins transformers 4.46.1, which conflicts with the shared transformers) — Parler requests fall back to Edge, and are never claimed as Parler audio.")},
        {"id": "models", "label": "Model availability",
         "status": "ok" if models else "unavailable",
         "detail": (f"{sum(1 for m in models if not m.get('needs_download'))} of {len(models)} parity models cached; the rest download on first use."
                     if models else f"Model list unavailable: {models_error}")},
        {"id": "output", "label": "Output folder writable",
         "status": "ok" if os.access(OUT, os.W_OK) else "unavailable",
         "detail": f"Output folder: {OUT}"},
    ]
    ready = (len(VOICES) == 19 and bool(ffmpeg_exe) and _parity_loaded
             and os.access(OUT, os.W_OK))
    return {"ok": True, "ready": ready, "parity_loaded": _parity_loaded,
            "voices_count": len(VOICES), "ffmpeg_path": ffmpeg_exe or "",
            "steps": steps, "models": models, "models_error": models_error,
            "note": "Models are lazy-loaded: this check reports download/bundled status only and does not load or download any model."}


# Parity scaffold (optional): if parity.py fails to import for any reason,
# the v1 server must still start and /api/voices must still work.
_parity_loaded = False
_parity_error = None
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from parity import router as _parity_router
    app.include_router(_parity_router)
    _parity_loaded = True
except Exception as _parity_exc:  # noqa: BLE001 - parity is optional by design
    _parity_error = str(_parity_exc)
    print(f"[VoxLab] parity routes disabled: {_parity_exc}", file=sys.stderr)



app.mount("/", StaticFiles(directory=os.path.join(DATA_DIR, "app"), html=True), name="app")

if __name__ == "__main__":
    import uvicorn
    # Remote-mode / one-click start: backend/remote.py sets these env
    # vars; defaults keep the historic 127.0.0.1:8000 behaviour.
    _host = os.environ.get("VOXLAB_SERVER_HOST", "127.0.0.1")
    try:
        _port = int(os.environ.get("VOXLAB_SERVER_PORT", "8000"))
    except ValueError:
        _port = 8000
    # Double-click UX: open the UI in the default browser shortly after
    # startup, so a frozen exe does not just sit in a console window
    # with no visible UI. Timer only — uvicorn.run() blocks, so the
    # browser must be scheduled before it starts. Console stays visible
    # (no --windowed in the PyInstaller command) so startup errors are
    # still seen instead of silently vanishing.
    import threading
    import webbrowser
    _url = f"http://{_host}:{_port}"
    threading.Timer(1.5, lambda: webbrowser.open(_url)).start()
    print(f"[VoxLab] Open {_url} in your browser", flush=True)
    uvicorn.run(app, host=_host, port=_port)
