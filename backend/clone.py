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


def generate_clone(text, ref_wav, device=None):
    """Clone via Chatterbox. device=None means auto (cuda -> mps -> cpu,
    see backend/device.py); an OOM on GPU retries once on CPU."""
    from device import is_oom_error, resolve_device
    from chatterbox.tts import ChatterboxTTS
    device = resolve_device(device)
    try:
        model = ChatterboxTTS.from_pretrained(device=device)
        wav = model.generate(text, audio_prompt_path=ref_wav)
    except Exception as exc:  # noqa: BLE001 - OOM falls back to CPU once
        if device == "cpu" or not is_oom_error(exc):
            raise
        model = ChatterboxTTS.from_pretrained(device="cpu")
        wav = model.generate(text, audio_prompt_path=ref_wav)
    return wav, model.sr


if __name__ == "__main__":
    import sys, soundfile as sf
    text = sys.argv[1] if len(sys.argv) > 1 else "This is VoxLab, a free voice studio running on my own computer."
    ref = sys.argv[2] if len(sys.argv) > 2 else "../output/kokoro_af_heart.wav"
    wav, sr = generate_clone(text, ref)
    sf.write("../output/clone_out.wav", wav, sr)
    print(f"sr={sr} seconds={wav.shape[-1]/sr:.2f}")
