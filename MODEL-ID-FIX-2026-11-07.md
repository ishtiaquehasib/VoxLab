# Qwen TTS Base download repo-id fix — 2026-11-07

**Task:** fix the VoxLab Models-page download 404 the user reported on his PC
(screenshot: Qwen TTS 1.7B "Needs download — error — Hugging Face repo not
found (404)"). User said every download has this problem — verified: the
same wrong-id bug hits both Qwen TTS Base entries; all other catalog repos
were checked and exist.

**This task did NOT push, tag, or release anything on GitHub.** GitHub for
VoxLab is ONLY ishtiaquehasib (ishtiaqueccr2017@gmail.com) — never
hasibtechqore.

## Cause (verified against the Hugging Face API)

`backend/parity.py` `MODEL_CATALOG` listed repo ids that do not exist on
the Hub:

| Entry | Listed id (wrong) | HF API | Correct id | HF API |
|---|---|---|---|---|
| Qwen TTS 1.7B | `Qwen/Qwen3-TTS-12Hz-1.7B` | 401 / not found | `Qwen/Qwen3-TTS-12Hz-1.7B-Base` | 200 |
| Qwen TTS 0.6B | `Qwen/Qwen3-TTS-12Hz-0.6B` | 401 / not found | `Qwen/Qwen3-TTS-12Hz-0.6B-Base` | 200 |

The Models-page download calls `snapshot_download(repo_id=...)` with the
catalog id, so it 404'd. The clone engine itself was never broken:
`backend/qwen_base.py` lines 34–35 already use the correct `-Base` ids.

## Files changed (local only, `~/workspace/voice-studio/`)

- **`backend/parity.py`** lines 2210, 2212 — `MODEL_CATALOG`:
  `Qwen/Qwen3-TTS-12Hz-1.7B` → `Qwen/Qwen3-TTS-12Hz-1.7B-Base`,
  `Qwen/Qwen3-TTS-12Hz-0.6B` → `Qwen/Qwen3-TTS-12Hz-0.6B-Base`.
  Nothing else changed. `server.py` and `app/index.html` use the
  `-CustomVoice` ids (correct, untouched). A tree-wide sweep for the
  bare `Qwen3-TTS-12Hz-1.7B"` / `Qwen3-TTS-12Hz-0.6B"` ids found no
  other occurrence (docs included).
- **This report** (`MODEL-ID-FIX-2026-11-07.md`, new).

## Verification (measured)

- HF API re-check after the fix: both corrected ids return **200**;
  the old ids still return **401**.
- `python3 -m py_compile backend/parity.py` — **OK**.
- Status logic confirmed: `_cache_present(repo)` looks for
  `models--Qwen--Qwen3-TTS-12Hz-1.7B-Base` under the HF cache, and the
  download path uses the same catalog id — so after the fix, Download
  will fetch the real repo and the status will flip to Downloaded once
  the snapshot is complete.
- Other catalog repos spot-checked against the HF API and exist (200):
  CustomVoice 1.7B/0.6B, LuxTTS, chatterbox, chatterbox-turbo,
  tada-1b/codec, Kokoro-82M, indic-parler, whisper-base/small,
  Qwen3 0.6B/1.7B/4B. Whisper Turbo returned 307 (redirect, exists).

## Staging (ready for the parent's browser upload, ishtiaquehasib only)

- Staging repo: `~/workspace/voice-studio-release-1.1.9/` — fresh clone
  of main at v1.1.8 (`b99c782`), junk excluded (no venvs/output/tmp).
- Local commit — verify with `git log --oneline -1` in the staging dir;
  message: "VoxLab v1.1.9 (test build): fix Qwen TTS Base download
  repo ids (404)". Local tag **`v1.1.9`** created. **NOT pushed**
  (verify via `git ls-remote`).
- 2 files changed vs v1.1.8: `backend/parity.py`, `MODEL-ID-FIX-2026-11-07.md` (new).
- Browser steps: as ishtiaquehasib, upload those 2 files to
  https://github.com/ishtiaquehasib/VoxLab on main, then create tag
  v1.1.9 (Pre-release, "VoxLab v1.1.9 (test build)") so all 3 installer
  workflows trigger. Windows #22 should then build and attach the
  installer.

## What the user must do after v1.1.9

1. Install `VoxLab-Setup-1.1.9-x64.exe` (close old VoxLab first;
   SmartScreen → More info → Run anyway).
2. Models page → **Qwen TTS 1.7B → Download** (~4 GB: the
   `model.safetensors` alone is 3.86 GB). The 1.7B Base weights are NOT
   on his PC yet — his screenshot shows only CustomVoice 1.7B as
   Downloaded, which is a different model and does not count for the
   Base clone engine.
3. After Download shows Downloaded ✓, Clone with the 1.7B Base engine
   (30 s reference + ref_text, seed 42) using the test sentence, then
   Turbo/Chatterbox and the A/B listen vs Voicebox.

## What remains unverified

- The actual v1.1.9 CI run (the real proof the Windows installer builds);
  the download itself on the user's PC (needs his machine + ~4 GB).
- 100% parity is NOT claimed. Chatterbox live, 1.7B live load, A/B
  listen, mic, WASAPI capture, hotkey still need the user's PC.
