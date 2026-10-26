# VoxLab next steps 2026-10-27 — Whisper Turbo dictation WIRED, push bundle re-verified, TADA BF16 note in README (NO push, NO release)

## 1. Whisper Turbo as dictation engine — WIRED, tested via endpoint

| Item | Exact result |
|---|---|
| Code | `backend/parity.py`: `transcribe()` default model is now `large-v3-turbo`; if Turbo fails to load/transcribe, `small` is tried and the response names the model actually used plus `fallback_from`/`fallback_error`. Explicit `model_size="small"` skips Turbo. `PARITY_MODELS` whisper-turbo status and `/api/parity/status` dictation text updated. `py_compile` on parity.py + server.py → OK. |
| Direct test | Mahbub venv, `transcribe('output/kokoro_af_heart.wav')` → `{'available': True, 'transcript': 'Hello, this is a free voice studio running on my own computer. No account, no subscription, just open models and my own voice.', 'model': 'large-v3-turbo', 'detected_language': 'en'}`, wall 29.6 s, no fallback needed. Transcript exact. |
| Endpoint test | Live server (mahbub venv, port 8000), `POST /api/parity/dictate` with `output/kokoro_af_heart.wav` → HTTP 200, `{'available': True, 'transcript': '<same exact sentence>', 'model': 'large-v3-turbo', 'detected_language': 'en'}`, wall 31.5 s (includes model load). Test server stopped afterwards (port 8000 free). Fallback path is coded, NOT live-triggered (Turbo succeeded). |
| Note | Turbo model is cached (`models--mobiuslabsgmbh--faster-whisper-large-v3-turbo`, 1.6 GB); small is cached as fallback. This wiring does NOT change any other dictation behaviour: librosa-decode path (av `metadata_errors` workaround) is unchanged. |

## 2. Push bundle re-verified — NOT pushed, NOT released

| Item | Exact result |
|---|---|
| Git status | `git status` → "not a git repository" — this tree is still NOT a git repo, nothing staged or pushed. |
| Bundle | **36 files, 3,401,160 bytes (~3.4 MB)** (grew from 30 files / ~3.3 MB because new test scripts were added since: test_luxtts_confirm.py, test_luxtts_retest.py, test_qwen_customvoice.py, test_tada.py, test_whisper_turbo.py, website/blogger-theme.xml moved to `website/`). No file over the GitHub 100 MB limit. Largest: app/logo.png and assets/voxlab-logo.png at 1,445,267 B each, then website/blogger-theme.xml 261,185 B. |
| Excluded, verified | venv_parler/, venv_tada/, output/ (incl. tada_clone.wav + Kokoro ONNX), tada_src/, luxtts_src/, github-profile/ (superseded draft), tmp/, __pycache__/, *.pyc — all in .gitignore and absent from the 36-file list. `website/blogger-theme.xml` IS in the bundle, under `website/`. |
| Workflows | PyYAML safe_load → YAML_OK for all three: windows-installer.yml (build-windows), macos-installer.yml (build-macos), linux-installer.yml (build-linux). No installer binary exists; a real Actions run still needs the first push + a v* tag. |

## 3. TADA BF16 load note — applied to README, test_tada.py untouched

| Item | Exact result |
|---|---|
| Already in PARITY.md | The top TADA section (2026-10-26) already documents the full BF16 finding: unpatched float32 init OOM-killed (exit 137) on 7.7 GiB no-swap VM; fix is `dtype=torch.bfloat16, low_cpu_mem_usage=True` on the LM load ONLY in `tmp/run_tada_bf16.py` (model load 4.6 s in isolation, 10.9 s in the full run); a global BF16 default breaks the float32 encoder (`RuntimeError: Input type (torch.FloatTensor) and weight type (CPUBFloat16Type)`); swapfile unavailable (`swapon: Operation not permitted`, deleted). |
| Added 2026-10-27 | Same note added to README.md under "TADA low-RAM load note", plus the stale README parity line fixed (Whisper Turbo no longer listed as needs_download). Verified: `test_tada.py` line 11 and `tmp/run_tada_bf16.py` line 11 both still carry the unchanged target "This is VoxLab, a free voice studio running on my own computer." — `test_tada.py` was NOT modified. `output/tada_clone.wav` still present: 379K, 4.04 s. |
| Remaining TADA caveat | The BF16 fix lives in `tmp/run_tada_bf16.py`, which is gitignored (tmp/) and therefore NOT in the push bundle — a fresh Windows install would need the same LM-load change applied to its own run path, not just the bundle as-is. |

# VoxLab TADA — DONE 2026-10-26 ~18:09: generation SUCCEEDED, transcript EXACT

## TADA generation — exact results (target sentence unchanged)

| Item | Exact result |
|---|---|
| Source files | User-uploaded files in `~/workspace/voice-studio/output/llama_tokenizer/`: tokenizer.json 8.7M, tokenizer_config.json 50K, special_tokens_map.json 301B, config.json 843B (LlamaForCausalLM config, valid). No licence-bypass mirror used, no token asked for, nothing pushed to GitHub. |
| HF cache placement | `~/.cache/huggingface/hub/models--meta-llama--Llama-3.2-1B/snapshots/userupload20261026/` with the 4 files, `refs/main` = `userupload20261026` (written WITHOUT trailing newline — the first attempt wrote it with `echo`, giving revision `userupload20261026\n`, which hub 0.36.2 does not match to the snapshot dir, so `try_to_load_from_cache` returned None; `printf %s` fixed it). Verified: `AutoTokenizer.from_pretrained("meta-llama/Llama-3.2-1B")` offline → PreTrainedTokenizerFast, vocab 128256, `This is VoxLab.` → `[128000, 2028, 374, 80712, 30146, 13]`. |
| Second dependency found | TADA's Aligner also loads `AutoConfig.from_pretrained("facebook/wav2vec2-large")` (aligner.py default `base_model_name`). That public config was NOT in cache, so offline load failed after the tokenizer passed. Fix: downloaded the public config.json (HTTP 200, 1555 bytes) from `facebook/wav2vec2-large` and cached it the same way (`models--facebook--wav2vec2-large/snapshots/w2vconfig/`, refs/main without newline). Verified: `AutoConfig.from_pretrained("facebook/wav2vec2-large")` offline → wav2vec2, hidden 1024. This is TADA's own upstream dependency, not a Llama mirror. |
| OOM blocker + fix | Unpatched `test_tada.py` is KILLED (exit 137, OOM) on this 7.7 GiB, no-swap VM, even for `TadaForCausalLM.from_pretrained` alone with `low_cpu_mem_usage=True`: float32 default-dtype init duplicates the BF16 weights (model file 3,922,463,244 B, 394 tensors, 2.16B params, BF16). Fix that worked: pass `dtype=torch.bfloat16, low_cpu_mem_usage=True` to the LM load ONLY (isolated probe: model load 4.6 s). Do NOT set global BF16 default dtype — that breaks the encoder: `RuntimeError: Input type (torch.FloatTensor) and weight type (CPUBFloat16Type)` in wav2vec2 conv1d, because the reference audio is float32. Swapfile was tried and is NOT available (`swapon: Operation not permitted`); the swapfile was deleted. |
| Run script | `tmp/run_tada_bf16.py` = `test_tada.py` with ONLY those two load changes (diff verified, target sentence unchanged: "This is VoxLab, a free voice studio running on my own computer."). `test_tada.py` itself was NOT modified. Run: `TMPDIR=~/workspace/voice-studio/tmp HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 no_proxy="" NO_PROXY="" venv_tada/bin/python tmp/run_tada_bf16.py`. |
| Timings | encoder load 6.3 s, model load 10.9 s, encode 23.7 s, **generate 928.5 s (~15.5 min), total 952.3 s**, exit 0. Generate is slow on 2-CPU VM (~0.2 core average, 5.7 GB RSS at peak). |
| Output | `output/tada_clone.wav`: **4.04 s (ffprobe 4.039750 s), sr 24000, 387,896 bytes (379K), audio shape (96954,)**, mean volume −22.6 dB, max −1.8 dB. |
| Transcript cross-check | **EXACT by both transcribers** (librosa-decode path, av `metadata_errors` bug avoided): faster-whisper small → "This is VoxLab, a free voice studio running on my own computer."; faster-whisper large-v3-turbo → identical sentence. Lang en. |
| Status | TADA is DONE as a tested model. Remaining TADA note: the BF16-load fix lives in `tmp/run_tada_bf16.py`, not in `test_tada.py`; a fresh Windows install would hit the same float32-init OOM risk on low-RAM PCs unless the same dtype/low_cpu_mem_usage load is used. |

# VoxLab TADA — 2026-10-26 late: browser-downloaded tokenizer files NOT found on this VM, generation NOT run

## Browser-download search — exhaustive, files absent

| Location checked | Result |
|---|---|
| `~/Downloads` | Does NOT exist on this VM. |
| `~/workspace/browser_downloads/` | Latest session folder is `sess-4030856112` (2026-10-26 09:34, one JPEG only). No session folder from the ~22:30 tokenizer downloads, no tokenizer file in any session folder. |
| `~/.config/chromium/` | Only Crash Reports; no download folder, no tokenizer files. |
| `~/.wine/drive_c/users/root/Downloads/` | Empty. |
| `/tmp` | No tokenizer files; only prior subagent scripts (`download_llama_tokenizer.py`, `hf_dl.py`, etc.) and `/tmp/whoami.json` = `{"error":"Invalid username or password."}` from the earlier surrogate check. |
| `~/.cache/huggingface/hub/` | NO `models--meta-llama--Llama-3.2-1B` directory at all. TADA weights/codec are present (`models--HumeAI--tada-1b`, `models--HumeAI--tada-codec`), but no Llama tokenizer cache. |
| `~/workspace/voice-studio/output/llama_tokenizer/` | Empty directory (created by the earlier surrogate download script, which failed with 401). |
| `output/tada_clone.wav` | Does NOT exist. No TADA audio produced or claimed. |

Conclusion: the browser task runs in a separate browser environment — its triggered downloads were never verified as saved files and were never transferred to this VM. The parent task's premise ("browser just downloaded the files") is NOT satisfied on this VM. Nothing was copied, because there was nothing to copy. No mirror was hunted to bypass the Meta licence gate, per the earlier deliberate decision.

## Expected location if the files arrive

`test_tada.py` calls `Encoder.from_pretrained("HumeAI/tada-codec")` → `Aligner.from_pretrained` → `AutoTokenizer.from_pretrained("meta-llama/Llama-3.2-1B")`. In HF-cache layout that is `~/.cache/huggingface/hub/models--meta-llama--Llama-3.2-1B/snapshots/<revision>/` containing `tokenizer.json` (9.09 MB), `tokenizer_config.json` (50.5 kB), `special_tokens_map.json` (301 Bytes) — AND `config.json`, because the rerun below shows `AutoTokenizer.from_pretrained` first requests `config.json` from the same gated repo. Copying only the 3 tokenizer files would therefore NOT be sufficient on its own; `config.json` from the same repo is also needed (or a local-directory tokenizer load, which `test_tada.py` does not currently do).

## Rerun of test_tada.py under venv_tada — exact failure, 2026-10-26 late

Command: `cd ~/workspace/voice-studio && TMPDIR=~/workspace/voice-studio/tmp no_proxy="" NO_PROXY="" venv_tada/bin/python test_tada.py`, wall ~26 s, fails at line 14 (`Encoder.from_pretrained("HumeAI/tada-codec", subfolder="encoder")`) before any generation:
`OSError: You are trying to access a gated repo. Make sure to have access to it at https://huggingface.co/meta-llama/Llama-3.2-1B. 401 Client Error. (Request ID: Root=1-6adf85ce-113711312502b9c175216664;dc2dea57-73b4-40cf-9c5e-d6ecfa30cc38) Cannot access gated repo for url https://huggingface.co/meta-llama/Llama-3.2-1B/resolve/main/config.json. Access to model meta-llama/Llama-3.2-1B is restricted. You must have access to it and be authenticated to access it. Please log in.`

## Required next step for the parent (browser requirement)

This subagent cannot operate a live browser. To get the files onto this VM, the parent must arrange, via an eligible browser delegation: (a) transfer the 3 tokenizer files PLUS `config.json` from the browser environment to this VM (e.g. a browser-task file transfer to `~/workspace/voice-studio/output/llama_tokenizer/`), OR (b) make the stored `custom.huggingface` credential actually authenticate as Devid8734 with ACCEPTED Llama 3.2 access (the stored credential still returns 401 on `/api/whoami`), then rerun the surrogate download. Until one of those happens, `test_tada.py` cannot run, and no TADA output can be claimed.

# VoxLab TADA — 2026-10-26 late, AFTER fresh HF reconnect: STILL 401, generation NOT run

## Reconnect rerun — exact results, no credential value recorded

| Item | Status | Exact result |
|---|---|---|
| Auth check (surrogate) | **HTTP 401** | `GET https://huggingface.co/api/whoami` via urllib + `add_surrogate_to_request(custom.huggingface, allowed_hosts=["huggingface.co"])` → `401 {"error":"Invalid username or password."}`. Public `GET https://huggingface.co/api/models/meta-llama/Llama-3.2-1B` → 200, so network/proxy to huggingface.co works; only authenticated calls fail. |
| Gated downloads (surrogate) | **HTTP 401, all three** | `GET https://huggingface.co/meta-llama/Llama-3.2-1B/resolve/main/tokenizer.json`, `tokenizer_config.json`, `special_tokens_map.json` → all `401 "Access to model meta-llama/Llama-3.2-1B is restricted. You must have access to it and be authenticated to access it. Please log in."` |
| huggingface_hub (venv_tada) | **GatedRepoError 401** | With the surrogate set in-process as `HF_TOKEN` (never printed), `hf_hub_download(repo_id="meta-llama/Llama-3.2-1B", filename="tokenizer_config.json")` → `GatedRepoError 401 … Cannot access gated repo … You must have access to it and be authenticated to access it.` |
| Generation | **NOT run** | `test_tada.py` was not run to completion, because the gated tokenizer is still missing. No `output/tada_clone.wav` exists. No TADA audio is produced or claimed. Weights, codec, and `venv_tada` remain in place and do not need redoing. Surrogate placement code was checked: `dynamic_credentials.py` `add_surrogate_to_request` correctly sets `Authorization: Bearer <surrogate>` for placement `bearer_header`, so the request format is not the obvious fault. |
| What this still does and does not prove | **Still indistinguishable from outside, but token-value hypothesis strengthened** | A 401 after a claimed fresh reconnect is still consistent with (a) the stored credential not being a valid HF token for the Devid8734 account with ACCEPTED Llama 3.2 access (e.g. a fine-grained token without gated-repo scope, a token from a different account, a revoked token, or a non-token value entered at connect time), or (b) the surrogate swap not taking effect on this egress path. The reconnect did not change the outcome, which weakens (but does not eliminate) the "old token" explanation and leaves (a) in its other forms and (b) both open. Do NOT assume either one, and do NOT blindly request another token without checking which account/scope the entered token belongs to. |
| Required next step (parent) | **Verify the token, not just reconnect** | Have the user verify, on his own HF account (Devid8734, licence ACCEPTED 2026-10-26): that the token entered at reconnect time is a Read token belonging to that account, with access to gated repos (not a fine-grained token restricted to other repos), and that it is still active/not revoked. If that checks out and whoami still returns 401, the surrogate swap path itself needs investigation. If it does not check out, reconnect once more with a correct token, then rerun this exact check before test_tada.py. |

# VoxLab TADA — 2026-10-26 late: gated tokenizer download FAILED on stored HF credential (401), generation NOT run

## TADA tokenizer via custom.huggingface surrogate — FAILED, exact evidence, no credential value recorded

| Item | Status | Exact result |
|---|---|---|
| Method used | Surrogate only | Read `~/workspace/custom-connectors/custom.huggingface/CONNECTOR.md` and `/opt/muse/skills/custom-connector-setup/bin/dynamic_credentials.py` first. Used `add_surrogate_to_request` with `custom.huggingface`, `allowed_hosts=["huggingface.co"]`. No credential value was printed, logged, or revealed anywhere, and the user was NOT asked for a token in chat. |
| Gated download attempt | **HTTP 401** | `GET https://huggingface.co/meta-llama/Llama-3.2-1B/resolve/main/tokenizer.json` via urllib + surrogate Bearer header → `urllib.error.HTTPError: HTTP Error 401: Unauthorized`. The other two files (tokenizer_config.json, special_tokens_map.json) were not downloaded after this failure. |
| Auth check | **HTTP 401** | `GET https://huggingface.co/api/whoami` via urllib + surrogate, and again via curl + surrogate → both `401 {"error":"Invalid username or password."}`. The public model metadata endpoint `GET https://huggingface.co/api/models/meta-llama/Llama-3.2-1B` returns 200 without auth, so the network/proxy path to huggingface.co works; only authenticated calls fail. |
| huggingface_hub attempt | **GatedRepoError 401** | Under `venv_tada`, with the surrogate set in-process as `HF_TOKEN` (never printed), `hf_hub_download(repo_id="meta-llama/Llama-3.2-1B", filename="tokenizer_config.json")` → `GatedRepoError 401 Client Error. Cannot access gated repo ... You must have access to it and be authenticated to access it.` |
| Browser downloads on this VM | **None found** | No `~/Downloads` directory exists, and no tokenizer files were found in the VM's local download locations. The browser task's earlier triggered downloads could not be verified as saved files, and they are not on this VM. |
| Generation | **NOT run** | `test_tada.py` under `venv_tada` was NOT rerun, because the gated tokenizer is still missing. No `output/tada_clone.wav` exists. No TADA audio is produced or claimed. Weights/codec/venv from the earlier retry remain in place and do not need redoing. |
| What this 401 does and does not prove | **Cannot distinguish** | A 401 is consistent with two different causes, and they cannot be told apart from the outside: (a) the stored `custom.huggingface` credential is not a valid HF token with access to the gated repo (for example, a token created before licence acceptance, a fine-grained token without gated-repo scope, a revoked token, or a value other than the HF token entered at connect time); or (b) the surrogate swap is not taking effect on this exec egress path. Do NOT assume either one. |
| Required next step (parent) | **Reconnect, do not ask in chat** | Reconnect `custom.huggingface` with `credentials.request_api_access` and `"reconnect": true`, using a fresh Read token created AFTER the Llama 3.2 licence acceptance (licence status ACCEPTED, 2026-10-26), then rerun the surrogate download and `test_tada.py` under `venv_tada`. If the reconnected token still returns 401 on `/api/whoami`, the swap path itself needs investigation, not another token. |

# VoxLab remaining work — 2026-10-26 (global shortcut + MCP clone DONE, push bundle verified, NOT pushed)

## 1. Global dictation shortcut + paste — IMPLEMENTED, headless-safe, NOT live-tested on a desktop

| Item | Status | Exact test result |
|---|---|---|
| Code | **Implemented** | New `backend/global_shortcut.py`: `default_hotkey()` (Ctrl+Alt+V Linux/Windows, Cmd+Option+V macOS), `is_headless()`, `copy_to_clipboard()` (pyperclip if installed, else native pbcopy/clip/wl-copy/xclip/xsel), `paste_into_focused_app()` (pynput Ctrl/Cmd+V, explicit only), `trigger_dictation(audio_path, transcribe_fn=None, paste=False)` (uses `parity.transcribe()` by default, copies transcript, pastes ONLY if paste=True), `start_hotkey_listener(on_trigger, hotkey=None)` (pynput GlobalHotKeys, background thread, caller-owned). No hotkey/clipboard/paste is started at import. `backend/requirements.txt` now lists optional `pynput` + `pyperclip` with a comment that the module works without them, with honest errors. |
| Headless self-check | **Tested, honest failures** | `python3 backend/global_shortcut.py` on this VM: `platform=Linux headless=True default_hotkey=<ctrl>+<alt>+v`, `clipboard_tool=(None, None)`, `copy_test={'ok': False, 'error': 'no clipboard tool available (install xclip/xsel/wl-copy on Linux, or pyperclip)'}`, `hotkey_test_ok=False (expected False on a headless system)`. No pynput, no pyperclip, no xclip/xsel/wl-copy, no DISPLAY on this VM. |
| Logic with a stub transcriber | **Tested** | Missing file → `{'ok': False, 'error': 'audio file not found: nope.wav'}`. Real file + stub transcribe_fn → transcript returned but `{'ok': False, 'error': 'transcript produced but clipboard copy failed: no clipboard tool available...'}` — the transcript is never claimed as copied/pasted when the clipboard write failed. `paste_into_focused_app()` → `{'ok': False, 'error': 'headless system: no GUI session to paste into'}`. `start_hotkey_listener()` → `{'ok': False, 'error': 'headless system: no GUI session for a global hotkey'}`. |
| NOT tested / NOT built | **Honest gap** | Live hotkey press on a real desktop, live clipboard copy/paste into another app, and mic-recording + shortcut wiring into a packaged desktop shell (the hotkey triggers dictation on a supplied audio file; it does not record by itself). All three need a real user PC with a GUI session. Do NOT claim "dictation anywhere" works end-to-end. |

## 2. MCP synthesis for clone voices — DONE, tested via endpoint

| Item | Status | Exact test result |
|---|---|---|
| Code | **Wired** | `backend/parity.py`: new `synthesize_clone()` — voice `clone_<reference-basename>` (e.g. `clone_kokoro_af_heart.wav`) or `voice="clone"` + `ref_wav` field; reference must exist in `output/` or `output/uploads/` (traversal/absolute rejected); routes through `backend/clone.py` Chatterbox. `POST /api/mcp/speak` now routes clone voices there before Parler/Edge/Kokoro. A failed clone call returns `synthesized: false` with the real error, no fallback voice substituted. `/api/parity/status` mcp_speak text updated to include clone. |
| Bug found + fixed | **Tested** | First run: Chatterbox returns a torch tensor, and `soundfile.write()` on the raw tensor failed with `"Format not recognised"` for `output/mcp_clone_test.wav`. Fixed in `synthesize_clone()` only (clone.py untouched): tensor → `detach().cpu().numpy()`, and a (1, N) mono tensor transposed to (N,) so soundfile does not read it as 1 sample / N channels. |
| Direct test | **Tested, synthesized** | Mahbub venv, text "This is VoxLab.", reference `output/kokoro_af_heart.wav` (synthetic Kokoro sample, permission-safe) → `{'ok': True, 'output': 'mcp_clone_test.wav', 'seconds': 1.4, 'sample_rate': 24000, 'engine': 'chatterbox-clone'}`, ffprobe duration 1.400000 s, file 67,244 bytes. |
| Via server endpoint | **Tested, synthesized** | Live server (mahbub venv, port 8000), `POST /api/mcp/speak {agent: default, voice: clone_kokoro_af_heart.wav, text: "This is VoxLab."}` → 200, `synthesized: true`, `audio: mcp_default_clone.wav`, `seconds: 0.72`, `engine: chatterbox-clone`, `reference: kokoro_af_heart.wav`. `GET /api/parity/audio/mcp_default_clone.wav` → 200, 34,604 bytes. Duration differs from the direct run (1.4 s vs 0.72 s) — Chatterbox sampling is nondeterministic, not an error. `GET /api/voices` → 200 in the same server run. Test server stopped afterwards. |
| py_compile | **Tested** | `py_compile` on server.py, parity.py, clone.py, global_shortcut.py, llm.py, bengali.py → OK. |

## 3. GitHub push bundle preparation — VERIFIED, NOT pushed (per task)

| Item | Status | Exact result |
|---|---|---|
| Present + consistent | **Verified** | README.md (3,671 B, stale lines fixed in this task: Bengali wiring now "DONE", parity list now Qwen3-0.6B tested / others needs_download, Layout no longer claims a /api/clone route — clone.py is a standalone module), LICENSE (MIT, Copyright (c) 2026 Ishtiaque Hasib, 1,221 B), CONTRIBUTING.md (1,207 B), SECURITY.md (952 B), workflows windows/macos/linux-installer.yml (2,814 / 2,866 / 2,627 B, all YAML-validated earlier, Python 3.12 + PyInstaller, models NOT bundled), backend/server.py, parity.py, clone.py, bengali.py, parler_cli.py, llm.py, global_shortcut.py (new), requirements.txt (now with optional pynput/pyperclip), app/index.html + app/logo.png, assets/voxlab-logo.png + voxlab-favicon.png. |
| Would-be-pushed total | **3,342,310 bytes (~3.3 MB)** | 30 files listed below (before this PARITY.md edit grows it slightly). No file over the GitHub 100 MB limit. Largest: app/logo.png and assets/voxlab-logo.png at 1,445,267 B each (same 1.4 MB logo duplicated — harmless, but could be deduplicated later), blogger-theme.xml 261,185 B, assets/voxlab-favicon.png 60,975 B. All other files are under 30 KB. |
| Would-be-pushed files | **List** | .github/workflows/linux-installer.yml, macos-installer.yml, windows-installer.yml; .gitignore; AUDIT.md; COMPETITOR_ANALYSIS.md; CONTRIBUTING.md; LICENSE; PARITY.md; README.md; SECURITY.md; app/index.html; app/logo.png; assets/voxlab-favicon.png; assets/voxlab-logo.png; audit_transcribe.py; backend/bengali.py, clone.py, global_shortcut.py, llm.py, parity.py, parler_cli.py, requirements.txt, server.py; blogger-theme.xml (see flag below); test_chatterbox.py, test_kokoro.py, test_kokoro_onnx.py, test_qwen3.py, test_whisper_turbo.py. |
| Excluded by .gitignore | **Verified** | venv_parler/ (1.7 GB, pinned transformers venv), output/ (340 MB, 20 files incl. Kokoro ONNX 310 MB + voices 27 MB + all test MP3/WAV), tmp/, venv/, .venv/, __pycache__/, *.pyc, github-profile/ (see below). `.gitignore` was tightened in this task (added venv/, .venv/, tmp/, github-profile/). This tree is NOT a git repository yet (`git status` → "not a git repository"), so nothing was staged or pushed. |
| Flags for the parent before pushing | **Decide, do not assume** | (a) `github-profile/README.md` (1,444 B) is a SUPERSEDED local draft — the live profile README is already on GitHub (ishtiaquehasib/ishtiaquehasib) — it is now gitignored and must NOT be pushed. (b) `blogger-theme.xml` (261,185 B) is the Blogger website theme, not app code; it is currently in the tree and would be pushed with a whole-tree `git add .` — decide to keep it, move it under a website/ folder, or exclude it before pushing. (c) Homepage/topics for the repo (website https://voxlabapp.blogspot.com, topics ai/voice-clone/tts/bengali-tts/chatterbox/kokoro/parler-tts/whisper/voice-ai/open-source) can only be set via the GitHub About editor after the first push, per the earlier browser task. |

## Final remaining list (after this task — no papered-over gaps)
1. Live browser mic test — recorder JS is code-reviewed only; subagents have no live browser/mic.
2. System capture end-to-end test — implemented for Linux PulseAudio, untestable on this VM (no audio server, no pactl, apt install failed/stalled); Windows WASAPI and macOS BlackHole paths are documentation only.
3. Global dictation shortcut + paste — module implemented and headless-tested, but live hotkey/clipboard/paste on a real desktop NOT tested; mic-recording + shortcut wiring into a packaged desktop shell NOT built.
4. LLM rewrite quality — Qwen3-0.6B is real but minimal/sometimes verbatim; stronger rewriting would need a larger Qwen3 (not downloaded).
5. Parity models still needs_download, none downloaded/tested: Chatterbox Turbo, LuxTTS, TADA, Qwen CustomVoice, Whisper Turbo. (Qwen3 LLM is DONE at 0.6B; Whisper small is used for dictation; test_whisper_turbo.py exists as a script but Whisper Turbo was NOT run/downloaded in this task.)
6. Parler speakers beyond Arjun — same code path, not individually generated; Parler Edge-fallback header path in /api/generate still coded, not live-triggered.
7. Real installer binaries + GitHub release — workflows only (Windows/macOS/Linux, YAML-validated), no Actions run; repo https://github.com/ishtiaquehasib/VoxLab was created earlier by the parent (empty, no push yet) — this task did NOT push, per instructions.
8. Testimonials — deliberately none; real users only after release. Demo/sample only if labelled Demo, never as a testimonial.
9. Push-bundle decision flags above (blogger-theme.xml, github-profile exclusion already handled, homepage/topics after first push).

# VoxLab remaining parity models — 2026-10-26 (Whisper Turbo DONE; Chatterbox Turbo / Qwen CustomVoice / LuxTTS / TADA in progress below)

## Whisper Turbo — DONE, tested

| Item | Status | Exact test result |
|---|---|---|
| Model | **Downloaded, tested** | faster-whisper `large-v3-turbo` (CTranslate2 conversion `mobiuslabsgmbh/faster-whisper-large-v3-turbo`), 1.6 GB in `~/.cache/huggingface/hub/models--mobiuslabsgmbh--faster-whisper-large-v3-turbo/`. First download attempt failed after 72 MB with `ConnectionError: 403 Forbidden` on the xet CDN (`us.aws.cdn.hf.co/xorbs/...`); retry with `HF_HUB_DISABLE_XET=1` completed the 1.6 GB download. |
| Test | **Tested, exact transcript** | Script `test_whisper_turbo.py` (librosa decode, same av workaround as dictation): model load 12.2 s, transcribe 25.2 s, total 43.9 s (offline rerun, model cached). Input `output/kokoro_af_heart.wav` (8.13 s) → transcript exactly: "Hello, this is a free voice studio running on my own computer. No account, no subscription, just open models and my own voice.", language `en`, duration 8.13 s. No transcript invented. |
| Note | Whisper Turbo is the transcription engine, not a voice — it does not change the in-page dictation default (small) yet; wiring it as the dictation engine is still to do. |

## Chatterbox Turbo — DONE, tested

| Item | Status | Exact test result |
|---|---|---|
| Model | **Downloaded, tested** | `ResembleAI/chatterbox-turbo` (350M, MIT), 4.0 GB in `~/.cache/huggingface/hub/models--ResembleAI--chatterbox-turbo/`. First run failed at 3.1 GB with `ChunkedEncodingError: IncompleteRead(539129742 bytes read, 517354878 more expected)`; retry resumed the partial files (fetch 10/10 in 3:10) and completed. Code path: installed `chatterbox-tts` 0.1.7 `ChatterboxTurboTTS.from_pretrained(device="cpu")` — no new package install needed. |
| Test | **Tested, exact transcript** | Script `test_chatterbox_turbo.py`: clone from synthetic `output/kokoro_af_heart.wav` (8.128 s, >5 s Turbo minimum), text "This is VoxLab, a free voice studio running on my own computer." → `output/chatterbox_turbo_clone.wav`, sr 24000, shape (1, 91200), **3.80 s, 182,444 bytes**. Cross-check with faster-whisper small: transcript exactly "This is VoxLab, a free voice studio running on my own computer.", lang en. PerTh watermark is applied by the Turbo code (its own `PerthImplicitWatermarker`), as in the upstream library. |
| Note | Paralinguistic tags (`[laugh]` etc.) were NOT tested in this run — only the plain clone sentence. Do not claim tag support tested. |

## Qwen CustomVoice — DONE, tested

| Item | Status | Exact test result |
|---|---|---|
| Model | **Downloaded, tested** | `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice` (public, ungated), 2.5 GB total (model.safetensors 1,812 MB + speech_tokenizer 682 MB) in `~/.cache/huggingface/hub/models--Qwen--Qwen3-TTS-12Hz-0.6B-CustomVoice/`. Code path: installed `qwen-tts` 0.1.1 `Qwen3TTSModel.generate_custom_voice()`, CPU float32, same package as the earlier Base test. |
| Test | **Tested, exact transcript** | Script `test_qwen_customvoice.py`: speaker `Ryan`, language English, text "This is VoxLab, a free voice studio running on my own computer." → `output/qwen_customvoice_ryan.wav`, sr 24000, **5.04 s, 241,964 bytes**. Supported speakers printed by the model: aiden, dylan, eric, ono_anna, ryan, serena, sohee, uncle_fu, vivian (9). Cross-check with faster-whisper small: transcript exactly the target sentence, lang en. SoX-not-found and flash-attn warnings are harmless (same as the Base test). |
| Note | Only Ryan was generated; the other 8 preset speakers use the same code path but were NOT individually generated. Instruct-style control (1.7B model) was NOT tested — 0.6B only. |

## LuxTTS — ISSUE SOLVED 2026-10-26 (retest): EXACT with the right settings

| Item | Status | Exact test result |
|---|---|---|
| Retest script | **One load, 5 variants + 2 confirmations** | `test_luxtts_retest.py` (loads LuxTTS + faster-whisper small once, encodes once, generates 5 variants, transcribes each) + `test_luxtts_confirm.py`. Total retest wall 137.5 s. Target sentence for every variant: "This is VoxLab, a free voice studio running on my own computer.", reference `output/kokoro_af_heart.wav` (synthetic, permission-safe). |
| A baseline (repeat of the old run) | **NOT exact — issue reproduced** | encode duration=5, steps=4, speed=1.0 → 2.95 s, 283,692 bytes (byte-identical size to the old run), transcript "A free voice studio running on my own computer.", gen 12.4 s. |
| B more steps | **NOT exact** | duration=5, steps=16, speed=1.0 → 2.95 s, transcript "lab, a free voice studio running on my own computer.", gen 27.1 s. Steps alone do not fix it. |
| C slower | **NOT exact** | duration=5, steps=8, speed=0.7 → 6.38 s, 612,396 bytes, transcript "Lab, a free voice studio running on my own computer.", gen 21.7 s. Slower alone does not fix it. |
| D slower + smooth | **NOT exact** | duration=5, steps=8, speed=0.7, return_smooth=True → 6.38 s, transcript "and having good spirits? This is VoxLab, a free voice studio running on my own computer." — the full target is present but whisper hears a garbled lead-in, so NOT exact. (return_smooth had no effect on duration/size in the CPU ONNX path.) |
| E full reference + slow | **EXACT** | encode duration=8 (the full 8.13 s reference; whisper-tiny prompt text then the complete reference sentence), steps=8, speed=0.7 → **5.37 s, 515,116 bytes, ffprobe 5.365333 s, transcript exactly the target sentence, lang en, gen 28.2 s.** |
| F1 repeat of E | **EXACT, repeatable** | Same settings as E → 5.37 s, 515,116 bytes, transcript exactly the target, gen 24.5 s. |
| F2 full ref, baseline speed/steps | **NOT exact — proves the combination matters** | duration=8, steps=4, speed=1.0 → 1.35 s, 130,092 bytes, transcript "You're the only one I'm on.", gen 11.4 s. Full reference alone is NOT enough; the fix is the combination: full reference + steps=8 + speed=0.7. |
| Independent cross-check | **EXACT on both files** | faster-whisper large-v3-turbo (independent of small) transcribed BOTH `output/luxtts_retest_E_fullref_slow8.wav` and `output/luxtts_confirm_F1_repeat_E.wav` as exactly the target sentence, lang en. |
| Recommended LuxTTS settings | **Use these** | `encode_prompt(ref, rms=0.01, duration=8)` (or the full reference length), `generate_speech(text, enc, num_steps=8, speed=0.7)`. Do NOT use the old defaults (duration=5, steps=4, speed=1.0) — they drop the opening words. |
| Note | The 150x-realtime GPU claim was NOT verified here (CPU only, no GPU on this VM). |

## LuxTTS — OLD TEST, with a real quality issue (SUPERSEDED by the retest above — do NOT use this section's verdict)

| Item | Status | Exact test result |
|---|---|---|
| Model/code | **Downloaded, tested** | `YatharthS/LuxTTS` (public, ungated), 1.18 GB total (model.pt 491 MB, fm_decoder.onnx 478 MB, vocoder/vocos.bin 64 MB, etc.) in `~/.cache/huggingface/hub/models--YatharthS--LuxTTS/`. Code: `ysharma3501/LuxTTS` (Apache-2.0), cloned to `luxtts_src/` (gitignored, test-only copy, not VoxLab code). CPU path uses ONNX (`load_models_cpu`, `generate_cpu`) + Vocos 48 kHz vocoder + a whisper-tiny transcriber for the reference prompt. Extra deps installed into the mahbub venv for this test only: lhotse 1.33.0, onnxruntime (already present), linacodec 0.0.11 (git), piper_phonemize 1.5.9 (with the k2-fsa find-links URL), cn2an, inflect, jieba, pypinyin. Note: `/tmp/luxtts` was cleared mid-task (tmpfs is ephemeral) — the clone was redone under `luxtts_src/`. |
| Test | **Generated audio, but transcript PARTIAL** | Script `test_luxtts.py`: clone from synthetic `output/kokoro_af_heart.wav`, text "This is VoxLab, a free voice studio running on my own computer.", num_steps=4 → `output/luxtts_clone.wav`, sr 48000, **2.95 s (2.954667 s), 283,692 bytes**, mean volume −24.2 dB, max −9.4 dB. Its internal whisper-tiny prompt transcription printed "Hello, this is a free voice studio running on my own computer." (the 5 s prompt window cuts the 8.13 s reference). Output cross-check, TWO engines agreeing: faster-whisper small AND large-v3-turbo both transcribed the output as "Lab, a free voice studio running on my own computer." — i.e. the opening "This is Vox" is missing/inaudible in the LuxTTS output. So LuxTTS works as a clone engine here, but this run does NOT pass the exact-sentence check. Do not claim LuxTTS exact until a retest (e.g. different ref_duration / speed / return_smooth) produces the full sentence. |
| Note | The 150x-realtime GPU claim was NOT verified here (CPU only, no GPU on this VM). |

## TADA — RETRY 2026-10-26: install + weights SOLVED, generation BLOCKED on the gated Llama tokenizer (exact evidence)

| Item | Status | Exact result |
|---|---|---|
| Separate venv (the real fix for the old pip stall) | **Installed, working** | `venv_tada/` (1.7 GB, gitignored, must NOT be pushed): Python 3.12, torch/torchaudio/torchvision **2.7.1+cpu** (CPU index, satisfies pyproject `torch>=2.7.0,<2.8.0`), transformers **4.57.6**, descript-audio-codec 1.0.0, hume-tada **0.1.8** (installed from local `tada_src/` = cloned https://github.com/HumeAI/tada.git). `import torch` → 2.7.1+cpu, cuda False; `from tada.modules.tada import TadaForCausalLM; from tada.modules.encoder import Encoder` → "tada import ok". The old 12.5-min stall was pip's resolver fighting the shared mahbub venv's pinned packages, NOT TADA itself — in a clean venv every install completed. |
| Weights | **Downloaded, verified** | `HumeAI/tada-1b` (gated=False per HF API, licence llama3.2, base meta-llama/Llama-3.2-1B): model.safetensors 3,922 MB, download 22:25, cache 3.7 GB. `HumeAI/tada-codec` subset (encoder + decoder + aligner only, not the 10.72 GB full repo): download 14:21, cache 2.1 GB. Total ~5.8 GB, ~37 min at ~150 MB/min. `HF_HUB_DISABLE_XET=1` used (xet gave 403 on the Turbo download). |
| Weight integrity (metadata only, no full load) | **Verified** | safetensors metadata: tada-1b 394 tensors, BF16, config architectures=[TadaForCausalLM], model_type=llama, vocab=128256, 16 layers, hidden=2048; codec encoder 208 tensors BF16; decoder 207 BF16; aligner 405 BF16 with lm_head bias shape [128256] — i.e. the Llama 3.2 vocab, confirming the tokenizer below is the only missing piece. |
| Generation attempt | **FAILED at tokenizer load, no audio produced** | Script `test_tada.py` (official ljspeech.wav 7.58 s reference + README prompt text, CPU float32, target sentence same as the other model tests) → `Encoder.from_pretrained("HumeAI/tada-codec", subfolder="encoder")` fails in `Aligner.__init__`: `AutoTokenizer.from_pretrained("meta-llama/Llama-3.2-1B")` → OSError (not in cache, offline run). The same default tokenizer is used by `TadaForCausalLM` (tada.py line ~184), so the model load fails at the same step. No TADA audio was produced, none is claimed. |
| Why the tokenizer cannot be fetched here | **Gated, needs the user's HF action** | HF API: `meta-llama/Llama-3.2-1B` gated="manual", private=False. Anonymous download attempt → "Cannot access gated repo … You must have access to it and be authenticated". I did NOT hunt for an ungated mirror to bypass Meta's licence gate — that would sidestep a licence acceptance the user has not given. The tada-1b weights themselves are ungated; only the Llama tokenizer (and the Llama licence) is gated. |
| CPU feasibility — CORRECTED | **Code allows CPU** | The old note "official example is CUDA-only" was incomplete: README examples use `device="cuda"`, but `tada/modules/tada_test.py` uses `device = "cpu" if not torch.cuda.is_available() else "cuda"`, and the code guards CUDA calls with `torch.cuda.is_available()`. So CPU generation is not ruled out by the code — it is untested only because the tokenizer blocks loading. On this VM (2 CPU, ~7 GB RAM) a 1B BF16 model (~2 GB weights + encoder/codec) may still be slow, but that is unproven, not a proven failure. |
| Exact retry path (GPU Windows PC or after HF acceptance) | **Ready, nothing to redo except the tokenizer** | 1) On the user's HF account, accept the Meta Llama 3.2 licence for meta-llama/Llama-3.2-1B and provide an HF token via the secure flow (never in chat). 2) In `venv_tada`: `huggingface_hub` download of the tokenizer files (tokenizer.json, tokenizer_config.json, special_tokens_map.json) — or simply rerun `test_tada.py` online (it will fetch the tokenizer, ~a few MB). 3) Run `venv_tada/bin/python test_tada.py` (CPU float32; on a Windows GPU PC use device="cuda" + bf16 per README). Weights, codec, venv and test script are all already in place; do NOT re-download the 5.8 GB. |
| Test script | `test_tada.py` (new), `tada_src/` (cloned repo, gitignored, test-only), `venv_tada/` (gitignored). `py_compile` on parity.py → OK (status text updated). |

## TADA — OLD BLOCKED NOTE (SUPERSEDED by the retry above — pip stall and "CUDA-only" claims are corrected there)

| Item | Status | Exact evidence |
|---|---|---|
| Model existence | **Public, ungated, but large** | `HumeAI/tada-1b` (Llama 3.2 1B, MIT) — HF API: gated=False, model.safetensors **3,922 MB**. Shared codec `HumeAI/tada-codec` — gated=False, 10.72 GB total, but only the English-relevant subset is needed: encoder 602 MB + decoder 653 MB + aligner 894 MB = **2,149 MB**. Minimum TADA-1B download ≈ **6.1 GB**. At this VM's observed HF download rate (~150 MB/min, see Turbo/Qwen runs), that is ~40 min of download alone, before any generation. |
| Package install | **Failed / abandoned after 12.5 min, not installed** | `pip install --no-cache-dir hume-tada` in the mahbub venv ran 12 min 31 s with no output (pip output piped through tail) and no completion; the process was killed (SIGTERM) and `pip list` confirms **hume-tada is NOT installed**. The package itself is small (PyPI 0.1.6: wheel 1.5 MB, total release 2.9 MB), so the stall was dependency resolution/download through the slow proxy, not the package size — the exact dependency that stalled was not visible in pip's buffered output, so it is NOT guessed here. |
| CPU feasibility | **No documented CPU path** | The official inference example (PyPI 0.1.6 README) uses `device = "cuda"` only, with no CPU example. This VM has **no GPU** (torch 2.6.0+cu124 installed, but no CUDA device), 2 CPU cores, ~7 GB RAM. A 1B Llama-based autoregressive model on CPU here would be far slower than the already-slow Qwen/Chatterbox CPU runs, with no evidence it completes in reasonable time. |
| Verdict | **BLOCKED — needs_download, do not claim** | TADA remains `needs_download` / blocked on this VM. It is NOT gated and NOT ruled out in principle — on a GPU PC, or with a longer download window, the 1B model + codec subset + `pip install hume-tada` (from source if pip stalls again: `git clone https://github.com/HumeAI/tada.git`) could be retried. No TADA audio was produced, none is claimed, and no TADA test file exists. |
| Regression check | Venv intact after the killed install | `py_compile` on server.py, parity.py, clone.py, llm.py, bengali.py → OK; `import faster_whisper, torch` → ok, torch 2.6.0+cu124. |

## Final remaining list (after this task)

1. **TADA** — blocked as above (6.1 GB weights, pip stall, no GPU / no CPU example). Retry only on a GPU PC or with a long download window.
2. LuxTTS exact-sentence retest — LuxTTS works but dropped "This is Vox" in this run; retest with different ref_duration / speed / return_smooth before claiming exact.
3. Chatterbox Turbo paralinguistic tags (`[laugh]` etc.) — not tested; only the plain clone sentence was.
4. Qwen CustomVoice other 8 speakers — same code path, not individually generated; 1.7B instruct control not tested.
5. Whisper Turbo wiring as the dictation engine — Turbo is tested as a transcriber, but in-page dictation still defaults to small.
6. Live browser mic test, system-capture end-to-end test, global dictation shortcut, MCP clone voices, installer binaries + GitHub release, testimonials — unchanged from earlier sections (see below).

# VoxLab remaining work — 2026-10-26 (LLM personalities DONE, MCP Parler/Edge DONE, system capture implemented but NOT testable on this VM)

## 1. Real LLM personalities — DONE, tested, with an honest quality limit

| Item | Status | Exact test result |
|---|---|---|
| Model | **Downloaded, 0.6B only** | `Qwen/Qwen3-0.6B` (chat model, NOT the larger sizes), snapshot `c1899de289a04d12100db370d81485cdf75e47ca`, 10 files, 1.5 GB in `~/.cache/huggingface/hub/models--Qwen--Qwen3-0.6B/`, download took 5:06. No other parity model was downloaded in this task. |
| Code | **Wired, llm_used flag real** | New `backend/llm.py` (lazy load, CPU float32, never loaded at import; `model_cached()` checks the cache without network). `backend/parity.py` Rewrite/Compose now try the LLM first and return `llm_used: true` ONLY on a real generation; any failure falls back to the template with the real error in `note`. `backend/parity.py` PARITY_MODELS qwen3-llm status updated from needs_download to tested. |
| Thinking-model fix | **Tested** | First test: Qwen3's `<think>` block ate the whole 120-token budget and the answer was truncated. Fix in `llm.py`: `apply_chat_template(..., enable_thinking=False)` plus a regex strip of any `<think>...</think>` block. After the fix, answers are direct. |
| Rewrite, direct | **Tested, llm_used=true, quality MINIMAL** | "The app is free and it runs on your own computer, with no account needed." → with the anti-copy prompt: "The app is free and it runs on your own computer, requiring no account." (a genuine but minimal reword). Earlier runs of the same prompt returned the input verbatim — sampling at temperature 0.7 is nondeterministic, and the 0.6B model sometimes copies. Via endpoint, the same input returned verbatim with `llm_used: true`. So: the LLM path is real and is NOT the template (template would prefix `[friendly narrator]`), but 0.6B persona rewriting is weak/minimal — do NOT claim strong persona rewriting. A larger Qwen3 would rewrite better but was NOT downloaded (task said 0.6B only). |
| Compose, direct + endpoint | **Tested, llm_used=true** | Direct: `"Good morning! Enjoy your cup of coffee!"` / `"Good morning, enjoy your cup of coffee!"` (sampling variance). Via endpoint: `"☕ Good morning! 🌞"` with `method: qwen3-llm, llm_used: true`. On-topic, short, persona-appropriate. |
| Test command | `py_compile` on parity.py, llm.py, server.py → OK. |

Files: `backend/llm.py` (new), `backend/parity.py` (rewrite_text/compose_text LLM-first + template fallback).

## 2. System capture — IMPLEMENTED for Linux, NOT testable on this VM (exact reason, no fake)

| Item | Status | Exact test result |
|---|---|---|
| Code | **Implemented** | `backend/parity.py`: `_monitor_sources()` (pactl `*.monitor` detection), `capture_info()` now reports real `monitor_sources` / `detection_method` / `detection_error` and `available: true` ONLY if a monitor source is actually found, `capture_system_audio()` (ffmpeg `-f pulse -i <monitor> -t <1-60s>`, file must exist and be non-empty or ok=false), new endpoint `POST /api/parity/capture`, Windows WASAPI and macOS BlackHole documented as setup steps in capture_info (not claimed as done). |
| Via server | **Tested to honest failure** | `GET /api/parity/capture-info` → `{"platform": "Linux", "status": "needs_os_setup", "available": false, "monitor_sources": [], "detection_error": "pactl not installed and no monitor source found"}`. `POST /api/parity/capture {"duration": 3}` → HTTP 503, `{"ok": false, "error": "no PulseAudio monitor source found: pactl not installed and no monitor source found"}`. No capture file was created, none is claimed. |
| Why it cannot be tested here | **This VM has no audio server** | `pactl`, `pulseaudio`, `pipewire`, `wpctl`, `parec` are all absent; `/run/user/*/pulse/` does not exist; no monitor source exists to capture. Attempted install: `apt-get install pulseaudio` → "Package 'pulseaudio' has no installation candidate" in the initial index; `apt-get update` stalled for 8+ minutes and was killed. So the Linux path is code-complete but unproven end-to-end — it needs a real user PC (Windows WASAPI / macOS BlackHole / Linux PulseAudio monitor) to test. Do NOT claim system capture works. |

## 3. MCP synthesis for Parler/Edge — DONE, tested

| Item | Status | Exact test result |
|---|---|---|
| Code | **Wired** | `backend/parity.py`: `synthesize_bengali()` routes parler_ via `bengali.generate_parler()` (venv_parler) and edge_ via `bengali.generate_edge()` (Deno server), with ffprobe duration for Edge; `POST /api/mcp/speak` now routes parler_/edge_ there BEFORE Kokoro. A failed Parler/Edge MCP call returns `synthesized: false` with the real error — NO silent Edge fallback for a requested Parler voice in MCP (unlike /api/generate, which does fall back with a header). |
| MCP Parler, via server | **Tested, synthesized: true** | `POST /api/mcp/speak {agent: default, voice: parler_arjun, text: "আসসালামু আলাইকুম, আমি ভক্সল্যাব।"}` → 200, `synthesized: true`, `audio: mcp_default.wav` (261,164 bytes), `seconds: 2.961`, `engine: parler`, ffprobe 2.960544 s, `GET /api/parity/audio/mcp_default.wav` → 200, 261,164 bytes. |
| MCP Edge, via server | **Tested, synthesized: true** | Same text, voice edge_pradeep → 200, `synthesized: true`, `audio: mcp_default.mp3` (18,720 bytes), `seconds: 3.12`, `engine: edge`, ffprobe 3.12 s. |
| Regression | **Tested** | `GET /api/voices` → 200 (full list). Test server stopped afterwards, port 8000 free. Note: an old server process (PID 3428, started 11:03 by an earlier task) was found still bound to port 8000 during this task and was killed before the new tests — earlier curl output in this session hit that stale server until it was replaced. |

Files: `backend/parity.py` (synthesize_bengali, MCP routing, capture, PARITY_MODELS + status text), `backend/llm.py` (new).

## Final remaining list (after this task — no papered-over gaps)
1. Live browser mic test — recorder JS is code-reviewed only; subagents have no live browser/mic.
2. System capture end-to-end test — implemented for Linux PulseAudio, untestable on this VM (no audio server, no pactl, apt install failed/stalled); Windows WASAPI and macOS BlackHole paths are documentation only.
3. Global dictation shortcut + paste into any app/clipboard — in-page dictation only.
4. LLM rewrite quality — Qwen3-0.6B is real but minimal/sometimes verbatim; stronger rewriting would need a larger Qwen3 (not downloaded) or a different prompt/model, not yet done.
5. Parity models still needs_download, none downloaded/tested: Chatterbox Turbo, LuxTTS, TADA, Qwen CustomVoice, Whisper Turbo. (Qwen3 LLM is now DONE at 0.6B; Whisper small is already used for dictation, Whisper Turbo is a different model.)
6. MCP synthesis for clone voices — still returns synthesized: false (clone engine not wired to MCP).
7. Parler speakers beyond Arjun — same code path, not individually generated; Parler Edge-fallback header path in /api/generate still coded, not live-triggered.
8. Real installer binaries + GitHub release — workflows only (Windows/macOS/Linux, YAML-validated), no Actions run, repo not published (parent's release gate, NOT done here — this task was told not to push).
9. Testimonials — deliberately none; real users only after release. Demo/sample only if labelled Demo, never as a testimonial.

# VoxLab all-OK work — 2026-10-26 (Parler FIXED via pinned venv; macOS/Linux workflows added)

## Priority 1 — Parler Bengali: FIXED, tested end-to-end

| Item | Status | Exact test result |
|---|---|---|
| venv_parler (separate, pinned) | **Tested, working** | `~/workspace/voice-studio/venv_parler/`: transformers **4.46.1** (the exact version parler-tts 0.2.2 requires; 4.46.3 was rejected by pip with ResolutionImpossible, 4.46.1 alone installed cleanly), torch/torchaudio **2.8.0+cpu** (matched pair — torch 2.14.1+cpu broke torchaudio 2.11 with an ABI .so load error, so torch was downgraded to 2.8.0). Install notes: transformers alone first, then parler-tts --no-deps, then descript-audiotools, descript-audiotools-unofficial, descript-audio-codec, sentencepiece, protobuf 4.25.9. Model NOT re-downloaded: HF_HUB_OFFLINE=1, cached RXD03/indic-parler-tts-pretrained (3.6 GB) reused. `from parler_tts import ParlerTTSForConditionalGeneration` → "parler import ok". Venv size 1.7 GB, local-only, listed in .gitignore, must NOT be pushed to GitHub. |
| Parler generation, direct | **Tested, working** | `venv_parler/bin/python output/bn_parler_test_446.py`, text "আসসালামু আলাইকুম, আমি ভক্সল্যাব।", speaker arjun → `parler_ok seconds=2.97 sr=44100 wall=132.9s`, file `output/bn_parler_test.wav`, **262,188 bytes, ffprobe 2.972154 s**. |
| Parler generation, via server | **Tested, working** | Server run under the OLD mahbub venv (transformers 4.57.3) on port 8000, `POST /api/generate` voice parler_arjun, same sentence → **HTTP 200, 26,079 bytes MP3, ffprobe 2.798005 s, NO X-VoxLab-Voice-Fallback header** (so this was real Parler audio, not the Edge fallback). The server route works because `backend/bengali.py:generate_parler()` now spawns `backend/parler_cli.py` under venv_parler when that venv exists, and only falls back to in-process generation if the venv is absent. |
| Edge regression, via server | **Tested, still working** | Same server run, voice edge_pradeep, same sentence → **HTTP 200, 18,720 bytes, 3.12 s** — identical to the earlier Edge test. `GET /api/voices` → 200. `py_compile` on server.py, bengali.py, parler_cli.py, parity.py → OK. Test server stopped afterwards. |
| Parler failure fallback | **Coded, not live-triggered** | `backend/server.py` parler_ route: if `generate_parler()` raises, it logs the error and returns Edge audio (female speakers aditi/rashmi/riya → edge_nabanita, others → edge_pradeep) with header `X-VoxLab-Voice-Fallback: edge_*`, so a fallback is never mistaken for the requested Parler voice. This fallback path was NOT triggered in the tests above (Parler succeeded), so it is code-reviewed only, not live-tested. |

Files: `backend/parler_cli.py` (new, venv-only worker), `backend/bengali.py` (generate_parler renamed in-process to `generate_parler_inprocess`, new `generate_parler()` prefers the venv subprocess), `backend/server.py` (parler_ route + Edge fallback header), `.gitignore` (new: venv_parler/, parler_venv_tmp/, output/, __pycache__). The earlier "Parler blocked" section below is superseded by this section.

## Priority 2 — macOS/Linux installer workflows: files created, YAML validated, NO real run yet

- Created: `.github/workflows/macos-installer.yml` — matrix macos-14/arm64 (VoxLab-macOS-ARM64) + macos-13/x64 (VoxLab-macOS-Intel), 7 steps, ditto zip, same shape as windows-installer.yml (Python 3.12, PyInstaller, app/ + logo as data, models NOT bundled, Release attach on v* tags only).
- Created: `.github/workflows/linux-installer.yml` — ubuntu-latest, 7 steps, tar.gz, same shape.
- Validated: PyYAML safe_load → YAML_OK for all three workflows (windows: build-windows, 7 steps, windows-latest; macos: build-macos, 7 steps, runs-on = matrix expression; linux: build-linux, 7 steps, ubuntu-latest).
- **Not a real run:** no macOS/Linux/Windows installer exists yet — a real Actions run can only happen after the repo is published to GitHub (parent's release gate, NOT done in this task). Do not claim any installer exists.

## All-OK checklist (2026-10-26, after this task)

### NOW OK (tested, exact results above or in earlier sections)
- v1 Kokoro generate/voices — intact (server tests pass).
- Bengali Edge presets — tested (200, 18,720 bytes, 3.12 s).
- Bengali Parler speakers — NOW tested (direct 2.97 s / 262,188 bytes; via server 200 / 26,079 bytes MP3, no fallback header). Arjun tested; other Parler speakers (aditi/tapan/rashmi/arnav/riya) use the same code path but have NOT each been generated — do not claim all six speakers individually tested.
- Dictation in-page (faster-whisper via librosa) — tested earlier, exact transcript.
- MCP synthesis for Kokoro presets — tested earlier (af_bella 1.365 s, af_heart 3.925 s).
- Stories (ffmpeg concat) and effects (atempo/volume/aecho) — tested earlier.
- Record upload, mic-recorder UI code, MCP UI player — code + upload tested; live mic NOT tested (below).
- Installer workflow FILES for Windows, macOS (ARM+Intel), Linux — YAML validated, 7 steps each.

### STILL NOT OK (honest, not papered over)
1. Live browser mic test (recorder JS is code-reviewed only; subagents have no live browser/mic).
2. System capture implementation (WASAPI / BlackHole / PulseAudio monitor) — info endpoint only, `available: false`.
3. Global dictation shortcut + paste into any app/clipboard — dictation works inside the page only.
4. Real LLM personalities (Qwen3 LLM) — Rewrite/Compose still template-only, `llm_used: false`.
5. Parity models — Chatterbox Turbo, LuxTTS, TADA, Qwen CustomVoice, Whisper Turbo, Qwen3 LLM: all still `needs_download`, none downloaded or tested in this task.
6. MCP synthesis for non-Kokoro voices (Parler/Edge/clone) — MCP returns `synthesized: false` for those; Parler/Edge work via `/api/generate`, not via `/api/mcp/speak`.
7. Parler Edge-fallback header path — coded, not live-triggered (Parler succeeded in tests).
8. Individual Parler speakers beyond Arjun — same code path, not individually generated.
9. Real installer binaries and GitHub release — workflows only, no Actions run, no repo published (parent's release gate, NOT done here).
10. User testimonials — deliberately none. Never invent testimonials; collect real ones only after real users use VoxLab. Demo/sample may be made only labelled Demo, never as a testimonial.
11. No model downloads in this task except the already-cached Parler model reused offline; no GitHub push; no other project touched; no testimonials/stars/downloads invented.

# VoxLab parity scaffold — 2026-10-26 (updated: Bengali wiring — Edge works, Parler blocked; Windows installer workflow)

## Bengali generation wiring (this task)

| Voice path | Status | Exact test result |
|---|---|---|
| Edge presets via /api/generate (edge_nabanita, edge_pradeep) | **Tested, working** | Server POST /api/generate, text "আসসালামু আলাইকুম, আমি ভক্সল্যাব।", voice edge_pradeep → HTTP 200, 18,720 bytes, ffprobe duration **3.12 s**. Re-tested after a runtime restart with the same result (200, 18,720 bytes, 3.12 s). Route: backend/bengali.py generate_edge() → user's own Deno server, secret read programmatically from the local Deno source, never printed/logged/committed. |
| Parler speakers via /api/generate (parler_arjun etc.) | **Blocked in this venv, NOT working** | Same one-sentence test via backend/bengali.py generate_parler("…", "arjun") failed four times in a row, each at a different transformers 4.57 incompatibility (the shared venv's transformers was upgraded to 4.57.3 by later chatterbox/qwen installs; the mahbub Parler test passed in 2026-10-26 00:20 under the older transformers). Errors in order: (1) ParlerTTSConfig.to_diff_dict default-init ValueError → patched (fallback to to_dict, load OK); (2) generation_config loaded as None → patched (restored from the checkpoint's own 4.46.1 values, bos 1025 / eos 1024 / pad 1024); (3) _validate_model_kwargs missing (ParlerTTS no longer inherits GenerationMixin in 4.57) → patched (bound mixin method); (4) _prepare_model_kwargs/_prepare_model_inputs missing, same root cause — generation still fails, no audio file produced. Stopping the patch-by-patch route here: each step exposes another removed mixin method. **Real fix, not yet done:** a separate venv pinned to transformers ~4.46 (the version the checkpoint was written under), reusing the already-cached RXD03 model — no new model download needed. Until that venv exists and a Parler test passes, Parler must be labelled not-working, and the server's parler_ route will fail honestly with the real error. |
| Bengali UI | Wired | app/index.html gen() now sends the selected voice's real lang (bn) instead of the first letter of the voice id, which was wrong for bn voices. Server dispatch ignores lang for bn voices and routes on the voice id, so the old UI could not have broken it. |

Files: backend/bengali.py (new, Edge + Parler code paths, Parler patches documented in-code), backend/server.py (/api/generate dispatches edge_/parler_ before Kokoro; Kokoro path unchanged), app/index.html (lang fix only). Test artifacts: output/bn_edge_test.mp3 (Edge, 3.12 s), output/bn_parler_test.py (Parler test script, no output audio produced).

## Windows installer workflow (this task)

- Created: .github/workflows/windows-installer.yml — runs on windows-latest, Python 3.12, installs backend/requirements.txt + PyInstaller, builds backend/server.py with app/ + logo as data, zips dist/VoxLab as VoxLab-Windows-x64.zip, uploads it as an artifact on every run, and attaches it to a GitHub Release only for v* tag pushes (softprops/action-gh-release@v2). No wine, no local Windows build, no model files bundled (they download on first run, per README).
- Validated: PyYAML safe_load → YAML_OK, job build-windows, 7 steps. **Not a real run:** a windows-latest run can only happen after the repo is published to GitHub (parent's release gate), so no installer exists yet and none is claimed.
- Nothing was pushed to GitHub in this task.

# VoxLab parity scaffold — 2026-10-26 (updated: mic recorder, dictation fix, MCP synthesis)

Status words used here, strictly:
- **Tested** = ran in this task with the exact command/result quoted.
- **Scaffold** = code exists, endpoint responds, but the full user-facing
  feature is not yet proven end-to-end.
- **Needs model download** = model was NOT downloaded in this task.
- **Needs OS setup** = OS-specific setup is required and was not done.
- No testimonials, star counts, or download counts are claimed anywhere
  in this scaffold. The app shows none.

## What was built (scaffold, not a finished release)

| Feature | Status | What still needs doing |
|---|---|---|
| Record — browser mic recorder (MediaRecorder, 30s cap, live waveform canvas, upload) + file upload (WAV/MP3/FLAC/WebM/OGG/M4A, max 50 MB) | Recorder code added, upload tested; live mic test NOT done by this agent (subagents cannot use a live browser/mic) | Live mic test in a real browser with mic permission; 30s auto-stop is coded, not live-tested |
| System capture | Needs OS setup, not performed | Windows WASAPI loopback, macOS BlackHole driver, Linux PulseAudio monitor — none bundled or tested |
| Dictation (in-page upload → transcript) | Tested, working via librosa decode (see below) | Global shortcut + paste-to-any-app is NOT built; dictation works inside this page only |
| MCP agent voice (`POST /api/mcp/speak`, per-agent voice) | Tested, synthesized with Kokoro ONNX for Kokoro preset voices (see below) | Synthesis for Parler/Edge/clone voices needs their own engines — those return synthesized: false with the reason |
| Personalities Rewrite / Compose | Template only, tested | Real Rewrite/Compose needs Qwen3 LLM, not loaded |
| Multi-voice stories (ffmpeg concat) | Scaffold, tested (previous task) | Real multi-voice generation per segment (needs TTS per speaker) — concat itself works |
| Audio effects (speed, volume, echo) | Scaffold, tested (previous task) | UI polish, preview — ffmpeg filters work |
| Chatterbox Turbo | Needs model download, not tested | Download + test, ~350M model, paralinguistic tags |
| LuxTTS | Needs model download, not tested | Download + test, CPU 48 kHz claim unverified here |
| TADA | Needs model download, not tested | Download + test, long-form 700s+ claim unverified here |
| Qwen CustomVoice | Needs model download, not tested | Download + test, 9 preset speakers |
| Whisper Turbo | Needs model download, not tested | Download + test, ~8x speed claim unverified here |
| Qwen3 LLM (transcript refinement, persona replies) | Needs model download, not tested | Download + test; Qwen3-TTS was tested before and dropped from v1, the LLM is a different model |
| Installer (Windows MSI, macOS, Linux) | Not built in this task | GitHub Actions build + Release — parent agent's release gate, not started here |
| User testimonials | Not created, deliberately | Never invent testimonials. Collect real ones only after real users use VoxLab |

## Endpoints (backend/parity.py, wired into backend/server.py, guarded)

- `GET /api/parity/status` — feature + model status, ffmpeg flag.
- `POST /api/parity/upload` — validated upload into output/uploads/.
- `GET /api/parity/capture-info` — OS capture note, capture_performed: false.
- `POST /api/parity/dictate` — faster-whisper if available, else HTTP 503 with the real error.
- `POST /api/mcp/speak` — {agent, text, voice?} → resolved voice, synthesized: false.
- `POST /api/parity/rewrite` — template framing, llm_used: false.
- `POST /api/parity/compose` — template line, llm_used: false.
- `POST /api/parity/story` — {segments: [filenames in output/]} → ffmpeg concat. Filenames are basenamed into output/; absolute/traversal paths cannot escape output/.
- `POST /api/parity/effect` — {input, speed 0.5–2.0, volume 0.1–3.0, echo} → ffmpeg atempo/volume/aecho.

UI: app/index.html gained Record, Dictate, MCP, Personalities, Stories,
Effects sections, each labelled Scaffold / Template only / Needs model
download. Existing Generate/voice UI was not changed.
2026-10-26 follow-up: Record section now has a MediaRecorder UI
(Start/Stop, 30s auto-stop, live waveform canvas via AnalyserNode,
playback, Upload recording → POST /api/parity/upload) plus the old file
upload as fallback. MCP section now has a Speak button + audio player
that plays /api/parity/audio/<file> when synthesized: true. Dictate
section label now states the librosa path and that no global shortcut
exists yet.

## What was actually tested (2026-10-26, follow-up task)

- `python -m py_compile backend/server.py backend/parity.py backend/clone.py` → OK.
- Server start (mahbub venv python, port 8000): started; `GET /api/voices`
  still returned the full Kokoro + Bengali list (200) — v1 intact.
- `GET /api/parity/status` → 200, ffmpeg_available: true, dictation now
  described as "faster-whisper via librosa decode", MCP as "mapping +
  Kokoro ONNX synthesis for Kokoro preset voices".
- Homepage `GET /` → contains startRec, mcpplayer, Record, Dictate,
  MCP agent voice sections (grep counts: Record 23, startRec 2, mcpplayer 2).
- Dictation, direct librosa test first: librosa.load
  (output/kokoro_af_heart.wav, sr=16000, mono) → WhisperModel small
  int8, transcribe(array, beam_size=5) → exact transcript in 17.9 s
  total including model load.
- Dictation, via endpoint: `POST /api/parity/dictate` with
  kokoro_af_heart.wav → 200, {"available": true, "transcript": "Hello,
  this is a free voice studio running on my own computer. No account,
  no subscription, just open models and my own voice.", "model":
  "small", "detected_language": "en"}. The old av metadata_errors 503
  is gone: transcribe() now decodes with librosa and passes the array,
  so av is never used for file decoding. No transcript was invented.
- MCP synthesis, claude: `POST /api/mcp/speak` {agent: claude, text:
  "Hello from VoxLab"} → 200, voice af_bella, synthesized: true,
  audio mcp_claude.wav (65 KB), seconds 1.365, engine kokoro-onnx.
- MCP synthesis, default: {agent: default, text: "This is VoxLab, a
  free voice studio running on my own computer."} → 200, voice
  af_heart, synthesized: true, audio mcp_default.wav (185 KB), seconds
  3.925, and `GET /api/parity/audio/mcp_default.wav` → 200, 188,460 bytes.
- MCP non-Kokoro voice: {agent: default, voice: parler_arjun, text:
  "Hello"} → 200, synthesized: false, error "voice parler_arjun is
  not a Kokoro preset voice; Parler/Edge/clone voices need their own
  engine". No fake audio claimed.
- Upload regression: `POST /api/parity/upload` kokoro_af_heart.wav →
  200, 390,188 bytes saved to output/uploads/.
- Test server was stopped after testing (background session killed).
- NOT tested: live browser mic recording (subagent has no live browser
  or mic; the recorder JS is code-reviewed only — getUserMedia,
  AnalyserNode waveform, 30s interval auto-stop, Blob upload as
  recording.webm), global dictation shortcut, system capture.

## What was actually tested (2026-10-26, this task)

- `python -m py_compile backend/server.py backend/parity.py backend/clone.py` → OK.
- Server start (mahbub venv python, port 8000): started, `/api/voices`
  still returned the full Kokoro + Bengali voice list (200).
- `GET /api/parity/status` → 200, ffmpeg_available: true, all six parity
  models listed as needs_download.
- `POST /api/mcp/speak` {agent: claude, text: "Hello from VoxLab"} → 200,
  voice af_bella, synthesized: false (honest scaffold response).
- `POST /api/parity/rewrite` → 200, method template, llm_used: false,
  original text preserved verbatim inside the framed output.
- `POST /api/parity/compose` → 200, method template, llm_used: false.
- `GET /api/parity/capture-info` → platform Linux, status needs_os_setup,
  available: false, capture_performed: false.
- Story: concat of kokoro_af_heart.wav (8.128 s) twice →
  parity_story_test.wav, 16.256 s, exactly 2× input. Test file removed after.
- Effect: kokoro_af_heart.wav at speed 1.25, volume 0.9, echo on →
  parity_effect_test.wav, 6.574 s (≈8.128/1.25), filters
  atempo=1.25,volume=0.9,aecho=0.8:0.7:60:0.3. Test file removed after.
- Upload: kokoro_af_heart.wav (390,188 bytes) → 200, saved to
  output/uploads/. Bad extension (.txt) → 400 unsupported extension.
  Story with a non-output filename → 400 missing file (basename into
  output/, so it cannot escape output/).
- Homepage `GET /` → 200 and contains Parity sections, Record, Dictate,
  MCP agent voice, Personalities, Stories, Effects.
- Dictation: `POST /api/parity/dictate` with kokoro_af_heart.wav →
  HTTP 503, error "open() got an unexpected keyword argument
  'metadata_errors'". That is the known faster-whisper/av incompatibility
  from AUDIT.md (av metadata_errors), not a fake transcript. Dictation is
  therefore NOT working in this venv until that av issue is fixed or a
  librosa-decode path (as in AUDIT.md) is used. No transcript was invented.
- Parity import alone: `import parity` → ok, 9 routes registered.
- Guard: server.py imports parity in try/except, so if parity ever fails
  to import, v1 /api/voices still starts. This guard was coded, not
  live-fault-tested in this task (fault-injection was not attempted).

## What was NOT done in this task (by design)

- No model downloads (no multi-GB downloads).
- No GitHub push, no release, no installer build.
- No other project touched; hasibtechqore account not used.
- No live browser mic test (impossible for this agent), no global
  shortcut, no system-capture implementation, no real LLM personality
  — all labelled as such in code, UI, and here.
- Existing v1 behaviour preserved: server.py's Kokoro /api/generate and
  /api/voices were not changed except for the guarded parity import
  (unchanged in this task); parity.py and app/index.html were the only
  files changed, plus this PARITY.md.

## What remains (after this task)

1. Live mic test in a real browser with mic permission (recorder code
   only, not live-tested).
2. System capture implementation (WASAPI / BlackHole / PulseAudio
   monitor) — info endpoint only.
3. Global dictation shortcut + paste into any app/clipboard.
4. Real LLM personalities (Qwen3 LLM download + test) — currently
   template only.
5. Parity models: Chatterbox Turbo, LuxTTS, TADA, Qwen CustomVoice,
   Whisper Turbo, Qwen3 LLM — all still needs_download.
6. MCP synthesis for non-Kokoro voices (Parler/Edge/clone engines).
7. Bengali generation wiring — SUPERSEDED by the all-OK section at the
   top: Edge works AND Parler now works via venv_parler (transformers
   4.46.1). Remaining Parler gaps are only: speakers beyond Arjun not
   individually generated, and the Edge-fallback path not live-triggered.
8. Installer — Windows, macOS (ARM+Intel), and Linux workflow files all
   created and YAML-validated, but no real Actions run and no installer
   yet; GitHub release not started, parent agent's release gate.
