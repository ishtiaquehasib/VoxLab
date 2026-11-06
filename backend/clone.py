"""VoxLab cloning (Chatterbox) — primary cloning engine, audit 2026-10-26.

Chatterbox won the audit over Qwen3-TTS (see ../AUDIT.md): perfect
transcript, loudness closest to the reference, and the same engine family
Voicebox itself uses for multilingual cloning.

Usage (auto device cuda -> mps -> cpu, slow on first run while the
model downloads; VOXLAB_DEVICE env overrides, see backend/device.py):
    from clone import generate_clone
    wav, sr = generate_clone("Hello VoxLab", ref_wav="path/to/reference.wav")
Reference audio must be a voice you own or have permission to clone.
No transcript is needed for the Chatterbox clone call.
"""
import torchaudio

# Explicit generation parameters (Voicebox parity, 2026-11-07 fix-first).
# Voicebox passes these on every Chatterbox call instead of relying on
# library defaults: global defaults exaggeration=0.5, cfg_weight=0.5,
# temperature=0.8, repetition_penalty=2.0 (Hebrew 0.4/0.7/0.65/2.5).
# Values only — no Voicebox code is used here.
CHATTERBOX_DEFAULTS = {"exaggeration": 0.5, "cfg_weight": 0.5,
                       "temperature": 0.8, "repetition_penalty": 2.0}
CHATTERBOX_DEFAULTS_HE = {"exaggeration": 0.4, "cfg_weight": 0.7,
                          "temperature": 0.65, "repetition_penalty": 2.5}


def generate_clone(text, ref_wav, device=None, seed=None, language="en"):
    """Clone via Chatterbox. device=None means auto (cuda -> mps -> cpu,
    see backend/device.py); an OOM on GPU retries once on CPU.
    seed sets torch.manual_seed for reproducible output; None leaves
    the library's own randomness in place."""
    from device import is_oom_error, resolve_device
    from chatterbox.tts import ChatterboxTTS
    device = resolve_device(device)
    params = dict(CHATTERBOX_DEFAULTS_HE if (language or "en").lower().startswith("he")
                  else CHATTERBOX_DEFAULTS)
    if seed is not None:
        try:
            import torch
            torch.manual_seed(int(seed))
        except Exception:
            pass
    try:
        model = ChatterboxTTS.from_pretrained(device=device)
        wav = model.generate(text, audio_prompt_path=ref_wav, language_id=language, **params)
    except Exception as exc:  # noqa: BLE001 - OOM falls back to CPU once
        if device == "cpu" or not is_oom_error(exc):
            raise
        model = ChatterboxTTS.from_pretrained(device="cpu")
        wav = model.generate(text, audio_prompt_path=ref_wav, language_id=language, **params)
    return wav, model.sr


if __name__ == "__main__":
    import sys, soundfile as sf
    text = sys.argv[1] if len(sys.argv) > 1 else "This is VoxLab, a free voice studio running on my own computer."
    ref = sys.argv[2] if len(sys.argv) > 2 else "../output/kokoro_af_heart.wav"
    wav, sr = generate_clone(text, ref)
    sf.write("../output/clone_out.wav", wav, sr)
    print(f"sr={sr} seconds={wav.shape[-1]/sr:.2f}")
