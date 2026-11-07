"""VoxLab Qwen3-TTS Base voice cloning (2026-11-07 fix-first, P0).

Voicebox's flagship clone engine is Qwen3-TTS 1.7B Base. VoxLab v1
chose Chatterbox instead and never wired a Base clone into any server
route (only a standalone test_qwen3.py for 0.6B existed). This module
wires the Base clone path the Voicebox way — own code, same published
parameter values, no Voicebox code copied:

- create_voice_prompt(ref_audio, ref_text) -> cached prompt, via
  model.create_voice_clone_prompt(ref_audio, ref_text,
  x_vector_only_mode=False), cached by (audio path, ref_text).
- generate_voice_clone(text, voice_clone_prompt=prompt, language,
  instruct) with torch.manual_seed(seed) before inference.
- CPU: torch.float32 (Base models fail in float16 on CPU);
  GPU: bfloat16. 1.7B is the default size, 0.6B the fallback.

RAM honesty: a 1.7B Base model in float32 needs ~7.7 GiB of weights
alone, so on a 7.7 GiB machine it cannot load beside the OS. The
loader checks available RAM first and returns an honest
needs_bigger_machine error instead of letting the server die with
SIGKILL. 0.6B Base (~3.7 GiB float32) is the testable fallback on
this VM. The 1.7B weights are downloaded on first use (Models page /
first clone), never bundled, never downloaded silently by generate.
"""
import hashlib
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "output")
os.makedirs(OUT, exist_ok=True)

# v1.1.11: the vendored qwen_tts package lives at the repo root
# (BASE) — see qwen_tts/VENDORED.md. Insert BASE so
# `from qwen_tts import ...` below finds the vendored copy even when
# the server is started from another working directory. (In the
# frozen build PyInstaller collects qwen_tts into _internal via
# --collect-all qwen_tts; this line is a no-op there.)

QWEN_BASE_REPOS = {
    "1.7B": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
    "0.6B": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
}
# float32 weight bytes for the Base model file alone (safetensors size
# rounded up): 1.7B ~3.86 GiB stored -> ~7.7 GiB in float32;
# 0.6B ~1.83 GiB stored -> ~3.7 GiB in float32. Plus tokenizer +
# Python/torch overhead, so the guard asks for a margin on top.
_QWEN_BASE_RAM_GB = {"1.7B": 8.5, "0.6B": 4.5}

_QWEN_MODEL = None
_QWEN_SIZE = None
_PROMPT_CACHE = {}
_PROMPT_CACHE_MAX = 8


def _cache_dir(repo):
    return os.path.join(os.path.expanduser("~"), ".cache", "huggingface",
                        "hub", "models--" + repo.replace("/", "--"))


def _available_ram_gb():
    try:
        for line in open("/proc/meminfo"):
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) / 1024 / 1024
    except Exception:
        pass
    return None


def _cache_complete(repo):
    """A model counts as cached only if a non-empty snapshot exists."""
    snap = os.path.join(_cache_dir(repo), "snapshots")
    try:
        return os.path.isdir(snap) and any(os.scandir(snap))
    except Exception:
        return False


def qwen_base_status(size="1.7B"):
    repo = QWEN_BASE_REPOS[size]
    return {"size": size, "repo": repo,
            "cached": _cache_complete(repo),
            "needs_download": not _cache_complete(repo)}


def _load_qwen_base(size="1.7B"):
    """Load (or reuse) the Base model. Returns (model, None) or
    (None, error-dict). Never downloads: a missing cache is an honest
    needs_download error for the caller to surface."""
    global _QWEN_MODEL, _QWEN_SIZE
    if _QWEN_MODEL is not None and _QWEN_SIZE == size:
        return _QWEN_MODEL, None
    repo = QWEN_BASE_REPOS[size]
    if not _cache_complete(repo):
        return None, {"ok": False, "error": "Qwen3-TTS Base model not downloaded",
                      "engine": "qwen-base", "repo": repo, "needs_download": True,
                      "size": size,
                      "note": "Download it on the Models page (1.7B is ~4.5 GB). "
                              "It is not bundled and is not downloaded silently."}
    avail = _available_ram_gb()
    need = _QWEN_BASE_RAM_GB[size]
    if avail is not None and avail < need:
        return None, {"ok": False, "error": "not enough free RAM for Qwen3-TTS "
                      f"{size} Base in float32 ({avail:.1f} GiB free, "
                      f"{need:.1f} GiB needed)",
                      "engine": "qwen-base", "repo": repo,
                      "needs_bigger_machine": True, "size": size,
                      "action": "Use the 0.6B Base fallback on this machine, "
                                "or run VoxLab on a PC with more RAM / a GPU."}
    try:
        from qwen_tts import Qwen3TTSModel
    except Exception as exc:  # noqa: BLE001
        return None, {"ok": False, "error": f"qwen-tts package not available: {exc}",
                      "engine": "qwen-base",
                      "install_action": "The vendored qwen_tts package (repo root "
                                        "qwen_tts/, bundled in the installer) is "
                                        "missing or failed to import — reinstall "
                                        "from a fresh release build. Do NOT pip "
                                        "install qwen-tts: its transformers pin "
                                        "conflicts with chatterbox-tts (see "
                                        "qwen_tts/VENDORED.md)."}
    try:
        import torch
        # Unload other heavy models first: a Base load beside Turbo /
        # Whisper / LLM kills a 7.7 GiB server with SIGKILL.
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from parity import _unload_heavy_models
            _unload_heavy_models()
        except Exception:
            pass
        _QWEN_MODEL = Qwen3TTSModel.from_pretrained(
            repo, device_map="cpu", dtype=torch.float32)
        _QWEN_SIZE = size
        return _QWEN_MODEL, None
    except Exception as exc:  # noqa: BLE001
        return None, {"ok": False, "error": f"Qwen3-TTS {size} Base failed to load: {exc}",
                      "engine": "qwen-base", "repo": repo, "size": size}


def _prompt_key(ref_audio, ref_text):
    h = hashlib.sha256()
    h.update(os.path.abspath(ref_audio).encode("utf-8"))
    h.update(b"\0")
    h.update((ref_text or "").encode("utf-8"))
    return h.hexdigest()


def create_voice_prompt(ref_audio, ref_text, size="1.7B"):
    """Build (or reuse from cache) the voice-clone prompt for a
    reference clip + its transcript. Returns (prompt, was_cached, error).
    ref_text is required: the Base clone API cannot prompt without it."""
    if not (ref_text or "").strip():
        return None, False, "reference transcript (ref_text) is required for Qwen Base cloning"
    key = _prompt_key(ref_audio, ref_text)
    if key in _PROMPT_CACHE:
        return _PROMPT_CACHE[key], True, None
    model, err = _load_qwen_base(size)
    if err:
        return None, False, err
    try:
        prompt = model.create_voice_clone_prompt(
            ref_audio=str(ref_audio), ref_text=ref_text,
            x_vector_only_mode=False)
    except Exception as exc:  # noqa: BLE001
        return None, False, f"voice prompt creation failed: {exc}"
    if len(_PROMPT_CACHE) >= _PROMPT_CACHE_MAX:
        _PROMPT_CACHE.clear()
    _PROMPT_CACHE[key] = prompt
    return prompt, False, None


def generate_qwen_base_clone(text, ref_wav, ref_text=None, instruct=None,
                             seed=None, size="1.7B", language="English",
                             out_name="qwen_base_clone.wav"):
    """Clone with Qwen3-TTS Base. ref_text is transcribed with Whisper
    (small) when not supplied — never invented. Returns the standard
    generate_* result dict."""
    if not (text or "").strip():
        return {"ok": False, "error": "text is required"}
    if not ref_wav or not os.path.exists(ref_wav):
        return {"ok": False, "error": f"reference audio not found: {ref_wav}"}
    if not (ref_text or "").strip():
        ref_text_source = "transcribed"
        # Transcribe first, BEFORE loading Qwen: transcribe() unloads
        # other heavy models, and a Base load beside them kills the server.
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from parity import transcribe
            tr = transcribe(ref_wav, model_size="small")
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"reference transcription failed: {exc}",
                    "action": "Supply ref_text (the exact words spoken in the "
                              "reference clip) with the clone request instead."}
        if not tr.get("available") or not (tr.get("transcript") or "").strip():
            return {"ok": False,
                    "error": "could not transcribe the reference clip — "
                             "faster-whisper unavailable or no speech found",
                    "detail": tr.get("error"),
                    "action": "Supply ref_text (the exact words spoken in the "
                              "reference clip) with the clone request instead."}
        ref_text = tr["transcript"]
    else:
        ref_text_source = "supplied"
    prompt, was_cached, err = create_voice_prompt(ref_wav, ref_text, size=size)
    fallback = None
    if err and isinstance(err, dict) and err.get("needs_bigger_machine") and size == "1.7B":
        # Auto-fallback (2026-11-07 fix-first): a small machine still gets a
        # clone from 0.6B instead of an error; the result says which size
        # actually ran. Big machines keep 1.7B.
        fallback = err.get("error", "1.7B Base needs more RAM; fell back to 0.6B Base")
        size = "0.6B"
        prompt, was_cached, err = create_voice_prompt(ref_wav, ref_text, size=size)
    if err:
        if isinstance(err, dict):
            return err
        return {"ok": False, "error": err}
    model, err = _load_qwen_base(size)
    if err:
        return err
    try:
        import torch
        if seed is not None:
            torch.manual_seed(int(seed))
        with torch.inference_mode():
            wavs, sr = model.generate_voice_clone(
                text=text, voice_clone_prompt=prompt,
                language=language, instruct=instruct or None)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"Qwen Base clone generation failed: {exc}",
                "engine": "qwen-base", "size": size}
    try:
        import numpy as np
        import soundfile as sf
        audio = np.asarray(wavs[0], dtype=np.float32).squeeze()
        out_path = os.path.join(OUT, out_name)
        sf.write(out_path, audio, int(sr))
        return {"ok": True, "file": out_name, "path": out_path,
                "seconds": round(float(len(audio) / int(sr)), 3),
                "bytes": os.path.getsize(out_path),
                "sample_rate": int(sr),
                "model": "qwen-base", "engine": QWEN_BASE_REPOS[size],
                "size": size, "ref_text": ref_text,
                "ref_text_source": ref_text_source,
                "prompt_cached": bool(was_cached),
                "fallback": fallback,
                "params": {"seed": seed, "instruct": instruct or None,
                           "language": language}}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"could not write clone audio: {exc}"}
