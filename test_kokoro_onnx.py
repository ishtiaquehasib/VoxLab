from kokoro_onnx import Kokoro
import soundfile as sf, os
out = os.path.expanduser("~/workspace/voice-studio/output")
os.makedirs(out, exist_ok=True)
# Download model + voices on first run (hexgrad/Kokoro-82M, same as Voicebox's Kokoro)
kokoro = Kokoro("kokoro-v1.0.onnx", "voices-v1.0.bin")
text = "Hello, this is a free voice studio running on my own computer. No account, no subscription, just open models and my own voice."
samples, sr = kokoro.create(text, voice="af_heart", speed=1.0, lang="en-us")
sf.write(os.path.join(out, "kokoro_af_heart.wav"), samples, sr)
print(f"seconds={len(samples)/sr:.2f} sr={sr} samples={len(samples)}")
