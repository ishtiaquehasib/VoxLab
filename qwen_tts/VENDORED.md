# Vendored qwen-tts 0.1.1 — VoxLab notice (2026-11-07, v1.1.11)

## What this is

A vendored copy of the `qwen-tts` 0.1.1 PyPI package (Apache-2.0,
LICENSE file in this directory, copyright Alibaba Qwen team), with
VoxLab patches applied. The stock package cannot be pip-installed
into VoxLab's frozen environment:

* stock qwen-tts pins `transformers==4.57.3`; chatterbox-tts 0.1.7
  (the other clone engine in the same frozen build) pins
  `transformers==5.2.0` — no resolver can satisfy both in one env
  (verified from PyPI metadata; chatterbox-tts latest is 0.1.7).
* stock qwen-tts imports librosa at module level; librosa was
  deliberately removed from VoxLab (numba/llvmlite/soxr bloat —
  see LIBROSA-FIX-2026-11-07.md).
* a `--no-deps` install was PROVEN to fail at import on
  transformers 5.2.0 (`ImportError: cannot import name
  'check_model_inputs' from 'transformers.utils.generic'`).

## VoxLab patches (all in `_voxlab_compat.py` + one-line import swaps)

1. `check_model_inputs` — transformers 5.x removed it; the compat
   module provides a minimal equivalent (use_cache / return_dict
   normalization only; the 4.57 output-capture hook machinery is
   omitted — Qwen TTS inference never requests those outputs).
2. `librosa.load` / `librosa.resample` — soundfile decode +
   torchaudio sinc resample (both already hard VoxLab deps).
3. `librosa.filters.mel` — Slaney mel filterbank in pure numpy,
   validated numerically against real librosa (see
   QWEN-TTS-FIX-2026-11-07.md).
4. `sox` (pysox, pure Python) is still imported by the 25Hz VQ
   module — it is listed in backend/requirements.txt. No SoX
   binary is needed (import only; no transform is executed).

## Layout — do NOT swap the two `__init__.py` files (v1.1.11/v1.1.12 CI)

The vendored package has TWO different `__init__.py` files with the
same filename and similar sizes — and the v1.1.11 browser web-upload
swapped them, which killed v1.1.11 AND v1.1.12 CI on both platforms:

* `qwen_tts/core/__init__.py` (~990 B) — TOKENIZER exports only:
  `Qwen3TTSTokenizerV1Config/Model` (25Hz) and
  `Qwen3TTSTokenizerV2Config/Model` (12Hz).
* `qwen_tts/core/models/__init__.py` (~807 B) — CONFIG / MODEL /
  PROCESSOR exports only: `Qwen3TTSConfig`,
  `Qwen3TTSForConditionalGeneration`, `Qwen3TTSProcessor`.
* The gradio demo lives at `qwen_tts/cli/demo.py` — NEVER at
  `qwen_tts/demo.py` (the same upload also misplaced it there).

With the files swapped, `import qwen_tts` fails with
`ModuleNotFoundError: No module named
'qwen_tts.core.configuration_qwen3_tts'` (raised from
`core/__init__.py` line 16). The local staging was correct, so the
lab import check passed — the swap was only visible in CI. Both
files now carry a header comment naming their own path and role, and
all three installer workflows run a "Verify qwen_tts layout"
upload-swap guard BEFORE the import check, which fails with a
readable LAYOUT ERROR if the files are ever swapped or demo.py is
misplaced again. When re-uploading, verify byte sizes AND the first
import line of each file against this section.

## Rules

* Do NOT `pip install qwen-tts` or re-add it to requirements.txt —
  that re-breaks the resolver (see above).
* Do NOT re-add librosa — the vendored code no longer needs it.
* When upstream qwen-tts releases a version supporting
  transformers 5.x, re-check whether vendoring can be dropped.
* The upstream sources are unchanged apart from the import swaps
  listed above; every patched line is marked `VOXLAB PATCH`.
