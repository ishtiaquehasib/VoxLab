"""VoxLab Bengali voices — Parler speakers + Edge presets.

Routes re-used from the proven mahbub_test code paths (2026-10-26):
- Edge: PRIMARY path is the edge-tts library directly
  (bn-BD-NabanitaNeural / bn-BD-PradeepNeural), no secret, no local
  file. The user's Deno voice server is used ONLY if the env var
  VOXLAB_EDGE_SECRET is set (never read from a local source file,
  never printed/logged/returned/committed) — on a user PC that file
  does not exist, and reading it caused a FileNotFound 500.
- Parler: public pretrained mirror RXD03/indic-parler-tts-pretrained
  (Apache 2.0, already in the local HF cache; official
  ai4bharat/indic-parler-tts is gated). The Arjun description below is
  the exact one used in mahbub_test; the other speakers use the same
  template with their name swapped in — that is a template variation,
  not a per-speaker description verified against the model card.

No Bengali generation is claimed to work until a real test audio
file exists (see PARITY.md test log).
"""
import json
import os
import re
import sys
import urllib.request

# FROZEN-BUNDLING NOTE (2026-10-27 Bengali fix): edge_tts was imported
# ONLY lazily inside generate_edge(), so a PyInstaller build could ship
# without it (the v1.0.6 Windows failure class: lazy import, missing
# package at runtime). This guarded top-level import makes the import
# visible to PyInstaller's static analysis AND to --collect-all
# edge_tts / --hidden-import edge_tts in all 3 workflows, while still
# letting the server start if edge-tts is absent (then generate_edge
# returns the honest missing-package error, never fake audio).
try:
    import edge_tts as _edge_tts_top  # noqa: F401
except Exception:  # noqa: BLE001 - absent package is reported at generate time
    _edge_tts_top = None

# Same frozen-exe split as server.py/parity.py: PyInstaller onedir puts
# bundled data in _internal/ (sys._MEIPASS), NOT beside the exe, so the
# old two-dirname BASE pointed at a nonexistent data dir when frozen.
# Split it: bundled data from _MEIPASS, writable output beside the exe.
# Unfrozen logic unchanged. Note: PARLER_VENV_PYTHON below then points
# under _MEIPASS when frozen, where no venv exists, so generate_parler
# honestly falls back to in-process generation (venv is never bundled).
if getattr(sys, "frozen", False):
    DATA_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    BASE = DATA_DIR
    OUT = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "output")
else:
    BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATA_DIR = BASE
    OUT = os.path.join(BASE, "output")

EDGE_VOICES = {
    "edge_nabanita": "bn-BD-NabanitaNeural",
    "edge_pradeep": "bn-BD-PradeepNeural",
}

PARLER_SPEAKERS = ["arjun", "aditi", "tapan", "rashmi", "arnav", "riya"]
PARLER_MODEL = "RXD03/indic-parler-tts-pretrained"
_DENO_URL = "https://bangla-voice-tts.hasibtechqore.deno.net/generate"


def _generate_edge_deno(text, voice_id):
    """Legacy Deno-server path, ONLY when VOXLAB_EDGE_SECRET is set.

    Never reads a local source file for the secret. Returns None if
    no secret is configured, so callers fall through to an error
    instead of crashing on a missing file.
    """
    secret = os.environ.get("VOXLAB_EDGE_SECRET", "")
    if not secret:
        return None
    url = os.environ.get("VOXLAB_DENO_URL", _DENO_URL)
    base_voice = EDGE_VOICES[voice_id]
    body = json.dumps(
        {"text": text, "base_voice": base_voice, "rate": 0, "pitch": 0}
    ).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json",
                 "x-proxy-secret": secret},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Edge Deno server returned HTTP {resp.status}")
        return resp.read()


def generate_edge(text, voice_id):
    """Edge preset, primary via edge-tts library. Returns raw MP3 bytes.

    No secret, no local file: edge_tts.Communicate speaks directly
    with Microsoft Edge neural voices. Deno fallback only if
    VOXLAB_EDGE_SECRET is set (see _generate_edge_deno).
    """
    if voice_id not in EDGE_VOICES:
        raise ValueError(f"unknown Edge voice: {voice_id}")
    try:
        import asyncio
        import tempfile
        import edge_tts
        async def _run():
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tf:
                out = tf.name
            try:
                await edge_tts.Communicate(text, EDGE_VOICES[voice_id]).save(out)
                with open(out, "rb") as fh:
                    return fh.read()
            finally:
                try:
                    os.remove(out)
                except OSError:
                    pass
        return asyncio.run(_run())
    except ImportError as exc:
        # edge-tts not installed: try Deno only if a secret is set,
        # otherwise surface the real missing-package error.
        deno = _generate_edge_deno(text, voice_id)
        if deno is not None:
            return deno
        raise RuntimeError(
            "edge-tts is not installed and VOXLAB_EDGE_SECRET is not set; "
            "install edge-tts to use Edge Bengali voices") from exc


_parler_model = None
_parler_tokenizer = None
_parler_desc_tok = None


def _load_parler():
    global _parler_model, _parler_tokenizer, _parler_desc_tok
    if _parler_model is not None:
        return _parler_model, _parler_tokenizer, _parler_desc_tok
    import torch  # noqa: F401  (needed by parler_tts)
    # Compatibility workaround, 2026-10-26: with transformers 4.57,
    # ParlerTTSConfig.to_diff_dict() tries to instantiate the config
    # with no arguments during from_pretrained logging and raises
    # "Config has to be initialized with text_encoder...". Patching
    # to_diff_dict to fall back to to_dict() lets the exact same
    # cached checkpoint load (verified: PATCH_LOAD_OK, model_type
    # parler_tts). This changes no model weights or config values.
    try:
        from parler_tts.configuration_parler_tts import ParlerTTSConfig
        _orig_to_diff = ParlerTTSConfig.to_diff_dict

        def _safe_to_diff(self):
            try:
                return _orig_to_diff(self)
            except Exception:  # noqa: BLE001 - fallback is the point
                return self.to_dict()

        ParlerTTSConfig.to_diff_dict = _safe_to_diff
    except Exception:  # noqa: BLE001 - if the patch cannot apply, load will fail honestly
        pass
    from parler_tts import ParlerTTSForConditionalGeneration
    from transformers import AutoTokenizer
    from device import get_device
    model = ParlerTTSForConditionalGeneration.from_pretrained(PARLER_MODEL).to(get_device())
    tokenizer = AutoTokenizer.from_pretrained(PARLER_MODEL)
    desc_tok = AutoTokenizer.from_pretrained(model.config.text_encoder._name_or_path)
    _parler_model, _parler_tokenizer, _parler_desc_tok = model, tokenizer, desc_tok
    return model, tokenizer, desc_tok


def generate_parler_inprocess(text, speaker):
    """Parler Bengali speaker, in this process. Returns (samples, sr).

    Works only when this process runs under a transformers version
    ParlerTTS supports (4.46.1 in venv_parler). Under transformers
    4.57 (the shared mahbub venv) generation fails — see PARITY.md.
    Use generate_parler() instead, which prefers the pinned venv.
    speaker is one of PARLER_SPEAKERS (the part after 'parler_').
    """
    speaker = speaker.lower()
    if speaker not in PARLER_SPEAKERS:
        raise ValueError(f"unknown Parler speaker: {speaker}")
    model, tokenizer, desc_tok = _load_parler()
    # transformers 4.57 compat, second half: this checkpoint's
    # generation_config loads as None under 4.57 (it was written
    # under 4.46.1), so model.generate() crashes with
    # "'NoneType' object has no attribute 'update'". Restore it
    # from the checkpoint's own generation_config.json values.
    try:
        if getattr(model, "generation_config", None) is None:
            from transformers import GenerationConfig
            model.generation_config = GenerationConfig(
                bos_token_id=1025, decoder_start_token_id=1025,
                do_sample=True, eos_token_id=1024, max_length=2610,
                pad_token_id=1024,
            )
    except Exception:  # noqa: BLE001 - generate will fail honestly below
        pass
    # transformers 4.57 compat, third half: ParlerTTS no longer
    # inherits GenerationMixin, so its own generate() calls a
    # _validate_model_kwargs that no longer exists on the class.
    # Bind the mixin's implementation to this instance only.
    try:
        import types
        from transformers.generation.utils import GenerationMixin
        if not hasattr(model, "_validate_model_kwargs"):
            model._validate_model_kwargs = types.MethodType(
                GenerationMixin._validate_model_kwargs, model)
    except Exception:  # noqa: BLE001 - generate will fail honestly below
        pass
    name = speaker.capitalize()
    description = (
        f"{name} speaks at a moderate pace with a calm, narrative tone. "
        "The recording is clear, with a close sound and only minimal ambient noise."
    )
    from device import is_oom_error
    # Use the model's actual device, not the detected one: after an
    # OOM fallback the cached model stays on CPU even if a GPU exists.
    try:
        _device = next(model.parameters()).device.type
    except Exception:
        _device = "cpu"
    desc_ids = desc_tok(description, return_tensors="pt").to(_device)
    prompt_ids = tokenizer(text, return_tensors="pt").to(_device)
    try:
        gen = model.generate(
            input_ids=desc_ids.input_ids, attention_mask=desc_ids.attention_mask,
            prompt_input_ids=prompt_ids.input_ids,
            prompt_attention_mask=prompt_ids.attention_mask,
        )
    except Exception as exc:  # noqa: BLE001 - OOM falls back to CPU once
        if _device == "cpu" or not is_oom_error(exc):
            raise
        model.to("cpu")
        desc_ids = desc_ids.to("cpu")
        prompt_ids = prompt_ids.to("cpu")
        gen = model.generate(
            input_ids=desc_ids.input_ids, attention_mask=desc_ids.attention_mask,
            prompt_input_ids=prompt_ids.input_ids,
            prompt_attention_mask=prompt_ids.attention_mask,
        )
    audio = gen.cpu().numpy().squeeze()
    return audio, int(model.config.sampling_rate)


# --- Pinned-venv Parler path (2026-10-26, tested) ---
# venv_parler: transformers 4.46.1 (exact requirement of parler-tts
# 0.2.2), torch/torchaudio 2.8.0+cpu, cached RXD03 model, no re-download
# (HF_HUB_OFFLINE=1). Created because the shared venv's transformers
# 4.57 breaks ParlerTTS generation. The venv lives inside the project
# for local use only and must NOT be pushed to GitHub (see .gitignore).
# FROZEN Parler CLI fallback (documented, not silently changed):
# - PARLER_VENV_PYTHON points under BASE (= _MEIPASS when frozen),
#   where no venv exists, because venv_parler is a local dev venv
#   that is never bundled into the PyInstaller exe.
# - PARLER_CLI points at parler_cli.py next to this file. When frozen,
#   that .py SOURCE file also does not exist: PyInstaller bundles
#   modules as .pyc inside the PYZ archive, not as .py files on disk,
#   so a frozen subprocess call to parler_cli.py can never run.
# - Consequence (by design, honest): frozen generate_parler() ALWAYS
#   takes the in-process fallback below. If the frozen env's
#   transformers version cannot run ParlerTTS, the real error surfaces
#   — never fake audio, never a silent venv/CLI claim. Shipping a
#   frozen Parler venv/CLI is a separate, unbuilt item; do not claim
#   it here.
PARLER_VENV_PYTHON = os.path.join(BASE, "venv_parler", "bin", "python")
PARLER_CLI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "parler_cli.py")


def generate_parler(text, speaker):
    """Parler Bengali speaker. Returns (samples ndarray, sample_rate).

    Preferred path: run parler_cli.py under venv_parler (transformers
    4.46.1) as a subprocess, so the caller venv does not matter.
    If that venv is absent, fall back to in-process generation (works
    only under a compatible transformers version) and let any error
    surface honestly — never a fake audio result.
    FROZEN note: when frozen, the venv path and the parler_cli.py
    source both do not exist (see the FROZEN comment at PARLER_CLI),
    so frozen generation is ALWAYS the in-process fallback.
    """
    speaker = speaker.lower()
    if speaker not in PARLER_SPEAKERS:
        raise ValueError(f"unknown Parler speaker: {speaker}")
    if os.path.exists(PARLER_VENV_PYTHON):
        import subprocess
        import tempfile
        import soundfile as sf

        with tempfile.TemporaryDirectory() as tmp:
            out_wav = os.path.join(tmp, "parler_out.wav")
            env = dict(os.environ)
            env["HF_HUB_OFFLINE"] = "1"
            env["no_proxy"] = ""
            env["NO_PROXY"] = ""
            proc = subprocess.run(
                [PARLER_VENV_PYTHON, PARLER_CLI, text, speaker, out_wav],
                capture_output=True, text=True, timeout=600, env=env,
            )
            if proc.returncode != 0 or not os.path.exists(out_wav):
                tail = (proc.stderr or proc.stdout or "").strip()[-500:]
                raise RuntimeError(
                    f"Parler venv generation failed (exit {proc.returncode}): {tail}")
            audio, sr = sf.read(out_wav)
            return audio, int(sr)
    return generate_parler_inprocess(text, speaker)
