from kokoro import KPipeline
import soundfile as sf, numpy as np, os
out = os.path.expanduser("~/workspace/voice-studio/output")
os.makedirs(out, exist_ok=True)
pipe = KPipeline(lang_code='a')
text = "Hello, this is a free voice studio running on my own computer. No account, no subscription, just open models and my own voice."
chunks=[]
for _,_,audio in pipe(text, voice='af_heart'):
    chunks.append(audio)
merged = np.concatenate(chunks)
sf.write(os.path.join(out, "kokoro_af_heart.wav"), merged, 24000)
print(f"seconds={len(merged)/24000:.2f} samples={len(merged)}")
