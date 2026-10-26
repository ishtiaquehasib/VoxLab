import torch, torchaudio
from chatterbox.tts import ChatterboxTTS
# CPU, reference = Kokoro af_heart sample (synthetic, no real person, permission-safe)
model = ChatterboxTTS.from_pretrained(device="cpu")
wav = model.generate("This is VoxLab, a free voice studio running on my own computer.", audio_prompt_path="/home/hatch/workspace/voice-studio/output/kokoro_af_heart.wav")
torchaudio.save("/home/hatch/workspace/voice-studio/output/chatterbox_clone.wav", wav, model.sr)
print(f"sr={model.sr} seconds={wav.shape[-1]/model.sr:.2f}")
