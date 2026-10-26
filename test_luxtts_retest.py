"""LuxTTS retest: one load, several settings, transcribe each with
faster-whisper small (librosa decode). Target sentence must transcribe
exactly, otherwise the attempt is NOT exact.
Variants (one factor changed where possible):
 A baseline: steps=4, speed=1.0, t_shift=0.5, ref Kokoro 5s
 B more steps: steps=16, speed=1.0
 C slower: steps=8, speed=0.7  (generate_cpu multiplies speed by 1.3,
   so effective ~0.91; slower => longer predicted duration, so the
   prompt-length slice at the start eats less of the output)
 D slower + smooth: steps=8, speed=0.7, return_smooth=True
 E full reference: encode duration=8, steps=8, speed=0.7
"""
import sys, time
sys.path.insert(0, "/home/hatch/workspace/voice-studio/luxtts_src")
import soundfile as sf, librosa
from zipvoice.luxvoice import LuxTTS
from faster_whisper import WhisperModel

BASE = "/home/hatch/workspace/voice-studio"
TARGET = "This is VoxLab, a free voice studio running on my own computer."
REF = f"{BASE}/output/kokoro_af_heart.wav"

t0 = time.time()
lux = LuxTTS('YatharthS/LuxTTS', device='cpu', threads=2)
print(f"lux load: {time.time()-t0:.1f}s", flush=True)
wm = WhisperModel("small", device="cpu", compute_type="int8")
print(f"whisper load: {time.time()-t0:.1f}s", flush=True)

def transcribe(path):
    audio, _ = librosa.load(path, sr=16000, mono=True)
    segs, info = wm.transcribe(audio, beam_size=5)
    return "".join(s.text for s in segs).strip(), info.language

def run(name, enc, steps, speed, smooth=False):
    t = time.time()
    wav = lux.generate_speech(TARGET, enc, num_steps=steps, speed=speed,
                              return_smooth=smooth)
    wav = wav.numpy().squeeze()
    out = f"{BASE}/output/luxtts_retest_{name}.wav"
    sf.write(out, wav, 48000)
    dur = len(wav) / 48000
    txt, lang = transcribe(out)
    exact = (txt == TARGET)
    print(f"[{name}] steps={steps} speed={speed} smooth={smooth} "
          f"dur={dur:.2f}s bytes={len(open(out,'rb').read())} "
          f"gen={time.time()-t:.1f}s transcript={txt!r} lang={lang} EXACT={exact}",
          flush=True)
    return exact

enc5 = lux.encode_prompt(REF, rms=0.01, duration=5)
print("encoded ref duration=5", flush=True)
run("A_baseline", enc5, 4, 1.0)
run("B_steps16", enc5, 16, 1.0)
run("C_slow8", enc5, 8, 0.7)
run("D_slow8_smooth", enc5, 8, 0.7, smooth=True)
enc8 = lux.encode_prompt(REF, rms=0.01, duration=8)
print("encoded ref duration=8", flush=True)
run("E_fullref_slow8", enc8, 8, 0.7)
print(f"total_wall={time.time()-t0:.1f}s", flush=True)
