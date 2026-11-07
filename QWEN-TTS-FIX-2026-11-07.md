# VoxLab v1.1.11 — CustomVoice clone fix (qwen-tts bundling)

Date: 2026-11-07. Status: fix staged locally, NOT pushed, NOT released.
Release: v1.1.11 (test build / Pre-release, same as v1.1.6–v1.1.10).

## The error (user's PC, Clone page, v1.1.10)

```json
{"ok": false, "model": "qwen-customvoice", "error": "No module named 'qwen_tts'"}
```

plus the page line "Pick an audio file first (the mic file above)."

## Cause (verified, not assumed)

The Qwen CustomVoice engine (`backend/parity.py:1877`
`generate_customvoice`, engine `qwen-customvoice`, repos
`Qwen/Qwen3-TTS-12Hz-*-CustomVoice`) and the Qwen Base clone
(`backend/qwen_base.py:105`) both do a lazy
`from qwen_tts import Qwen3TTSModel` — but the `qwen-tts` package
was installed NOWHERE: not in `backend/requirements.txt`, not in
any workflow install step, not in any `--collect-all`. The frozen
build therefore shipped without it, and the first CustomVoice clone
on a fresh install failed with the exact error above. The CI smoke
test never exercised any clone engine, and the "Verify server
dependencies installed" step never checked qwen_tts — so the gap
shipped silently (same silent-drop class as the v1.1.7 espeak-ng
failure and the 2026-10-27 faster-whisper failure).

## Why a plain `pip install qwen-tts` is impossible (measured)

* qwen-tts 0.1.1 (latest on PyPI; all versions pin the same deps)
  pins `transformers==4.57.3`.
* chatterbox-tts 0.1.7 (pinned in requirements.txt, the other clone
  engine in the same frozen build) pins `transformers==5.2.0` and
  `torch==2.6.0`. chatterbox-tts latest on PyPI is 0.1.7 — no newer
  release exists.
* No single environment can satisfy both pins. This was verified
  from PyPI metadata, not guessed.
* A `--no-deps` install was PROVEN to fail at import on
  transformers 5.2.0 (scratch venv, torch 2.6.0 + transformers
  5.2.0): `ImportError: cannot import name 'check_model_inputs'
  from 'transformers.utils.generic'`. That was the ONLY missing
  name — all 13 other transformers internals qwen-tts needs exist
  in 5.2.0.
* qwen-tts also imports librosa at module level in 5 places; librosa
  was deliberately removed from VoxLab (numba/llvmlite/soxr bloat —
  see LIBROSA-FIX-2026-11-07.md), so vendoring alone is not enough.
* The old "qwen-tts needs torch>=2.9.1" claim in parity.py comments
  was NOT the operative blocker: the lab env runs qwen-tts on torch
  2.7.1, and the v1.1.11 import test (below) passes on torch 2.6.0.
  The stale claim has been corrected in parity.py (VoiceDesign
  comment, PARITY_MODELS status, and the `torch_conflict` response
  field).

## Fix: vendor qwen-tts 0.1.1 (Apache-2.0) with 3 substitutions

New directory `qwen_tts/` at repo root (wheel unpacked, 17 .py
files, plus `LICENSE` and `VENDORED.md` with the full rationale and
rules). All patches are marked `VOXLAB PATCH` and live in one new
module, `qwen_tts/_voxlab_compat.py`:

1. `check_model_inputs` — minimal re-implementation of the
   transformers 4.57 decorator (use_cache / return_dict
   normalisation; the 4.57 output-capture hook machinery is omitted
   — Qwen TTS inference never requests those outputs).
2. `librosa.load` / `librosa.resample` — soundfile decode +
   torchaudio sinc resample (both already hard VoxLab deps).
   Note: the linear-interp resample in `backend/audio_io.py` was
   NOT reused here — resample quality feeds the speaker embedding
   directly.
3. `librosa.filters.mel` — Slaney mel filterbank in pure numpy.

`sox` (pysox, pure Python, no binary needed for import) is still
imported by the 25Hz VQ module — it is now listed in
`backend/requirements.txt` as `sox==1.5.0` (its only deps are
numpy>=1.9.0 + typing-extensions, both compatible with the pinned
set). qwen-tts itself and librosa are DELIBERATELY NOT in
requirements.txt — do not re-add them.

## Files changed (8 paths)

| File | Change |
|---|---|
| `qwen_tts/` (new) | Vendored qwen-tts 0.1.1 + `_voxlab_compat.py` + `LICENSE` + `VENDORED.md` |
| `backend/parity.py` | Repo root (`BASE`) inserted on `sys.path` at module level; stale torch-conflict claim corrected in 3 places (VoiceDesign comment, PARITY_MODELS status, `torch_conflict` field) |
| `backend/qwen_base.py` | Repo root (`BASE`) inserted on `sys.path`; error text no longer says "pip install qwen-tts" — it now points at the vendored package |
| `backend/requirements.txt` | `sox==1.5.0` added with a comment forbidding qwen-tts/librosa re-adds |
| `.github/workflows/{windows,linux,macos}-installer.yml` | `--collect-all qwen_tts` + `--collect-all chatterbox` in PyInstaller; `import qwen_tts` / `import sox` / `import chatterbox` checks in the Verify step; new "Verify qwen_tts bundled" step asserting `qwen_tts/__init__.py` AND `core/tokenizer_25hz/vq/assets/mel_filters.npz` exist in `dist/` before smoke |
| `app/index.html` | `cloneAndTranscribe()`: when no file is picked, it now tries the Record page's uploaded `mic_recording.webm` via `/api/parity/audio/` before showing "Pick an audio file first" (the second half of the user's screenshot) |

## Verification (measured on this VM, 2026-11-07)

* **Mel filterbank numerically identical to librosa**: 5 cases
  incl. the exact model params (sr 24000, n_fft 1024, n_mels 128,
  fmin 0, fmax 12000) — max abs diff **0.0** in every case.
  (Two bugs found and fixed during this check: NumPy 2 turns 0-d
  array arithmetic into scalars, and `np.linspace` with 1-element
  array endpoints changes shape.)
* **Vendored package imports under transformers 5.2.0 +
  torch 2.6.0 with librosa UNINSTALLED** (scratch venv, pip
  qwen-tts + librosa removed): `from qwen_tts import Qwen3TTSModel,
  Qwen3TTSTokenizer` — IMPORT OK, `__file__` confirmed as the
  vendored copy. This settles the torch-2.6.0 question at import
  level.
* **Load/resample shims work on a real wav**: 24 kHz ref →
  16 kHz → 24 kHz round-trips to exactly the original sample count
  (99840), peak 0.4834.
* **`PyInstaller.collect_all('qwen_tts')` from the repo root**
  (venv with numpy/torch/transformers, like CI): 21 datas entries
  INCLUDING `mel_filters.npz`, 8 hiddenimports including
  `qwen_tts._voxlab_compat`. The `--collect-all qwen_tts`
  mechanism is proven to find the vendored package and its data
  file. (A minimal venv without numpy warns on submodule
  collection — irrelevant for CI, which has all deps.)
* **`importlib.util.find_spec("qwen_tts")` works from another CWD**
  with the repo root on sys.path (the mechanism parity.py /
  qwen_base.py now use).
* **py_compile OK** on all 8 changed .py files; **node --check OK**
  on the extracted `cloneAndTranscribe()`; **all 3 workflows
  YAML-parse OK**; **sox==1.5.0 dry-run OK** (already satisfied in
  the scratch venv; deps compatible with the pinned set).
* **No librosa imports remain** in the vendored package (only
  comments and the kept `librosa_mel_fn` alias name); **no stale
  "pip install qwen-tts" advice remains** in backend/ or app/.

## NOT proven on this VM (honest limits)

* **Live 0.6B CustomVoice generate — NOT proven.** Needs 4.5 GiB
  free; the VM had ~0.6 GiB available at test time. Same RAM
  arithmetic that blocks the 1.7B live load. The import + mel +
  resample proofs above are the strongest evidence available here;
  the live generate is a user-PC step.
* **Live 0.6B Base clone via qwen_base.py — NOT proven** (same RAM
  block; the production guard would refuse honestly).
* **Full PyInstaller frozen build — NOT run here** (analysis of
  the torch/transformers tree needs far more RAM than available).
  CI is the proof gate, and the new "Verify qwen_tts bundled" step
  fails the job loudly if collection breaks — a silent broken ship
  is no longer possible.
* **Chatterbox Turbo live in the frozen build — still UNPROVEN**
  (same as before; now explicitly collected + import-checked).

## Other clone engines (same-gap audit, 2026-11-07)

| Engine | Bundled? | Evidence |
|---|---|---|
| Qwen CustomVoice (qwen-customvoice) | **YES, from v1.1.11** (vendored) | This fix |
| Qwen Base (qwen-base) | **YES, from v1.1.11** (same vendored package) | Same import path; 1.7B live load still needs the user's PC (8.5 GiB) |
| Chatterbox Turbo | **Installed in CI, now explicitly collected** | chatterbox-tts==0.1.7 in requirements.txt; lazy import in parity.py:1727; `--collect-all chatterbox` added to all 3 workflows + import check; live frozen generate still unproven |
| LuxTTS | **NO — by design, honestly reported** | `luxtts_src/` gitignored (.gitignore:14); endpoint 503s with "not bundled in this install"; Models page now says "Not usable on this install" |
| TADA 1B | **NO — by design, honestly reported** | `tada_src/` gitignored (.gitignore:15); endpoint 503s the same way; same Models-page note |

## Browser-upload + tag steps (for the parent)

Staging is ready at `~/workspace/voice-studio-release-1.1.11/`
(fresh clone of ishtiaquehasib/VoxLab main, local commit as
Ishtiaque Hasib <ishtiaqueccr2017@gmail.com>, local tag `v1.1.11`,
NOT pushed). Upload via the browser task signed in ONLY as
ishtiaquehasib (never hasibtechqore), same as v1.1.6–v1.1.10:

1. Web-upload the changed files (8 paths above; `qwen_tts/` is a
   new directory — upload its contents preserving paths) to main.
2. Create tag `v1.1.11` (Pre-release) targeting the new commit.
3. Watch CI: Windows + Linux installers must succeed; the new
   "Verify qwen_tts bundled" step must print
   "qwen_tts bundled: package + mel_filters.npz present".
   macOS is expected to stay queued on its pre-existing
   runner-config error ("macos-14-arm64-us-default is not
   supported") — not blocking Windows.
4. Give the user ONLY the v1.1.11 Windows installer link
   (`VoxLab-Setup-1.1.11-x64.exe`) once CI succeeds — do NOT
   offer v1.1.10 any more. Remind him: close old VoxLab fully
   before installing (file-lock error, same as v1.1.10).
5. User-PC test after install: Clone page → Chatterbox Turbo or
   Qwen CustomVoice (Ryan) → the qwen-tts error must be GONE;
   Clone + Transcribe with no file picked must now use his uploaded
   mic recording; then Qwen 1.7B Base clone once its download
   finishes, and the A/B listen vs Voicebox.

## What remains after v1.1.11

* User-PC live proofs: 0.6B CustomVoice generate, 1.7B Base clone,
  Turbo live, A/B listen, WASAPI capture, hotkey.
* LuxTTS/TADA vendoring is a separate, unplanned job (source dirs
  are gitignored test copies, not in the repo).
* Then the release gate: release only after all-OK (user's 02:07 /
  02:52 authorisation). Do NOT release before all-OK.
