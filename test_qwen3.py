import torch, soundfile as sf
from qwen_tts import Qwen3TTSModel
# CPU float32 is required for Base models (float16 fails)
try:
    model = Qwen3TTSModel.from_pretrained("Qwen/Qwen3-TTS-12Hz-0.6B-Base", device_map="cpu", dtype=torch.float32)
except Exception as e:
    print("retry plain from_pretrained after:", e)
    model = Qwen3TTSModel.from_pretrained("Qwen/Qwen3-TTS-12Hz-0.6B-Base")
ref_text = "Hello, this is a free voice studio running on my own computer. No account, no subscription, just open models and my own voice."
wavs, sr = model.generate_voice_clone(
    text="This is VoxLab, a free voice studio running on my own computer.",
    language="English",
    ref_audio="/home/hatch/workspace/voice-studio/output/kokoro_af_heart.wav",
    ref_text=ref_text,
)
sf.write("/home/hatch/workspace/voice-studio/output/qwen3_clone.wav", wavs[0], sr)
print(f"sr={sr} seconds={len(wavs[0])/sr:.2f}")
