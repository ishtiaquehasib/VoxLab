# Models-page status text fix — 2026-11-07 (v1.1.10)

**Bug (user's PC screenshot, v1.1.8):** many Models rows read
"Downloaded ✓ — downloading" at the same time (Qwen CustomVoice 0.6B,
LuxTTS, Chatterbox TTS, Whisper Base/Small/Medium/Large/Turbo, Qwen3
0.6B). LuxTTS also read "Downloaded ✓ — downloading — Source
luxtts_src/ is not bundled; endpoint 503s on a fresh install until
vendored." — claiming Downloaded while the model cannot work.

## Exact cause (confirmed in code, not guessed)

Two independent defects in `backend/parity.py` `_catalog_status()` +
`app/index.html` `loadModelCatalog()`:

1. **`downloaded` was cache-only, `download_state` was raw.**
   `_catalog_status()` set `downloaded` purely from `_cache_present()`
   (snapshot dir exists and is non-empty). `snapshot_download` creates
   the snapshot dir and writes files incrementally, so the dir is
   non-empty partway through a multi-file download — while the worker
   thread still holds `_DOWNLOADS[id] = {"state": "downloading"}`.
   The UI rendered `Downloaded ✓` from `m.downloaded` and
   unconditionally appended ` — downloading` from `m.download_state`.
   Same defect produced "Downloaded ✓ — done" from a stale terminal
   state. The user had pressed Download on several models at once, so
   many rows were mid-download with partial snapshots present.
2. **"Downloaded" never checked usability.** `downloaded` only checked
   the HF repo cache. LuxTTS/TADA endpoints additionally require a
   vendored source dir (`luxtts_src/` / `tada_src/`, checked in
   `generate_luxtts` / `generate_tada` via `os.path.isdir(os.path.join(
   BASE, ...))`), which is NOT bundled on a fresh install — the
   endpoint 503s. The catalog never checked `needs_src`, so a cached
   repo read as Downloaded although the model cannot generate.

## The fix

`backend/parity.py` — `_catalog_status()` now computes one canonical
`status_text` per row, and `downloaded` / `needs_download` follow the
same rules, so the ✓ and the Download button can never disagree:

- source dir missing → `"Not usable on this install"`, never ✓
  (`_CATALOG_NEEDS_SRC = {"luxtts": "luxtts_src", "tada-1b": "tada_src"}`,
  checked with `_src_bundled()` on the same `BASE` the generate
  endpoints use, frozen-exe aware)
- still downloading → `"Downloading…"`, never ✓ (a partial snapshot is
  not a download)
- failed download → `"Download failed"`, never ✓ (error text appended)
- cached + usable + idle/done → `"Downloaded ✓"`
- else `"Needs download"` / `"Not downloadable"`
- New fields per row: `"usable"`, `"status_text"`. The stale
  "not bundled" note is dropped once the source IS vendored (it would
  otherwise contradict the ✓).

`app/index.html` — `loadModelCatalog()` prefers `m.status_text`
(falls back to the same rules for an older server payload), never
appends a raw `download_state` when `status_text` exists, and hides
the Download button while downloading and for unusable models
(re-downloading the repo cannot fix a missing source dir).

No model repo ids changed — the v1.1.9 404 fix (`-Base` ids) is intact.

## Verification (this VM, measured)

- `python3 -m py_compile backend/parity.py` — OK.
- `node --check` on the extracted `loadModelCatalog()` — OK.
- `tmp/test_model_status.py` — **ALL CHECKS PASSED** (17 cases):
  cached+downloading renders "Downloading…" (was "Downloaded ✓ —
  downloading") for Whisper Small, CustomVoice 0.6B, Chatterbox, Qwen3
  0.6B; cached+done renders "Downloaded ✓" (was "… — done");
  not-cached+downloading renders "Downloading…"; 404 error renders
  "Download failed — Hugging Face repo not found (404)…"; LuxTTS and
  TADA 1B with cached repo + missing source render "Not usable on
  this install — Source … is not bundled…", and with the source
  vendored render plain "Downloaded ✓" with the stale note dropped;
  TADA 3B renders "Not downloadable"; Qwen TTS 1.7B/0.6B repo ids
  confirmed as `Qwen/Qwen3-TTS-12Hz-1.7B-Base` /
  `Qwen/Qwen3-TTS-12Hz-0.6B-Base`.

## What remains unverified

- The actual v1.1.10 CI run and the Models page on the user's PC
  after installing it (the real proof). The 1.7B Base download itself
  on his PC is still pending (v1.1.9 installer). 100% parity is NOT
  claimed.

## Staging (for the parent's browser upload, ishtiaquehasib only)

- Staging repo: `~/workspace/voice-studio-release-1.1.10/` — fresh
  clone of main at v1.1.9 (`4728a36`).
- Local commit: `VoxLab v1.1.10 (test build): fix Models status text
  (Downloaded vs downloading)` — author Ishtiaque Hasib
  <ishtiaqueccr2017@gmail.com>. Local tag `v1.1.10`, NOT pushed.
- Files changed vs v1.1.9: `backend/parity.py`,
  `app/index.html`, `MODEL-STATUS-FIX-2026-11-07.md` (new).
- Browser steps: as ishtiaquehasib, upload those 3 files to
  https://github.com/ishtiaquehasib/VoxLab on main, then create tag
  v1.1.10 (Pre-release, "VoxLab v1.1.10 (test build)") so the 3
  installer workflows trigger. Windows installer is the one the
  user's PC needs.
