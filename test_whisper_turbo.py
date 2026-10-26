"""Whisper Turbo test: faster-whisper 'large-v3-turbo' on the Kokoro sample.
Decodes with librosa first (av metadata_errors workaround, see AUDIT.md).
"""
import time, librosa
from faster_whisper import WhisperModel

t0 = time.time()
model = WhisperModel("large-v3-turbo", device="cpu", compute_type="int8")
print(f"model load: {time.time()-t0:.1f}s")
audio, _ = librosa.load("/home/hatch/workspace/voice-studio/output/kokoro_af_heart.wav", sr=16000, mono=True)
t1 = time.time()
segments, info = model.transcribe(audio, beam_size=5)
text = "".join(s.text for s in segments)
print(f"transcript: {text!r}")
print(f"language: {info.language} duration: {info.duration:.2f}s transcribe_wall: {time.time()-t1:.1f}s total_wall: {time.time()-t0:.1f}s")
