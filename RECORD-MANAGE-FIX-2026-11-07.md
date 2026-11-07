# Record-page management — Download + Delete recording (v1.1.12 test build)

Date: 2026-11-07. User request (Roman Bengali): "ami jeno record kora jinista
delete and download korte pari and chaile new record o korte pari, all functional"
— he wants to delete and download his recorded clip, and re-record a new one,
all functional.

## What was missing

The Record page could record (max 30 s) and upload (`POST /api/parity/mic-upload`
-> `output/uploads/mic_recording.webm`), and re-recording already overwrote the
file — but there was NO Download button and NO Delete button for the clip.
After an upload the user had no way to get the file back or remove it.

## Latent bug found while implementing (also fixes v1.1.11)

`GET /api/parity/audio/{filename}` only looked in `output/` itself, but mic
recordings live in `output/uploads/`. So `/api/parity/audio/mic_recording.webm`
404'd even when the file existed — the v1.1.11 Clone-page fallback that fetches
exactly that URL (to use the mic file without re-picking it) could never
succeed, and its comment wrongly claimed the file "lives in output/".
The audio route now tries `output/` first, then `output/uploads/`
(basename only, no traversal). The v1.1.11 comment is corrected to
`output/uploads/`.

## Fix

### `backend/parity.py`
- `delete_recording(filename)` (plain function, testable without FastAPI):
  basename only, allowed audio extension only, path must resolve inside
  `output/uploads/` — generated output (stories, clones, captures in
  `output/`) is never deleted. Also removes the `.norm` sibling that
  `_do_clone` writes next to a clip used as a clone reference, so no stale
  reference survives.
- `POST /api/parity/delete-recording` (new route): `{"filename": ...}`,
  defaults to `mic_recording.webm` when omitted. Missing file -> honest
  404, bad extension/traversal -> 400. After a delete, clone resolves the
  reference from disk (`_resolve_ref` / `GET /api/parity/reference-status`),
  so Clone honestly reports the reference missing instead of silently
  using a stale file.
- `GET /api/parity/audio/{filename}`: now serves `output/` then
  `output/uploads/` (see latent bug above). Download disposition is
  unchanged (Starlette `FileResponse` with `filename=`); the Download
  button also uses an `<a download>` element, so the file saves with its
  real name.

### `app/index.html` (Record page)
- New buttons next to Upload recording: **Download recording** and
  **Delete recording**. They act on the last uploaded clip (`lastUploaded`
  — mic recording or Choose-File clip) or `mic_recording.webm` from an
  earlier session, so they work after a page reload too. A short note
  under the buttons explains this.
- `downloadRecording()`: fetches the clip, checks `ok` first (honest
  "nothing to download" message when the server has no clip), then saves
  it via a blob URL with the real filename.
- `deleteRecording()`: `confirm()` guard, then POSTs the delete; on
  success clears `lastUploaded`, the player, the timer/clone status, and
  disables Upload. A fresh recording that has NOT been uploaded yet is
  left alone (tracked by a new `recUploaded` flag, set on upload success
  and reset by `startRec()`), so Delete never destroys an un-uploaded
  take.
- Re-record: verified, no change needed — `startRec()` already resets
  `recChunks`/`recSeconds`, and `uploadRecording()` overwrites the same
  server file (`open(..., "wb")`).

## Verification (measured, this VM)

- `py_compile backend/parity.py` — OK.
- `node --check` on the whole inline `<script>` extracted from
  `app/index.html` — OK.
- Live HTTP test `tmp/test_record_manage.py` (real uvicorn server with
  only the parity router, port 8123, 3 s sine WAVs — 1 s clips are
  rejected by the existing >= 2 s reference validation, so the first
  run failed on the fixture, not the feature): **17/17 checks passed**:
  mic-upload ok -> download returns byte-identical file ->
  reference-status `exists=true` -> delete ok, file gone from disk ->
  download 404 after delete, reference-status `exists=false` (no stale
  clone) -> second delete honest 404 -> `../server.py` and `/etc/passwd`
  refused (400) -> a file in `output/` (not uploads/) refused and left
  untouched -> re-upload after delete ok, download works again
  (re-record) -> uploaded-clip path (Choose File + Upload clip) download
  identical bytes + delete ok -> empty payload defaults to
  `mic_recording.webm`, honest 404.
- `.norm` sibling: direct `delete_recording()` unit check — both
  `mic_recording.wav` and `mic_recording.norm.wav` removed. Test files
  cleaned up afterwards.

## Not proven on this VM (honest)

- The actual buttons in a real browser on the user's PC (needs his
  machine); the live HTTP test above covers the exact endpoints the
  buttons call. No full PyInstaller build was run here.

## Browser-upload + tag steps (parent)

Staging: `~/workspace/voice-studio-release-1.1.12/`, local commit as
Ishtiaque Hasib, tag `v1.1.12` (NOT pushed). Changed vs v1.1.11:
`backend/parity.py`, `app/index.html`, `RECORD-MANAGE-FIX-2026-11-07.md`
(new). The live test `tmp/test_record_manage.py` is NOT in the commit
(`tmp/` is gitignored, same as the earlier test scripts) — it stays in
the working copy at `~/workspace/voice-studio/tmp/test_record_manage.py`.
Upload those 3 files as ishtiaquehasib (never hasibtechqore) to main, then create tag v1.1.12
(Pre-release, "VoxLab v1.1.12 (test build)"), watch CI, then give the
user only the v1.1.12 Windows installer link.
