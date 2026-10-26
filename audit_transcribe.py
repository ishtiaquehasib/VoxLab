from faster_whisper import WhisperModel
import librosa
m = WhisperModel("small", device="cpu", compute_type="int8")
for name in ["kokoro_af_heart","chatterbox_clone","qwen3_clone"]:
    y, sr = librosa.load(f"/home/hatch/workspace/voice-studio/output/{name}.mp3", sr=16000, mono=True)
    segs, info = m.transcribe(y, language="en", beam_size=5)
    text = " ".join(s.text.strip() for s in segs)
    print(f"{name}: {text}")
