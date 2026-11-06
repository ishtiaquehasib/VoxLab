"""Audio decoding without librosa (2026-11-07 librosa-fix).

VoxLab's only uses of librosa were decoding an audio file to a mono
float32 ndarray: parity.transcribe() (16 kHz for faster-whisper) and
qc.measure_wav() (native rate, MP3 fallback). librosa is NOT a declared
dependency — it is absent from backend/requirements.txt and from every
installer workflow, and it was only importable in the frozen build
transitively (via chatterbox-tts). A missing transitive import broke QC
transcripts and Dictate on a fresh-equivalent venv (TEST-REPORT-2026-11-07:
every /api/generate returned qc-available:false, "librosa not available").

The replacement uses only deps that are already hard requirements:
- soundfile (requirements.txt) for WAV/FLAC/OGG/AIFF — every format
  VoxLab itself writes (Kokoro/Qwen outputs, captures, mic uploads).
- imageio-ffmpeg (requirements.txt + --collect-all in all 3 workflows)
  for anything soundfile cannot read (MP3/WebM), decoded to a temp
  16 kHz mono WAV and read back with soundfile.
Resampling is plain numpy linear interpolation — the same method the
2026-11-07 self-test proved exact with faster-whisper (soundfile-array
bypass in tmp/test_transcribe_20261107.py: 24 kHz -> 16 kHz, transcripts
exact on both test files).

faster-whisper still receives a float32 ndarray, never a file path, so
the av `metadata_errors` clash the librosa path was working around
stays avoided. No model is substituted anywhere here: this is only a
decoder swap; the transcription model and the no-fallback rule are
unchanged (see parity.transcribe).
"""
import os
import subprocess
import tempfile

import numpy as np


def _resample_linear(arr, src_sr, target_sr):
    """Linear-interpolation resample of a mono float array. Exact enough
    for Whisper input (proven by the 2026-11-07 self-test bypass); no
    scipy/librosa dependency."""
    if src_sr == target_sr or arr.size == 0:
        return np.asarray(arr, dtype=np.float32)
    n_out = int(round(arr.size * target_sr / src_sr))
    if n_out <= 0:
        return np.zeros(0, dtype=np.float32)
    x = np.linspace(0, arr.size - 1, n_out)
    return np.interp(x, np.arange(arr.size), arr).astype(np.float32)


def _to_mono(arr):
    a = np.asarray(arr, dtype=np.float64)
    if a.ndim == 2:
        a = a.mean(axis=1)
    return a.squeeze()


def _decode_with_ffmpeg(path, target_sr):
    """Decode any ffmpeg-readable file to a temp WAV, then soundfile-read
    it. Only used when soundfile cannot read the file (e.g. MP3/WebM)."""
    import soundfile as sf
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        exe = None
    if not exe or not os.path.exists(exe):
        # Last resort: a system ffmpeg on PATH (dev machines; the frozen
        # build always has the imageio-ffmpeg binary collected).
        import shutil
        exe = shutil.which("ffmpeg")
    if not exe or not os.path.exists(exe):
        raise RuntimeError("ffmpeg not available for audio decode: "
                           "neither imageio-ffmpeg nor a system ffmpeg found")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    tmp.close()
    try:
        cmd = [exe, "-v", "error", "-y", "-i", path, "-ac", "1"]
        if target_sr:
            cmd += ["-ar", str(int(target_sr))]
        cmd += ["-f", "wav", tmp.name]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0 or not os.path.exists(tmp.name) \
                or os.path.getsize(tmp.name) == 0:
            raise RuntimeError(
                f"ffmpeg decode failed: {proc.stderr.strip() or 'no output'}")
        audio, sr = sf.read(tmp.name, always_2d=False)
        return _to_mono(audio), int(sr)
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def decode_mono(path, target_sr=16000):
    """Decode an audio file to mono float32 at target_sr (default 16 kHz,
    the rate faster-whisper expects). Returns (samples, sample_rate).
    Raises RuntimeError/ValueError with a plain message on failure."""
    if not path or not os.path.isfile(path):
        raise ValueError(f"audio file not found: {path}")
    try:
        import soundfile as sf
        audio, sr = sf.read(path, always_2d=False)
    except Exception:
        # soundfile cannot read this container (MP3/WebM/...): ffmpeg.
        audio, sr = _decode_with_ffmpeg(path, target_sr)
        return _resample_linear(_to_mono(audio), sr, target_sr), int(target_sr)
    mono = _to_mono(audio)
    if target_sr:
        return _resample_linear(mono, int(sr), int(target_sr)), int(target_sr)
    return mono.astype(np.float32), int(sr)


def decode_mono_16k(path):
    """Decode to 16 kHz mono float32 — the faster-whisper input format."""
    samples, _sr = decode_mono(path, target_sr=16000)
    return samples


def decode_native(path):
    """Decode to mono float32 at the file's native sample rate (for
    qc.measure_wav peak/RMS measurement). Returns (samples, sr)."""
    samples, sr = decode_mono(path, target_sr=None)
    return samples, sr
