"""Qwen CustomVoice test: 0.6B preset speaker Ryan, one short sentence, CPU float32."""
import torch, soundfile as sf
from qwen_tts import Qwen3TTSModel

model = Qwen3TTSModel.from_pretrained("Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice", device_map="cpu", dtype=torch.float32)
print("speakers:", model.get_supported_speakers())
wavs, sr = model.generate_custom_voice(
    text="This is VoxLab, a free voice studio running on my own computer.",
    language="English",
    speaker="Ryan",
)
sf.write("/home/hatch/workspace/voice-studio/output/qwen_customvoice_ryan.wav", wavs[0], sr)
print(f"sr={sr} seconds={len(wavs[0])/sr:.2f}")
