# Librosa Fix + Re-test — 2026-11-07

**Task:** fix the librosa release blocker from TEST-REPORT-2026-11-07.md
(verdict: NOT all-OK) and re-test. User authorized the fix with no further
permission needed; user also confirmed again that if all-OK, release it.
**This task did NOT push, tag, or release anything.** GitHub for VoxLab is
ONLY ishtiaquehasib (ishtiaqueccr2017@gmail.com) — never hasibtechqore.

## The blocker (from TEST-REPORT-2026-11-07)

`parity.transcribe()` decoded audio with librosa, but librosa is in neither
lab venv and is NOT in `backend/requirements.txt` or any installer workflow,
so every `/api/generate` returned `qc-available: false`
("librosa not available") and Dictate failed the same way. Whisper itself
was healthy — the failure was purely the decode step.

## The fix — soundfile decode, NOT librosa

**Decision: do NOT add librosa. Replace the decoder with soundfile +
ffmpeg fallback.** Reasons, tested not assumed:

- librosa was only importable in the frozen build transitively (via
  chatterbox-tts, per PARITY.md) — an accidental dependency. Adding it
  properly would pull numba/llvmlite/soxr into the frozen build for a job
  two already-shipped deps do.
- The replacement uses only hard requirements: `soundfile`
  (requirements.txt) for WAV/FLAC/OGG/AIFF, and `imageio-ffmpeg`
  (requirements.txt + `--collect-all` in all 3 workflows) for anything
  soundfile cannot read (MP3/WebM), decoded to a temp 16 kHz mono WAV.
- Resampling is numpy linear interpolation — the exact method the 2026-11-07
  self-test already proved exact with faster-whisper (soundfile-array
  bypass in `tmp/test_transcribe_20261107.py`).
- faster-whisper still receives a float32 ndarray, never a file path, so
  the av `metadata_errors` clash the librosa path was working around
  stays avoided. No model is substituted: decode only, transcription
  model + no-fallback rule unchanged.

### Files changed (local only, NOT pushed)

- **NEW `backend/audio_io.py`** — `decode_mono_16k()` / `decode_mono()` /
  `decode_native()`: soundfile first, ffmpeg fallback (imageio-ffmpeg,
  else a system ffmpeg on PATH), linear-interp resample.
- **`backend/parity.py`** — `transcribe()` now decodes via
  `audio_io.decode_mono_16k`; docstring + dictation status string updated.
  Error on decode failure is now `audio decode failed: <real reason>`.
- **`backend/qc.py`** — `measure_wav()` MP3 fallback now uses
  `audio_io.decode_native` instead of librosa.
- **`backend/global_shortcut.py`** — comment updated (librosa → audio_io).
- **`app/index.html`** — user-facing text: "via soundfile decode".
- **`backend/requirements.txt`** — comment block: librosa is DELIBERATELY
  NOT a dependency; do NOT re-add it.
- **`.github/workflows/{windows,linux,macos}-installer.yml`** —
  `--collect-all soundfile` added (1 line each, next to the other
  collect-alls). Guarantees libsndfile ships in the frozen build.
  No new package was added anywhere.

Remaining "librosa" strings in the tree are only comments/docstrings
explaining this fix — zero librosa imports remain in code (grep verified;
stale `.pyc` matches regenerate on next import).

## Clone test FIRST (before any server work, per the RAM rule)

- Server stopped, no server running. MemAvailable at test time: **1.2 GiB**
  (worse than the prior test's 3.1 GiB; `drop_caches` is read-only here,
  cannot reclaim page cache).
- Production `_do_clone`, engine `qwen-base`, ref `kokoro_af_heart.wav`,
  ref_text supplied, seed 42, venv_tada:
  `{'ok': False, 'error': 'not enough free RAM for Qwen3-TTS 0.6B Base in
  float32 (1.2 GiB free, 4.5 GiB needed)', 'engine': 'qwen-base',
  'needs_bigger_machine': True, 'size': '0.6B'}`, wall **0.3 s**.
- **Clone: NOT re-proven — BLOCKED by RAM, honestly.** The guard worked
  exactly as designed (refused both sizes, no load attempted, no OOM, no
  crash). The prior run's full clone path (8.72 s, RMS −20.0, transcript
  exact) stands as prior evidence only. 1.7B live load remains impossible
  on this VM by arithmetic (needs 8.5 GiB, VM has 7.7 GiB total).

## Re-test results (this run, measured)

### Decoder unit tests — 12/12 PASS (`tmp/test_audio_io.py`, venv_kokoro)

| Case | Result |
|---|---|
| WAV 24 kHz → 16 kHz | PASS — sr 16000, n=130048 (8.128 s), float32 |
| MP3 → 16 kHz (ffmpeg fallback) | PASS — sr 16000, n=130048, peak 0.466 |
| Stereo WAV → mono | PASS — shape (130048,), peak 0.363 = 0.75× mono peak |
| FLAC → 16 kHz | PASS — n=130048 |
| `measure_wav` on MP3 | PASS — 8.128 s, RMS −22.91 dBFS, peak −6.62 dBFS |
| `transcribe` small, WAV | PASS — 11.5 s, available=True, transcript EXACT |
| `transcribe` small, MP3 | PASS — 9.0 s, available=True, transcript EXACT |
| Missing file | PASS — plain `audio file not found` error, no crash |

Note: `imageio_ffmpeg` was missing from the lab venv (it is in
requirements.txt, so the frozen build has it). Installed 0.8.1 into
venv_kokoro for testing (68 MB, matches the shipped binary); a system
ffmpeg also exists at /usr/bin/ffmpeg, and `audio_io` falls back to it.

### Pipeline + compile — PASS

- `audio_pipeline` tests: **20/20 pass** (re-run).
- `py_compile`: OK on `audio_io, parity, qc, global_shortcut, server,
  clone, qwen_base, audio_pipeline`.
- Workflows YAML: all 3 parse OK after the `--collect-all soundfile` edit.

### HTTP end-to-end (server in venv_kokoro, `GET /` 200, `/health` 200, 19 voices)

| Test | Result |
|---|---|
| `POST /api/generate` short, Kokoro af_heart, qc=1 | **200**, 32,660 B, 17.8 s — `X-VoxLab-QC-Available: true`, `QC-Match: true`, `QC-Word-Match: 1.0`, peak −2.2 dBFS, **RMS −20.0 dBFS**, transcript EXACT |
| `POST /api/generate` long, 895 chars (>800, chunked path) | **200**, 452,252 B, 156.5 s — `QC-Available: true`, `QC-Match: true`, `QC-Word-Match: 1.0`, peak −1.41 dBFS, **RMS −20.0 dBFS**, transcript EXACT (header truncated at 500 chars by design) |
| `POST /api/parity/dictate` (kokoro_af_heart.wav upload) | **200**, 42.5 s — `available: true`, model `large-v3-turbo`, language `en`, transcript EXACT: "Hello, this is a free voice studio running on my own computer. No account, no subscription, just open models and my own voice." |
| Independent re-measure of `output/last.wav` (long output) | 56.57 s, 24 kHz, peak −1.41 dBFS, **RMS −20.0 dBFS** — matches QC headers |

Server stopped afterwards; port 8000 closed; no stray processes left running.

## Verdict

- **Librosa fixed: YES.** QC transcript + Dictate now work end-to-end on a
  librosa-free venv, through the real HTTP paths, with exact transcripts.
- **QC + Dictate pass: YES.**
- **Clone re-proven: NO — BLOCKED by RAM** (guard working, 1.2 GiB free vs
  4.5 GiB needed). Prior evidence only.
- **All-OK for release: NO — not yet.** The librosa blocker is closed, but
  the release still needs: (1) user-PC run — first live 1.7B Base load,
  Turbo/Chatterbox live clone, A/B listen vs Voicebox, live mic, system
  capture (WASAPI), global hotkey/paste; (2) frozen-build re-verification
  (Kokoro bundle, faster-whisper/av versions, Generate + Clone on a fresh
  install, with the soundfile collect-all in). Chatterbox live is still
  code-only. 100% parity is NOT claimed.
- **No push/tag/release was done in this task.** Per the user's
  confirmation, release is the next step once all-OK is reported — signed
  in ONLY as ishtiaquehasib (ishtiaqueccr2017@gmail.com).

## Evidence files

- This report: `~/workspace/voice-studio/LIBROSA-FIX-REPORT-2026-11-07.md`
- Decoder test: `tmp/test_audio_io.py` (12/12), `tmp/test_audio_pipeline.py` (20/20)
- Clone retest: `tmp/clone_retest2.py` (guard refusal, wall 0.3 s)
- HTTP outputs: `tmp/gen_short2.mp3` (32,660 B) + headers, `tmp/gen_long2.mp3`
  (452,252 B) + headers, `tmp/test_server3_20261107.log`
- Code: `backend/audio_io.py` (new), `backend/parity.py`, `backend/qc.py`,
  `backend/global_shortcut.py`, `backend/requirements.txt`,
  `app/index.html`, `.github/workflows/*.yml`
