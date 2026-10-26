"""VoxLab shared compute-device helper (2026-10-27, GPU support).

Previously every engine hardcoded CPU (Parler ``.to("cpu")``,
Chatterbox ``device="cpu"``, Qwen3 ``device_map="cpu"``, Whisper
``device="cpu"`). That made VoxLab CPU-only even on a machine with a
GPU, unlike Voicebox, which uses Metal / CUDA / ROCm / DirectML.

Detection order (``auto``, the default):
    CUDA (torch.cuda — covers NVIDIA CUDA and, on Linux, ROCm builds)
    -> Apple MPS (torch.backends.mps — Metal)
    -> DirectML (torch-directml — Windows only, AMD/Intel GPUs)
    -> CPU

Env override: ``VOXLAB_DEVICE`` may be ``auto``, ``cuda``, ``mps``,
``dml`` or ``cpu``. An explicitly requested accelerator that is not
available falls back to CPU with a warning instead of crashing —
the override is a preference, not a guarantee.

DirectML, optional Windows-only install (NOT in requirements.txt,
so Linux/macOS installs are unaffected):
    pip install torch-directml
If the package is not installed, DirectML is honestly reported as
unavailable and the helper returns CPU — it never crashes and never
claims GPU acceleration it cannot use.

Honest limits, do NOT over-claim:
- DirectML paths are UNTESTED on a real Windows GPU: this VM has
  no GPU and no torch-directml, so live tests here prove only
  that detection degrades to CPU with a warning, not that DML
  accelerates a model.
- faster-whisper / CTranslate2 has no MPS backend, so Whisper always
  uses CUDA (float16) or CPU (int8) — see ``whisper_device()``.
  MPS only accelerates the torch engines (Parler, Chatterbox, Qwen3).
- GPU paths are UNTESTED on a real GPU: this VM has no GPU, so all
  live tests here prove only the CPU path. GPU behaviour is code
  review + torch's standard availability checks, not a tested run.
- On out-of-memory, callers retry once on CPU via
  ``is_oom_error()`` — never invent audio/transcripts on failure.
"""

import os
import warnings

_VALID = ("auto", "cuda", "mps", "dml", "cpu")
_cache = None


def _torch_available():
    try:
        import torch  # noqa: F401
        return True
    except Exception:
        return False


def _directml_available():
    """True only if torch-directml imports and yields a device.

    Windows-only optional package; on any machine without it this
    returns False quickly instead of raising.
    """
    try:
        import torch_directml
        torch_directml.device()  # raises if no DML device exists
        return True
    except Exception:
        return False


def detect_device():
    """Return 'cuda', 'mps', 'dml' or 'cpu' from availability checks."""
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    if _directml_available():
        return "dml"
    return "cpu"


def get_device():
    """Cached detected device, honouring VOXLAB_DEVICE override."""
    global _cache
    if _cache is not None:
        return _cache
    requested = os.environ.get("VOXLAB_DEVICE", "auto").strip().lower()
    if requested not in _VALID:
        warnings.warn(f"VOXLAB_DEVICE={requested!r} invalid, using auto")
        requested = "auto"
    if requested == "auto":
        _cache = detect_device()
    elif requested == "cpu":
        _cache = "cpu"
    else:
        detected = detect_device()
        if detected == requested:
            _cache = requested
        else:
            warnings.warn(
                f"VOXLAB_DEVICE={requested} requested but not available "
                f"(detected {detected}), falling back to cpu")
            _cache = "cpu"
    return _cache


def resolve_device(requested=None):
    """Resolve an explicit caller device (or None = auto) to cuda/mps/cpu."""
    if requested is None:
        return get_device()
    requested = str(requested).strip().lower()
    if requested in ("cuda", "mps", "dml", "cpu"):
        # Reuse the availability check so an explicit cuda on a
        # CPU-only machine still falls back instead of crashing.
        if requested == "cpu":
            return "cpu"
        return requested if detect_device() == requested else "cpu"
    return get_device()


def is_gpu(device=None):
    return (device or get_device()) in ("cuda", "mps", "dml")


def is_oom_error(exc):
    """True for torch CUDA OOM (and generic 'out of memory' failures)."""
    try:
        import torch
        if isinstance(exc, torch.cuda.OutOfMemoryError):
            return True
    except Exception:
        pass
    return "out of memory" in str(exc).lower()


def whisper_device():
    """(device, compute_type) for faster-whisper / CTranslate2.

    CTranslate2 has no MPS or DirectML backend, so MPS/DML machines
    use CPU int8 — the same path already proven on this VM.
    CUDA uses float16.
    """
    device = get_device()
    if device == "cuda":
        return "cuda", "float16"
    return "cpu", "int8"
