"""LuxTTS confirmation: does the full-reference fix hold, and is it
the reference length or the slow speed that matters?
 F1: duration=8, steps=8, speed=0.7  (repeat of exact E)
 F2: duration=8, steps=4, speed=1.0  (full ref, baseline speed/steps)
Transcribe with faster-whisper small, librosa decode.
"""
import sys, time
sys.path.insert(0, "/home/hatch/workspace/voice-studio/luxtts_src")
import soundfile as sf, librosa
from zipvoice.luxvoice import LuxTTS
from faster_whisper import WhisperModel

BASE = "/home/hatch/workspace/voice-studio"
TARGET = "This is VoxLab, a free voice studio running on my own computer."
REF = f"{BASE}/output/kokoro_af_heart.wav"
lux = LuxTTS('YatharthS/LuxTTS', device='cpu', threads=2)
wm = WhisperModel("small", device="cpu", compute_type="int8")

def run(name, enc, steps, speed):
    t = time.time()
    wav = lux.generate_speech(TARGET, enc, num_steps=steps, speed=speed).numpy().squeeze()
    out = f"{BASE}/output/luxtts_confirm_{name}.wav"
    sf.write(out, wav, 48000)
    audio, _ = librosa.load(out, sr=16000, mono=True)
    segs, info = wm.transcribe(audio, beam_size=5)
    txt = "".join(s.text for s in segs).strip()
    print(f"[{name}] steps={steps} speed={speed} dur={len(wav)/48000:.2f}s "
          f"bytes={len(open(out,'rb').read())} gen={time.time()-t:.1f}s "
          f"transcript={txt!r} EXACT={txt == TARGET}", flush=True)

enc8 = lux.encode_prompt(REF, rms=0.01, duration=8)
run("F1_repeat_E", enc8, 8, 0.7)
run("F2_fullref_baseline", enc8, 4, 1.0)
