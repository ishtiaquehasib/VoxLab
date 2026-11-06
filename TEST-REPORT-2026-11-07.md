# VoxLab Fix-First — Self-Test Report 2026-11-07

**Tester:** autonomous self-test, per user order "tumi test kore naw" (you test it).
**Scope:** re-test the fix-first work in `FIX-PROGRESS-2026-11-07.md` against the
gap report `VOICEBOX-GAP-ANALYSIS-2026-11-07.md`, on this VM only (7.7 GiB RAM,
no GPU, no mic, no display, no Windows). **NO push, NO tag, NO release.**
GitHub for VoxLab is ONLY ishtiaquehasib (ishtiaqueccr2017@gmail.com) — never
hasibtechqore. Nothing was pushed in this test.

**Machine at test time:** MemTotal 7.7 GiB; MemAvailable 4.0 GiB at session
start, falling to ~3.1 GiB during tests (Kokoro server ~1.0 GiB RSS + page
cache; `drop_caches` is read-only in this container, `posix_fadvise`
DONTNEED on 55 HF blobs did not reclaim it). This RAM pressure is itself
a finding — see Test 3.

## Verdict: NOT all-OK for release yet

**NO — do not release.** The generation pipeline and reference validation
are proven, but two release-gate items FAIL on a fresh-install-equivalent
build, and the flagship clone could not be re-proven live in this run:

1. **QC transcript + Dictate are broken by a missing package (NEW finding,
   FAIL):** `parity.transcribe()` decodes with librosa, but librosa is in
   NEITHER lab venv and is NOT in `backend/requirements.txt` or any workflow
   `--collect-all`. Every `/api/generate` in this test returned
   `x-voxlab-qc-available: false` / `qc-error: librosa not available`.
   The frozen build would ship the same gap.
2. **Qwen Base clone could not be re-proven live (BLOCKED by RAM):**
   production `_do_clone` refused both sizes honestly (1.7B guard, then
   0.6B guard: 3.1 GiB available < 4.5 GiB needed). No OOM, no crash —
   but no fresh clone audio from this run either. The prior run's clone
   artifact was re-measured (RMS −20.0, transcript words-exact) — that is
   prior evidence, not a re-proof.
3. **Chatterbox (Turbo + full) is still code-only:** the package is in NO
   lab venv, so no live Chatterbox generation was possible here.

What still needs the user's PC: first live 1.7B Base load, live Chatterbox /
Turbo clone, A/B listening vs Voicebox, live mic, system capture (WASAPI),
global hotkey/paste. 100% parity is NOT claimed.

## PASS / FAIL / BLOCKED table

| # | Path | Result | Measured evidence |
|---|------|--------|-------------------|
| 1 | audio_pipeline unit tests | **PASS** | 20/20, re-run 2026-11-07 20:37 UTC (`tmp/test_audio_pipeline.py`, venv_kokoro): chunker 2 chunks ≤800 chars, tag-safe; trim; runaway detect; RMS −30→−20.0 dBFS, peak 0.141; crossfade exact length; validation cases (below) |
| 1b | py_compile changed files | **PASS** | `server.py, parity.py, clone.py, audio_pipeline.py, qwen_base.py, qc.py, llm.py` — all OK |
| 2a | HTTP smoke: GET / + /health | **PASS** | `GET /` 200; `/health` 200 `{"status":"ok","voices":19,"parity_loaded":true}` |
| 2b | HTTP generate Kokoro, short | **PASS** | `POST /api/generate` (af_heart, "This is VoxLab…") → 200, MP3 32,661 B, 6.1 s wall; `output/last.wav` 3.93 s, peak 0.777, **RMS −20.0 dBFS** |
| 2c | HTTP generate Kokoro, long 989 chars (>800) | **PASS** | `POST /api/generate` → 200, MP3 485,877 B, 50.7 s wall; `output/last.wav` 60.41 s, peak 0.85 (peak limit respected), **RMS −20.0 dBFS** — chunked path exercised |
| 2d | Startup-status (splash steps) | **PASS** | `ready=true`, voices 19, ffmpeg ok, models 5/5 cached, output writable. Note: `bengali_edge unavailable` + `edge_tts_installed=false` in THIS venv only (see §6) |
| 2e | QC transcript (Whisper) via HTTP | **FAIL** | Both generates: `qc-available: false`, `qc-error: librosa not available: No module named 'librosa'`. Peak/RMS still measured (−20.0), transcript never produced |
| 3a | Qwen Base clone, production `_do_clone` | **BLOCKED (RAM)** | `{'ok': False, 'error': 'not enough free RAM for Qwen3-TTS 0.6B Base in float32 (3.1 GiB free, 4.5 GiB needed)', 'needs_bigger_machine': True, 'size': '0.6B'}` — wall 0.4 s. The 1.7B refusal + auto-fallback to 0.6B happened first (returned error names 0.6B), then 0.6B was also refused. No load attempted, no OOM, no crash |
| 3b | 1.7B live load | **BLOCKED (RAM)** | Not attempted by design: needs 8.5 GiB, VM has 7.7 GiB total. Weights complete in cache (4.3 GiB dir, `model.safetensors` 3,857,413,744 B, `needs_download: False`) |
| 3c | Prior clone artifact re-measured | **PASS (prior evidence)** | `output/qwen_base_clone_path.wav` (fix run, 2026-11-06 20:32): 8.72 s, peak 0.616, **RMS −20.0 dBFS**; faster-whisper small transcript (re-measured now): "Hello? This is a free voice studio running on my own computer. No account, no subscription, just open models and my own voice." — words exact |
| 3d | Qwen 0.6B direct test artifact | **PASS (prior evidence, note)** | `output/qwen_base_06b_test.wav`: 4.16 s, RMS −23.65 dBFS — NOT normalised (direct test call, bypasses `_do_clone` normalisation); production path normalises, so this is expected, not a regression |
| 4 | Reference validation (production `_validate_audio_file`) | **PASS** | 44-byte header-only WAV → rejected ("only a 44-byte WAV header, 0 audio frames"); 0.5 s clip → rejected ("at least 2.0 s"); silent 3 s clip → rejected ("peak 0"); real `kokoro_af_heart.wav` → accepted (8.128 s, peak 0.49, rms 0.076). Pipeline-level normalise also re-verified: −22.36 → −20.0 dBFS |
| 5a | Transcribe engine (faster-whisper small) | **PASS (engine only)** | Model loads in 4.6 s (venv_kokoro); `kokoro_af_heart.wav` transcript EXACT via soundfile-array decode. File-path decode fails with av `metadata_errors` (known clash) — hence the librosa decode path in `transcribe()` |
| 5b | Dictate product path (`transcribe()` / `POST /api/parity/dictate`) | **FAIL** | Route exists (`parity.py:2015`), but its engine `transcribe()` returns `available=False, error: librosa not available` in the server venv. Same root cause as 2e |
| 5c | Mic-upload / system capture / global hotkey / live mic | **NOT PROVEN** | `capture-info`: `available:false` on Linux ("pactl not installed and no monitor source found"); `live_windows_test_pending=true` for WASAPI. No mic/display on this VM — cannot be proven here |
| 5d | A/B listen vs Voicebox | **NOT PROVEN** | Needs human ears + a Voicebox sample + the user's PC. Objective half only: both engines RMS −20.0, transcripts exact |
| 5e | Chatterbox / Turbo live generate | **NOT PROVEN (code-only)** | Package in NO lab venv (`pip list` both venvs: no chatterbox). Explicit params verified in code only (Step 4): `clone.py:21-24` Chatterbox 0.5/0.5/0.8/2.0, Hebrew variant; `parity.py:1721-1726` Turbo 0.8/1000/0.95/1.2 + seed |
| 6a | Frozen gate: Kokoro bundle in workflows | **PASS** | All 3 workflows `--add-data` `kokoro-v1.0.onnx` + `voices-v1.0.bin` + `kokoro_af_heart.wav`; `requirements.txt` has `kokoro-onnx==0.6.1`, `onnxruntime==1.31.1`, `faster-whisper==1.2.1`; CI smoke now generates Kokoro audio (`linux-installer.yml:264`, `qc=0`, non-empty check) — the v1.1.5 hole is closed in the workflow |
| 6b | Frozen gate: faster-whisper / av versions | **PARTIAL** | venv_kokoro: faster-whisper 1.2.1, av 19.0.2; workflows `--collect-all av` (all 3) but av is NOT version-pinned in `requirements.txt`. File-path transcribe hits the av `metadata_errors` clash in this venv — product path avoids av via librosa, which is missing (see 2e). Frozen `av` version must be checked at the release gate |
| 6c | Frozen gate: librosa in frozen build | **FAIL** | librosa is absent from `requirements.txt` AND from all workflows (`grep` zero hits). The frozen build will therefore ship without librosa, breaking QC transcript + Dictate on first install — same as this test |
| 6d | Frozen gate: edge-tts in frozen build | **PASS (workflow)** | `edge-tts` IS in `requirements.txt` and `--collect-all edge_tts` in all workflows; CI smoke asserts `edge_tts_installed`. The `edge_tts_installed=false` in THIS test is a lab-venv gap only (venv_kokoro never installed it), not a frozen-build gap. Bengali Edge could not be tested live here |

## New findings from this test (not in FIX-PROGRESS)

1. **librosa is a missing hard dependency (release blocker).** `transcribe()`
   is the only transcription engine, and it hard-requires librosa before
   faster-whisper is even touched. Fix: add `librosa` (or a soundfile-based
   decode in `transcribe()`) to `requirements.txt` + workflows, then
   re-test QC + Dictate on a fresh-equivalent venv. Until then, every
   generate's QC transcript is unavailable and Dictate fails honestly.
2. **RAM on this VM is now the binding constraint for clone tests.**
   MemAvailable was 4.0 GiB at session start and ~3.1 GiB when the clone
   was attempted — below even the 0.6B guard (4.5 GiB). The guard works
   correctly, but it means this VM can no longer re-prove the clone path
   while a Kokoro server / page cache is warm. Rule for future runs: stop
   the server and run the clone test first, before any HTTP/Kokoro work.
3. **Whisper itself is healthy.** faster-whisper small loads in 4.6 s and
   transcribes exactly via a soundfile-array decode — the transcription
   failure is purely the missing librosa decode step, not the model.

## What remains before release

1. Add librosa (or a soundfile decode) to `requirements.txt` + workflows;
   re-test QC transcript + Dictate end-to-end (HTTP) on a fresh-equivalent venv.
2. User-PC run: 1.7B Base clone (first live load), Turbo/Chatterbox clone,
   A/B listen vs Voicebox → listening verdict. (Also live mic, system
   capture WASAPI, global hotkey/paste — all need the user's PC.)
3. Frozen-build re-verification: Kokoro bundle, faster-whisper/av versions,
   Generate + Clone on a fresh install, with the librosa fix in.
4. Then: user confirms all-OK → release via browser task signed in ONLY as
   ishtiaquehasib (ishtiaqueccr2017@gmail.com).

## Update 2026-11-07 — librosa fix + re-test (see LIBROSA-FIX-REPORT-2026-11-07.md)

- **Librosa blocker CLOSED:** decoder replaced with `backend/audio_io.py`
  (soundfile + ffmpeg fallback; librosa NOT added anywhere).
- **Re-test:** decoder 12/12 pass; pipeline 20/20; HTTP short + long
  generate both QC-available:true, match:true, RMS −20.0, transcripts
  exact; Dictate HTTP 200, Turbo, transcript exact.
- **Clone:** still NOT re-proven — BLOCKED by RAM (1.2 GiB free vs 4.5 GiB
  needed, guard worked). **Verdict stays NOT all-OK for release** until
  the user-PC run + frozen-build re-verification are done. No
  push/tag/release in the fix task.

- This report: `~/workspace/voice-studio/TEST-REPORT-2026-11-07.md`
- HTTP outputs: `tmp/gen_short.mp3` (32,661 B), `tmp/gen_long.mp3`
  (485,877 B), `tmp/gen_short_headers.txt`, `tmp/gen_long_headers.txt`
  (QC headers showing the librosa error), `tmp/test_server_20261107.log`,
  `tmp/test_server2_20261107.log`
- Clone retest log: `tmp/clone_path_retest_20261107.log` (guard refusal,
  wall 0.4 s)
- Transcribe test: `tmp/test_transcribe_20261107.py` (small model, exact
  transcripts for both files)
- Prior artifacts re-measured, not re-generated:
  `output/qwen_base_clone_path.wav`, `output/qwen_base_06b_test.wav`
- No stray processes left running (server stopped, verified 0 procs).
- No code was changed in this test; no push/tag/release.
