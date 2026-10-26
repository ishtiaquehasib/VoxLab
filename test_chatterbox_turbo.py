"""Chatterbox Turbo test: clone from the Kokoro af_heart sample (synthetic,
permission-safe), one short sentence, CPU. Turbo needs a >5s reference."""
import torch, soundfile as sf
from chatterbox.tts_turbo import ChatterboxTurboTTS

model = ChatterboxTurboTTS.from_pretrained(device="cpu")
wav = model.generate(
    text="This is VoxLab, a free voice studio running on my own computer.",
    audio_prompt_path="/home/hatch/workspace/voice-studio/output/kokoro_af_heart.wav",
)
print(f"sr={model.sr} shape={tuple(wav.shape)}")
sf.write("/home/hatch/workspace/voice-studio/output/chatterbox_turbo_clone.wav", wav[0].numpy(), model.sr)
import numpy as np
print(f"seconds={wav.shape[-1]/model.sr:.2f}")
