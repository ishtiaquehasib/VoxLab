"""TADA test: official ljspeech reference + README prompt text, CPU,
float32 (no CUDA on this VM). Target sentence matches the other
VoxLab model tests. Run ONLY under venv_tada (torch 2.7.1+cpu,
transformers 4.57.6, hume-tada 0.1.8 from tada_src).
"""
import time, torch, torchaudio
from tada.modules.encoder import Encoder, EncoderOutput
from tada.modules.tada import TadaForCausalLM

BASE = "/home/hatch/workspace/voice-studio"
TARGET = "This is VoxLab, a free voice studio running on my own computer."
device = "cpu"
t0 = time.time()
encoder = Encoder.from_pretrained("HumeAI/tada-codec", subfolder="encoder").to(device)
print(f"encoder load: {time.time()-t0:.1f}s", flush=True)
model = TadaForCausalLM.from_pretrained("HumeAI/tada-1b").to(device)
print(f"model load: {time.time()-t0:.1f}s", flush=True)
encoder.eval(); model.eval()
audio, sr = torchaudio.load(f"{BASE}/tada_src/tada/samples/ljspeech.wav")
audio = audio.to(device)
prompt_text = ("The examination and testimony of the experts, enabled the "
               "commission to conclude that five shots may have been fired.")
prompt = encoder(audio, text=[prompt_text], sample_rate=sr)
print(f"encode: {time.time()-t0:.1f}s", flush=True)
t1 = time.time()
with torch.inference_mode():
    output = model.generate(prompt=prompt, text=TARGET)
print(f"generate: {time.time()-t1:.1f}s total: {time.time()-t0:.1f}s", flush=True)
wav = output.audio[0].detach().cpu()
print(f"audio shape={tuple(wav.shape)}", flush=True)
torchaudio.save(f"{BASE}/output/tada_clone.wav",
                wav.unsqueeze(0) if wav.dim() == 1 else wav, 24000)
import soundfile as sf
info = sf.info(f"{BASE}/output/tada_clone.wav")
print(f"saved output/tada_clone.wav seconds={info.duration:.2f} sr={info.samplerate}")
