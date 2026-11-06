"""Tutorial 01 narration via Kokoro ONNX af_heart (en-us).
English narration matching the script's meaning; the script's Roman
Bengali lines are the on-screen meaning, Kokoro en-us cannot speak them.
No cloned voice is claimed here: narration is the Kokoro fixed voice.
"""
import os, numpy as np, soundfile as sf
from kokoro_onnx import Kokoro

BASE = os.path.expanduser("~/workspace/voice-studio")
OUT = os.path.join(BASE, "tutorials")
kokoro = Kokoro(os.path.join(BASE, "output", "kokoro-v1.0.onnx"),
                 os.path.join(BASE, "output", "voices-v1.0.bin"))
blocks = [
    "Cloning your own voice in VoxLab is easy. First, go to Clone.",
    "Upload a clear thirty second voice sample, or record with your microphone.",
    "Now type the text you want spoken, and select your cloned voice.",
    "Press Generate. When the audio is ready, play it back, and download it if you like it.",
    "That is VoxLab Clone. In the next tutorial, we will look at dictation.",
]
parts, durs = [], []
for i, text in enumerate(blocks):
    samples, sr = kokoro.create(text, voice="af_heart", speed=1.0, lang="en-us")
    parts.append(np.asarray(samples, dtype=np.float32))
    durs.append(len(samples) / sr)
    print(f"block {i+1}: {len(samples)/sr:.2f}s sr={sr} text={text!r}")
    if i < len(blocks) - 1:
        parts.append(np.zeros(int(sr * 0.4), dtype=np.float32))
merged = np.concatenate(parts)
sf.write(os.path.join(OUT, "tutorial-01-clone-narration.wav"), merged, 24000)
print(f"total={len(merged)/24000:.3f}s samples={len(merged)}")
with open(os.path.join(OUT, "tutorial-01-clone-narration.txt"), "w") as f:
    for i, (d, t) in enumerate(zip(durs, blocks)):
        f.write(f"block {i+1}: {d:.2f}s | {t}\n")
    f.write(f"total: {len(merged)/24000:.3f}s\n")
print("durations:", [round(d, 2) for d in durs])
