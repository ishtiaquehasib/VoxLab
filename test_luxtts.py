"""LuxTTS test: clone from the Kokoro af_heart sample (synthetic,
permission-safe), one short sentence, CPU ONNX path.
Code from https://github.com/ysharma3501/LuxTTS (Apache-2.0), cloned to /tmp/luxtts.
"""
import sys
sys.path.insert(0, "/home/hatch/workspace/voice-studio/luxtts_src")
import soundfile as sf
from zipvoice.luxvoice import LuxTTS

lux = LuxTTS('YatharthS/LuxTTS', device='cpu', threads=2)
enc = lux.encode_prompt("/home/hatch/workspace/voice-studio/output/kokoro_af_heart.wav", rms=0.01)
wav = lux.generate_speech("This is VoxLab, a free voice studio running on my own computer.", enc, num_steps=4)
wav = wav.numpy().squeeze()
sf.write("/home/hatch/workspace/voice-studio/output/luxtts_clone.wav", wav, 48000)
print(f"seconds={len(wav)/48000:.2f} sr=48000")
