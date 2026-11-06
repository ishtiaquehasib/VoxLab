# VoxLab Fix-First — Progress Report 2026-11-07

**User orders driving this session:** "as fast as you can" + "do NOT ask him again and again — do whatever gives the best / 100% output". Work done autonomously, local only. **NO push, NO tag, NO release.** GitHub for VoxLab is ONLY ishtiaquehasib (ishtiaqueccr2017@gmail.com) via Secure Vault — never hasibtechqore.

**Gap report:** `VOICEBOX-GAP-ANALYSIS-2026-11-07.md` (§11 fix order). Full evidence also in `PARITY.md` (Fix-First section + updates).

## What is DONE (with evidence)

### Step 1 — Frozen-gate Layer A: VERIFIED
- Workflows + `requirements.txt` already bundle Kokoro ONNX + voices + reference wav, `kokoro-onnx`/`onnxruntime`/`faster-whisper`, with CI smoke. Re-proven live: Kokoro ONNX Heart, 3.499 s / 167,980 B, 7.4 s wall.
- **Bug found + fixed:** `server.py` referenced `_kp_exc` after its `except` block deleted it (PEP 3110) — masked real ONNX errors. Now captured as `_kp_error`.

### Step 2 — Qwen3-TTS 1.7B Base flagship clone: WIRED + 0.6B PROVEN LIVE
- New `backend/qwen_base.py`: `create_voice_prompt` (ref audio + ref_text, cached) → `generate_voice_clone(instruct, seed)`, CPU float32, 1.7B default / 0.6B fallback, RAM guard (honest `needs_bigger_machine`, never SIGKILL), no silent download, ref_text transcribed with Whisper small when missing (never invented).
- Wired into `parity.py`: `engine="qwen-base"` in `_clone_with_engine`, `POST /api/parity/generate-qwen-base`, clone endpoints accept `ref_text` + `seed`, `PARITY_MODELS` entry added.
- **Auto-fallback added:** if 1.7B is refused for RAM, 0.6B runs automatically and the result says which size ran.
- **0.6B live pass:** direct call ok=True, 4.16 s, 199,724 B, wall 146.3 s. Whisper transcript EXACT ("This is VoxLab, a free voice studio running on my own computer.").
- **1.7B weights COMPLETE in cache:** `model.safetensors` 3,857,413,744 B, cache-complete for 1.7B and 0.6B, `needs_download: False`. 1.7B live load NOT attempted on this 7.7 GiB VM (needs 8.5 GiB — arithmetic, not a bug).

### Step 3 — Generation pipeline in main `/api/generate`: WIRED + PROVEN
- New `backend/audio_pipeline.py` (own code): 800-char chunking (tag/abbreviation-aware), trim, runaway detect + halve-and-retry, 50 ms crossfade, RMS −20 dB / peak 0.85. **20/20 tests pass** (re-run by hand).
- `server.py`: `_chunked_generate` wired into Kokoro KPipeline + ONNX + Qwen CustomVoice paths (>800 chars, no pause); `_finalise_generate` RMS-normalises (was peak-only −3 dBFS).
- **Proven:** Kokoro long text 1524 chars → 200, 95.91 s, peak −2.98 dBFS, **RMS −20.0 dBFS exactly**, MP3 784,629 B, wall 215 s.
- **HTTP smoke proven:** `GET /` → 200; `POST /api/generate` Kokoro → 200, MP3 13,917 B, last.wav RMS −20.0 dBFS exactly.

### Step 4 — Explicit generation parameters: DONE (code)
- Chatterbox: exaggeration 0.5, cfg 0.5, temp 0.8, repetition-penalty 2.0 (+ seed, language_id); Hebrew 0.4/0.7/0.65/2.5.
- Turbo: temp 0.8, top_k 1000, top_p 0.95, repetition-penalty 1.2 (+ seed).
- LuxTTS kept at lab recipe (steps 8, speed 0.7, ≤8 s ref) — NOT silently swapped to Voicebox defaults; A/B listen still needed to pick one.

### Step 5 — Reference validation + normalisation + transcript: DONE + PROVEN
- `_validate_audio_file`: min 2.0 s + min RMS 0.01 added. Verified: 0.5 s clip rejected, silent 3 s rejected, 44-byte header rejected, real `kokoro_af_heart.wav` accepted (8.128 s, peak 0.49, rms 0.076).
- `_do_clone` now normalises a COPY of the reference (DC remove + RMS −20 dB, peak 0.95); original never modified. Verified: −22.36 → −20.0 dBFS exactly.
- `_do_clone` now RMS-normalises every clone output (−20 dBFS / peak 0.85).
- **Bug found by own testing + fixed:** `_do_clone` called `rms_normalize(_arr, sample_rate=...)` but the function takes no `sample_rate` — the silent `except: pass` would have hidden it. Fixed; lesson recorded in PARITY.md.

### Full clone path (Steps 2+3+5 together): PROVEN
- `_do_clone`, engine `qwen-base`, production path, no test bypass: ok=True, **8.72 s, 418,604 B**, fallback field shows 1.7B refused (6.7 GiB free vs 8.5 needed) and 0.6B ran, **peak −4.21 dBFS, RMS −20.0 dBFS exactly**, wall 305.9 s. Whisper transcript: words exact.

## What is BLOCKED / NOT proven (honest)
- **1.7B live load on this VM:** impossible by RAM arithmetic (7.7 GiB VM vs 8.5 GiB needed). First 1.7B run must be on the user's PC (more RAM/GPU).
- **Chatterbox (Turbo + full) live:** package installed in NO local venv (weights cached, package not). Needs an isolated torch==2.6.0 venv (conflicts with qwen-tts torch≥2.9.1) and duplicates CI workflow coverage. Params are code-only so far. Release-gate item for the user PC.
- **A/B listen (Step 6):** objective half done (both engines RMS −20.0, transcripts exact, same reference). The listening verdict needs human ears + a Voicebox sample — user PC only. **Do NOT claim 100% parity.**
- **Two silent OOM deaths during testing** (1.6 GiB and 3.6 GiB free, while the 1.7B download ran): VM-RAM deaths, not code faults. Rule learned: run Qwen tests with nothing else heavy running.
- **Lab-only note:** faster-whisper 1.2.1 + PyAV 19 clash (`av.open(metadata_errors=...)` removed) — transcript QC worked via soundfile bypass. The frozen build's `av` version must be checked at the release gate.

## Files changed (local only, NOT pushed)
- NEW: `backend/audio_pipeline.py`, `backend/qwen_base.py`
- Edited: `backend/server.py`, `backend/parity.py`, `backend/clone.py`, `PARITY.md`
- Lab venvs only: `venv_tada` += qwen-tts 0.1.1, accelerate, sox, onnxruntime; `venv_kokoro` += fastapi, uvicorn, python-multipart, faster-whisper 1.2.1, av 19.0.2 (test-only, not shipped)
- HF cache: Qwen 1.7B Base (~4.3 GB) + 0.6B Base + 0.6B CustomVoice cached
- Proof audio: `output/qwen_base_clone_path.wav` (8.72 s, RMS −20.0), `output/qwen_base_06b_test.wav` (4.16 s), `output/last.wav` (Kokoro, RMS −20.0)

## What remains before release
1. User-PC run: 1.7B Base clone (first live load), Turbo/Chatterbox clone, A/B listen vs Voicebox (same sentence + reference) → listening verdict.
2. Release-gate re-verification (frozen build: Kokoro bundle, faster-whisper/av versions, Generate + Clone on fresh install).
3. Then: user confirms all-OK → release via browser task signed in ONLY as ishtiaquehasib (ishtiaqueccr2017@gmail.com).

## Bottom line
The flagship fix is proven end-to-end on this VM at 0.6B: Qwen Base clone works, the pipeline lands every output at exactly −20 dBFS RMS, transcripts are exact, and the 1.7B weights are cached and ready for a bigger machine. 100% output parity is NOT claimed — the listening test and the 1.7B run still need the user's PC.
