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
# Real server log file (Logs tab reads this; no secrets are ever logged —
# Edge/Parler code paths must never print a proxy secret).
try:
    import logging as _logging
    _fh = _logging.FileHandler(os.path.join(OUT, "voxlab-server.log"), encoding="utf-8")
    _fh.setFormatter(_logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    _logging.getLogger().addHandler(_fh)
    _logging.getLogger().setLevel(_logging.INFO)
    _logging.info("VoxLab server started, output=%s", OUT)
except Exception:
    pass

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
    # Bengali honesty labels (2026-10-27): Edge Nabanita/Pradeep are the
    # GUARANTEED Bengali voices (edge-tts direct, no model download).
    # Parler speakers are NOT guaranteed in the shared/frozen env:
    # parler-tts pins transformers 4.46.1, conflicting with the shared
    # transformers, so a Parler request may fall back to Edge — and a
    # fallback is labelled as Edge, never as Parler audio.
    {"id": "parler_arjun", "name": "Arjun (male, Bengali, Parler)", "lang": "bn", "engine": "parler", "guaranteed": False, "availability": "Needs Parler download / falls back to Edge"},
    {"id": "parler_aditi", "name": "Aditi (female, Bengali, Parler)", "lang": "bn", "engine": "parler", "guaranteed": False, "availability": "Needs Parler download / falls back to Edge"},
    {"id": "parler_tapan", "name": "Tapan (male, Bengali, Parler)", "lang": "bn", "engine": "parler", "guaranteed": False, "availability": "Needs Parler download / falls back to Edge"},
    {"id": "parler_rashmi", "name": "Rashmi (female, Bengali, Parler)", "lang": "bn", "engine": "parler", "guaranteed": False, "availability": "Needs Parler download / falls back to Edge"},
    {"id": "parler_arnav", "name": "Arnav (male, Bengali, Parler)", "lang": "bn", "engine": "parler", "guaranteed": False, "availability": "Needs Parler download / falls back to Edge"},
    {"id": "parler_riya", "name": "Riya (female, Bengali, Parler)", "lang": "bn", "engine": "parler", "guaranteed": False, "availability": "Needs Parler download / falls back to Edge"},
    {"id": "edge_nabanita", "name": "Nabanita (female, Bengali, Edge)", "lang": "bn", "engine": "edge", "guaranteed": True, "availability": "Guaranteed Bengali voice (Edge)"},
    {"id": "edge_pradeep", "name": "Pradeep (male, Bengali, Edge)", "lang": "bn", "engine": "edge", "guaranteed": True, "availability": "Guaranteed Bengali voice (Edge)"},
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


@app.get("/api/bengali-status")
def bengali_status():
    """Bengali status for the Generate UI + CI smoke, no network, no generate.

    Returns exactly the 8 bn voices, which 2 are guaranteed (Edge), which
    6 are Parler (needs download / falls back to Edge), and whether
    edge_tts is importable in THIS build — the frozen-bundling check.
    A build that cannot import edge_tts reports edge_tts_installed=false
    here, so CI can fail it before release instead of shipping a 500.
    """
    bn = [v for v in VOICES if v.get("lang") == "bn"]
    return {
        "ok": True,
        "bn_voices": bn,
        "bn_count": len(bn),
        "guaranteed_edge": [v["id"] for v in bn if v.get("guaranteed")],
        "parler_needs_download_or_fallback": [v["id"] for v in bn if not v.get("guaranteed")],
        "edge_tts_installed": _spec_present("edge_tts"),
        "edge_tts_version": _pkg_version("edge-tts"),
        "parler_tts_installed": _spec_present("parler_tts"),
        "transformers_version": _pkg_version("transformers"),
        "note": "Edge Nabanita/Pradeep are the guaranteed Bengali voices. Parler speakers need the Parler model (transformers 4.46.1 pin conflicts with the shared env) and fall back to gender-matched Edge, labelled with X-VoxLab-Voice-Fallback — never claimed as Parler audio.",
    }

# Server-side generation history (in-memory only, this process only).
# File responses carry no JSON body, so history is recorded by the
# generate() paths below before returning a file. It is NOT persisted
# to disk and NOT synced to any account.
HISTORY = []


def _record_history(voice, engine, text, filename):
    try:
        import datetime
        HISTORY.append({"voice": voice, "engine": engine,
                        "text": (text or "")[:200],
                        "file": filename,
                        "at": datetime.datetime.now().isoformat(timespec="seconds")})
        del HISTORY[:-200]
    except Exception:
        pass


@app.get("/health")
def health():
    return {"status": "ok", "voices": len(VOICES), "parity_loaded": _parity_loaded,
            "parity_error": _parity_error}


@app.get("/profiles")
def profiles():
    return {"profiles": VOICES}


@app.get("/api/voices-table")
def voices_table():
    """Voices table: Name / Language / Generations / Samples / Effects / Channels.

    Generations counts this process's /history per voice id. Samples is
    the count of saved clone profiles for that voice (0 for fixed preset
    voices — no clone profile store exists yet, so this is honestly 0,
    not a copied count). Effects is 'none' for fixed voices unless a
    preset was applied in this process (not tracked per voice, so
    'none'). Channels is 'mono' (Kokoro/Bengali outputs are mono).
    """
    counts = {}
    for h in HISTORY:
        counts[h.get("voice")] = counts.get(h.get("voice"), 0) + 1
    rows = []
    for v in VOICES:
        rows.append({"name": v.get("name"), "id": v.get("id"),
                     "language": v.get("lang"), "generations": counts.get(v.get("id"), 0),
                     "samples": 0, "effects": "none", "channels": "mono"})
    return {"voices": rows, "note": "Generations = this server process only (/history, in-memory). Samples = saved clone profiles (0 for fixed voices). Effects per voice are not tracked, so 'none' is the honest value, not a preset count."}

@app.get("/history")
def history():
    return {"history": list(reversed(HISTORY))}

def _qc_headers(qc_result):
    """QC results as response headers (file responses carry no JSON body).
    Transcript is truncated to 500 chars for a header; the full check
    is available via POST /api/qc-check."""
    if not qc_result:
        return {}
    h = {"X-VoxLab-QC-Available": str(bool(qc_result.get("qc_available"))).lower(),
         "X-VoxLab-QC-Match": str(bool(qc_result.get("qc_match"))).lower(),
         "X-VoxLab-QC-Word-Match": str(qc_result.get("qc_word_match")),
         "X-VoxLab-QC-Model": str(qc_result.get("qc_model") or ""),
         "X-VoxLab-QC-Peak-Dbfs": str(qc_result.get("peak_dbfs")),
         "X-VoxLab-QC-Rms-Dbfs": str(qc_result.get("rms_dbfs"))}
    if qc_result.get("qc_transcript"):
        h["X-VoxLab-QC-Transcript"] = qc_result["qc_transcript"][:500]
    if qc_result.get("qc_error"):
        h["X-VoxLab-QC-Error"] = str(qc_result["qc_error"])[:300]
    return h


def _finalise_generate(wav_path, text, do_qc, rate, pitch, voice="", engine=""):
    """Rate/pitch prosody + QC + MP3 conversion for a finished WAV.
    Returns (FileResponse, None) or (None, JSONResponse error)."""
    import soundfile as sf
    final_wav = wav_path
    if (rate and float(rate) != 1.0) or (pitch and float(pitch) != 0):
        from qc import apply_rate_pitch
        pros_path = os.path.join(OUT, "last_prosody.wav")
        ok, err = apply_rate_pitch(wav_path, pros_path, rate=float(rate or 1.0),
                                   pitch_semitones=float(pitch or 0))
        if not ok:
            return None, JSONResponse({"ok": False, "error": err}, status_code=503)
        final_wav = pros_path
    # Normalize toggle (Settings > Generation, default on): peak-normalize
    # the finished WAV to -3 dBFS via qc.normalize_audio_file, before MP3.
    try:
        import json as _json
        _cfg = {}
        _sp = os.path.join(OUT, "voxlab-settings.json")
        if os.path.isfile(_sp):
            with open(_sp, encoding="utf-8") as _fh:
                _cfg = _json.load(_fh)
        if _cfg.get("normalize_audio", True):
            from qc import normalize_audio_file
            normalize_audio_file(final_wav)
    except Exception:
        pass
    qc_result = None
    if do_qc:
        try:
            from qc import qc_check
            qc_result = qc_check(final_wav, text)
        except Exception as exc:  # noqa: BLE001 - QC failure must not lose the audio
            qc_result = {"qc_available": False, "qc_transcript": None,
                         "qc_match": False, "qc_word_match": None,
                         "qc_model": None, "qc_error": str(exc)}
    mp3_path = os.path.join(OUT, "last.mp3")
    out = mp3_path if _to_mp3(final_wav, mp3_path) else final_wav
    _record_history(voice, engine, text, os.path.basename(out))
    return FileResponse(out, filename=os.path.basename(out),
                        headers=_qc_headers(qc_result)), None


@app.post("/api/qc-check")
def qc_check_endpoint(file_path: str = Form(""), expected_text: str = Form("")):
    """JSON QC for an existing file in output/ (no upload, no generation).
    Returns qc_transcript + qc_match + peak/RMS, or qc_available=false."""
    from qc import qc_check
    if not file_path:
        return JSONResponse({"ok": False, "error": "file_path is required"}, status_code=400)
    path = os.path.join(OUT, os.path.basename(file_path))
    if not os.path.exists(path):
        return JSONResponse({"ok": False, "error": f"missing file: {file_path}"}, status_code=404)
    result = qc_check(path, expected_text)
    result["ok"] = True
    return result


@app.post("/api/generate")
def generate(text: str = Form(...), voice: str = Form("af_heart"), lang: str = Form("a"),
             engine: str = Form("kokoro"), qwen_speaker: str = Form("Ryan"),
             qwen_language: str = Form("English"), qwen_style: str = Form(""),
             rate: float = Form(1.0), pitch: float = Form(0.0),
             pause_ms: int = Form(0), qc: int = Form(1)):
    """Main generate (2026-10-27, best-output work):
    - engine=kokoro (default, backward compatible): Kokoro preset, or
      Bengali Parler/Edge dispatch when voice starts with parler_/edge_.
    - engine=qwen-customvoice: Qwen3-TTS-12Hz-0.6B-CustomVoice preset
      speaker (qwen_speaker, qwen_language, qwen_style=instruct).
    - engine=qwen-1.7b: Qwen3-TTS-12Hz-1.7B-CustomVoice, ONLY if its
      HF cache is present; otherwise HTTP 503 needs_download — the
      1.7B model is NOT bundled and is NOT downloaded silently.
    - Prosody: rate (0.5-2.0), pitch (-12..+12 st), pause_ms (silence
      between sentences, applied at generation time by generating
      per sentence). qc=1 (default) runs faster-whisper QC and returns
      qc_transcript/qc_match in response headers; qc=0 skips it.
    Returns an MP3/WAV file (plus QC headers), or a JSON error."""
    do_qc = bool(qc)
    # --- Qwen main engines (English; Bengali voices keep their dispatch below) ---
    if engine in ("qwen-customvoice", "qwen-1.7b"):
        import soundfile as sf
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from parity import generate_customvoice
        from qc import sentence_split, join_with_pauses
        if engine == "qwen-customvoice":
            repo = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
            cache = os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub",
                                 "models--Qwen--Qwen3-TTS-12Hz-0.6B-CustomVoice")
        else:
            repo = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
            cache = os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub",
                                 "models--Qwen--Qwen3-TTS-12Hz-1.7B-CustomVoice")
        if not os.path.isdir(cache):
            return JSONResponse({"ok": False, "error": "model not downloaded",
                                 "engine": engine, "repo": repo, "needs_download": True,
                                 "note": "Qwen 1.7B is not bundled; download it on first use (several GB, CPU generation is slow). "
                                         "0.6B CustomVoice is the cached, tested main Qwen engine."},
                                status_code=503)
        if pause_ms and int(pause_ms) > 0:
            chunks = []
            for sent in sentence_split(text):
                r = generate_customvoice(sent, qwen_speaker, qwen_language,
                                         out_name="last_qwen_sent.wav",
                                         instruct=qwen_style or None,
                                         model_repo=repo, model_id=engine)
                if not r.get("ok"):
                    return JSONResponse({"ok": False, "engine": engine, "error": r.get("error")},
                                        status_code=500)
                audio, sr = sf.read(os.path.join(OUT, "last_qwen_sent.wav"))
                chunks.append((audio, sr))
            if not chunks:
                return JSONResponse({"ok": False, "error": "empty text"}, status_code=400)
            merged, sr = join_with_pauses(chunks, chunks[0][1], int(pause_ms))
            wav_path = os.path.join(OUT, "last_qwen.wav")
            sf.write(wav_path, merged, sr)
        else:
            r = generate_customvoice(text, qwen_speaker, qwen_language,
                                     out_name="last_qwen.wav",
                                     instruct=qwen_style or None,
                                     model_repo=repo, model_id=engine)
            if not r.get("ok"):
                return JSONResponse({"ok": False, "engine": engine, "error": r.get("error")},
                                    status_code=500)
            wav_path = os.path.join(OUT, "last_qwen.wav")
        resp, err = _finalise_generate(wav_path, text, do_qc, rate, pitch, voice=voice, engine=engine)
        return err if err is not None else resp
    # Bengali dispatch — the voice id, not the lang form field, decides.
    # Bengali dispatch — the voice id, not the lang form field, decides.
    # (The UI historically sent lang = first letter of the voice id,
    # which is wrong for bn voices, so lang is ignored on this path.)
    if voice.startswith("edge_"):
        from bengali import generate_edge
        try:
            data = generate_edge(text, voice)
        except Exception as exc:
            # Honest, named error — never a bare 500: missing package
            # is 503, network/service failure is 500, both carry
            # edge_error so the client/UI can show the real reason.
            msg = str(exc)
            status = 503 if ("not installed" in msg or "No module named" in msg) else 500
            return JSONResponse({"ok": False, "error": "Bengali generation failed",
                                 "voice": voice, "actual_voice": None,
                                 "parler_error": None,
                                 "edge_error": msg}, status_code=status)
        mp3_path = os.path.join(OUT, "last_bn.mp3")
        with open(mp3_path, "wb") as fh:
            fh.write(data)
        _record_history(voice, "edge", text, "last_bn.mp3")
        return FileResponse(mp3_path, filename="last_bn.mp3",
                            headers={"X-VoxLab-Voice-Actual": voice})
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
                emsg = str(edge_exc)
                estatus = 503 if ("not installed" in emsg or "No module named" in emsg) else 500
                return JSONResponse({"ok": False, "error": "Bengali generation failed",
                                     "voice": voice, "actual_voice": None,
                                     "parler_error": str(exc),
                                     "edge_error": emsg,
                                     "fallback_voice": edge_voice}, status_code=estatus)
            mp3_path = os.path.join(OUT, "last_bn.mp3")
            with open(mp3_path, "wb") as fh:
                fh.write(data)
            _record_history(voice, "edge-fallback", text, "last_bn.mp3")
            return FileResponse(mp3_path, filename="last_bn.mp3",
                                headers={"X-VoxLab-Voice-Fallback": edge_voice})
        wav_path = os.path.join(OUT, "last_bn.wav")
        sf.write(wav_path, audio, sr)
        mp3_path = os.path.join(OUT, "last_bn.mp3")
        out = mp3_path if _to_mp3(wav_path, mp3_path) else wav_path
        _record_history(voice, "parler", text, os.path.basename(out))
        return FileResponse(out, filename=os.path.basename(out),
                            headers={"X-VoxLab-Voice-Actual": voice})
    import soundfile as sf
    import numpy as np
    wav_path = os.path.join(OUT, "last.wav")
    _kokoro_ok = False
    try:
        from kokoro import KPipeline
        key = lang
        pipes = get_pipe()
        if key not in pipes:
            pipes[key] = KPipeline(lang_code=lang)
        if pause_ms and int(pause_ms) > 0:
            from qc import sentence_split, join_with_pauses
            chunks = []
            for sent in sentence_split(text):
                sent_chunks = [audio for _, _, audio in pipes[key](sent, voice=voice)]
                if sent_chunks:
                    chunks.append((np.concatenate(sent_chunks), 24000))
            if not chunks:
                return JSONResponse({"ok": False, "error": "empty text"}, status_code=400)
            merged, _sr = join_with_pauses(chunks, 24000, int(pause_ms))
        else:
            audio_chunks = []
            for _, _, audio in pipes[key](text, voice=voice):
                audio_chunks.append(audio)
            merged = np.concatenate(audio_chunks) if audio_chunks else np.zeros(24000)
        sf.write(wav_path, merged, 24000)
        _kokoro_ok = True
    except Exception as _kp_exc:  # noqa: BLE001 - fall back to proven ONNX path
        print(f"[VoxLab] Kokoro KPipeline failed ({_kp_exc}); trying Kokoro ONNX", file=sys.stderr)
    if not _kokoro_ok:
        # Proven ONNX route (parity.synthesize_kokoro, test_kokoro_onnx.py):
        # KPipeline fails in the shared venv on a spacy tokenizer
        # OverflowError, while ONNX generates the same preset voices.
        # Never return a fake file: if ONNX also fails, report both errors.
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from parity import synthesize_kokoro
            from qc import sentence_split, join_with_pauses
            if pause_ms and int(pause_ms) > 0:
                chunks = []
                for sent in sentence_split(text):
                    r = synthesize_kokoro(sent, voice, out_name="last_onnx_sent.wav")
                    if not r.get("ok"):
                        raise RuntimeError(r.get("error"))
                    audio, sr = sf.read(os.path.join(OUT, "last_onnx_sent.wav"))
                    chunks.append((audio, sr))
                if not chunks:
                    return JSONResponse({"ok": False, "error": "empty text"}, status_code=400)
                merged, sr = join_with_pauses(chunks, chunks[0][1], int(pause_ms))
                sf.write(wav_path, merged, sr)
            else:
                r = synthesize_kokoro(text, voice, out_name="last.wav")
                if not r.get("ok"):
                    raise RuntimeError(r.get("error"))
        except Exception as _onnx_exc:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": "Kokoro generation failed",
                                 "kPipeline_error": str(_kp_exc),
                                 "onnx_error": str(_onnx_exc)}, status_code=500)
    resp, err = _finalise_generate(wav_path, text, do_qc, rate, pitch, voice=voice, engine=engine)
    return err if err is not None else resp

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
