"""VoxLab v1 backend: local FastAPI server, no cloud, no account.

Engines (audit 2026-10-26, see ../AUDIT.md):
- Kokoro-82M preset voices (fast CPU, English etc., same engine as Voicebox)
- Chatterbox cloning in clone.py — primary cloning engine, audit winner
  over Qwen3-TTS. Qwen3-TTS is dropped from v1.

Run: python backend/server.py  ->  http://127.0.0.1:8000
"""
import os, io, sys
from fastapi import FastAPI, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Frozen (PyInstaller) layout: the exe lives in dist/VoxLab/ and the
# bundled data lands beside it (dist/VoxLab/app, dist/VoxLab/assets).
# Unfrozen, __file__ is backend/server.py, so two dirnames up = project
# root. Frozen, __file__ points inside dist/VoxLab/_internal/, so the
# old two-dirname math landed in _internal/ (or dist/) instead of
# dist/VoxLab/ — StaticFiles then failed at startup and the exe
# closed instantly with no UI. Use the exe directory when frozen.
if getattr(sys, "frozen", False):
    BASE = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
        data = generate_edge(text, voice)
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
            data = generate_edge(text, edge_voice)
            mp3_path = os.path.join(OUT, "last_bn.mp3")
            with open(mp3_path, "wb") as fh:
                fh.write(data)
            return FileResponse(mp3_path, filename="last_bn.mp3",
                                headers={"X-VoxLab-Voice-Fallback": edge_voice})
        wav_path = os.path.join(OUT, "last_bn.wav")
        sf.write(wav_path, audio, sr)
        mp3_path = os.path.join(OUT, "last_bn.mp3")
        rc = os.system(f'ffmpeg -y -v error -i "{wav_path}" -c:a libmp3lame -q:a 4 "{mp3_path}"')
        out = mp3_path if rc == 0 and os.path.exists(mp3_path) else wav_path
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
    rc = os.system(f'ffmpeg -y -v error -i "{wav_path}" -c:a libmp3lame -q:a 4 "{mp3_path}"')
    out = mp3_path if rc == 0 and os.path.exists(mp3_path) else wav_path
    return FileResponse(out, filename=os.path.basename(out))

# Parity scaffold (optional): if parity.py fails to import for any reason,
# the v1 server must still start and /api/voices must still work.
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from parity import router as _parity_router
    app.include_router(_parity_router)
except Exception as _parity_exc:  # noqa: BLE001 - parity is optional by design
    print(f"[VoxLab] parity routes disabled: {_parity_exc}", file=sys.stderr)

app.mount("/", StaticFiles(directory=os.path.join(BASE, "app"), html=True), name="app")

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
