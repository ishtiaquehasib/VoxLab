"""VoxLab compatibility shims for the vendored qwen-tts 0.1.1 package.

Why this file exists (2026-11-07, v1.1.11):
  The stock qwen-tts 0.1.1 cannot run in VoxLab's frozen environment:
  * it pins transformers==4.57.3, while chatterbox-tts 0.1.7 (the other
    clone engine in the same frozen build) pins transformers==5.2.0 —
    no pip resolver can satisfy both in one environment (verified from
    PyPI metadata; chatterbox-tts latest is 0.1.7, no newer release);
  * it imports librosa at module level, and librosa was deliberately
    removed from VoxLab (it pulls numba/llvmlite/soxr into the frozen
    build for a job soundfile already does — see LIBROSA-FIX report).
  A full `pip install qwen-tts` is therefore impossible here, and a
  `--no-deps` install was PROVEN to fail at import time on
  transformers 5.2.0: `ImportError: cannot import name
  'check_model_inputs' from 'transformers.utils.generic'`
  (measured 2026-11-07 in a scratch venv with torch 2.6.0 +
  transformers 5.2.0 — that was the ONLY missing name; every other
  transformers internal qwen-tts needs exists in 5.2.0).

  So qwen-tts is vendored (Apache-2.0, see LICENSE) with exactly
  three substitutions, all in this module:
  1. check_model_inputs — minimal re-implementation of the
     transformers 4.57 decorator (see docstring).
  2. librosa.load / librosa.resample — soundfile decode +
     torchaudio sinc resample (both already hard VoxLab deps).
  3. librosa.filters.mel — a Slaney mel filterbank in pure numpy,
     validated numerically against librosa.filters.mel (see
     QWEN-TTS-FIX-2026-11-07.md for the measured max abs diff).

  Do NOT "fix" this by re-adding qwen-tts or librosa to
  requirements.txt — that re-breaks the resolver (see above).
"""

import functools

import numpy as np


# ---------------------------------------------------------------------------
# 1. check_model_inputs (transformers 4.57 -> 5.x shim)
# ---------------------------------------------------------------------------
def check_model_inputs(func=None, *, tie_last_hidden_states=True):
    """Minimal equivalent of transformers 4.57's decorator.

    transformers 5.x removed ``check_model_inputs`` entirely. The
    full 4.57 implementation also wires output-capture hooks
    (output_attentions / hidden_states recording via
    _CAN_RECORD_REGISTRY); this shim deliberately omits that
    machinery: Qwen TTS inference never requests those outputs, and
    the decorated forward (Qwen3TTSTokenizerV2Model.forward) accepts
    **kwargs, so a requested recordable kwarg is ignored rather than
    captured. What the shim DOES preserve, exactly as 4.57:
    use_cache defaulted from the model config, return_dict defaulted
    from the config, and return_dict=False converting the output to
    a tuple.
    """
    def wrapped_fn(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            use_cache = kwargs.get("use_cache", None)
            if use_cache is None:
                use_cache = getattr(self.config, "use_cache", None)
            if use_cache is not None:
                if getattr(self, "gradient_checkpointing", False) and self.training and use_cache:
                    use_cache = False
                kwargs["use_cache"] = use_cache

            return_dict = kwargs.pop("return_dict", None)
            if return_dict is None:
                return_dict = getattr(self.config, "return_dict", True)

            outputs = func(self, *args, **kwargs)
            if return_dict is False:
                outputs = outputs.to_tuple()
            return outputs

        return wrapper

    if func is not None:
        return wrapped_fn(func)
    return wrapped_fn


# ---------------------------------------------------------------------------
# 2. Audio load / resample (replaces librosa.load / librosa.resample)
# ---------------------------------------------------------------------------
def resample_audio(y, orig_sr, target_sr):
    """Resample float32 mono audio with torchaudio's sinc resampler.

    librosa.resample defaults to soxr_hq (high-quality sinc); the
    linear-interp resample in backend/audio_io.py is NOT used here
    because the Qwen tokenizer encodes the reference audio — resample
    quality feeds the speaker embedding directly. torchaudio is
    already a hard VoxLab dependency (torch 2.6.0).
    """
    y = np.asarray(y, dtype=np.float32)
    orig_sr = int(orig_sr)
    target_sr = int(target_sr)
    if orig_sr == target_sr:
        return y
    import torch
    import torchaudio

    wav = torch.from_numpy(y).unsqueeze(0)
    out = torchaudio.transforms.Resample(orig_freq=orig_sr, new_freq=target_sr)(wav)
    return out.squeeze(0).numpy().astype(np.float32)


def load_audio_native(path):
    """Load an audio file as float32 mono at its NATIVE sample rate.

    Replaces ``librosa.load(path, sr=None, mono=True)`` where the
    caller resamples downstream itself (qwen3_tts_model
    _load_audio_to_np). Returns (audio, sr).
    """
    import soundfile as sf

    audio, sr = sf.read(path, dtype="float32", always_2d=False)
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim > 1:
        audio = np.mean(audio, axis=-1)
    return audio.astype(np.float32), int(sr)


def load_audio(path, target_sr):
    """Load an audio file as float32 mono at target_sr.

    Replaces ``librosa.load(path, sr=None, mono=True)`` + the
    ``librosa.resample`` that followed it. soundfile handles
    WAV/FLAC/OGG/AIFF; MP3/WebM go through the same file the
    tokenizer already used soundfile for (URL/base64 branches).
    Raises a plain error (not a librosa ImportError) on failure.
    """
    import soundfile as sf

    audio, sr = sf.read(path, dtype="float32", always_2d=False)
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim > 1:
        audio = np.mean(audio, axis=-1)
    if int(sr) != int(target_sr):
        audio = resample_audio(audio, int(sr), int(target_sr))
    return audio.astype(np.float32), int(target_sr)


# ---------------------------------------------------------------------------
# 3. Mel filterbank (replaces librosa.filters.mel)
# ---------------------------------------------------------------------------
def _hz_to_mel(frequencies, htk=False):
    # np.atleast_1d: NumPy 2 turns 0-d array arithmetic into scalars,
    # which do not support item assignment below.
    frequencies = np.atleast_1d(np.asanyarray(frequencies, dtype=np.float64))
    if htk:
        return 2595.0 * np.log10(1.0 + frequencies / 700.0)
    f_min = 0.0
    f_sp = 200.0 / 3
    mels = (frequencies - f_min) / f_sp
    min_log_hz = 1000.0
    min_log_mel = (min_log_hz - f_min) / f_sp
    logstep = np.log(6.4) / 27.0
    log_t = frequencies >= min_log_hz
    mels = mels.copy()
    mels[log_t] = min_log_mel + np.log(frequencies[log_t] / min_log_hz) / logstep
    return mels


def _mel_to_hz(mels, htk=False):
    mels = np.atleast_1d(np.asanyarray(mels, dtype=np.float64))
    if htk:
        return 700.0 * (10.0 ** (mels / 2595.0) - 1.0)
    f_min = 0.0
    f_sp = 200.0 / 3
    freqs = mels * f_sp + f_min
    min_log_hz = 1000.0
    min_log_mel = (min_log_hz - f_min) / f_sp
    logstep = np.log(6.4) / 27.0
    log_t = mels >= min_log_mel
    freqs = freqs.copy()
    freqs[log_t] = min_log_hz * np.exp(logstep * (mels[log_t] - min_log_mel))
    return freqs


def mel_filterbank(sr, n_fft, n_mels=128, fmin=0.0, fmax=None, htk=False,
                   norm="slaney", dtype=np.float32):
    """Slaney mel filterbank, numerically matching librosa.filters.mel.

    Same signature and defaults as librosa.filters.mel (norm="slaney").
    The vendored qwen-tts calls it with (sr=24000, n_fft=1024,
    n_mels=128, fmin=0, fmax=12000) for the speaker-embedding mel
    spectrogram, and with the 25Hz VQ encoder's own params. Validated
    against real librosa.filters.mel — see QWEN-TTS-FIX-2026-11-07.md.
    """
    if fmax is None:
        fmax = float(sr) / 2
    n_mels = int(n_mels)
    weights = np.zeros((n_mels, int(1 + n_fft // 2)), dtype=dtype)
    fftfreqs = np.linspace(0, float(sr) / 2, int(1 + n_fft // 2), endpoint=True)
    mel_f = _mel_to_hz(np.linspace(float(_hz_to_mel(fmin)), float(_hz_to_mel(fmax)), n_mels + 2))
    fdiff = np.diff(mel_f)
    ramps = np.subtract.outer(mel_f, fftfreqs)
    for i in range(n_mels):
        lower = -ramps[i] / fdiff[i]
        upper = ramps[i + 2] / fdiff[i + 1]
        weights[i] = np.maximum(0, np.minimum(lower, upper))
    if norm == "slaney":
        enorm = 2.0 / (mel_f[2:n_mels + 2] - mel_f[:n_mels])
        weights *= enorm[:, np.newaxis]
    return weights
