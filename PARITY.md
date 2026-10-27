## SERVER-FAILED FIX — v1.1.1 USER-PC DIALOG (2026-10-27) — LOCAL ONLY, NOT pushed, NO tag, NO release

USER SCREENSHOT: dialog "VoxLab — server failed: VoxLab's local server did not start in time. Expected it at http://127.0.0.1:8000 (/api/voices never answered 200). Another program may already use port 8000, or the server crashed at startup — see output/voxlab-server.log next to the app for the startup lines. Click OK to close VoxLab."

DIAGNOSIS (why the v1.1.1 dialog could not say what actually failed):
- The dialog came from run_desktop BEFORE any window/splash, via one of two paths only: ServerThread.start() raising, or pywebview import failing AND the 60 s wait failing. The splash loader never shows this dialog.
- Root flaw 1 — silent thread death: uvicorn runs in a daemon thread; a bind failure ([Errno 10048] on 8000, seen in the user's earlier video when a previous VoxLab server still held the port) makes that thread die, start() had already returned success, and wait_for_server polled 60 s against a server that would never answer.
- Root flaw 2 — no log in frozen build: in a --noconsole exe uvicorn's bind error went to discarded stderr; server.py's FileHandler is on the root logger, not guaranteed for uvicorn's loggers, so output/voxlab-server.log (relative path in the dialog) often contained no bind error at all.
- Root flaw 3 — single-port logic: reuse probe was one 2 s check on port 8000 only; a first instance that had itself moved to 8001 was invisible, and a failed start was never retried on another port.

FIX (backend/desktop.py only):
- start_server_with_retry(host, start_port): (a) scans 8000–8010 (MAX_PORT_OFFSET=10) for an answering VoxLab server via /api/voices and reuses it (find_reused_url, 1 s probe per port); (b) otherwise binds the first FREE port in that range (_port_free socket bind test) and opens the window on THAT url — never the occupied 8000; (c) a thread that dies during startup is detected immediately (ServerThread.died/error/traceback_text, wait_for_server server_thread= param breaks early) and the next free port is tried at once; (d) a thread that stays alive but never answers after 60 s is a hang, stopped and reported, NOT retried port-by-port (same binary would hang the same way); (e) an import failure is raised synchronously in ServerThread.start() (main thread), logged, and never retried (port-independent).
- Real error capture: ServerThread._run wraps uvicorn.run() in try/except storing error + full traceback; uvicorn/uvicorn.error/uvicorn.access loggers get a FileHandler to the ABSOLUTE output/voxlab-server.log (beside the exe frozen, project root unfrozen); _append_server_log() writes failures there; _server_failed_message(url, detail) shows the truncated real error + absolute log path + the "close the other program / relaunch — VoxLab reuses a running server or moves to 8001, 8002, … on its own" instruction. The old guessed text ("may already use port 8000… see output/voxlab-server.log next to the app") is gone from the dialog path.
- run_desktop rework: reuse-or-start WITH retry now happens BEFORE opening the window (GUI path previously opened the window first and only the splash loader waited — that is why the user saw a dialog, not a splash, on failure). The splash steps then run against an already-answering server; NO_GUI path unchanged except it uses the same chosen url. The pywebview-import failure path no longer waits a blind 60 s: if the server thread died it shows that thread's real error at once.
- No workflow/requirements/server.py change needed; the frozen entry is still backend/desktop.py.

TESTS (local, /tmp/test_desktop_fix.py, ports freed after each test):
- BEFORE (v1.1.1 dialog text): generic guess, relative log path, no error, no port retry — reproduced from the screenshot text.
- AFTER, occupied-port: socket listener on 8000 (no voices) → _port_free(8000)=False, _port_free(8002)=True; stub HTTP server on 8001 answering /api/voices 19 voices → find_reused_url(8000)=http://127.0.0.1:8001, start_server_with_retry(8000)=(None, http://127.0.0.1:8001, reused=True, detail="").
- AFTER, crash simulation: FakeThread dying instantly with OSError [Errno 10048] → start_server_with_retry(18010) tried ports [18010…18020], returned (None, None, False) with detail containing "10048" AND the absolute log path; _server_failed_message shows "What actually happened: …10048…" + full log path; voxlab-server.log tail verified containing the same failure line.
- AFTER, import-crash simulation (system python, no fastapi): start_server_with_retry returned in 0.1 s with the full ModuleNotFoundError traceback tail as detail — previously this class of failure would have died in the thread and waited 60 s. (This is the import path, not a real VoxLab failure: the shipped frozen build bundles fastapi.)
- AFTER, real server (mahbub venv, which has fastapi/uvicorn): start_server_with_retry(18040) → http://127.0.0.1:18040, reused=False, detail="", 2.2 s, voices_ok=True; second call on 18050 while the first server ran → (None, http://127.0.0.1:18050, reused=True). Servers stopped after, ports free.
- py_compile OK (desktop.py); the only "webbrowser" string left in desktop.py is the docstring describing the OLD server.py timer — no webbrowser import, no silent browser open.
- HONEST LIMITS: a real pywebview window was NOT seen (headless VM); the dialog text itself was verified by calling _server_failed_message directly, not by clicking a dialog on Windows. A frozen Windows run is still the final proof: launch with port 8000 held by another program → window must open on 8001+ (not the server-failed dialog); launch with a genuinely crashing server → dialog must name the real error + absolute log path. The most likely user-PC trigger remains an old VoxLab/v1.0.9 server still holding 8000 (or another program on 8000) — the fix makes that case succeed on 8001 instead of failing, but the user should still close stray old VoxLab windows first. Files changed (local only, NOT pushed): backend/desktop.py, PARITY.md (this section). Browser requirement for parent: pushing needs a parent/root browser task signed in as ishtiaquehasib only — I cannot operate a live browser and did not attempt it.

## NO-FALLBACK RULE — USER DECISION (2026-10-27): "fallback jeno konotai na hoy" + "limit tumi thik kore daw" — LOCAL ONLY, NOT pushed, NO tag, NO release

USER DECISION, IN HIS WORDS: no fallback at all. Follow-up: "limit tumi thik kore daw" — he told the agent to decide the limits, not keep asking him. So the limits below are SET HERE by the agent, documented, not pending his decision. The old plan (Parler -> labelled Edge fallback) is SUPERSEDED and removed — the previous PARITY sections describing the Edge fallback are historical only and no longer describe shipped behaviour.

### THE LIMIT RULE (set by the agent, 2026-10-27)
A "fallback" is banned when it SUBSTITUTES a different output for the requested one: a different voice, a different model, different text, or a different effect. Two things are NOT substitutions and are KEPT, because they return the exact requested output through a different backend:
- SAME voice/model/effect, different backend: Kokoro KPipeline -> Kokoro ONNX (same preset voice, server.py); Edge edge-tts library -> Deno transport (same Edge neural voice, bengali.py generate_edge — only when VOXLAB_EDGE_SECRET is set, dead in a shipped build); device GPU -> CPU retry of the SAME model (parity.py transcribe, bengali.py Parler in-process, device.py); scipy FFT -> numpy FFT convolution (same reverb, parity.py _apply_convolution_reverb).
- NO output at all on failure: an honest error + a download/install action is always preferred over a substitute. Refine-transcript already worked this way (refine=True failure returns the original with refined=False + real error) and is kept.
Everything else that substituted a different output was REMOVED in this change (list below). If a future feature needs a substitute, it must be offered as an EXPLICIT user choice ("use X instead?") — never automatic, never silent, never labelled-after-the-fact.

### REMOVED — Parler -> Edge (the mandated one)
- backend/server.py parler_ route: the gender-matched Edge block (female -> edge_nabanita, male -> edge_pradeep, X-VoxLab-Voice-Fallback header, "edge-fallback" history) is DELETED. On generate_parler() failure the route now returns JSON {ok:false, error:"Parler generation failed", voice, actual_voice:null, parler_error, install_steps, install_endpoint:"POST /api/parity/install-parler", install_status_endpoint:"GET /api/parity/install-parler-status"} — 503 when Parler is not installed/unavailable, else 500. No Edge call, no fallback header, no edge-fallback history row.
- backend/bengali.py generate_parler(): rewritten. Order: (1) isolated venv worker (see below); (2) in-process ONLY under transformers 4.46.x — that is still real Parler audio from the same speaker, not a substitute, and under any other transformers version it is skipped, not attempted (the old attempt wasted minutes / OOM-killed exit -9); (3) otherwise raise with PARLER_INSTALL_STEPS. The old FAST-SKIP error text saying "so this request falls back to Edge" is gone. grep: no "parler_needs_download_or_fallback", no "X-VoxLab-Voice-Fallback", no "edge-fallback" anywhere in backend/*.py or app/index.html.
- VOICES availability: all 6 Parler speakers now read "Needs Parler install — no other voice substituted" (was "Needs Parler download / falls back to Edge"). GET /api/bengali-status: key renamed parler_needs_download_or_fallback -> parler_needs_install, plus a new parler_env object {venv_python, venv_installed, venv_dir, worker_script, worker_bundled, model_cached, model_repo, ready}.
- app/index.html: Bengali panel text rewritten (no fallback sentence), Parler buttons read "needs Parler install — no substitute", new buttons "Install Parler voices" + "Parler install status", gen() Parler error now shows parler_error + install_steps (no Edge-fallback sentence), success status uses X-VoxLab-Voice-Actual only, panel status shows Parler venv installed / model cached from /api/bengali-status.

### REAL PARLER ROUTE FOR THE SHIPPED BUILD — feasibility verdict
Bundling the venv is NOT feasible for v1.1.0: dev venv_parler is 1.7 GB installed and the RXD03 model cache is 3.6 GB; the current installer is 239 MB and GitHub release assets cap at 2 GB. A bundled Parler venv would dwarf the app and break the release. The shipped route is therefore ON-DEMAND INSTALL, built now:
- NEW backend/parler_worker.py (self-contained, NO VoxLab imports): the old parler_cli.py imports bengali.py, so it can NEVER run frozen (backend/*.py sources do not exist on disk in a PyInstaller PYZ). parler_worker.py imports only parler_tts/transformers/torch/soundfile, same speaker descriptions, same RXD03 model. All 3 workflows now --add-data backend/parler_worker.py -> backend (so _MEIPASS/backend/parler_worker.py exists frozen). parler_cli.py is kept only as the dev entry point.
- backend/bengali.py parler_env_status() / _parler_venv_python() / _parler_worker_script(): venv resolution order = VOXLAB_PARLER_VENV_PYTHON override, output/parler-env (bin/python, or Scripts/python.exe on Windows), dev venv_parler (unfrozen only). Worker resolution = VOXLAB_PARLER_WORKER override, _MEIPASS/backend/parler_worker.py, _MEIPASS/parler_worker.py, backend/parler_worker.py, parler_cli.py. Offline mode (HF_HUB_OFFLINE=1) is set ONLY when the model is already cached; otherwise the worker may download on first use (the old code forced offline=1 always, which would fail a fresh install).
- NEW parity.py POST /api/parity/install-parler + GET /api/parity/install-parler-status (background thread, pollable): creates output/parler-env with a host Python (venv), pip-installs CPU torch (download.pytorch.org/whl/cpu) then parler-tts==0.2.2 + soundfile. The model itself is downloaded separately via the existing POST /api/parity/download-model id=parler-bengali. Status reports install_state idle/installing/done/error + log tail + parler_env.
- FROZEN LIMIT, HONEST AND UNTESTED ON WINDOWS: a frozen exe has no Python interpreter of its own, so if no python/python3 is on PATH the install endpoint returns needs_python + the exact step (install Python 3.12 from python.org, tick Add to PATH, restart VoxLab, press Install Parler again) instead of starting. The Windows embeddable-Python download path is NOT coded — it would be untested on this Linux VM and must not be claimed until a Windows run proves it. So on a fresh user PC the honest sequence is: Python install (one-time, free) -> Install Parler button -> model download -> real Parler audio. That is the v1.1.0 Parler story; it is slower than a bundled venv and it says so.

### REMOVED — other substitutions (same limit rule)
- parity.py transcribe(): automatic Whisper Turbo (large-v3-turbo) -> small substitution REMOVED. Only the requested model is tried (same-model CUDA->CPU retry on OOM kept). Failure returns {available:false, transcript:null, model:<requested>, error, download_action:"Download the requested Whisper model on the Models page (Turbo: mobiuslabsgmbh/faster-whisper-large-v3-turbo), or call with model_size='small' explicitly."}. Callers that explicitly request small (qc.py) are unaffected; the dictate endpoints now 503 honestly when Turbo is unavailable instead of returning a small-model transcript under a Turbo name.
- parity.py rewrite_text()/compose_text(): template substitutes REMOVED — "[persona] <input>" is not a rewrite and "Here is a line about X, spoken in character" is not a compose. On LLM failure/empty output both now return {method:"unavailable", llm_used:false, rewritten/composed:null, error, download_action:"Download Qwen3 0.6B on the Models page (Qwen/Qwen3-0.6B), then retry."}; the /api/parity/rewrite and /api/parity/compose endpoints return that body with HTTP 503.
- parity.py apply_effect() reverb: the aecho multi-tap approximation REMOVED — it is not convolution reverb. Convolution failure now returns {ok:false, error:"convolution reverb failed (...); reverb requires numpy/scipy — no echo approximation is substituted."}. _apply_convolution_reverb() error engine renamed from reverb_aecho_fallback to "none". Normal case (numpy present) is unchanged.

### KEPT, BY THE LIMIT RULE (same output, different backend — NOT substitutions)
- server.py Kokoro KPipeline -> Kokoro ONNX (same preset voice; both errors reported if both fail).
- bengali.py generate_edge(): edge-tts library first, Deno transport only if VOXLAB_EDGE_SECRET is set (same bn-BD-NabanitaNeural / bn-BD-PradeepNeural voice either way; secret never read from a local file).
- Device: CUDA -> MPS -> DirectML -> CPU detection (device.py) and same-model CPU retry on OOM (bengali.py, parity.py, clone.py, llm.py) — same model, different device.
- parity.py _apply_convolution_reverb(): scipy FFT else numpy FFT — same convolution, same IR.
- parity.py refine_transcript(): refine failure returns the original with refined=False + real error (not a substitute "refined" text).
- desktop.py error dialog (tkinter -> Win32 MessageBoxW -> log file): a UI fallback, not an output substitution; it never opens a browser silently.
- Clone profiles / MCP: already no-substitution (failed voice returns synthesized:false with the real error).

### TESTS (local, mahbub venv server port 8041, HF_HUB_OFFLINE=1; server stopped after, port free)
- py_compile OK (bengali.py, server.py, parity.py, parler_worker.py); JS_OK (node --check, page script 39,022 B); YAML_OK (linux + macos workflows; windows workflow matches the surrounding PowerShell backtick style — see note in files).
- GET /api/bengali-status: bn_count 8, guaranteed_edge [edge_nabanita, edge_pradeep], parler_needs_install 6 ids, parler_env {venv_python: .../venv_parler/bin/python, venv_installed:true, worker_script: .../backend/parler_worker.py, worker_bundled:true, model_cached:true, ready:true}, edge_tts 7.3.1, transformers 4.57.3.
- REAL PARLER via the NEW standalone worker: POST /api/generate voice=parler_arjun, Bengali text "আমি ভক্সল্যাব, আপনার নিজের কম্পিউটারে চলা একটি বিনামূল্যে ভয়েস স্টুডিও।" -> HTTP 200, 47,225 B MP3, ffprobe 5.039 s, header X-VoxLab-Voice-Actual: parler_arjun, NO fallback header, wall 2m46s (model load + CPU generate). This proves parler_worker.py works under venv_parler (transformers 4.46.1) — the worker itself is proven; the on-demand install that creates such a venv on a user PC is NOT yet proven (see below).
- NO-FALLBACK ERROR (simulated frozen: venv + worker monkeypatched absent, transformers 4.57.3): generate_parler() raises RuntimeError in <1 s with the install steps, and the message contains NO "falls back to Edge" action. The server route forwards this as the 503 JSON above (route code verified by grep: no generate_edge call in the parler_ block; the only generate_edge call in server.py is the edge_ voice path, i.e. a voice the user actually requested).
- PERSONA unavailable (LLM monkeypatched to raise): rewrite -> {method:"unavailable", rewritten:null, error:"simulated LLM load failure", download_action present}; compose -> {method:"unavailable", composed:null}. With the real LLM present in this venv, rewrite/compose succeed via qwen3-llm (rewrite "hello world" -> "hello there"), so the unavailable path was proven by simulation, not by a missing model.
- GET /api/parity/install-parler-status on this VM: install_state idle, parler ready:true (dev venv found) — the install button correctly reports already-installed instead of reinstalling.

### WHAT REMAINS — DO NOT OVERCLAIM
- On-demand Parler install end-to-end is UNPROVEN: the pip install of CPU torch + parler-tts==0.2.2 into a fresh output/parler-env was NOT run here (it would download several hundred MB and take many minutes on this VM, and the Windows branch — Scripts/python.exe, PATH python, embeddable Python — cannot run on Linux at all). First proof must be a user-PC run: install Python 3.12 (if needed) -> Models page Install Parler -> status done -> download Bengali Parler model if uncached -> Generate Arjun -> real Parler audio, header X-VoxLab-Voice-Actual: parler_arjun.
- A frozen-simulated server run (venv hidden) was NOT done — the error path was proven at generate_parler() unit level with monkeypatching, not through HTTP with a hidden venv, because the dev venv cannot be hidden without renaming it mid-test.
- The gen() JS error/install buttons were syntax-checked only, not clicked in a real browser (headless VM).
- Whisper Turbo-only dictation and persona-unavailable 503s are behaviour changes: users who previously got a small-model transcript or a template line will now get an honest error + download action instead. That is the intended limit, but it must be stated in the v1.1.0 release notes, not discovered by users.
Files changed (local only, NOT pushed): backend/bengali.py, backend/parler_worker.py (new), backend/server.py, backend/parity.py, app/index.html, .github/workflows/windows-installer.yml, .github/workflows/linux-installer.yml, .github/workflows/macos-installer.yml, PARITY.md (this section). Browser requirement for parent: pushing these needs a parent/root browser task signed in as ishtiaquehasib only — I cannot operate a live browser and did not attempt it. Nothing was pushed, tagged, or released.

## DESKTOP SPLASH — REAL 1-BY-1 STEPS, VOXLAB THEME ONLY (2026-10-27) — LOCAL ONLY, NOT pushed, NO tag, NO release

WHY: the user video shows the competitor splash stepping through startup items one by one before the main UI. VoxLab's desktop splash was a single animated progress bar that swapped to the UI as soon as the server answered, with no per-item result. This change gives VoxLab the same 1-by-1 behaviour — steps, not a spinner — without copying anything from the competitor.

NO-COPY RULE (applies to this splash and to any later splash work): VoxLab theme only — dark navy #05081f, gradient #00d4ff -> #4868D8 -> #8b5cf6, the VoxLab logo (assets/voxlab-favicon.png, 256x256, data URI; fallback app/logo.png, then text-only). NO competitor gold mic image, NO gold/black design, NO competitor splash texts (none of the "Warming up tensors / Initializing voice models / Loading neural networks / Preparing audio pipelines / Optimizing waveform generators / Tuning frequency analyzers / Building voice embeddings / Configuring text-to-speech cores / Syncing audio buffers / Establishing model connections" style lines are used anywhere in desktop.py — verified by grep: all absent). Step labels are plain functional VoxLab wording, and every step state comes from a real check, never from cycling invented text.

EXACT STEP LIST (backend/desktop.py SPLASH_STEPS, in check order):
1. server — "Local server starting": reused running server (probe /api/voices first) counts as done; otherwise wait_for_server polls /api/voices up to 60 s. Failed -> all later steps marked failed "Not checked — the server did not start", status "Close this window to stop VoxLab", NO Continue button (there is no working UI to continue to).
2. voices — "Voice list loading": GET /api/voices; done only on exactly 19 voices (11 Kokoro + 8 Bengali, the established ready count); fewer/more or no answer -> failed with the real count.
3. ffmpeg — "Audio tools (ffmpeg)": the DESKTOP process's own check — bundled imageio-ffmpeg exe first, else system PATH (same rule as server.py/parity.py, not a copied server string). Missing -> failed.
4. bengali_edge — "Bengali Edge voices": GET /api/bengali-status; done only when edge_tts_installed is true (version reported when present). "Done" means the package is installed in this build, NOT that a Bengali generation succeeded (Edge still needs network to its service).
5. models — "Model availability": GET /api/parity/models; done when the list answers with entries, detail "X of Y models cached; the rest download on first use". Cache status only — lazy load: done does NOT mean every model is downloaded or loaded.
6. output — "Output folder writable": proven by actually writing and deleting output/.voxlab-splash-write-test (not os.access alone); failure detail names the folder and the error.

SWAP GATE + NEVER TRAP: the loader thread (_splash_and_swap) runs the steps in order, each step pending -> running -> done/failed only from its check's result, and calls window.load_url(main UI) ONLY when ALL six steps pass. On any failed non-server step the splash STAYS on the failed step and shows a "Continue to the studio anyway" button (hidden until voxlabShowContinue()); clicking it navigates the window itself to the main UI URL (window.location.href, no Python callback, no browser tab opened). On load_url failure the splash status shows the real error + the Continue button. run_desktop no longer waits for the server before opening the window in the GUI path — the window opens on the splash first and the loader shows a slow first start as steps; the NO_GUI CI path still waits (it has no window), and the pywebview-missing fallback still waits before its dialog so the dialog's "server is running" claim stays true.

WHAT CHANGED (local only): backend/desktop.py only — new SPLASH_STEPS, splash_html rewritten (step <ul> with id step-<id>, voxlabSetStep/voxlabSetStatus/voxlabShowContinue JS, Continue button, animated progress bar REMOVED), new _get_json/_set_step/_set_status/_show_continue/_ffmpeg_exe_local/_check_output_writable/_evaluate_splash_checks/_splash_and_swap, run_desktop restructured to open the splash window first + loader thread. No workflow, requirements, or server change was needed (pywebview + favicon add-data already in the workflows from the native-window change).

TESTS (local, headless — no real GUI window seen, same limit as the native-window change):
- py_compile OK (desktop.py); splash HTML 84,326 B, all 6 step ids present (step-server, step-voices, step-ffmpeg, step-bengali_edge, step-models, step-output), logo data URI present, Continue button present, progress-bar markup absent, no webbrowser import, competitor phrases + "gold" absent from desktop.py by grep.
- Fake-window + stub HTTP server (fake evaluate_js/load_url recorder; ffmpeg/output monkeypatched for determinism): PASS path (19 voices, edge_tts 7.3.1, bn_count 8, models 1/2 cached, reused server) -> all_pass True, steps in order running -> done each, load_url called once with the main UI URL. FAIL path (5 voices, edge_tts false, models []) -> all_pass False, Continue shown, load_url NEVER called. SERVER-FAIL path (dead port, reused=False, wait mocked False) -> all_pass False, server_ok False, Continue NOT shown, no swap.
- Real local checks (unmonkeypatched): _check_output_writable() -> True, output folder /home/hatch/workspace/voice-studio/output, probe file verified absent afterwards; _ffmpeg_exe_local() -> /usr/bin/ffmpeg on this VM.
WHAT REMAINS — DO NOT OVERCLAIM: the splash rendering, step animation, and Continue click have NOT been seen in a real pywebview window (headless VM, no WebView2/WebKit GUI); first visual proof must be a user-PC run of the next release's Setup exe: double-click -> VoxLab window on the splash -> steps tick 1-by-1 -> main UI only on a full pass (or Continue button on a failed step). Files changed (local only, NOT pushed): backend/desktop.py, PARITY.md (this section). Browser requirement for parent: pushing these needs a parent/root browser task signed in as ishtiaquehasib only — I cannot operate a live browser and did not attempt it.

## GENERATE-STUCK FIX — Kokoro -> Arjun (Parler) Bengali, old audio kept (2026-10-27) — LOCAL ONLY, NOT pushed, NO tag, NO release

USER FAILURE (exact, clarified): first audio generated once (Kokoro Heart + English text), then he switched to Arjun + Bengali script text via main Generate, and NOTHING generated afterwards — the OLD generated audio stayed in the player.

BEFORE — REPRODUCED, sequential HTTP, mahbub venv (transformers 4.57.3), qc=0:
- Gen 1 Kokoro af_heart "First test one, VoxLab turns text into voice." -> 200, 27,380 B, 3.285 s (wall 27 s, first model load).
- Gen 2 Kokoro af_heart, different text -> 200, 38,108 B, 4.672 s, different md5 from gen 1 — the server itself is NOT stuck on repeat Kokoro.
- Gen 3 engine switch to Qwen CustomVoice Ryan -> 200, 34,172 B, 5.040 s (wall 73 s) — engine switching works server-side; the stuck symptom is NOT a server lock or a reused filename (each engine writes its own last_*.wav/mp3 and FileResponse streams fresh bytes).
- Gen Arjun (parler_arjun, Bengali script "আমি ভক্সল্যাব, আপনার নিজের কম্পিউটারে চলা একটি বিনামূল্যে ভয়েস স্টুডিও।", engine Kokoro/Bengali) on the venv-present server -> HTTP 500, 918 B JSON, after 42.5 s: parler_error "Parler venv generation failed (exit -9)" followed by a useless config dump (the last 500 chars of stderr are ParlerTTS decoder config JSON, not the error), edge_error "Cannot connect to host speech.platform.bing.com:443 ssl: WRONG_VERSION_NUMBER" (known VM egress break, NOT a code bug), fallback_voice edge_pradeep (correct gender match for male Arjun). Exit -9 = SIGKILL, almost certainly OOM: the Parler subprocess loads a ~GB model into a machine whose server process already holds Kokoro ONNX (+ Qwen in the earlier sequence) on 7.7 GiB RAM.
- On the user's frozen v1.0.9 PC the chain is worse, not better: no pinned venv exists (venv_parler is a dev-only dir, never bundled; parler_cli.py source does not exist in a PyInstaller PYZ either), so generate_parler() always falls into the in-process path under transformers 5.2.0 (user screenshot), which Parler-tts does not support — minutes of model loading, then failure, then the Edge fallback attempt. If Edge also fails (or the user gives up during the long wait), the UI shows nothing new.
- UI ROOT CAUSE (the "old audio stays" part, in app/index.html gen() BEFORE this fix): (1) on !r.ok it set status to "Error: 500 <full raw JSON>" and returned WITHOUT touching #player — so the previous blob URL stayed loaded and playable, indistinguishable from a new result; (2) gen() had NO try/catch/finally: a thrown fetch (network abort, server restart, tab navigation) left the Generate button disabled forever and the status stuck on "Generating..."; (3) no empty-blob check; old blob URLs were never revoked.

WHAT CHANGED (local only):
- backend/bengali.py generate_parler(): FAST-SKIP — when PARLER_VENV_PYTHON does not exist AND transformers is not 4.46.x, raise immediately ("Parler unavailable in this build: transformers X (Parler needs 4.46.1) and no pinned Parler venv is bundled, so this request falls back to Edge") instead of loading the model in-process. In a frozen build this sends Arjun straight to the gender-matched Edge fallback in server.py, labelled with X-VoxLab-Voice-Fallback (never claimed as Parler audio). The pinned-venv path is untouched: where venv_parler exists, Parler still runs through it.
- backend/bengali.py venv-failure error: stderr tail now prefers lines containing Error/Traceback/Killed/MemoryError, and exit -9 is named "(killed by signal 9 — likely out of memory: this server already holds Kokoro/Qwen models)" instead of a config dump.
- app/index.html gen(): new clearPlayer() (pause, remove src, load(), revoke previous blob URL, hide download link). Called the moment Generate starts AND on every failure path; error status now parses the JSON and, for parler_ voices, states plainly "NOT Parler audio here: Parler is unavailable in this build (...), Edge fallback edge_pradeep also failed: (...)" instead of dumping raw JSON; needs_download gets "(model not downloaded — use the Models page)"; empty blob -> "empty audio file — old audio cleared"; fetch throw -> catch shows the error + clears the player; button re-enable moved to finally, so it can never stay disabled after a throw. genBottom()/modelGenerate() unchanged (their players are separate elements; the main Generate player is the one this bug was about).

AFTER — FROZEN-SIMULATED HTTP (venv_parler moved aside, server port 8033, then venv restored; VM Edge still fails at egress, so this proves the chain + error, not Edge audio):
- Direct fast-skip: generate_parler("আমি ভক্সল্যাব।", "arjun") with venv path pointed at /nonexistent -> RuntimeError in 0.03 s (was 42.5 s to OOM-kill) with the transformers 4.57.3 message.
- Kokoro af_heart first -> 200, 27,380 B, 3.285 s.
- Arjun Bengali script, frozen-simulated -> HTTP 500 in 0.79 s (was 42.5 s), 467 B JSON: parler_error = the fast-skip message, edge_error = the VM SSL error, fallback_voice = edge_pradeep, actual_voice = null. No fake audio, no hang.
- edge_nabanita direct -> HTTP 500 with the same VM SSL edge_error (confirms Edge failure on this VM is egress, not Arjun-specific).
- Kokoro af_heart AFTER the Arjun failure -> 200, 24,644 B, 2.965 s — the server is not wedged by a failed Bengali generate; a second Generate works immediately.
- JS_OK (node --check on the page script); py_compile OK (bengali.py). Test servers stopped, ports 8031/8032/8033 free; venv_parler restored (ls: venv_kokoro, venv_parler, venv_tada).

WHAT REMAINS — DO NOT OVERCLAIM:
- A real Edge-fallback MP3 for Arjun has NOT been produced anywhere yet: on this VM Edge-tts fails at TLS egress (SSL WRONG_VERSION_NUMBER to speech.platform.bing.com:443, with and without proxy env) for every Edge voice, so the frozen path's success branch (Arjun -> Edge Pradeep MP3, X-VoxLab-Voice-Fallback header, UI status "(Edge fallback — NOT Parler audio)") is proven only up to the fallback dispatch, not as audio. First real proof must be on the user's PC with direct internet: select Arjun + Bengali text -> Generate -> audio plays AND status says Edge fallback, not Parler.
- Real Parler audio in a shipped build still needs the pinned-transformers venv bundled (unbuilt) or a separate Parler worker; until then Arjun/Aditi/Tapan/Rashmi/Arnav/Riya are honestly Edge-fallback voices in the frozen build, and the UI now says so on failure instead of silently keeping old audio.
- The new gen() JS was syntax-checked only, not clicked in a real browser (headless VM); the player-clear + button-reenable behaviour needs one user-PC click-through: Generate Kokoro, then Generate Arjun (fail or Edge audio), then Generate Kokoro again — player must never show the previous audio after a failed generate, and the button must never stay disabled.
Files changed (local only, NOT pushed): backend/bengali.py, app/index.html, PARITY.md (this section). Browser requirement for parent: pushing these needs a parent/root browser task signed in as ishtiaquehasib only — I cannot operate a live browser and did not attempt it.

## VOICE CLONE WIRING FIX — Record upload -> profile -> clone (2026-10-27) — LOCAL ONLY, NOT pushed, NO tag, NO release

USER FAILURE (exact, from his screenshot): Record page returned
{"ok":true,"filename":"recording-1793045854097.system.wav","bytes":44,"note":"Saved as a reference clip. Cloning from it needs the Chatterbox engine (see /api/clone path in README, not yet wired to this upload)."}
Two bugs in one response: (1) bytes:44 is a WAV header with 0 audio frames — nothing was recorded, yet the server said ok:true; (2) the note itself admits clone was NOT wired to the upload at all — there was no /api/parity/clone endpoint, no saved voice profile, and the Clone view's file picker was ignored (modelGenerate() sent only a ref_wav name string, so uploading your own voice cloned the Kokoro sample instead). "Create Voice" only switched to the Clone view; it created nothing.

ROOT CAUSES (traced, not guessed):
- POST /api/parity/upload saved any file with ok:true and no audio validation. POST /api/parity/mic-upload called _wav_waveform_metadata which returns waveform_error "empty audio" for 0-frame WAVs, but save_mic_upload still returned ok:true (the error was only attached as metadata).
- capture_windows_audio() (WASAPI loopback) accepted any file with size > 0 — a 44-byte header passes — and never checked peak, so a silent capture also passed.
- Clone view (app/index.html modelGenerate): modelfile was read ONLY for the whisper-turbo branch; for turbo/luxtts/tada/customvoice it was ignored and payload.ref_wav was a typed name defaulting to kokoro_af_heart.wav.
- backend/clone.py (full Chatterbox) had no HTTP endpoint at all; PARITY.md itself logged "No dedicated /api/parity/clone endpoint — clone is wired only via MCP default/claude paths and test scripts."

WHAT CHANGED (local only):
- backend/parity.py: _validate_audio_file() — WAV via stdlib wave: size<=44 -> "only a 44-byte WAV header, 0 audio frames"; 0 seconds -> rejected; peak==0 -> "silent" rejected. Non-WAV via ffprobe duration + size. save_mic_upload() and parity_upload() now delete the file and return 400 with that reason instead of ok:true. capture_windows_audio() and Linux pulse capture now reject header-only (<=44 B) and silent (peak 0) captures with the reason (play audio during capture / check loopback device).
- NEW endpoints: POST /api/parity/clone {text, ref_wav | profile, engine "chatterbox-turbo" (default) | "chatterbox", profile_name, out_name} — validates the reference first, then generates; POST /api/parity/clone-from-upload (multipart file + text + profile_name + engine) — the file itself IS the reference, validated, profiled, cloned in one call; GET/POST /api/parity/profiles — profiles persisted as JSON in output/profiles/ (name, ref_wav, engine, created, clone_endpoint). parity_upload / mic-upload accept optional clone_text + profile_name + engine form fields: with clone_text the same request clones and returns clone_result; without it the response carries the exact clone call instead of the old "not yet wired" note (that note is gone from the code).
- app/index.html: Record view gains a "Clone this voice" panel (text + voice-name inputs, uses the last uploaded filename) and a "Capture system audio" button (POST /api/parity/capture, duration input); recorder onstop now refuses empty blobs (0 chunks or <=44 B) with "Recording is empty — check mic permission, speak during recording" and does NOT enable Upload; Clone view modelGenerate() now sends a picked file to /api/parity/clone-from-upload instead of ignoring it. JS_OK (script 36,953 B).
- backend/requirements.txt: + sounddevice (was a commented Windows-only optional; the new Capture button needs it, otherwise it always errors "sounddevice not available"). Lazy import inside capture_windows_audio() only, so server start is unaffected without PortAudio.
- Bug caught by testing, fixed same session: _save_profile() used `re` without importing it -> NameError 500 on the first clone-from-upload call. Fixed with a local `import re as _re`. A second small fix: /api/parity/clone no longer re-saves a profile when called by profile name (profile_name only).

TESTS (local mahbub venv server, port 8021, HF_HUB_OFFLINE=1, stopped after unless noted):
- Baseline before fix: POST /api/parity/generate-chatterbox-turbo {text, ref kokoro_af_heart.wav 8.128 s} -> 200, 2.32 s / 111,404 B, ResembleAI/chatterbox-turbo. So the Turbo engine itself worked; the failure was the wiring around it, not the model.
- Empty 44-byte WAV via /api/parity/upload AND via /api/parity/mic-upload -> HTTP 400, error "only a 44-byte WAV header, 0 audio frames … check mic permission, speak during recording, and for system capture make sure audio is actually playing", file NOT saved (verified absent from output/uploads/).
- 1 s silent WAV (48,044 B, peak 0) via upload -> HTTP 400, "clip is silent (peak 0)".
- Real WAV upload (kokoro_af_heart.wav) -> 200, bytes 390,188, seconds 8.128, peak 0.49, plus the clone endpoint example in the response.
- POST /api/parity/clone-from-upload (same Kokoro WAV as file, text "This is VoxLab clone test from my uploaded voice.", profile testvoice) -> 200, output clone_from_upload.wav, 3.04 s / 145,964 B, 24 kHz, ResembleAI/chatterbox-turbo, ref 8.128 s / peak 0.49, profile testvoice saved to output/profiles/testvoice.json.
- GET /api/parity/profiles -> 200, lists testvoice. POST /api/parity/clone {text, profile testvoice} -> 200, clone.wav 2.44 s / 117,164 B.
- POST /api/parity/upload with clone_text + profile_name uploadvoice -> 200, clone_result upload_clone.wav 2.24 s / 107,564 B + profile uploadvoice.
- POST /api/parity/capture on this Linux VM (no PulseAudio monitor) -> 503, "no PulseAudio monitor source found: pactl not installed and no monitor source found" — honest error, no empty file.
- Full Chatterbox engine (engine "chatterbox", backend/clone.py): NOT PROVEN in-app, and NOT the default for a reason — the in-app attempt killed the server process silently: no traceback in the server log (last line is the earlier capture 503), no clone_full.wav, and a follow-up curl got connection refused (exit 7). Most plausible cause is OOM: the full Chatterbox model (diffusers, 1000 diffusion steps) loading into a process that already holds the Turbo model on this 7.9 GiB RAM VM. The code path itself is unchanged from the standalone lab test (clone.py direct run previously produced chatterbox_clone audio), but in-app full-Chatterbox on a low-RAM machine is unsafe in the same process as Turbo — Turbo stays the supported in-app clone engine, and engine="chatterbox" must not be offered as equal until it is proven in a fresh process. Server restarted afterwards: clone-by-profile worked again immediately (2.2 s / 105,644 B), proving the death was the generation attempt, not code damage; test server stopped at the end, port 8021 free.

WHAT REMAINS — DO NOT OVERCLAIM:
- Windows WASAPI live capture is still unproven (this VM is Linux; capture_windows_audio has never run on Windows). The new validation guarantees a silent/empty Windows capture now fails with a reason instead of a fake voice, but a real Windows system-audio clip is still user-PC-only proof.
- Real-browser mic recording (MediaRecorder) is still user-PC-only: the JS empty-blob guard and upload->clone flow were syntax-checked only, not clicked in a real browser.
- The user's exact filename pattern "recording-<epoch>.system.wav" appears nowhere in this codebase (grep: no match) — it likely came from an external recorder/system-capture tool whose output was then uploaded. The fix covers that case at the server boundary (any empty/silent upload is rejected with the reason, any valid upload now clones), regardless of which tool produced the file.
- py_compile OK (parity.py); JS_OK. Files changed (local only, NOT pushed): backend/parity.py, backend/requirements.txt, app/index.html, PARITY.md (this section). Browser requirement for parent: pushing these needs a parent/root browser task signed in as ishtiaquehasib only — I cannot operate a live browser and did not attempt it.

## NATIVE DESKTOP WINDOW — NO BROWSER TAB, NO TERMINAL (2026-10-27) — LOCAL ONLY, NOT pushed, NO tag, NO release
WHY: shipped VoxLab (v1.0.9) is a PyInstaller server whose __main__ opens http://127.0.0.1:8000 in the user's Edge browser via a 1.5 s webbrowser timer, and the exe is a console-subsystem binary — so the user sees a terminal window + a browser tab. The competitor opens its own native app window. User, verbatim complaint: "voicebox er to terminal open hoy na". This change makes VoxLab open its own window instead.
WHAT CHANGED:
- backend/desktop.py (NEW, 17 KB, PyInstaller entry from now on): starts the FastAPI app from backend/server.py with uvicorn in a daemon background thread on 127.0.0.1:8000 (env VOXLAB_SERVER_HOST/PORT override), polls /api/voices until 200 (60 s timeout), then opens a pywebview window (title "VoxLab", 1280x800) on that URL. Splash first: VoxLab navy theme + logo (assets/voxlab-favicon.png, 256x256, embedded as a data URI; falls back to app/logo.png, then text-only) + animated progress bar — never a blank window; a loader thread swaps splash -> real UI via load_url(). On window close, ONLY a server this process started is stopped (uvicorn should_exit + 10 s join); a pre-existing server on port 8000 is REUSED (probe /api/voices first, no address-in-use crash) and left running on close. Window icon: pywebview create_window takes NO icon argument in targeted versions, so the icon comes from PyInstaller --icon assets/voxlab-logo.ico (already in the Windows workflow) — do NOT add icon= to create_window. server.py is imported LAZILY inside the start function, so `import desktop` works headless without pywebview/torch/display; desktop.py itself never imports webbrowser (grep-confirmed) — no silent Edge open anywhere in this path.
- Fallback (honest, non-silent): pywebview import failure or window start failure (on Windows almost always "WebView2 runtime missing" — WebView2 ships with Windows 11 / Edge; older Windows 10 needs the free Evergreen runtime, NOT bundled) shows an error dialog with the localhost URL while the server stays up, so the user may open that address manually; dismissing the dialog stops our server and exits. Dialog chain: tkinter (stdlib) -> Win32 MessageBoxW via ctypes -> output/voxlab-desktop-error.log + exit 1 (a --noconsole build has no console to print to).
- backend/requirements.txt: + pywebview (desktop-only; lazy import, server-only/headless runs never need it).
- .github/workflows/windows-installer.yml: entry backend/server.py -> backend/desktop.py; + --noconsole (windowed exe, no console window); + --collect-all pywebview + --hidden-import webview + webview.platforms.edgechromium; + --add-data assets/voxlab-favicon.png;assets (splash logo); verify step now also imports pywebview; NEW step "Verify windowed build (no console)": stdlib PE-header check on dist/VoxLab/VoxLab.exe (subsystem field must be 2 = Windows GUI, not 3 = console), logic proven locally on synthetic PE files (GUI -> exit 0, console -> exit 1). Smoke step now exports VOXLAB_DESKTOP_NO_GUI=1 (see CI hook below).
- .github/workflows/linux-installer.yml + macos-installer.yml: entry -> backend/desktop.py; + --collect-all pywebview + platform hidden import (gtk / cocoa); + favicon add-data; smoke exports VOXLAB_DESKTOP_NO_GUI=1. Linux .desktop launcher already sets Terminal=false, so no terminal from the launcher. macOS: still a bare folder binary, NOT a --windowed .app — double-clicking it directly may still show a terminal; a true .app is a separate, unbuilt item (already noted at the macOS .dmg step).
- installer/voxlab.iss: [Run] comment corrected — the installed exe is the desktop entry (own window), not the old browser-timer path. server.py __main__ browser behaviour is RETAINED for dev runs (`python backend/server.py`) only; it is no longer the shipped entry.
- CI-only hook VOXLAB_DESKTOP_NO_GUI=1 (desktop.py): starts the server thread and blocks without a window. GitHub runners have no guaranteed interactive desktop session for pywebview, so CI smoke uses it to prove the DESKTOP ENTRY starts a working server. It does NOT prove window creation.
TESTS (local, mahbub venv, ports freed after each test):
- py_compile OK (desktop.py); YAML_OK all 3 workflows; import desktop OK (title VoxLab, 1280x800, URL http://127.0.0.1:8000); splash 82,292 B HTML, contains logo data URI; voices_ok(dead port) = False; webview NOT imported at desktop import time.
- Own-server path (VOXLAB_DESKTOP_NO_GUI=1, port 8000): server up in <2 s, /api/voices 19 voices / 8 bn, / 200; killing the desktop process stopped the server (it owned it).
- Reuse path (external uvicorn on port 8001 first, then desktop NO_GUI on 8001): desktop stayed alive while reusing, external kept serving, and external was STILL alive after the desktop process exited — reuse never kills another server. (One stray external uvicorn survived a shell-job kill during cleanup and was killed separately; both ports verified free at the end.)
- Fallback path: show_error_dialog with no display/tkinter returned False in <1 s, wrote output/voxlab-desktop-error.log (test file removed after), never opened a browser, exit 0; message text verified to contain the localhost URL and "WebView2".
WHAT REMAINS — DO NOT OVERCLAIM:
- A real GUI window has NOT been seen: this VM is headless (no display, no WebView2/WebKit GUI, pywebview not installed here), so window creation, splash rendering, and close-cleanup on Windows were NOT visually proven. The first proof must be a user-PC run of the next release's VoxLab-Setup exe: double-click -> own VoxLab window (no terminal, no Edge tab) -> Bengali panel -> Generate. If WebView2 is missing on that PC, the fallback dialog (not a silent browser tab) is the expected honest behaviour.
- CI smoke with VOXLAB_DESKTOP_NO_GUI=1 proves only that the desktop entry starts a server; it does not prove the window. The PE subsystem check proves the Windows exe is windowed, not that pywebview renders.
- macOS .app (windowed bundle) still unbuilt; Linux needs a GUI session with WebKitGTK for the window (same as any pywebview app).
Files changed (local only, NOT pushed): backend/desktop.py (new), backend/requirements.txt, .github/workflows/windows-installer.yml, linux-installer.yml, macos-installer.yml, installer/voxlab.iss, PARITY.md (this section). Browser requirement for parent: pushing these needs a parent/root browser task signed in as ishtiaquehasib only — I cannot operate a live browser and did not attempt it.

## v1.0.8 LINUX/macOS CI SMOKE FIX (2026-10-27 ~05:09) — LOCAL ONLY, NOT pushed, NO tag, parent pushes as v1.0.9
EXACT CAUSE — QUOTING, NOT A SERVER CRASH (proven, not guessed):
- v1.0.8 Linux/macOS smoke step (run #10) contained, verbatim:
  python3 -c "import json, sys; d = json.load(open('/tmp/bengali.json')); print(f"bengali: {d['bn_count']}, edge_tts: {d['edge_tts_installed']}, guaranteed: {d['guaranteed_edge']}"); sys.exit(0 if d['bn_count'] == 8 and d['edge_tts_installed'] else 1)"
  Bash ends the -c argument at the double quote after f, so Python received `print(fbengali:` and died with `SyntaxError: invalid syntax` (reproduced locally, exact command, exit 1, plus bash `unexpected EOF while looking for matching '"'`). The first voices check used single quotes inside the -c double quotes (f'voices: ...') and survived — which is why /api/voices had already printed 19 voices / 8 Bengali before the failure.
- Downstream chain, also proven: GitHub Actions runs bash steps with -e, so the SyntaxError exited the smoke step at once; the step's EXIT trap then killed the server; the .deb (Linux) / .dmg (macOS) steps never ran because the job had already failed. Any curl retried after that point would fail with connection refused — that curl failure is an EFFECT of the trap kill, not a server crash. Windows was unaffected: its smoke step uses PowerShell ConvertFrom-Json, no nested-quote hazard.
WHAT CHANGED (linux-installer.yml + macos-installer.yml smoke step only; windows-installer.yml untouched):
- ZERO python3 -c one-liners remain in the Linux/macOS smoke steps (grep confirms: only comment lines mention python3 -c). All checks are `python3 - <<'PY'` heredocs (quoted delimiter = no shell interpolation, no nested-quote hazard).
- Each endpoint is retried up to 30 s (15 x 2 s): /api/voices, /, /api/bengali-status, /api/parity/status. The script does NOT exit on the first failure: FAIL flag + fail() (set -e is NOT relied on for the check phase), so the server stays alive through ALL checks; only at the end, on FAIL != 0, are smoke.log + /tmp/voices.json + /tmp/bengali.json + /tmp/parity.json all printed before exit 1. On success the old pass line is printed, then the server is killed and the trap removed.
- Linux and macOS smoke scripts are byte-identical after extraction (diff clean).
VERIFICATION (local, NOT a CI run — CI can only prove itself on the next tag push):
- YAML_OK both workflows (yaml.safe_load, 13 Linux steps / 12 macOS steps, smoke step present); bash -n OK both extracted smoke scripts; both heredoc blocks (2 per script) compile OK.
- Reproduction of the OLD line: exact v1.0.8 command -> SyntaxError invalid syntax, exit 1, AFTER line never reached under set -e. Reproduction of the NEW script, pass path: real local backend server (mahbub venv, port 8000) -> voices: 19 bengali: 8; bengali: 8 edge_tts: True guaranteed: ['edge_nabanita', 'edge_pradeep']; "Smoke test passed..." exit 0.
- Reproduction of the NEW script, fail path: stub HTTP server returning voices=1/bn=0, bengali bn_count=0/edge_tts=False -> BOTH heredoc checks ran (no early exit), diagnostics printed all three JSON files, exit 1, and the stub server still answered afterwards (curl 200) — proving checks run through to the end and only the launched binary is killed.
- Test servers/stubs stopped after testing; port 8000 free at the end.
WHAT REMAINS: the next tag push (parent, v1.0.9) is the only proof the CI smoke now passes on ubuntu-latest / macos runners; a CI pass still does not prove a user-PC double-click, and Bengali Edge audio on a user PC remains unproven (see Bengali section below).
Files changed (local only, NOT pushed): .github/workflows/linux-installer.yml, .github/workflows/macos-installer.yml, PARITY.md (this section). Browser requirement for parent: pushing these needs a parent/root browser task signed in as ishtiaquehasib only.

## BENGALI 100% HONEST FIX (2026-10-27 ~04:50) — LOCAL ONLY, NOT pushed, NO release, NO tag
Why "Bengali nai" on the user PC: (1) edge_tts was imported ONLY lazily inside bengali.generate_edge(), so a PyInstaller build could ship without it — the same failure class as v1.0.5 (silent missing package -> 500). (2) Parler cannot bundle in the shared/frozen env (parler-tts pins transformers 4.46.1, shared env is 4.57.3) — so Parler requests in a frozen build always fell to the in-process fallback and then to Edge, without the UI ever saying so clearly. (3) Edge network on this VM is blocked by the VM egress path (see below), so no VM test can prove Edge audio.
WHAT CHANGED:
- backend/bengali.py: guarded top-level `import edge_tts` (try/except, server still starts if absent) so PyInstaller's static analysis sees the import; generate_edge() still returns the honest missing-package error if the package is absent at runtime.
- All 3 workflows (.github/workflows/windows-installer.yml, linux-installer.yml, macos-installer.yml): PyInstaller now adds `--collect-all edge_tts --hidden-import edge_tts --hidden-import aiohttp --hidden-import edge_tts.communicate --hidden-import edge_tts.data_classes` beside the existing `--collect-all imageio_ffmpeg`. Windows verify step also imports edge_tts and fails the job if it is missing. YAML_OK all 3.
- backend/server.py: VOICES entries now carry `guaranteed` + `availability`: edge_nabanita/edge_pradeep = guaranteed True ("Guaranteed Bengali voice (Edge)"); all 6 Parler speakers = guaranteed False ("Needs Parler download / falls back to Edge"). NEW GET /api/bengali-status (no network, no generate): bn_count, bn_voices (8), guaranteed_edge [edge_nabanita, edge_pradeep], parler_needs_download_or_fallback (6 ids), edge_tts_installed + version, parler_tts_installed, transformers_version. Edge success now carries X-VoxLab-Voice-Actual; Parler success carries the same; Parler->Edge fallback already carried X-VoxLab-Voice-Fallback. Edge failure: missing package -> HTTP 503, network/service -> HTTP 500, BOTH with JSON {ok:false, error:"Bengali generation failed", voice, actual_voice:null, parler_error, edge_error} — never a bare traceback, never a generic 500 without edge_error. Parler-fallback failure carries both parler_error and edge_error plus fallback_voice, with the same 503/500 split.
- app/index.html: NEW always-visible "Bengali — always here" panel in Generate (id bengali-panel, served HTML contains it): status from /api/bengali-status, 8 voice buttons (Edge buttons marked "✓ guaranteed", Parler buttons marked "needs Parler / falls back to Edge"), "Try Bengali sample text" (sets an Assalamu Alaikum Bengali sample) and "Show only Bengali voices" (langfilter=bn). Voice-profile cards now also show the availability label. gen() status now shows "Actual voice: ..." and "(Edge fallback — NOT Parler audio)" when the fallback header is present, so a fallback is never mistaken for Parler audio in the UI either.
- CI smoke (all 3 workflows, no network generate in CI): after the 19-voices check, smoke now requires exactly 8 bn voices in /api/voices AND GET /api/bengali-status 200 with bn_count==8 AND edge_tts_installed==true — a lazy-import miss now fails the build before release instead of shipping as a user-PC 500.
TESTS (local, mahbub venv, server port 8020, stopped after, port free):
- Frozen simulation (clean venv /tmp/voxlab_frozen_venv, pyinstaller + edge-tts only, onefile exe built with the EXACT new flags): built 13 MB exe, ran frozen (FROZEN: True), EDGE_TTS_SPEC: True, AIOHTTP_SPEC: True. This proves the bundling flags include edge_tts + aiohttp in a frozen exe; it is NOT a full VoxLab frozen server (that needs torch/kokoro and only CI builds it).
- HTTP: GET /api/voices 200, 19 voices, 8 bn [parler_arjun, parler_aditi, parler_tapan, parler_rashmi, parler_arnav, parler_riya, edge_nabanita, edge_pradeep]. GET /api/bengali-status 200: bn_count 8, guaranteed_edge [edge_nabanita, edge_pradeep], edge_tts_installed true, edge_tts_version 7.3.1, parler_tts_installed true, transformers_version 4.57.3. GET / 200, 68,961 B, contains bengali-panel + "Bengali — always here" (2 matches). GET /api/parity/startup-status 200.
- Edge direct, proxy bypassed (env -u http_proxy/https_proxy/HTTP_PROXY/HTTPS_PROXY, no_proxy="*"): STILL FAILED in <1 s, ClientConnectorSSLError to speech.platform.bing.com:443, SSL WRONG_VERSION_NUMBER — the same error as with the proxy. So the VM egress path itself intercepts/breaks the TLS handshake regardless of proxy env vars; this is a VM-network failure, NOT proof Edge fails on a user PC. No Edge MP3 was produced on this VM in this task, and none is claimed. The old output/bn_edge_test.mp3 (18,720 B, 2026-10-26) is a leftover, not a new test.
- Edge HTTP honest-error path: POST /api/generate voice=edge_pradeep, Bengali text -> HTTP 500, 289 B JSON {ok:false, error:"Bengali generation failed", voice:"edge_pradeep", actual_voice:null, parler_error:null, edge_error:"Cannot connect to host speech.platform.bing.com:443 ssl:... WRONG_VERSION_NUMBER"} — named network error, no traceback, no fake file.
- py_compile OK (server.py, bengali.py); node --check JS_OK (script 34,603 B).
WHAT REMAINS USER-PC-ONLY (do not claim until a real user-PC run):
- A real Edge MP3 on a user PC with direct internet (Nabanita + Pradeep, and a Parler->Edge fallback labelled as Edge).
- A real Parler MP3 in the shipped env (needs the transformers 4.46.1 conflict resolved or a bundled Parler venv — unbuilt; until then Parler = needs-download/fallback, honestly labelled).
- The full frozen VoxLab exe's /api/bengali-status on windows-latest CI (the new smoke check will prove it there; the minimal frozen test above proves only the edge_tts bundling mechanism).
- Real-browser clicks on the new Bengali panel (served HTML + JS syntax only).
Files changed (local only, NOT pushed): backend/bengali.py, backend/server.py, app/index.html, .github/workflows/windows-installer.yml, linux-installer.yml, macos-installer.yml. Browser requirement for parent: pushing these needs a parent/root browser task signed in as ishtiaquehasib only — I cannot operate a live browser and did not attempt it.

## Settings full detail (2026-10-27 ~04:35) — LOCAL ONLY, NOT pushed, NO release, NO tag

VoxLab's own theme only. No competitor text/design copied. Files: backend/server.py (file log, normalize wiring, /api/voices-table), backend/parity.py (settings expansion + 12 new endpoints), backend/qc.py (normalize_audio_file), app/index.html (66,467 B served, 33,156 B script, node --check OK, py_compile OK).

### Settings tabs — full detail, all stored in output/voxlab-settings.json
- **Generation:** auto-chunk limit slider 100–2000, default 800 — POST /api/parity/chunk-text with no max_chars now uses this (tested: 200-word text → 2 chunks [799, 199], all ≤800). Chunk crossfade ms 0–500, default 50 — POST /api/parity/story with no crossfade_ms now uses this (story builder). Normalize audio toggle, default on — qc.normalize_audio_file peak-normalizes finished WAVs to -3 dBFS (peak-based, NOT LUFS) before MP3 in server._finalise_generate; proven: main generate MP3 peak -2.99 dBFS, direct normalize -6.19 → -3.0 dBFS. Autoplay on generate toggle, default on (player autoplays after a successful generate). Generations folder path = output/ absolute path, Open is display-only in a browser (browser cannot open a local folder).
- **Captures:** push-to-talk shortcut display Ctrl+Alt+V (Windows/Linux) / Cmd+Option+V (macOS) from settings; changing the text does NOT rebind the listener — real global hotkey still pending (honest note in UI). Toggle shortcut toggle (stored only until a real listener honours it). Auto-paste toggle, default off, GUI only — paste only when dictate-shortcut payload asks. Transcription model select Whisper Base/Small/Medium/Large/Turbo (stored; dictate endpoint still uses its own model_size param — stored value is the UI default, not yet forced into dictate). Language auto-detect (auto/en/bn, stored). Refinement toggle + model Qwen3 0.6B, smart cleanup, remove self-corrections, preserve technical terms — POST /api/parity/refine-transcript honours them: tested "um hello, uh this is a test, actually no, this is the real test" → refined "this is the real test", method qwen3-llm, settings_applied [smart_cleanup, remove_self_corrections, preserve_technical_terms(no-op: no term rewriting coded)].
- **MCP:** GET /api/parity/mcp-snippets — server URL http://127.0.0.1:8000, mcp URL /api/mcp/speak, HTTP snippet with X-VoxLab-Client-Id header, stdio snippet (frozen exe / server.py), default voice af_heart. Per-agent bindings: GET/POST /api/parity/mcp-bindings, stored in settings; MCP speak honours binding — tested: client test-agent → af_bella, POST /api/mcp/speak {agent: test-agent} → voice af_bella, synthesized true, 1.472 s, kokoro-onnx (test binding removed after test). Per-agent pill/ACP/A2A/WebSocket NOT built.
- **GPU:** GET /api/parity/gpu — detected device cpu on this VM, backends CUDA → MPS → DirectML → CPU, OOM CPU fallback. CUDA backend download note: ~2.4 GB torch CUDA wheel, NVIDIA only, NOT downloaded by default, no auto-installer built.
- **Logs:** server.py writes output/voxlab-server.log on startup (no secrets ever logged); GET /api/parity/logs?lines=200 returns real lines — tested present=true, 1 startup line. Absent file → honest note + console fallback.
- **Changelog:** GET /api/parity/releases — live GitHub releases list (per_page=20) — tested ok, first entry v1.0.7 (2026-10-26T22:18:26Z, i.e. the in-flight release landed while this work ran — v1.0.7 push is the parent's browser task, not this change).
- **About:** VoxLab, Developed by Ishtiaque Hasib, SupportKori link https://www.supportkori.com/seoacademy, GitHub link https://github.com/ishtiaquehasib/VoxLab, MIT app code.

### New pages
- **Stories page:** New Story (focuses builder), search, list from output stories — GET /api/parity/stories?q= (story_*.wav/mp3 only) — tested: story_test.wav 390,222 B listed, select loads /api/parity/audio/<name> into player (test file removed after test).
- **Captures page:** search transcripts, list — GET /api/parity/captures?q= (output/captures/*.txt, saved by dictate since this change) — tested end-to-end: POST /api/parity/dictate Kokoro sample → transcript EXACT, capture_file capture_20261026_223439.txt, search q=hello → 1 capture, 126 chars (test file removed after test).
- **Voices table:** GET /api/voices-table (server.py) — Name/Language/Generations/Samples/Effects/Channels from /profiles + /history — tested 19 rows. Generations = this process only; Samples = saved clone profiles (0 for fixed voices, honestly); Effects = none (per-voice presets not tracked); Channels = mono. LIMIT: MCP speak generations are NOT counted (MCP runs in parity, history lives in server) — table counts main-generate history only.
- **Effects presets page:** GET /api/parity/effect-presets — Robotic (chorus), Radio (highpass 300 + lowpass 3400 + compressor), Echo Chamber (convolution reverb decay 1.8 mix 0.5 + delay 250), Deep Voice (pitch -6 + lowpass 800 + compressor); POST /api/parity/effect-preset applies a preset — tested Radio on Kokoro wav → ok, filters lowpass/highpass/compressor, preset_radio.wav 381K (removed after test); POST /api/parity/effect-presets saves a custom preset in settings (tested my-deep, removed after test). Presets page + New Preset form wired in Effects view.

### Honest limits — do not overclaim
- Real global hotkey rebinding NOT built; shortcut text change is display-only.
- Stored transcription model/language are UI defaults; dictate endpoints still take their own model_size (large-v3-turbo default) — forcing stored values into dictate is not coded.
- Autoplay/chunk/crossfade/normalize are honoured as described above; normalize is peak-based, not LUFS loudness.
- Browser visual clicks NOT tested (HTML served + JS syntax only); live Windows hotkey/paste, fresh-install needs_download paths, and TADA-in-shipped-env remain pending from before.
- Test artifacts removed after testing; settings reset to transcription large-v3-turbo, bindings [], presets []; Kokoro reference file regenerated (8.128 s) after the direct normalize test touched it.

# BEST-OUTPUT WORK — Qwen main engine + QC + prosody — 2026-10-27, NOT pushed, NO release, NO tag
VoxLab own code only; no competitor assets/code copied. Qwen CustomVoice is now a MAIN generate engine, not just a parity-panel engine.

WHAT CHANGED:
- backend/server.py: POST /api/generate takes engine (kokoro | qwen-customvoice | qwen-1.7b), qwen_speaker, qwen_language, qwen_style (instruct, e.g. "Speak slowly and warmly"), rate (0.5-2.0), pitch (-12..+12 st), pause_ms, qc (1 default, 0 skips). Kokoro path: KPipeline first, Kokoro-ONNX fallback (parity.synthesize_kokoro) when KPipeline fails — this was REQUIRED, not optional: in the shared mahbub venv KPipeline dies on a spacy tokenizer OverflowError ("Python int too large to convert to C ssize_t") while ONNX generates the same preset voices. Bengali Parler/Edge dispatch unchanged. _finalise_generate() applies rate/pitch (ffmpeg, honest 503 if ffmpeg missing and prosody requested — never silently skipped) + QC + MP3 conversion. QC results ride on X-VoxLab-QC-* response headers (transcript truncated to 500 chars in headers).
- backend/qc.py (NEW): qc_check() measures the real file (peak/RMS dBFS, seconds, sample rate; WAV via soundfile, MP3 via librosa fallback) + transcribes with faster-whisper (small default, cached) via parity.transcribe(). qc_match = normalised exact match; qc_word_match = word-overlap ratio. Unavailable Whisper returns qc_available=false with the real error, never an invented transcript. sentence_split() splits on . ! ? … and Bengali danda with or without a following space; join_with_pauses() inserts pause_ms silence between per-sentence generations (pause is applied at generation time, not guessed into a finished WAV). apply_rate_pitch() = atempo rate + asetrate/atempo-compensated pitch (duration preserved approximately).
- backend/parity.py: generate_customvoice() now takes instruct + model_repo/model_id, so main generate reuses it for 0.6B and (when cached) 1.7B CustomVoice; parity endpoint passes instruct/style through.
- app/index.html genbar: Engine select now includes "Qwen CustomVoice 0.6B (main)" and "Qwen 1.7B (main, download)"; new controls for Qwen speaker, Qwen language, Style (instruct), Rate, Pitch, Pause ms, QC checkbox; gen() sends them to /api/generate and shows QC (available/match/word_match/model/peak/rms/transcript) in #qcstatus; genBottom() routes qwen engines to main gen() instead of the parity panel. node --check JS_OK (script 20,526 B, extracted).
- POST /api/qc-check: JSON QC for an existing file in output/ (file_path + expected_text) — returns qc_transcript + qc_match + peak/RMS.

HEAD-TO-HEAD, SAME SENTENCE (local mahbub venv, server port 8011 isolated from the shared port-8000 server):
Sentence: "VoxLab turns your text into a clear, natural voice on your own computer, with no account and no subscription."
- Kokoro af_heart (ONNX fallback, qc=1): 6.656 s / 54,812 B MP3, wall 46.4 s incl. ONNX + Whisper-small load. QC: available=true, match=true, word_match=1.0, model=small, peak=-3.64 dBFS, rms=-22.25 dBFS, transcript EXACT.
- Qwen CustomVoice Ryan, English, no style (main /api/generate, qc=0 then QC separately): 8.160 s / 56,132 B MP3, wav 391,724 B at 24 kHz, wall ~254 s incl. 0.6B float32 load + CPU generate. QC (faster-whisper small, via /api/qc-check 200): available=true, match=false, word_match=0.941, peak=-7.82 dBFS, rms=-25.91 dBFS, transcript "BoxLab turns your text into a clear, natural voice on your own computer, with no account and no subscription." — every word exact EXCEPT the brand name misheard as "BoxLab" (Whisper-small proper-noun artifact, not a generation error in the other 20 words). Qwen is louder-quieter: lower peak/RMS than Kokoro here, so per-engine loudness normalisation is still an open gap, not claimed.
- Prosody (Kokoro, rate 1.2, pitch +2 st, pause 500 ms, qc=0): 2.539 s / 18,500 B MP3, OK. Invalid rate 9.0 → HTTP 503 honest error.
- Qwen 1.7B gate: engine=qwen-1.7b → HTTP 503 {"needs_download": true, "repo": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"} — cache absent on this machine, NOT downloaded, NOT claimed working.

HONEST LIMITS (do not overclaim):
- Qwen 1.7B is NOT tested: not cached, not downloaded (several GB), CPU generation would be far slower than the 0.6B's ~254 s wall. The competitor's "Qwen3-TTS 1.7B" label is matched only as a selectable, honestly-gated engine, not as a proven 1.7B output.
- One server process holding Kokoro ONNX + Qwen 0.6B + Whisper together risks OOM on 7.7 GiB RAM: the first Qwen main-generate attempt died mid-generation when the shared port-8000 server was shut down during the run (server log: "Shutting down" after Qwen fetch started); the successful run used an isolated port-8011 server. On low-RAM machines, generate with one engine at a time; a per-engine subprocess worker is still unbuilt.
- QC uses faster-whisper "small": it mishears proper nouns (VoxLab→BoxLab above), so qc_match=false does NOT automatically mean bad audio — read qc_transcript + qc_word_match together. QC adds Whisper load time to every generate unless qc=0.
- py_compile OK (server/parity/qc). Browser requirement for parent: pushing backend/server.py + backend/parity.py + backend/qc.py (NEW) + app/index.html needs a parent/root browser task signed in as ishtiaquehasib only — I cannot operate a live browser and did not attempt it; nothing pushed, tagged, or released.

# VOXLAB SETTINGS + MODELS PAGES — 2026-10-27, NOT pushed, NO release, NO tag
VoxLab own theme only (dark navy #05081f, gradient #00d4ff -> #4868D8 -> #8b5cf6, VoxLab logo). No competitor design, assets, or text copied.
WHAT CHANGED:
- backend/server.py: GET /health {status ok, voices 19, parity_loaded}, GET /profiles (same VOICES list as /api/voices), GET /history (in-memory, this process only, last 200). generate() records history before every successful file return (Kokoro/Qwen via _finalise_generate, Edge, Parler, Edge-fallback) — verified by direct _record_history call (history len 1, af_heart/kokoro/last.mp3). History is NOT persisted to disk or any account.
- backend/parity.py: GET/POST /api/parity/settings (keep_alive, network_access, host, port; stored in output/voxlab-settings.json; POST returns restart_required=true — the RUNNING uvicorn bind host does not change without restart), GET /api/parity/updates (live GitHub releases API for ishtiaquehasib/VoxLab, real error on failure), GET /api/parity/model-catalog (20 models, HF cache path, downloaded/needs_download/downloadable per model), POST /api/parity/download-model (background thread via huggingface_hub snapshot_download; already_downloaded if cached; 503 if not downloadable; 404 if unknown), GET /api/parity/download-status/{id}.
- backend/remote.py: get_remote_config() local host now prefers env, then output/voxlab-settings.json host (127.0.0.1/0.0.0.0 only), then default — so a remote/start server honours the Settings network toggle after restart.
- app/index.html (50,810 B): Models view rebuilt as a catalog (storage location + Refresh, grouped Voice Generation / Transcription / Language Models, Download + Status buttons per model); Settings view rebuilt as 8 tabs — General (keep-alive toggle, network toggle, server URL + Online, Language select, Theme select, API Access list, App Updates + Check button), Generation (defaults note + Go to Generate), Captures (info + Go to Record), MCP (Go to MCP/Remote), GPU (auto-detect note + startup check), Logs (startup/parity/shortcut status; note: console logs live in the server window, not stored by the page), Changelog (live releases page, nothing baked in), About (MIT app code, model licences separate, clone-only-own/permissioned). Theme select ACTUALLY switches CSS: light theme overrides + system via prefers-color-scheme; language select is stored in localStorage (UI text itself stays English — stated in the UI, not faked as a translation).
MODEL CATALOG (20, repos only where known): Voice Generation — Qwen TTS 1.7B/0.6B, CustomVoice 1.7B/0.6B, LuxTTS, Chatterbox, Chatterbox Turbo, TADA 1B, TADA 3B (download DISABLED, HF repo not confirmed — not guessed), Kokoro 82M, Bengali Parler (RXD03 mirror), Bengali Edge (service, not a download); Transcription — Whisper Base/Small/Medium/Large/Turbo (Turbo = faster-whisper-large-v3-turbo); Language Models — Qwen3 0.6B/1.7B/4B.
HONEST LIMITS:
- keep_alive does NOT keep a frozen exe alive after its window closes (the exe IS its own server process); it applies to remote/start-launched servers. This is stated in the UI and the settings note.
- /api/parity/updates on this VM returned ok:false, HTTP 403 rate limit from GitHub — a real rate-limit error, not a fake version; on a normal network it returns the live latest tag/assets.
- Model download was tested only on the already-cached path (qwen-customvoice-0.6b -> already_downloaded=true) and error paths (tada-3b -> 503 disabled, unknown id -> 404); a multi-GB fresh download was NOT run, so download progress beyond idle/downloading/done/error states is unproven.
- Live HTTP tests (local mahbub venv server, stopped after, port 8000 free): /health 200 {status ok, voices 19, parity_loaded true}, /profiles 200, /history 200 [], settings GET/POST 200 (network_access true stored host 0.0.0.0, restart_required true; settings file reset afterwards to 127.0.0.1/false), model-catalog 200 with 20 models (cached on this machine: customvoice-0.6b, luxtts, chatterbox, turbo, tada-1b, kokoro, parler, whisper-turbo, qwen3-0.6b), / 200, 50,969 B with set-general/modelcatalog/Settings present. py_compile OK (server/parity/remote), node --check JS_OK (24,605 B script). One real bug found in testing: a stale leftover server on port 8000 answered the first test round (new parity routes but old server routes -> /health 404); after killing it and restarting fresh, all endpoints passed — the 404s were the stale process, not the new code.
- Browser requirement for parent: pushing app/index.html + backend/server.py + backend/parity.py + backend/remote.py needs a parent/root browser task signed in as ishtiaquehasib only — I cannot operate a live browser and did not attempt it, and nothing was pushed, tagged, or released.

# VOXLAB STARTUP SPLASH — 2026-10-27, NOT pushed, NO release, NO tag
Polished opening screen in VoxLab's OWN branding only: dark navy #05081f
with the VoxLab gradient (#00d4ff -> #4868D8 -> #8b5cf6) and the VoxLab
logo (app/logo.png, 1,445,267 B). NO competitor gold mic image, NO gold
colour, NO competitor step wording copied — step labels are neutral VoxLab
wording (e.g. "Local server running", "Voice list loaded", "Audio tools
ready"), not the competitor's splash lines.
WHAT CHANGED:
- backend/server.py: GET /api/parity/startup-status, registered BEFORE the
  parity router (parity.py already had a minimal startup-status that only
  reported router/ffmpeg/models — the server version wins on route order
  and is the one the splash calls). 7 real steps, each checked on this
  machine, none invented: server (endpoint answering), voices (19 =
  11 Kokoro + 8 Bengali), ffmpeg (bundled imageio-ffmpeg else PATH),
  bengali_edge (edge_tts package present, via find_spec — no load),
  bengali_parler (parler_tts present, HF cache present, transformers
  version reported; Parler's 4.46.1 pin conflict is stated in the detail),
  models (parity_model_status: downloaded/needs_download/bundled per
  model), output (output/ writable). ready=true only when voices==19,
  ffmpeg present, parity loaded and output writable. Bengali/model
  failures do NOT block ready — they are reported, and the splash offers
  "Continue to the studio anyway" so it can never trap the user.
- app/index.html: full-screen #splash overlay (fixed, z-index 9999,
  radial navy gradient, 180px VoxLab logo, progress bar, step list with
  ok/warning/unavailable marks, "Continue anyway" button). runStartup()
  fetches startup-status once, reveals the already-checked steps one by
  one (180 ms stagger, UI animation only — no new checks invented),
  then hides the splash after 900 ms and calls loadVoices()+checkServer().
  On fetch failure it shows the real error and the Continue button.
  The newer topbar+sidebar layout underneath is untouched.
TESTS (local server on port 8014, mahbub venv, NOT a user-PC run):
- GET /api/parity/startup-status HTTP 200: ready=true, parity_loaded=true,
  voices_count=19, all 7 steps ok on this dev machine; models 5/5 cached
  (chatterbox-turbo, luxtts, tada, qwen-customvoice, whisper-turbo —
  cached HERE, on a fresh install they honestly report needs_download).
- GET / 200: splash markup present (splash-logo x2, runStartup x2),
  topbar layout intact; GET /api/voices 200; GET /logo.png 200, 1,445,267 B.
- py_compile OK (server.py); node --check OK (18,929 B script, final).
HONEST LIMITS: model load is lazy — the splash checks download/bundled
status only and does NOT load or download any model, so a green splash
does NOT mean every model is ready to generate; first use still downloads
and loads. Edge "ok" means the edge-tts package is installed, not that a
Bengali generation succeeded (Edge still needs network access to the Edge
service). Splash animation was verified via served HTML + endpoint JSON,
NOT by watching it in a real browser (no browser test here).

# APP-LIKE UI REDESIGN — 2026-10-27, NOT pushed, NO release, NO tag
Redesigned app/index.html (was 26,312 B single scrolling page, now
33,837 B) into an app-like layout in VoxLab's OWN theme only — dark
navy #05081f / panels #0d1433 / borders #2a3a7a, gradient
#00d4ff -> #4868D8 -> #8b5cf6, VoxLab logo. NO competitor gold/black
design, NO competitor assets, NO gold colour in the file (grep: gold
absent). Original saved at /tmp/voxlab-index-orig.html (not shipped).
LAYOUT MAP:
- Topbar (sticky): VoxLab logo 44px + title + tagline + server pill
  (checkServer() -> /api/voices, "Server online"/"Server unreachable").
- Left sidebar nav (220px, horizontal scroll under 900px): Generate,
  Clone, Record, Dictate, Stories, Effects, MCP, Models, Settings.
  showView() toggles .view sections; nav buttons keep .active state.
- Generate view: voice profiles panel (cards rendered from
  /api/voices, click selects the voice select; Create Voice -> Clone
  view, Import Voice -> Record view) + generation history panel
  (session-only, in-page memory, NOT persisted) + text panel +
  sticky bottom generate bar (language filter, voice select, engine
  select: kokoro/main Generate vs Turbo/Lux/TADA/CustomVoice, Generate
  button). genBottom() routes kokoro -> gen() (/api/generate) and
  other engines -> modelGenerate() with the main text.
- Clone view: model clone controls (Turbo/Lux/TADA/CustomVoice/
  Whisper Turbo) + VoiceDesign skeleton form
  (POST /api/parity/voice-design, needs_download until real pass).
- Record view: mic recorder (30s, waveform) + mic-upload + file
  upload (/api/parity/upload, also the Import Voice path).
- Dictate view: dictate upload + Personalities Rewrite/Compose +
  transcript refinement (moved here; no separate nav item).
- Stories view: story legacy + timeline + auto-chunking.
- Effects view: full effect panel (ffmpeg + convolution reverb).
- MCP view: /api/mcp/speak + remote config/start/health.
- Models view: read-only /api/parity/models status (generate lives
  in Clone; Models does not duplicate the generate form).
- Settings view: startup status + full parity status + capture-info
  + shortcut-info + About/licence note (MIT app code; model
  licences separate; clone only own/permissioned voices).
WIRED vs SCAFFOLD (unchanged behaviour, only layout moved):
- WIRED (same function names/IDs/endpoints as before; all old IDs
  verified present, zero missing): /api/voices, /api/generate,
  /api/parity/mic-upload, /api/parity/upload, /api/parity/dictate,
  /api/parity/dictate-shortcut (server-side; live Windows hotkey
  pending), /api/parity/story, /api/parity/chunk-text,
  /api/parity/effect, /api/mcp/speak, /api/parity/rewrite,
  /api/parity/compose, /api/parity/refine-transcript,
  /api/parity/remote-config, /api/parity/remote/start,
  /api/parity/remote/health, /api/parity/models, model generate
  endpoints, /api/parity/voice-design, /api/parity/audio/*.
- NEW with this redesign: GET /api/parity/startup-status in
  backend/parity.py (real checks only: parity_router loaded,
  ffmpeg_available + ffmpeg_path, parity_model_endpoints; it does
  NOT claim any model downloaded). It did NOT exist before this
  change (grep found no startup-status in backend/ or app/);
  Settings falls back to /api/parity/status on older builds.
- STILL SCAFFOLD / NOT browser-tested: real-browser clicks on the
  new layout (JS syntax only, see below); live mic, WASAPI capture,
  Windows hotkey/paste, UI playback clicks, fresh-install
  needs_download paths, TADA in the shipped env (venv-sensitive,
  see model-endpoint section). History is session-only by design.
TESTS (this task, local mahbub venv server on 127.0.0.1:8000):
- node --check extracted script: JS_OK (16,079 B script, 1 block).
- GET /: HTTP 200, 33,837 B, contains view-generate, genbar,
  "Voice profiles". GET /api/voices: 200, 19 voices.
  GET /api/parity/startup-status: 200, ok=true,
  parity_router=loaded, ffmpeg_available=true (imageio-ffmpeg
  bundled path shown), 5 model endpoints listed.
  GET /api/parity/status: 200. Server stopped after tests.
- parity.py py_compile OK. NOT pushed, NO release, NO tag; pushing
  app/index.html + backend/parity.py needs a parent/root browser
  task signed in as ishtiaquehasib only.

# REAL INSTALLER (not a zip) — 2026-10-27, NOT pushed, NO release, NO installer binary built
User evidence: Voicebox_0.5.0_x64_en-US.msi, 518 MB — a real MSI installer.
VoxLab so far ships only a zip folder (v1.0.6 Windows zip 325 MB).
WHY A ZIP IS NOT AN INSTALLER: a zip is extract-and-find-the-exe by hand —
no wizard, no Start Menu entry, no desktop shortcut, no Settings > Apps
uninstall entry, no version/upgrade tracking, and an update means
re-extracting over (or beside) the old folder with leftovers. An installer
does all of that in one double-click and removes cleanly on uninstall.
DECISION — Inno Setup .exe, NOT WiX .msi (honest, not a dodge):
- A WiX MSI for this app would need heat-harvested components for EVERY
  file in the PyInstaller folder (thousands: torch, transformers,
  _internal/*.pyd/*.dll), a GUID per component, plus WiX v4 + WixUI
  extension plumbing — fragile for a folder whose contents change every
  release. Inno Setup takes the folder recursively with one [Files] entry
  and still gives: wizard, Start Menu + desktop shortcuts, a real
  Settings > Apps uninstall entry + uninstaller, and an upgrade path via
  a stable AppId. Output is VoxLab-Setup-<version>-x64.exe, NOT .msi —
  never rename it to .msi. To switch to a true .msi later would need:
  a .wxs + .wixproj, heat harvest of dist/VoxLab, WixUI_InstallDir, and
  a candle/light (WiX v4 dotnet tool) build step — none of that is built here.
- PER-USER, NOT PROGRAM FILES (deliberate): server.py (frozen) writes
  <exe-dir>/output and makedirs() it at startup, so a Program Files
  install would make output non-writable for a normal user and Generate
  would fail after a "successful" install. Per-user install to
  %LOCALAPPDATA%\VoxLab needs no admin prompt and keeps output writable.
  Trade-off: other Windows accounts on the same PC do not get VoxLab.
- UNSIGNED: no code-signing certificate (zero-cost rule), so SmartScreen
  WILL warn on first run. Do not claim otherwise.
FILES CHANGED (local only):
- installer/voxlab.iss (NEW): AppId {7608EC24-8A02-4072-BBE9-25FBE92E7670}
  (stable for upgrades), AppPublisher Ishtiaque Hasib, version from
  /DMyAppVersion (tag vX.Y.Z -> X.Y.Z, else 0.0.0), SetupIconFile
  assets/voxlab-logo.ico, LZMA2 solid compression, Start Menu VoxLab
  shortcut + Uninstall shortcut, desktop shortcut (Tasks: desktopicon),
  postinstall launch of VoxLab.exe (which opens http://127.0.0.1:8000
  via its own timer), [UninstallDelete] dirifempty only (user output/
  files are never deleted by uninstall). CRITICAL PATH FIX found during
  review: Inno resolves relative build-time paths from the SCRIPT's
  directory (installer/), not repo root — all repo files are therefore
  ..\assets\..., ..\LICENSE, ..\dist\VoxLab\*, ..\installer-output.
  Without this fix the build would look for installer\dist\VoxLab.
- installer/voxlab.desktop (NEW): Linux desktop entry for the .deb.
- .github/workflows/windows-installer.yml: NEW steps AFTER the smoke test
  (a broken exe can never be packaged into an installer): Derive version
  from tag, Build real installer (choco install innosetup -y, ISCC.exe
  at "C:\Program Files (x86)\Inno Setup 6\ISCC.exe", output renamed to
  VoxLab-Setup-<version>-x64.exe), Check installer size (1.8 GiB guard).
  Upload/attach now include BOTH the setup exe AND the zip fallback.
- .github/workflows/macos-installer.yml: NEW Build disk image step
  (hdiutil create -format UDZO) AFTER Package, upload/attach zip + .dmg.
  HONEST LIMIT: the PyInstaller build is a bare folder binary, NOT a
  .app bundle, so the .dmg is that folder in a disk image, NOT a
  drag-to-Applications .app install, and it is unsigned (Gatekeeper will
  flag it). Users must copy to a USER-WRITABLE folder (~/Applications),
  not /Applications (output-dir write issue, same as Windows).
- .github/workflows/linux-installer.yml: NEW Build .deb step AFTER smoke
  (copy, not move, so the tar.gz is unaffected): dpkg-deb, /opt/voxlab,
  /usr/bin/voxlab launcher, desktop entry, DEBIAN/control + postinst
  (mkdir /opt/voxlab/output, chmod 777 that dir ONLY). DEBIAN mode forced
  to 0755 (a restrictive umask made a dry-run dpkg-deb fail on control
  dir permissions). Upload/attach tar.gz + .deb, size guard for both.
  AppImage DEFERRED (not built): needs appimagetool + FUSE runtime +
  its own smoke test for no user-facing gain over .deb + tar.gz.
SIZE EXPECTATIONS (estimates, NOT measured — no installer has been built yet):
- Windows setup exe: v1.0.6 zip was 325 MB (LZMA-ish); Inno LZMA2 solid
  should land in the same ballpark, ~300-360 MB. Voicebox's 518 MB MSI
  is bigger because its payload differs (its bundled models/runtime),
  NOT because MSI is inherently bigger — VoxLab bundles NO models
  (first-run download, unchanged), so do not expect 518 MB.
- Linux .deb: ~440 MB, same payload as the 443 MB v1.0.6 tar.gz (deb
  metadata is negligible beside torch).
- macOS .dmg: ~255 MB, same payload as the 256 MB v1.0.6 ARM64 zip
  (UDZO compression, similar to zip).
VERIFICATION (local, NOT a CI run — no installer binary exists yet):
- YAML_OK all 3 workflows after the edits (PyYAML safe_load). Step order
  Windows: ... Build, Smoke (7), Derive version (8), Build installer (9),
  Check size (10), Package zip (11), Upload (12), Attach (13).
  Linux: ... Slim, Smoke (7), Build .deb (8), Package tar (9), Size (10),
  Upload (11), Attach (12). macOS: ... Smoke (6), Package zip (7),
  Build .dmg (8), Size (9), Upload (10), Attach (11).
- .iss structure: 7 sections ([Setup][Languages][Tasks][Files][Icons]
  [Run][UninstallDelete]), no tabs, referenced LICENSE + voxlab-logo.ico
  both exist in repo. iscc CANNOT run on this Linux VM (Windows-only),
  so Inno compilation is UNPROVEN until a windows-latest run — the first
  real parse/compile happens in CI, and that caveat must stay until it passes.
- .deb logic dry-run on a tiny fake folder: dpkg-deb --build OK,
  dpkg-deb --info/--contents OK (package voxlab, version 0.0.0, files
  /opt/voxlab, /usr/bin/voxlab) — proves control/postinst syntax, NOT a
  real VoxLab .deb (payload was a 3-byte dummy file).
- hdiutil CANNOT run on this Linux VM (macOS-only), so the .dmg step is
  syntax-checked only, unproven until a macos runner runs it.
BROWSER REQUIREMENT FOR PARENT: pushing installer/voxlab.iss,
installer/voxlab.desktop, and the 3 workflow files needs a parent/root
browser task signed in as ishtiaquehasib only — I cannot operate a live
browser and did not push, tag, or release anything.

# BENGALI GENERATE 500 + FFMPEG + CHUNK FIX — 2026-10-27, NOT pushed, NO release
Evidence: user Windows screenshots, app running at 127.0.0.1:8000, Generate Arjun (Parler) -> 500.
Root causes: (1) parler_tts not in frozen exe, (2) Edge fallback crashed reading
~/workspace/bangla-voice-server/deno/main.ts which does not exist on a user PC
(C:\Users\ALPHA TECH\workspace\... FileNotFoundError), (3) ffmpeg not on user PATH
-> "ffmpeg not available", (4) chunk panel returned 1 chunk 434-438 chars at max 200.
Fixes:
- backend/bengali.py: generate_edge() PRIMARY via edge-tts library directly
  (bn-BD-NabanitaNeural / bn-BD-PradeepNeural), no secret, no local file.
  Deno server ONLY if env VOXLAB_EDGE_SECRET is set (VOXLAB_DENO_URL override);
  no local source file is ever read for a secret (grep: zero main.ts /
  bangla-voice-server refs in backend/). No secret embedded in code.
- backend/server.py: /api/generate Bengali paths return JSON 500 with BOTH
  errors, not a bare traceback: {ok:false, error:"Bengali generation failed",
  voice, parler_error, edge_error, fallback_voice}. X-VoxLab-Voice-Fallback
  header kept for successful Parler->Edge fallback. MP3 conversion now uses
  _to_mp3() (imageio_ffmpeg else PATH ffmpeg) instead of os.system ffmpeg.
- backend/parity.py: _ffmpeg_path() = imageio_ffmpeg exe if present else PATH
  ffmpeg; _ffmpeg_available() uses it; ALL ffmpeg calls (capture, effect,
  story, concat via story) now use _ffmpeg_path(). requirements.txt adds
  edge-tts + imageio-ffmpeg. All 3 workflows add --collect-all imageio_ffmpeg
  (Windows PowerShell backtick continuation and Linux/macOS backslash
  continuation both fixed after an initial bad insertion; YAML_OK all 3).
- backend/parity.py split_text_chunks: danda with NO space ("।X" -> "। X")
  now splits, plus final hard enforcement: any chunk > max_chars is
  word-split, and a single over-long word is hard-split by characters.
Tests (mahbub venv, local, NOT a user-PC run):
- Chunk no-space danda at max 200: 2 chunks [178, 40], all <=200: True.
- Long sentence at max 200: 4 chunks [197, 197, 197, 5], all <=200: True.
- Oversized word 250 chars at max 200: [200, 50].
- User-like 432-char Bengali text at max 200: 3 chunks [131, 179, 120],
  all <=200: True (was 1 chunk 434 chars in the screenshot).
- JSON error path (mocked engines, fast): parler_arjun -> HTTP 500 JSON
  {parler_error:"mock parler missing", edge_error:"mock edge network down",
  fallback_voice:"edge_pradeep"}; edge_pradeep -> 500 JSON with edge_error.
  No traceback propagated to the client.
- ffmpeg: _ffmpeg_path() = /usr/bin/ffmpeg before imageio install; after
  pip-installing imageio-ffmpeg in the test venv it returns the bundled
  ffmpeg-linux-x86_64-v7.0.2 binary (exists: True) — bundled-path logic proven.
- Edge-tts Bengali sample: NOT proven on this VM. Direct generate_edge
  (edge_pradeep, Bengali text) FAILED in 2.2 s both with and without the VM
  egress proxy: ClientConnectorSSLError, speech.platform.bing.com:443,
  SSL WRONG_VERSION_NUMBER. This is a VM-proxy SSL failure, not proof it
  fails on a user PC (direct internet, no VM proxy) — but do NOT claim
  Edge generation works until a real MP3 is produced on a user PC or a
  non-proxy network. Unmocked server generate also timed out at 60 s
  (Parler load + Edge network retries), which is why the mocked test
  above was used for the JSON path.
- py_compile OK (bengali/server/parity), YAML_OK all 3 workflows.
Next push must include: backend/bengali.py, backend/server.py,
backend/parity.py, backend/requirements.txt, all 3 workflows.

# IN-APP PARITY MODEL ENDPOINTS 2026-10-27 (NOT pushed, NO release, NO tag)

- New endpoints in backend/parity.py (py_compile OK), all lazy-loaded at first
  use, all failures return the real error with HTTP 503, never a fake file:
  POST /api/parity/generate-chatterbox-turbo, POST /api/parity/generate-luxtts,
  POST /api/parity/generate-tada, POST /api/parity/generate-qwen-customvoice,
  POST /api/parity/dictate-whisper-turbo + alias POST /api/parity/generate-whisper-turbo,
  GET /api/parity/models (per-model endpoint + downloaded + needs_download +
  bundled + lab_result). /api/parity/status now also lists parity_model_endpoints.
- UI: app/index.html "Parity models" section with a model select, text,
  reference-file, CustomVoice speaker and Whisper upload inputs, Generate and
  Show model status buttons, audio player on success. node --check JS_OK
  (11,755 B script). UI playback was NOT clicked in a real browser.
- HTTP tests, live server (mahbub venv, port 8011, one server process per
  model to keep RAM free on this 7.7 GiB VM; target sentence for all clone
  tests: "This is VoxLab, a free voice studio running on my own computer."):
  - GET /api/parity/models: 200, all 5 models downloaded=true on this dev
    machine (HF cache present). On a fresh install needs_download=true until
    first download, and LuxTTS/TADA bundled=false because luxtts_src/ and
    tada_src/ are gitignored test copies, not in the repo -- those two
    endpoints honestly return 503 there until the sources are vendored.
  - Chatterbox Turbo: HTTP 200, http_turbo.wav 3.72 s / 178,604 B, 24 kHz,
    192.7 s wall incl. model load; faster-whisper small transcript EXACT.
    (Lab was 3.80 s / 182,444 B; small delta is normal generation variance.)
  - LuxTTS: HTTP 200, http_luxtts.wav 5.365 s / 515,116 B, 48 kHz, 54.2 s
    wall -- EXACT reproduction of the lab numbers (full ref <=8 s, rms=0.01,
    num_steps=8, speed=0.7); faster-whisper small transcript EXACT.
  - Qwen CustomVoice (Ryan): first attempt HTTP 503 because the test server
    was started with HF_HUB_OFFLINE=1 and qwen-tts refuses to resolve the
    cached model offline -- that was a test-env error, not an endpoint bug.
    Retry with offline off: HTTP 200, http_customvoice.wav 5.12 s /
    245,804 B, 24 kHz, 127.9 s wall; faster-whisper small transcript EXACT.
    (Lab was 5.04 s / 241,964 B; small delta is normal generation variance.)
  - Whisper Turbo dictation: POST /api/parity/dictate-whisper-turbo AND the
    alias both HTTP 200, model large-v3-turbo (no fallback), transcript
    EXACT for the Kokoro sample: "Hello, this is a free voice studio
    running on my own computer. No account, no subscription, just open
    models and my own voice." First call 47.7 s, alias call 35.4 s (model
    already loaded). This is the sample's own sentence, not the clone target.
  - TADA: HTTP 200, http_tada.wav 4.28 s / 205,472 B, 24 kHz, 1003.8 s
    wall; faster-whisper small transcript EXACT (see final TADA section).
- Incidents during testing, fixed or noted honestly:
  - An early test server on port 8010 died mid-Turbo-load (RemoteDisconnected;
    only ~1.5 GiB RAM was free at the time). Retried on port 8011 with one
    model per server process; no further OOM. Do NOT run all five engines in
    one process on a low-RAM machine.
  - A stray pkill -f "backend/server.py" in one test command matched its own
    shell and killed the running test servers; restarted cleanly on 8011.
    No release or user-facing server was affected (all test servers only).
- NOT yet proven: real-browser UI clicks; a fresh-install run (needs_download
  + bundled=false paths are coded but only the dev-machine downloaded=true
  path was HTTP-tested); TADA HTTP generation (below).

## TADA HTTP endpoint test -- DONE VIA venv_tada SERVER (mahbub server venv CANNOT load it, see below)
- First HTTP attempt (mahbub server venv, transformers 4.57.3): 503 in
  25.9 s -- gated Llama tokenizer 401, because that env has no HF token.
  Fix applied to generate_tada(): on a gated/401 load error it retries once
  with HF_HUB_OFFLINE=1 / TRANSFORMERS_OFFLINE=1 AND the in-process
  huggingface_hub constant flipped (setting the env var alone after import
  does nothing). The retry STILL 401d in that venv.
- Root cause found by direct test: with HF_HUB_OFFLINE=1, AutoTokenizer
  from the local cache FAILS in the mahbub venv (transformers 4.57.3,
  "cannot reach api/models/... offline") but SUCCEEDS in venv_tada
  (transformers 4.57.6, PreTrainedTokenizerFast) on the identical cache
  (snapshot userupload20261026: config.json, special_tokens_map.json,
  tokenizer.json, tokenizer_config.json; tokenizer_class =
  PreTrainedTokenizerFast, no tokenizer.model file). So the TADA endpoint
  is venv-sensitive: it needs the venv_tada-style transformers, not just
  the model cache. The shipped installer env must be checked against this
  before TADA is claimed there -- do NOT assume torch 2.6 + transformers
  4.57.3 will load it.
- Workaround for the HTTP proof: fastapi + uvicorn + python-multipart
  installed into venv_tada (test-only, gitignored venv, NOT shipped), server
  started there on port 8012 with HF_HUB_OFFLINE=1, /api/parity/models and
  /api/parity/status both 200. Full TADA HTTP generation: HTTP 200,
  http_tada.wav 4.28 s / 205,472 B, 24 kHz, 1003.8 s wall (load + generate);
  faster-whisper small transcript EXACT. Byte difference vs the lab file
  (4.04 s / 387,896 B) is WAV subtype only: the lab script saved float32
  via torchaudio (4 bytes/sample), the endpoint saves PCM_16 via soundfile
  (2 bytes/sample); durations are the same class (4.28 vs 4.04 s, normal
  generation variance).
- NOT proven by this: TADA in the main server venv (mahbub, transformers
  4.57.3) -- it 503s there on the tokenizer -- and on a fresh install
  (tada_src/ is gitignored, endpoint 503s until vendored). TADA-in-app is
  therefore proven only in the venv_tada configuration, not universally.

# REQUIREMENTS.TXT CONFLICT FIXED — 2026-10-27 (NOT pushed, NO release, NO tag, workflows UNCHANGED)

- File changed: [backend/requirements.txt](sandbox://workspace/voice-studio/backend/requirements.txt) only. Old: torch>=2.8 / torchaudio>=2.8 / numpy unpinned, no transformers line — unsatisfiable against chatterbox-tts, which is why workflows had to filter it and why v1.0.5 Windows pip failed (numpy 1.25.2 source tarball, "Cannot import setuptools.build_meta", no "Successfully installed" line).
- New pins: torch==2.6.0, torchaudio==2.6.0, numpy>=1.24,<2, transformers>=4.57. Kept: fastapi, uvicorn, kokoro>=0.9, chatterbox-tts, soundfile, pynput, pyperclip (+ sounddevice stays Windows-only commented).
- Verification: py_compile OK for all backend/*.py. Pip dry-run (mahbub_test venv, --report /tmp/voxlab_req_report.json) exit=0: "Would install transformers-5.2.0 pynput-1.8.2 pyperclip-1.11.0 ..." with 165 deps already satisfied in that venv, including torch 2.6.0, torchaudio 2.6.0, numpy 1.26.4, chatterbox-tts 0.1.7, fastapi 0.162.0, uvicorn 0.54.0, kokoro 0.9.4, soundfile 0.14.0 — exactly the pinned set.
- Why it resolves (PyPI metadata, checked directly): chatterbox-tts 0.1.7 pins torch==2.6.0, torchaudio==2.6.0, numpy<2,>=1.24, transformers==5.2.0 — all consistent with the new file, and 5.2.0 satisfies >=4.57, so Qwen3 loads (unlike 4.46.x). chatterbox-tts 0.1.6 is intentionally REJECTED by transformers>=4.57 because it pins transformers==4.46.3 (the Parler-venv line that cannot load Qwen3).
- Honest caveat: the dry-run was NOT clean-room — most deps were already satisfied in that venv, so it proves consistency, not a fresh-install time. A clean-room dry-run with system pip 24.0 backtracked for 10.8 min without finishing (transformers 5.21 -> 5.2.0 backtracking), then was killed. So: the file is now satisfiable as written, but a fresh pip run may still be slow unless the workflow keeps its torch-first step or a future change pins transformers==5.2.0 / chatterbox-tts>=0.1.7. Workflows were NOT changed in this task, per instructions — the next push still needs a workflow decision (install this file as-is, or keep filtering it as a belt-and-braces step).
- Browser requirement for parent: none for this file change itself; pushing it needs a parent/root browser task signed in as ishtiaquehasib only.

# TUTORIAL 01 VIDEO RENDERED — 2026-10-27 (NOT pushed, NO release, NO tag)

- DONE: tutorials/tutorial-01-clone.mp4 rendered and watched via frames. ffprobe: duration 22.500000 s, size 551,144 B, video h264 1920x1080 @ 30 fps, audio aac 24,000 Hz. Narration WAV tutorials/tutorial-01-clone-narration.wav 22.528 s / 1,081,388 B (540,672 frames, 24 kHz), Kokoro ONNX af_heart en-us, 5 blocks: 4.12 s / 4.12 s / 3.56 s / 4.86 s / 4.27 s with 0.4 s gaps. Render: PIL frames piped to ffmpeg libx264 + aac, -shortest, 675 frames.
- Honest deviations from the script's 60-90 s target: the real narration is only 22.53 s, so the video is 22.50 s — NOT padded with silence to fake 60-90 s. Narration is English (Kokoro en-us cannot speak the script's Roman Bengali lines); on-screen text matches the English narration, plus the Bengali line "নিজের কণ্ঠ ক্লোন করুন" (NotoSansBengali-Bold + raqm, conjuncts verified in frames). Narration is the Kokoro fixed voice, NOT presented as a cloned user voice.
- QC watch: frames extracted at 2 s / 6 s / 11 s / 15 s / 20 s and viewed — all clean: VoxLab logo, dark navy #05081f + gradient bar, correct step card per timestamp (Step 1 at 2 s, Step 3 at 11 s, Done card at 20 s), progress dots highlight the current step, "Demo — UI screenshots pending" label on every card, permission note "Use your own voice, or a voice you have permission to use." on every card. NO real UI screenshots, NO mock UI, NO Voicebox screenshot — text step cards + logo only, as the script required when no real screenshot exists.
- Files: tutorials/tutorial-01-clone.mp4, tutorials/tutorial-01-clone-narration.wav, tutorials/tutorial-01-clone-narration.txt, tutorials/gen_narration.py, tutorials/render_tutorial01.py. QC frame PNGs deleted after viewing. NOT pushed — parent must push via the ishtiaquehasib browser route if this is to ship. Still missing for a non-Demo tutorial: real app screenshots from a real running build (v1.0.6 smoke or later).

# WORKING FIX SPRINT — 2026-10-27 (NOT pushed, NO release, NO tag)

- 1) Windows smoke parity check: .github/workflows/windows-installer.yml smoke now requires GET /api/parity/status -> 200 AND fails if smoke.log/smoke-err.log contains "parity routes disabled", same as Linux (line 129 area) / macOS (line 124). This closes the parity-bypass gap: server.py loads parity routes in try/except, so / + /api/voices 200 alone could previously ship a parity-broken build.
- 2) Frozen remote/start launcher: backend/remote.py start_local_server() now selects, in order: frozen -> [sys.executable] (launcher=frozen_executable; the frozen exe's __main__ reads VOXLAB_SERVER_HOST/PORT and runs uvicorn + browser open), unfrozen with existing server.py -> [python, server.py] (launcher=server_script), neither -> ok=False "server script missing: ..." (launcher=none). Old code failed frozen with "server script missing" even though the exe itself is the server, because PyInstaller ships no .py source (modules are .pyc in PYZ). Module docstring updated with the frozen-launcher explanation.
- 3) Frozen Parler CLI fallback documented in code: backend/bengali.py now states at PARLER_CLI and in generate_parler() docstring that frozen venv_parler and parler_cli.py source both do not exist (venv never bundled, .py source not bundled as .pyc-only PYZ), so frozen generate_parler() is ALWAYS the in-process fallback; an incompatible frozen transformers version surfaces its real error, never fake audio. No behaviour changed, documentation only, per task.
- 4) requirements.txt already aligned — verified, NOT re-changed: dependency lines (comments excluded) are torch==2.6.0, torchaudio==2.6.0, numpy>=1.24,<2, transformers>=4.57; 0 dependency lines with torch>=. The old torch>=2.8 vs chatterbox torch==2.6.0 conflict is gone from the file itself (workflow filtering is now redundant but harmless; workflow update is a separate step).
- Tests: py_compile OK (remote.py, bengali.py, server.py, parity.py); YAML_OK all 3 workflows. Frozen simulation (fake _MEIPASS=/tmp/fake_meipass, fake exe=/tmp/fake_exe/VoxLab, no server.py in _MEIPASS): BASE=/tmp/fake_meipass, SERVER_SCRIPT missing=False-exists check, start_local_server timeout result launcher=frozen_executable with proc args [/tmp/fake_exe/VoxLab] (proves the exe, not the missing .py, was launched); missing-script case returns ok=False "server script missing" with launcher=none. Local server (mahbub venv, port 8009): /api/voices 200 with 19 voices, / 200 24,894 B, /api/parity/status 200, "parity routes disabled" count 0 in server log; server stopped after (curl down confirmed).
- Honest limit: Windows PowerShell smoke syntax was not locally syntax-checked (pwsh absent on this VM); its first real parse is on windows-latest. Real Windows double-click still unproven.

# REAL CONVOLUTION REVERB — 2026-10-27 (NOT pushed, NO release, NO tag)

- DONE: backend/parity.py reverb is now REAL convolution, not the aecho approximation. Method: synthetic exponential-decay impulse response (seeded noise, -60 dB at decay_s, RT60-style, deterministic seed 42) convolved with the ffmpeg-filtered audio via scipy.signal.fftconvolve when scipy is present, else numpy FFT convolution (numpy is a required dependency). Pedalboard is NOT installed and NOT imported; it is only a commented optional line in backend/requirements.txt (alternative engine, unused). The old multi-tap aecho path survives ONLY as reverb_aecho_fallback, used when convolution itself fails (e.g. numpy unavailable) and labelled with reverb_fallback_reason — it is not the default and must never be reported as convolution.
- New params: POST /api/parity/effect accepts reverb_decay_s (0.2-3.0, default 1.2) and reverb_mix (0.0-0.8, default 0.3); out-of-range values return ok=False with the real error. Convolution output is FULL length (dry + IR tail), peak-normalised to <= 0.99; the ffmpeg temp file (*.noreverb.wav) is deleted after convolution. UI label updated in app/index.html: "reverb (convolution)", no longer "(approx)".
- Exact tests (source kokoro_af_heart.wav 8.128 s, 24 kHz mono; venv = mahbub_test venv, scipy present, pedalboard absent):
  - Full chain (pitch +3st, lowpass 8000 Hz, chorus, delay 200 ms, reverb convolution, compressor): test_effect_conv.wav 9.535 s / 457,702 B, reverb_engine=convolution_scipy_fft, filters contain NO reverb aecho (only the 200 ms delay tap). Prior aecho full chain was 8.513 s / 408,696 B — the longer duration is the real 1.2 s IR tail, not a bug.
  - Reverb-only direct: test_reverb_only.wav 9.324 s / 447,582 B (8.128 + 1.2 = 9.328 expected, 0.004 s rounding), tail last 1.0 s RMS 0.0040 / peak 0.0441 — non-silent, so the tail is real audio, not a trimmed dry signal.
  - Reverb-only via HTTP POST /api/parity/effect (server port 8010): test_effect_http.wav 9.324 s / 447,582 B, identical to the direct run (deterministic IR), reverb_engine=convolution_scipy_fft.
  - numpy FFT fallback: _fft_convolve_channel with scipy.signal blocked returns convolution_numpy_fft and the exact result [0.5, 0.5, 0.125, 0.0] for data [0.5, 0.25, 0.0] x IR [1.0, 0.5].
  - Aecho fallback (forced convolution failure): test_reverb_fallback.wav 8.284 s / 397,698 B, applied includes reverb_aecho_fallback, reverb_engine=reverb_aecho_fallback, reverb_fallback_reason="simulated numpy missing".
  - Validation: reverb_decay_s=9 returns ok=False "reverb_decay_s must be between 0.2 and 3.0". No *.noreverb.wav temp files left in output/.
- py_compile OK for backend/parity.py. NOT pushed, NO release — parent must push via the ishtiaquehasib browser route if this is to ship.
- Honest limits remaining: the IR is synthetic (no recorded room impulse / IR file upload yet); reverb is not Pedalboard; the shipped-env scipy presence is unproven (shipped env has soundfile + numpy per requirements.txt, scipy is used only when present and numpy FFT covers its absence).

# QWEN VOICEDESIGN SKELETON + TUTORIAL 01 SCRIPT — 2026-10-27 (NOT pushed, NO release, NO tag, NO download, NO video)

## Licence verdict: NOT verified on the HF card itself — do NOT ship as Apache-verified
- HF card fetch 2026-10-27: https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign returned 106 lines (Overview, 10 languages, Quickstart with qwen-tts pip install + CustomVoice example). NO licence field appeared in that fetched text. The HF connector doc in this workspace is an unfilled template with no helper, so no HF-API licence field could be read that way either.
- Secondary sources ONLY (do NOT count as the HF-field check): the Qwen3-TTS paper quoted in secondary coverage says tokenizers and models are released under Apache 2.0; DeepInfra's VoiceDesign page frontmatter says license: apache-2.0; multiple secondary guides say Apache 2.0. Until the HF card's own licence field is seen, VoxLab must say "licence unverified on HF card", never "Apache 2.0 verified".
- Consequence: NO model download was started, NO qwen-tts install was attempted, NO generation was claimed.

## Disk + torch-conflict check (exact)
- Disk: /home/hatch 100G total, 43G used, 57G available — a ~4.54 GB VoiceDesign download would fit on disk, but /tmp is only 512M tmpfs, so any download must use a workspace cache dir, never /tmp. RAM is the real limit: this VM has ~7.7 GiB, no GPU; 1.7B in bf16 is an OOM/slowness risk on CPU, same lesson as TADA (bf16 + low_cpu_mem_usage, never float32).
- Torch conflict CONFIRMED as a conflict, not assumed away: qwen-tts pyproject (via DeepWiki) needs torch>=2.9.1, transformers>=4.57.3, accelerate>=1.12.0, onnxruntime>=1.24.2, librosa>=0.11.0, soundfile>=0.13.1. VoxLab backend/requirements.txt now ships torch==2.6.0 / torchaudio==2.6.0 (chatterbox-tts pin; the file was already aligned in the workspace, the old torch>=2.8 note in earlier PARITY.md sections is stale). A shared env cannot satisfy both pins. VoiceDesign therefore needs an ISOLATED env (separate venv, like venv_tada/venv_parler) or a torch upgrade that re-proves chatterbox — neither was attempted here.
- Languages: 10 (Chinese, English, Japanese, Korean, German, French, Russian, Portuguese, Spanish, Italian). NO Bengali. VoiceDesign does NOT close the Bengali gap; Bengali stays Parler + Edge. Same description does NOT guarantee the identical voice every time (description-only, no reference audio, no preset speaker) — UI must never promise identical voices.

## What was actually built (skeleton only)
- backend/parity.py: PARITY_MODELS entry id "qwen-voicedesign", status "needs_download" with the licence-unverified + torch-conflict notes; VOICEDESIGN_MODEL_ID = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"; VOICEDESIGN_DIR env VOXLAB_QWEN_VOICEDESIGN_DIR (default HF hub cache path); voice_design_available() (package + model-dir checks, no import at server start); generate_voice_design(text, language, instruct) — lazy import inside the function only, returns needs_download=true with licence_verified_on_hf_card=false when package/model are absent, and returns the real exception (never fake audio) if a present model fails to load/generate; POST /api/parity/voice-design (text required, 400 if empty; 503 if needs_download, 400 on other failure; audio_url only on real success).
- Verification: py_compile OK; stubbed-FastAPI direct test PASS — generate_voice_design("Hello, this is a test.", "English", "A calm young woman") returned ok=false, needs_download=true, synthesized=false, package_present=false, model_dir_present=false, licence_verified_on_hf_card=false, NO download, NO audio file. This is a skeleton test, NOT a VoiceDesign generation test — do NOT upgrade the status until a real generation + transcript check passes.
- NOT done: no model download, no qwen-tts install, no isolated venv, no UI panel, no real generate, no licence re-check. Next steps in order: (1) see the HF card licence field itself, (2) build an isolated venv with torch>=2.9.1 + qwen-tts, (3) download ~4.54 GB to a workspace cache dir, (4) CPU bf16 generate + Whisper transcript check, (5) only then change status from needs_download.

## Video tutorials: script + render plan only, NO video faked
- Created tutorials/tutorial-01-clone-script.md (3,518 B): Tutorial 01 "Clone your voice in VoxLab", 60-90 s target, neutral opening (no religious greeting), 5 narration blocks, step cards 1-4, honest note that cloning needs your own or permissioned voice. Render plan reuses the proven cartoon/ffmpeg pipeline: PIL 1920x1080@30fps, dark navy #05081f, VoxLab gradient, NotoSansBengali-Bold (verified present at /usr/share/fonts/truetype/noto/NotoSansBengali-Bold.ttf), emoji at 109 px only, ffmpeg 8.1.2 mux at a common 24 kHz rate, narration from VoxLab Kokoro af_heart or the presenter's own clone. Real app screenshots ONLY from a real running build; otherwise the video is labelled "Demo — UI screenshots pending". tutorials/tutorial-01-clone.mp4 and narration WAV do NOT exist yet and must not be claimed until rendered + watched through + ffprobe seconds/bytes recorded. Later tutorials (dictation, stories, effects, Bengali, MCP) are planned only.

# FULL-WORKING AUDIT 2026-10-27 — PARITY.md top status vs actual code (NOT pushed, NO release, NO tag)

- Method: grep of backend/*.py + app/index.html, py_compile OK, compared against PARITY.md evidence sections below. Classification: DONE-TESTED = real HTTP/direct test with exact numbers in PARITY.md; CODE-ONLY = endpoint/function exists but its live OS/GPU/browser test is still pending; MISSING = no endpoint/file at all.
- Small fix in this audit: app/index.html stale footer line said all parity models "Needs model download, not tested" — contradicted PARITY_MODELS tested entries — corrected to "tested in lab, not bundled, needs first-use download". py_compile OK after edit.

## Gap table (clean list for v1.0.7)

| Feature | Verdict | Exact evidence / gap |
|---|---|---|
| Core server + 19 voices + homepage | CODE-ONLY (frozen) / DONE-TESTED (local) | Local frozen simulation 127.0.0.1:8009: /api/voices 200, 1,427 B, 19 voices; / 200, 21,527 B. Real Windows/macOS/Linux double-click + CI smoke still unproven (v1.0.6 in flight). |
| Kokoro fixed voices (/api/generate) | DONE-TESTED (local) | kokoro_af_heart.wav 8.128 s / 390,188 B, 24 kHz; transcript exact via Whisper. Bundling in frozen installer depends on pip success (v1.0.5 pip failed). |
| Chatterbox clone (primary) | DONE-TESTED (lab, not in-app endpoint) | clone.py generate_clone exists; chatterbox_clone.wav exact transcript (PARITY.md audit). No dedicated /api/parity/clone endpoint — clone is wired only via MCP default/claude paths and test scripts. |
| Mic record (30 s, waveform) | CODE-ONLY | POST /api/parity/mic-upload exists; synthetic 2.0 s WAV 64,044 B -> ok, peak 0.366, rms 0.259, 100 peaks; 31 s rejected. Real browser mic + Windows live test PENDING. UI recorder code present, unclicked in a real browser. |
| System capture (WASAPI/PulseAudio) | CODE-ONLY | POST /api/parity/capture + capture_windows_audio() (WasapiSettings loopback) exist; Linux VM honestly returns Windows-only error. Real Windows WASAPI capture PENDING; sounddevice NOT in requirements (optional comment only). |
| Dictation (upload transcribe) | DONE-TESTED (local HTTP) | POST /api/parity/dictate: Kokoro sample ~41 s, large-v3-turbo, transcript EXACT: "Hello, this is a free voice studio running on my own computer. No account, no subscription, just open models and my own voice." |
| Dictation shortcut + paste anywhere | CODE-ONLY | POST /api/parity/dictate-shortcut + GET /api/parity/shortcut-info (Ctrl+Alt+V / Cmd+Option+V) exist; headless test: transcript exact but clipboard failed honestly (503, no clipboard tool). Real Windows hotkey + paste into another app PENDING. |
| MCP agent voices | DONE-TESTED (local HTTP, Kokoro only) | POST /api/mcp/speak: claude -> af_bella, kokoro-onnx, 5.0 s request, 1.173 s audio. Non-Kokoro agent voices honestly return synthesized:false. No MCP pill/ACP/A2A/WebSocket — those are website "coming soon" only. |
| Personalities Rewrite/Compose | DONE-TESTED (lab, minimal) | 6 presets; Qwen3-0.6B rewrite noir 5.4 s verbatim:false, compose warm 4.9 s; refine "um, hello..." -> "hello this is a test of the refinement" 39.5 s direct-function. Refine=true via HTTP in torch env still UNPROVEN. 0.6B rewriting is minimal, sometimes verbatim. |
| Stories timeline + sequence + crossfade | DONE-TESTED (local) | Timeline 8.128 s / 390,222 B; sequence crossfade 300 ms 11.662 s / 559,848 B exact; legacy concat fixed to 12.262333 s / 588,670 B, crossfade 11.661875 s. UI panel wired, playback not clicked in a real browser. |
| Auto-chunking (incl. Bengali danda) | DONE-TESTED (local) | POST /api/parity/chunk-text: 4 chunks [122,499,499,499] at max_chars=500; 12 chunks at 500 in direct test. Text only, synthesizes nothing (stated in UI). |
| Audio effects | CODE-ONLY (partial) | POST /api/parity/effect: full chain 8.513 s / 408,696 B, preview 3.057 s, pitch +/-12st, low/highpass, chorus, delay, compressor tested locally. Reverb = multi-tap aecho APPROXIMATION, NOT convolution/Pedalboard — MISSING as real reverb. No per-voice effect presets saved. |
| GPU (CUDA/MPS/DirectML) | CODE-ONLY | backend/device.py: CUDA->MPS->DirectML->CPU, env override, OOM CPU retry. VM tests only prove CPU fallback (detect=cpu, whisper cpu/int8). Real CUDA/MPS/DirectML speed runs PENDING; torch-directml NOT in requirements. |
| Remote mode | CODE-ONLY | GET remote-config, POST remote/start (already_running proven on ports 8001/8002, 19 voices), GET remote/health exist. No auth/encryption, no auto-discovery (mDNS/LAN scan MISSING). Frozen remote/start is BROKEN-BY-DESIGN: SERVER_SCRIPT=_MEIPASS/backend/server.py, but PyInstaller does not ship .py source — returns honest "server script missing" error, not a crash. Same frozen .py gap affects bengali PARLER_CLI path. |
| Bengali (Parler + Edge) | DONE-TESTED (lab, Parler Arjun first) | /api/generate parler_* / edge_* dispatch exists; Parler Arjun ranked first by user verdict 2026-10-26; Edge Pradeep 54.26 s, Parler Arjun 55.31 s (Mahbub test). Only Arjun individually proven; other 5 Parler speakers + Edge presets are listed voices, not individually transcript-verified. Frozen Parler venv path falls back to in-process (venv never bundled). |
| Models: Chatterbox Turbo / LuxTTS / TADA / Qwen CustomVoice / Whisper Turbo / Qwen3 LLM | DONE-TESTED (lab, not bundled) | Turbo 3.80 s / 182,444 B exact ([laugh] untested); LuxTTS 5.37 s / 515,116 B exact only with full-ref + steps=8 + speed=0.7; TADA 4.04 s / 387,896 B exact both Whisper models; CustomVoice Ryan 5.04 s / 241,964 B exact (other 8 speakers untested); Whisper Turbo exact on Kokoro sample; Qwen3-0.6B as above. NONE is a shipped/in-app selectable engine — PARITY_MODELS is a status list only, no /api/parity/generate-<model> endpoint. |
| Qwen VoiceDesign | MISSING | Investigation only in PARITY.md; NO endpoint, NO download, NO test. Needs HF licence verification + torch-conflict check first. 10 languages, no Bengali. |
| Video tutorials | MISSING | No video files, no tutorial endpoints, website says coming soon. |
| Global shortcut registration at app start | CODE-ONLY | global_shortcut.py + shortcut-info exist; no evidence the running server registers the hotkey on startup (server.py __main__ only opens browser). |
| Installer (Windows/Linux/macOS) | CODE-ONLY / UNPROVEN | v1.0.5 Windows exe icon confirmed (1,996 KB) but app did not run (pip failure + _MEIPASS bug). v1.0.6 fixes + CI smoke are in flight via parent browser task — NOT audited here, do not claim. requirements.txt itself remains unsatisfiable (torch>=2.8 vs chatterbox torch==2.6.0); workflows filter it, the file itself is unfixed — v1.0.7 gap. |
| Testimonials / star counts | MISSING (by rule) | Correctly absent: no-fake rule, only real users after release. Do not add. |

## v1.0.7 clean gap list (no version claims)
1. Real-OS proof: Windows double-click, macOS double-click, Linux run — after v1.0.6 smoke, not before.
2. Frozen remote/start + frozen Parler CLI: ship a frozen-safe launcher or remove the frozen path claim.
3. Real reverb (Pedalboard/convolution) or keep aecho label forever — do not rename it reverb without the engine.
4. Per-voice effect presets; MCP pill/ACP/A2A/WebSocket; remote auto-discovery; remote auth warning in UI.
5. Model endpoints: selectable in-app Turbo/LuxTTS/TADA/CustomVoice/Whisper Turbo, or keep them lab-only and say so.
6. Qwen VoiceDesign implementation only after licence + torch check; video tutorials; other 8 CustomVoice speakers; other Parler speakers; [laugh] tags test; refine=true via HTTP in torch env.
7. Align requirements.txt to torch==2.6.0/numpy>=1.24,<2 + transformers>=4.57 (LLM needs it; Parler venv 4.46.1 cannot load Qwen3).
8. Windows live tests only a user PC can give: mic, WASAPI capture, Ctrl+Alt+V paste, DirectML GPU, UI playback clicks.

# Linux/macOS smoke audit 2026-10-27 (NOT pushed, NO release, NO tag)

- Shipped-folder check, PASS: Linux smoke (line 129) runs AFTER Slim (line 101) and BEFORE Package (165)/Upload/Attach — it tests ./dist/VoxLab/VoxLab, the slimmed folder that is then tarred (tar -C dist VoxLab). macOS smoke (line 94) runs AFTER Build and BEFORE Package (130)/Upload/Attach — it tests ./dist/VoxLab/VoxLab, the folder then zipped (ditto --keepParent dist/VoxLab). Attach is tag-only in both; Upload has no if:always(), so a failed job uploads nothing. A smoke failure therefore cannot attach a broken Linux/macOS build.
- BUG FOUND + FIXED LOCALLY (both workflows): parity routes are OPTIONAL in server.py (try/except, "parity routes disabled" fallback) — a build whose parity.py fails to import still serves / 200 and /api/voices 200 (19 voices, verified: 11 Kokoro + 8 Bengali in server.py VOICES), so the old smoke would have let a parity-broken build attach. Fix: smoke now also requires GET /api/parity/status -> 200 AND fails if smoke.log contains "parity routes disabled". Windows smoke has the SAME gap — flagged for parent, not fixed here (this task is Linux/macOS only).
- GAP FIXED LOCALLY (macOS only): macOS had no release-size guard while Linux has a 1.8 GiB guard (line 170); a >2 GiB macOS zip would have failed late at attach. Added "Check release size" (line 134, stat -f%z, same 1.8 GiB threshold) after Package, before Upload/Attach.
- RESIDUAL GAP, NOT fixed (would need model downloads): smoke proves server start + static UI + voices + parity router loaded, but NOT a real generation — Kokoro/Parler/Chatterbox imports in server.py are lazy (get_pipe / generate), so a generation-broken build could still pass smoke. A generate smoke would need a Kokoro model download on the runner; do not add it silently — parent decision.
- OPEN, NOT changed: macOS Intel matrix still uses macos-13 (line 33), the job that stayed queued on v1.0.4. A runner-label change was NOT made locally (replacement label unverified); do not claim Intel is fixed until a run proves it. v1.0.4 latest known good, per parent context + release page check (v1.0.4, commit 3016fdf, body still shows macOS text): Linux VoxLab-Linux-x64.tar.gz 464,547,432 B (443 MB, sha256 40582256…), macOS ARM64 255 MB. Note: the v1.0.4 release page text fetch did NOT list asset sizes — the 443 MB / 255 MB figures are from parent context, not re-verified from that page fetch; re-verify from the release asset list before quoting them as freshly checked.
- Verification: PyYAML safe_load -> YAML_OK both workflows; step order confirmed above; bash -n OK for both extracted smoke scripts (22 lines each, parity-status + disabled-check present).

# CI SMOKE TESTS ADDED TO ALL 3 INSTALLER WORKFLOWS 2026-10-27 (NOT pushed, NO release, NO tag)

- Why: prior checks were only simulation (frozen-path simulation, local server) plus Actions build success — and v1.0.5 proved build success is NOT runtime proof: pip had failed (setuptools.build_meta), fastapi/uvicorn were never installed, yet PyInstaller still "succeeded" with a broken 11 MB exe that closed instantly on the user's Windows desktop. A runtime gate in CI is the fix for that class of failure.
- What was added (all 3 workflows, existing icon/torch fixes untouched — grep confirms windows --icon and torch==2.6.0 pins still present):
  - Linux (.github/workflows/linux-installer.yml, line 129): "Smoke test built app (CI runtime check)" AFTER the Slim step (so it tests the slimmed folder that actually ships) and BEFORE Package/Upload/Attach. Bash: starts ./dist/VoxLab/VoxLab in background (log to smoke.log), polls GET http://127.0.0.1:8000/api/voices up to 30x2s = 60s, then requires GET / -> 200 and exactly 19 voices via python3 JSON count; server always killed afterwards (trap). Any failure (no answer, wrong count, non-200) fails the job with the server log printed.
  - macOS (.github/workflows/macos-installer.yml, line 94): same bash smoke step, AFTER Build with PyInstaller and BEFORE Package/Upload/Attach, same binary path dist/VoxLab/VoxLab, same 60s poll, 19-voice check, trap kill. Applies to both matrix runners (macos-14 arm64, macos-13 x64).
  - Windows (.github/workflows/windows-installer.yml, line 88): same gate in PowerShell (shell: pwsh, AFTER Build, BEFORE Package/Upload/Attach): Start-Process dist\VoxLab\VoxLab.exe (stdout/stderr to smoke.log/smoke-err.log), poll Invoke-WebRequest http://127.0.0.1:8000/api/voices up to 30x2s = 60s, fail if the exe exits early, require 19 voices (ConvertFrom-Json .voices.Count) and GET / -> 200, server always stopped in a finally block.
- Verification: PyYAML safe_load -> YAML_OK for all three workflows; step order confirmed (Build -> [Slim on Linux] -> Smoke -> Package -> Upload -> Attach); bash smoke script extracted and bash -n -> OK; 19-voice count matches backend/server.py VOICES (verified: 19 entries). pwsh is NOT installed on this VM, so the Windows PowerShell script could NOT be syntax-checked here — its first real parse is on windows-latest; keep that caveat until a Windows run passes it.
- HONEST NOTE: a passing CI smoke proves the built server starts and serves /api/voices + / on THAT runner OS (ubuntu-latest / macos-14 / macos-13 / windows-latest) — a real OS run of the real binary, not a path simulation — but it does NOT prove a user double-click on their own desktop (different machine, Gatekeeper/SmartScreen, missing system libs, port conflicts, browser launch). Do NOT claim "Windows app works" from CI smoke alone; the user's own double-click test remains the final proof. Next push must include all 3 workflow files.

# Frozen split applied to bengali.py + remote.py 2026-10-27 (NOT pushed, NO release, NO tag)

- Closes the follow-up flagged in the section below: backend/bengali.py and backend/remote.py still used the old two-dirname BASE. Both now use the same frozen split as server.py/parity.py: when frozen, DATA_DIR = sys._MEIPASS (fallback: exe dir), BASE = DATA_DIR, OUT (bengali.py) = dirname(sys.executable)/output (writable, beside exe — NOT _internal). Unfrozen logic unchanged (project root).
- bengali.py: DATA_DIR/BASE/OUT split added (sys import added); PARLER_VENV_PYTHON now resolves under _MEIPASS when frozen, where no venv exists, so generate_parler honestly falls back to in-process generation (venv is never bundled — behaviour unchanged, path no longer silently wrong).
- remote.py: DATA_DIR/BASE split added; SERVER_SCRIPT = BASE/backend/server.py, i.e. _MEIPASS/backend/server.py when frozen, project-root backend/server.py unfrozen.
- Verification: py_compile OK (both files); unfrozen import: bengali BASE/OUT = voice-studio / voice-studio/output, remote SERVER_SCRIPT = voice-studio/backend/server.py; frozen simulation (sys.frozen=True, sys._MEIPASS=/tmp/fake_meipass, sys.executable=/tmp/fake_exe/VoxLab): bengali BASE=/tmp/fake_meipass, OUT=/tmp/fake_exe/output, remote SERVER_SCRIPT=/tmp/fake_meipass/backend/server.py — exactly as specified.
- HONEST NOTE: same as the section below — real Windows double-click run still unproven (no Windows machine here); do NOT claim "Windows app works" until the user runs the next build. Next push must include backend/bengali.py + backend/remote.py alongside server.py, parity.py, windows-installer.yml.

# Windows app STILL not running — CORRECTED frozen fix 2026-10-27 (NOT pushed, NO release, NO tag)

- CORRECTION to the previous fix: the previous fix was WRONG. User screenshot proof: extracted Windows folder = VoxLab.exe (1,996 KB, icon present) + _internal/ ONLY, NO app/ beside the exe. PyInstaller onedir puts --add-data files into _internal/ (sys._MEIPASS), NOT the exe dir. So BASE = dirname(sys.executable) made StaticFiles look for dist/VoxLab/app, which does not exist — exe still failed at startup. Before/after paths: BEFORE (v1.0.5, broken): static dir dist/VoxLab/app (absent). AFTER (this fix): static dir dist/VoxLab/_internal/app (where --add-data actually lands).
- Fix (backend/server.py + backend/parity.py, both): when frozen, DATA_DIR = sys._MEIPASS (fallback: exe dir), OUT = dirname(sys.executable)/output (writable, beside exe — NOT _internal, which must not collect outputs). Unfrozen logic unchanged (project root). server.py StaticFiles now uses DATA_DIR/app; parity.py OUT/uploads use the exe-dir OUT. NOTE (follow-up, out of this task's scope): backend/bengali.py and backend/remote.py still use the old two-dirname BASE — they will need the same frozen split before a frozen Parler/remote path is trusted.
- SECOND root cause (Windows run #7 log): pip install -r backend/requirements.txt FAILED with "Cannot import setuptools.build_meta", NO "Successfully installed" line — fastapi/uvicorn/torch/kokoro were never installed, yet PyInstaller still "succeeded" with a broken 11 MB exe. pip also backtracked numpy to a 1.25.2 source tarball.
- Fix (.github/workflows/windows-installer.yml ONLY, linux/macOS untouched): new "Install build tools" step (pip setuptools wheel) before dependencies; new "Install chatterbox-compatible torch/numpy first" step (torch==2.6.0 / torchaudio==2.6.0 / numpy>=1.24,<2, same pins as linux/macOS — every chatterbox-tts pins torch==2.6.0 while requirements.txt asks torch>=2.8, unresolvable in one install); dependencies now install a Python-filtered requirements file (torch/torchaudio/numpy lines removed, verified locally: filtered file keeps fastapi, uvicorn, kokoro>=0.9, chatterbox-tts, soundfile, pynput, pyperclip) with --only-binary=numpy; new hard-gate "Verify server dependencies installed" step (import fastapi+uvicorn, pip show torch/torchaudio/numpy) so a silent pip failure can never again produce an exe.
- Verification: py_compile OK (server.py, parity.py); YAML_OK all three workflows; frozen simulation with a fake onedir layout (/tmp/frozen_sim: VoxLab.exe path + _internal/app/index.html, NO app/ beside exe — proven absent): import with sys.frozen=True, sys._MEIPASS=_internal, sys.executable=fake exe gave DATA_DIR=/tmp/frozen_sim/_internal, OUT=/tmp/frozen_sim/output, static dir exists, index.html exists; live server on 127.0.0.1:8009 under the same frozen env: GET /api/voices HTTP 200, 1,427 B, 19 voices; GET / HTTP 200, 21,527 B, title "VoxLab — free local voice studio"; server stopped afterwards.
- HONEST NOTE: icon IS confirmed on the user's desktop (v1.0.5 screenshot, 1,996 KB exe with logo icon). Real Windows double-click run is STILL unproven — no Windows machine here — so do NOT claim "Windows app works" until the user runs the next (v1.0.6) build. Next push must include backend/server.py, backend/parity.py, .github/workflows/windows-installer.yml (assets/voxlab-logo.ico already on main from v1.0.5).

# Windows app not running + no logo icon — FIXED LOCALLY 2026-10-27 (NOT pushed, NO release, NO tag)

- Root cause (run failure): frozen PyInstaller layout. Unfrozen, backend/server.py is two dirnames below the project root, so BASE worked. Frozen, the module lives in dist/VoxLab/_internal/backend/, so the old two-dirname math landed in dist/VoxLab/_internal/ instead of dist/VoxLab/ — StaticFiles(directory=BASE/app) failed at startup and the exe closed instantly with no UI. Simulation proved it: old BASE = .../VoxLab/_internal, new BASE = .../VoxLab.
- Fix (backend/server.py): if getattr(sys, "frozen", False): BASE = dirname(abspath(sys.executable)), else the old two-dirname logic. OUT = BASE/output in both cases. Same frozen fix applied to backend/parity.py (its OUT/uploads had the identical bug).
- Fix (no logo icon): generated assets/voxlab-logo.ico from app/logo.png (1254x1254 RGB) via PIL, sizes 256,128,64,48,32,16, 95,339 bytes, verified by re-reading (ICO, sizes {(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)}). Added --icon "assets/voxlab-logo.ico" to the PyInstaller command in .github/workflows/windows-installer.yml ONLY. Linux/macOS workflows untouched (grep: no --icon in either). Note: the .ico must be included in the next browser push or the Windows build will fail on the missing icon file.
- Fix (double-click shows UI): server.py __main__ now schedules threading.Timer(1.5s, webbrowser.open(http://host:port)) before the blocking uvicorn.run(), and prints the URL. Console stays visible (no --windowed in the PyInstaller command) so startup errors are seen, not hidden.
- Verification: py_compile OK for server.py + parity.py; YAML_OK for all three workflows (Windows/Linux/macOS); frozen simulation OK (above); ico file exists, 95,339 B.
- HONEST NOTE: real Windows run still needs the user's test — no Windows machine was available here, so the frozen exe has not been double-clicked and the icon has not been seen on a real Windows desktop yet. Do NOT claim "Windows app works" until that test passes.

# LEGACY STORY CONCAT MIXED-RATE BUG — FIXED 2026-10-27 (NOT pushed, NO release, NO site change)

- Bug: POST /api/parity/story legacy `segments` + crossfade_ms ignored crossfade AND used ffmpeg concat demuxer with `-c copy`, which keeps each segment's raw samples but declares the FIRST segment's sample rate for the whole file. A 44.1 kHz segment in a 24 kHz container played back stretched: the full-server test recorded api_sequence.wav 14.933 s / 716,878 B instead of the true 12.262 s (its 130,560 frames at 44.1 kHz play as 5.44 s at 24 kHz).
- Reproduction here (same segments: kokoro_af_heart.wav 24 kHz 8.128 s + mcp_default.wav 44.1 kHz 2.961 s + mcp_claude.wav 24 kHz 1.173 s, true total 12.262 s): old concat_story gave test_legacy_bug.wav 14.741 s at 24 kHz — same mechanism, slightly different total than the server test's 14.933 s (its mcp_claude had been overwritten by the MCP test mid-run); the bug class, not the 0.19 s delta, is what was fixed.
- Fix (backend/parity.py only): concat_story(wav_names, out_name, crossfade_ms=0) now routes legacy segments through build_story_timeline() instead of the concat demuxer, and POST /api/parity/story legacy mode now passes crossfade_ms through. build_story_timeline's _trim_filter now adds an explicit `aresample=24000` to every track, so all segments are re-encoded to VoxLab's common 24 kHz rate before amix/acrossfade (44.1 kHz inputs are resampled down, never stretched). No other caller of concat_story exists (only parity_story); legacy signature/output name unchanged, result gains mode/seconds/sample_rate keys.
- Tests (direct function calls, real ffmpeg, py_compile OK):
  - Legacy no crossfade: test_legacy_fixed.wav 12.262333 s, 588,670 B, rate 24000 — exact (8.128+2.961+1.173).
  - Legacy crossfade_ms=300: test_legacy_fixed_xfade.wav 11.661875 s, mode sequence-crossfade — exact (12.262-0.600).
  - Endpoint legacy via parity_story({segments, crossfade_ms: 300}): test_legacy_endpoint.wav 11.661875 s, 559,848 B, mode sequence-crossfade — crossfade no longer ignored.
  - Single file: kokoro 8.128 s unchanged; single 44.1 kHz mcp_default 2.960542 s at 24 kHz (resampled, not stretched).
  - Error case preserved: missing file -> ok False "missing file: nope.wav".
  - Timeline regression: build_story_timeline sequence crossfade 300 on the same 3 clips 11.661875 s, unchanged from its earlier exact result.
- NOT re-tested here: a live HTTP POST through a running server (function-level tests only, FastAPI stubbed as system Python lacks fastapi — same method as prior backend tests); Windows mic/capture/GPU live tests remain pending on a real user PC.

# FULL LOCAL SERVER TEST — ALL NEW ENDPOINTS, REAL HTTP CALLS 2026-10-27 (NOT pushed, NO release, NO site change)

- Server: backend/server.py started locally with mahbub venv (fastapi+uvicorn+faster-whisper+librosa), TMPDIR=voice-studio/tmp, HF_HUB_OFFLINE=1, http://127.0.0.1:8000. /api/voices HTTP 200 (19 voices), homepage HTML served. Server stopped after tests.
- CRITICAL BUG FOUND BY THIS TEST AND FIXED LOCALLY (not in any release yet): POST /api/parity/dictate first returned HTTP 500, NameError: name 'transcribe' is not defined — the `def transcribe(...)` line was missing in backend/parity.py, its body orphaned after dictate_shortcut's return. Fixed by restoring `def transcribe(audio_path, model_size="large-v3-turbo"):` before that body; py_compile OK afterwards. Dictate/shortcut then passed (below). This bug means any release built from the pre-fix parity.py would have broken dictation — the fix must be included in the next push.
- Test table (all real HTTP, Kokoro inputs: kokoro_af_heart.wav 8.128 s / 390,188 B at 24 kHz, mcp_default.wav 2.961 s at 44.1 kHz, mcp_claude.wav 1.173 s at 24 kHz — note mcp_claude was overwritten by the MCP test itself):
  - POST /api/parity/chunk-text, max_chars=500: HTTP 200, 0.0 s, 4 chunks, lengths [122, 499, 499, 499].
  - POST /api/parity/story timeline (kokoro@0, mcp_default@1.0 s vol 0.8, mcp_claude trimmed 0-1 s @2.0 s): HTTP 200, 0.6 s, api_timeline.wav 8.128 s, 390,222 B, mode timeline.
  - POST /api/parity/story tracks sequence, crossfade_ms=300: HTTP 200, api_tracks_xfade.wav 11.662 s, 559,848 B, mode sequence-crossfade (expected 8.128+2.961+1.173-0.600=11.662, exact).
  - POST /api/parity/story tracks sequence, crossfade_ms=0: HTTP 200, api_tracks_seq.wav 12.262 s, 588,670 B (sum exact).
  - LEGACY BUG FOUND IN THIS TEST, FIXED 2026-10-27 (see top section): POST /api/parity/story with legacy `segments` + crossfade_ms=300 ignored crossfade (concat_story path) AND produced api_sequence.wav 14.933 s / 716,878 B instead of 12.262 s — because concat -c copy puts the 44.1 kHz mcp_default file into a 24 kHz container without resampling (its 130,560 frames play as 5.44 s). Legacy concat now routes through the timeline builder with a common 24 kHz resample and honoured crossfade; do NOT use the old -c copy behaviour.
  - POST /api/parity/effect full chain, correct param names (pitch_semitones=3, delay_ms=200, lowpass=8000, chorus, reverb, compressor): HTTP 200, api_effect_full2.wav 8.513 s, 408,696 B, applied [pitch_+3st, lowpass_8000Hz, chorus, delay_200ms, reverb_aecho_approx, compressor, speed_1.0, volume_1.0]. NOTE: first attempt used wrong param names pitch/delay — endpoint silently ignored them (applied list had no pitch/delay); the UI sends the correct pitch_semitones/delay_ms names, so this was a test-script error, not an endpoint bug.
  - POST /api/parity/effect preview (pitch_semitones=-2, chorus, preview_seconds=3): HTTP 200, api_effect_preview.wav 3.057 s, 146,810 B (3 s + filter tail).
  - POST /api/parity/mic-upload (kokoro file as mic clip): HTTP 200, 0.2 s, mic_kokoro_af_heart.wav, bytes 390188, seconds 8.128, sample_rate 24000, channels 1, peak 0.49, rms 0.076, 100 waveform peaks.
  - POST /api/mcp/speak agent=claude, text "Hello, this is a test.": HTTP 200, 5.0 s, synthesized true, voice af_bella, engine kokoro-onnx, seconds 1.173, audio mcp_claude.wav via /api/parity/audio/mcp_claude.wav.
  - GET /api/parity/audio/api_timeline.wav: HTTP 200, 390,222 B, ffprobe 8.128 s — UI player route works.
  - POST /api/parity/dictate (Kokoro sample, AFTER transcribe fix): HTTP 200, ~41 s, available true, model large-v3-turbo, lang en, transcript EXACT: "Hello, this is a free voice studio running on my own computer. No account, no subscription, just open models and my own voice."
  - POST /api/parity/dictate-shortcut {audio_file: kokoro_af_heart.wav, paste: false}: HTTP 503, transcript exact (same text), error "transcript produced but clipboard copy failed: no clipboard tool available" — honest headless behaviour, NOT a transcription failure.
  - GET /api/parity/shortcut-info: HTTP 200, hotkey <ctrl>+<alt>+v, platform Linux, headless true, paste_requires_gui true, live_windows_test_pending true.
  - GET /api/parity/capture-info: HTTP 200, available false, monitor_sources [], error "pactl not installed and no monitor source found" — no capture on this VM, as expected.
  - GET /api/parity/remote-config: HTTP 200, mode local, base_url http://127.0.0.1:8000, local_server_running true, encrypted false.
  - GET /api/parity/remote/health: HTTP 200, reachable true, status 200, voices_count 19, mode local.
  - POST /api/parity/rewrite (warm narrator, HF offline): HTTP 200, 17.6 s, method template, llm_used false, note "LLM unavailable ... offline mode is enabled" — honest fallback, not a claimed LLM rewrite.
  - POST /api/parity/refine-transcript refine=false: HTTP 200, refined false, original unchanged.
  - Device helper direct: detect_device()=cpu, resolve_device('dml')=cpu, whisper_device()=(cpu, int8) on this GPU-less VM.
- STILL PENDING — needs a real user PC, never claimed here: Windows live mic recording, Windows WASAPI system capture, Windows Ctrl+Alt+V hotkey + paste into another app, CUDA/MPS/DirectML GPU speed runs, macOS Intel installer (still queued in Actions), UI playback clicked in a real browser (curl only here), legacy segments concat mixed-rate fix.

# Remote mode + transcript refinement + personalities improvement — IMPLEMENTED AND TESTED 2026-10-27 (backend + app/index.html only, NOT pushed, NO release, NO site change)

- Remote mode (new backend/remote.py): VOXLAB_REMOTE_MODE local (default) / remote, VOXLAB_REMOTE_BASE_URL, VOXLAB_SERVER_HOST/PORT. server.py __main__ now binds those env vars (defaults still 127.0.0.1:8000). Endpoints: GET /api/parity/remote-config (mode/base_url/valid/local_server_running), POST /api/parity/remote/start (one-click local server: returns already_running=True if a server already answers, else spawns backend/server.py and polls /api/voices until it answers), GET /api/parity/remote/health?base_url= (reachable/status/voices_count or the real error). Remote fetch allowlist is GET /api/voices and /api/parity/status ONLY — any other path is rejected, so this is not an open proxy.
- Transcript refinement (new POST /api/parity/refine-transcript {transcript, refine}): refine=false returns the original unchanged (refined=False). refine=true uses Qwen3-0.6B to clean fillers/self-corrections/punctuation only, preserving meaning/names/facts; if the LLM is unavailable or empty, the original returns with refined=False and the real error — never an invented "refined" transcript.
- Personalities improvement (backend/llm.py + parity.py): 6 presets (neutral, warm narrator, noir detective, news anchor, friendly teacher, calm guide) add a trait to the LLM prompt; free-form persona names still work (no trait). Rewrite now retries once at higher temperature if the first pass is verbatim, and the response always carries verbatim + quality_note ("0.6B rewriting is minimal and sometimes verbatim — not strong rewriting"). Compose uses the same presets. Template fallback unchanged (llm_used=False, real error in note). New GET /api/parity/personas lists presets. app/index.html: Personalities label updated from "Template only", plus new Remote panel (config/start/health buttons) and Refinement panel (toggle + textbox).
- LLM load bug FIXED in this task (real blocker, found by testing, not assumed): llm.py used device_map, which requires the `accelerate` package — not a VoxLab dependency — so loading failed with "device_map ... requires accelerate". Fixed by loading on CPU memory then .to(device); no new dependency. Second blocker documented, NOT a code bug: the pinned venv_parler transformers 4.46.1 predates the Qwen3 architecture, so the LLM cannot load there at all ("Transformers does not recognize this architecture") — LLM tests below used venv_tada (transformers 4.57.6, torch 2.7.1+cpu), which is the correct env for Qwen3-0.6B. The shipped server env (requirements.txt, unpinned transformers) must therefore resolve to >=4.57 for the LLM path; the Parler venv must never be used for the LLM.
- Exact LLM test results (venv_tada, CPU, Qwen3-0.6B cached 1.5 GB): refine "um, hello, uh, this is, this is a test of the, of the refinement" -> "hello this is a test of the refinement" in 39.5 s (first load included; fillers + duplicate "this is / of the" removed, meaning kept). Rewrite "The cat sat on the mat all afternoon." as noir detective -> "The cat lounged on the mat for the afternoon." verbatim=False in 5.4 s (genuine reword). Compose warm narrator on "rain" -> '"Rain is a natural beauty that brings life and color to the world."' in 4.9 s (on-topic; quotes included by the model, harmless).
- Exact remote endpoint test results (real FastAPI server on localhost, temp venv with fastapi+uvicorn+python-multipart, server stopped afterwards): server on port 8001 -> GET /api/voices 200 (19 voices); GET /api/parity/remote-config -> mode local, base_url http://127.0.0.1:8001, local_server_running true; GET /api/parity/remote/health?base_url=http://127.0.0.1:8001 -> reachable true, status 200, voices_count 19; health for port 9999 -> reachable false, "Connection refused" (real error); POST /api/parity/refine-transcript refine=false -> original unchanged; GET /api/parity/personas -> all 6 presets; POST /api/parity/rewrite in the torch-less test venv -> template fallback, llm_used false, real "No module named 'torch'" error in note; POST /api/parity/remote/start while running -> already_running true. Fresh one-click launch separately proven: start_local_server(port 8002) from a not-running state -> ok true, already_running false, pid returned, health reachable true with 19 voices, stop -> stopped true, then not running. Remote-mode config proven in-process: VOXLAB_REMOTE_MODE=remote + base http://192.168.1.20:8000 -> mode remote, valid true, remote_url correct; base "not-a-url" -> valid false with a clear error. All edited files py_compile OK.
- HONEST LIMITS, do NOT over-claim: (1) refine=true was proven by direct function test, NOT via the HTTP endpoint (the endpoint test venv had no torch, so it could only prove the refine=false + template-fallback paths via HTTP; refine=true via HTTP needs a torch env and is still unproven end-to-end). (2) No auth, no encryption in remote mode — use only on a network the user controls; do not expose a VoxLab server publicly. (3) No automatic discovery (no mDNS/LAN scan) — the user types the remote host:port; one-click remote setup with auto-discovery is still open. (4) Remote GPU is not a property of this module: a remote machine accelerates only if its own device.py detects CUDA/MPS; DirectML (Windows) is still undetected (needs torch-directml, not in requirements). (5) 0.6B personalities remain minimal — strong rewriting needs a larger persona LLM, not downloaded. (6) UI Remote/Refine panels are wired to the endpoints but were not clicked in a real browser here (server test was curl only).

# App UI wired to stories/effects/chunk endpoints — DONE 2026-10-27 (app/index.html only, NOT pushed, NO release, NO site change)

- Stories panel: legacy segments concat still works (Build story), plus Build story timeline — one track per line as file,start,trim_start,trim_end,volume, crossfade_ms (0-5000, sequence mode only), out_name; result plays via /api/parity/audio/<output> (not /output/, which is not mounted — caught and fixed during verification).
- Auto-chunking panel (new): POST /api/parity/chunk-text with text + max_chars (min 100, default 2000); shows count, total chars, and each chunk with its char length. Text only — synthesizes nothing, stated in the panel.
- Effects panel: POST /api/parity/effect now sends speed, volume, echo plus pitch_semitones (-12..12), lowpass/highpass Hz, delay_ms (0-2000), chorus, reverb, compressor, preview_seconds; result plays via /api/parity/audio/<output>. Reverb label stays honest: multi-tap aecho approximation, NOT convolution/Pedalboard reverb.
- Honest labels kept: Stories/Effects headers say backend-wired but UI playback not yet tested in a real browser; mic/capture live tests still pending (Record/Dictate panels unchanged); no fake available claims added.
- Verification: HTML tag-balance check clean (no unclosed/stray tags), all new element IDs present, all three endpoints present in the script, node --check on the extracted <script> passes (JS_OK, 10,226 bytes). No live browser/server test was run here — FastAPI server was not started in this task, so UI playback against a running server is still untested.

# Windows DirectML detection — IMPLEMENTED, CPU FALLBACK TESTED 2026-10-27 (backend/device.py only, NOT pushed, NO release, NO site change)

- backend/device.py now detects DirectML: detection order auto = CUDA -> Apple MPS (Metal) -> DirectML (torch-directml, Windows only, AMD/Intel GPUs) -> CPU. Env override VOXLAB_DEVICE now accepts dml; resolve_device() and is_gpu() include dml. torch-directml is NOT added to requirements.txt — it is documented in device.py as an optional Windows-only install (`pip install torch-directml`), so Linux/macOS installs are unaffected. If the package is absent, detection returns CPU, never crashes.
- Whisper: CTranslate2 has no MPS or DirectML backend, so whisper_device() still returns (cpu, int8) for mps/dml machines; only CUDA gets float16.
- Tests on this GPU-less, DirectML-less VM, all exit 0, no crash: VOXLAB_DEVICE=auto -> cpu, dml -> warns "requested but not available, falling back to cpu" -> cpu, cuda -> same warning -> cpu, bogus -> warns invalid -> cpu, cpu -> cpu; detect_device()=cpu, resolve_device('dml')=cpu, is_gpu()=False, whisper_device()=(cpu, int8) in every case; py_compile OK; requirements.txt confirmed to contain no torch-directml (intended).
- HONEST LIMIT: DirectML acceleration is UNTESTED on a real Windows GPU — this VM has neither a GPU nor torch-directml, so this change proves only safe degradation to CPU, not DML speed. Do NOT claim DirectML works until a Windows GPU run proves it.

# GPU device support — IMPLEMENTED, CPU PATH TESTED 2026-10-27 (backend only, NOT pushed, NO release, NO site change)

- New file backend/device.py: shared helper. Detection order auto = CUDA (torch.cuda, covers NVIDIA CUDA and Linux ROCm builds) -> Apple MPS (torch.backends.mps, Metal) -> CPU. Env override VOXLAB_DEVICE=auto|cuda|mps|cpu; an unavailable requested accelerator (or an invalid value) warns and falls back to CPU instead of crashing. is_oom_error() detects torch CUDA OOM / "out of memory" for the CPU retry. whisper_device() returns (cuda, float16) or (cpu, int8) — CTranslate2 has no MPS backend, so MPS machines use CPU for Whisper.
- Changed: backend/bengali.py _load_parler .to("cpu") -> .to(get_device()); generate moves description/prompt tensors to the model's actual device (so a model that fell back to CPU after OOM stays consistent) and retries once on CPU on OOM. backend/clone.py generate_clone(device="cpu") -> device=None (auto via resolve_device), OOM retries once on CPU with a fresh model. backend/llm.py load_llm device_map="cpu" -> device_map=get_device(), float32 kept on GPU too, OOM load retries once on CPU; _generate moves inputs to the model's device. backend/parity.py transcribe WhisperModel(device="cpu", int8) -> whisper_device(), OOM retries that same model once on CPU (result gains device_fallback="cpu") before falling through to "small".
- Remaining "cpu" strings in those files are only the fallback branches and the tensor-to-numpy .cpu() conversion in parity.py (correct on any device) — no engine still hardcodes CPU as its only device.
- HONEST LIMITS (do not over-claim): DirectML is NOT detected — it needs torch-directml, which is not in requirements.txt; Windows DirectML is still open. Remote-mode (connection to a remote machine) is NOT part of this change. GPU paths (cuda/mps) are UNTESTED on a real GPU — this VM has none, so only the CPU path is live-tested (below).
- Tests on this GPU-less VM, all exit 0: system python (no torch) -> cpu; venv_parler torch 2.8.0+cpu, cuda=False, mps=False -> get_device()=cpu, whisper_device()=(cpu, int8); VOXLAB_DEVICE=cuda -> warns and falls back to cpu; VOXLAB_DEVICE=bogus -> warns, auto -> cpu; py_compile OK for all 5 files. Live CPU-path proof: parity.transcribe() on output/kokoro_af_heart.wav via the mahbub venv returned exact transcript "Hello, this is a free voice studio running on my own computer. No account, no subscription, just open models and my own voice." (model small, lang en). Full model loads (Parler/Chatterbox/Qwen3) were NOT re-run here — import + helper tests only, plus the proven Whisper path.

# Windows mic + WASAPI capture + dictation shortcut — CODE IMPLEMENTED AND TESTED 2026-10-27 (backend only, NOT pushed, NO release, NO site change, NO live Windows test)

- Mic upload: new POST /api/parity/mic-upload backed by save_mic_upload() in backend/parity.py — same 50 MB cap as /api/parity/upload plus a 30 s recorder cap (0.5 s container tolerance), WAV waveform metadata measured from the file (sample_rate/channels/seconds/peak/rms + 100 normalised peaks); non-WAV duration via ffprobe with waveform=None and an honest note. Browser recorder in app/index.html now posts to /api/parity/mic-upload (generic file upload still posts to /api/parity/upload).
- System capture: new capture_windows_audio() in backend/parity.py — Windows WASAPI loopback via sounddevice WasapiSettings(loopback=True), 1-60 s, written with soundfile; capture_system_audio() now dispatches Windows to it (Linux PulseAudio unchanged). pyaudiowasapi is NOT used (its loopback API is untested here, so claiming it would be a guess). On non-Windows or without sounddevice it returns an honest unavailable error, never a fake capture. requirements.txt gains only a commented optional sounddevice note (no hard dependency, no installer-resolution change).
- Dictation shortcut: new POST /api/parity/dictate-shortcut backed by dictate_shortcut() — global_shortcut.trigger_dictation() wired to the SAME transcribe() as POST /api/parity/dictate (faster-whisper Turbo first, small fallback), clipboard copy via pyperclip/native tool, paste into the focused app only if paste=True and a GUI session exists. New GET /api/parity/shortcut-info and global_shortcut.shortcut_status(): hotkey Ctrl+Alt+V (Windows/Linux) / Cmd+Option+V (macOS). Every shortcut/capture response carries live_windows_test_pending=True.
- Exact local test (test script /tmp/test_mic_upload.py, FastAPI stubbed because system Python has no fastapi — functions are real ffmpeg/wave/stdlib runs, not stubs): synthetic 2.0 s 16 kHz mono WAV, 64,044 bytes -> mic_upload ok=True, filename mic_synthetic_mic_test.wav, bytes 64044, seconds 2.0, sample_rate 16000, channels 1, peak 0.366, rms 0.259, 100 waveform peaks; synthetic 31.0 s clip -> ok=False "over the 30 s recorder limit", no file left behind; capture_windows_audio() on this Linux VM -> ok=False "WASAPI loopback capture only runs on Windows", live_windows_test_pending=True; shortcut trigger with a stub transcript on headless Linux -> transcript produced but clipboard copy honestly failed (no pyperclip/xclip here), ok=False — that is the honest headless behaviour, not a wiring bug. py_compile OK for parity.py + global_shortcut.py.
- NOT live-tested and NEVER claimed: real browser mic recording, real Windows WASAPI loopback recording, real Windows Ctrl+Alt+V hotkey + paste into another app — all three need a real Windows PC with a mic/GUI session, which this VM does not have. Until those three runs pass on Windows, VoxLab must keep labelling them pending, not available.

# Stories timeline + full effects + auto-chunking — IMPLEMENTED AND TESTED 2026-10-27 (backend/parity.py only, NOT pushed, NO release, NO site change)

- What changed: concat-only stories replaced by build_story_timeline() with two real modes: (1) timeline — tracks with explicit start offsets, trim_start/trim_end, per-track volume, mixed in parallel via adelay + amix; (2) sequence — clips in list order, crossfade_ms>0 joins with acrossfade (triangular), 0 = back-to-back re-encode (trim/volume still apply). Legacy concat_story() and the segments payload still work unchanged.
- Effects: apply_effect() extended (legacy speed/volume/echo args unchanged) with pitch_semitones (-12..12, asetrate + atempo, duration preserved), lowpass/highpass (Hz), chorus (ffmpeg chorus filter), delay_ms (single aecho tap), reverb (multi-tap aecho approximation — HONEST LIMIT: ffmpeg 8.1.2 here has no reverb filter and pedalboard is not installed, so this is NOT a convolution/Pedalboard reverb), compressor (acompressor), and preview_seconds (same chain, trimmed output = live-preview parameters). New endpoints: POST /api/parity/story accepts tracks + crossfade_ms, POST /api/parity/chunk-text accepts {text, max_chars}, POST /api/parity/effect accepts all new effect params.
- Auto-chunking: split_text_chunks() splits at sentence boundaries (. ! ? … and Bengali danda ।), groups sentences into chunks <= max_chars, hard-splits only a single over-long sentence at word boundaries. Chunking synthesizes nothing — each chunk is synthesized separately, then assembled with the story builder (crossfade optional). This is the Voicebox-style auto-split flow, text-level only.
- Test inputs (all from output/, no new synthesis): kokoro_af_heart.wav 8.128 s, mcp_default.wav 2.961 s, mcp_claude.wav 1.365 s. Direct function tests + endpoint tests both passed; FastAPI was stubbed for the direct tests (system Python has no fastapi installed) — the functions themselves are real ffmpeg runs, not stubs.
- Exact test results: timeline (kokoro@0, mcp_default@1.0s vol 0.8, mcp_claude trimmed 0-1s @2.0s) -> test_timeline.wav 8.128 s, 390,222 B (expected max offset+duration = 8.128 s, exact). Sequence crossfade 300 ms, 3 clips -> test_sequence_xfade.wav 11.854 s, 569,064 B (expected 8.128+2.961+1.365-0.600 = 11.854 s, exact). Sequence no crossfade, 2 clips -> test_sequence.wav 11.089 s (expected 11.089 s, exact). Full effect chain (pitch +3st, lowpass 8000 Hz, chorus, delay 200 ms, reverb approx, compressor) on kokoro -> test_effect_full.wav 8.513 s, 408,696 B (8.128 s source + echo/reverb tails, expected). Preview (pitch -2st, chorus, 3 s) -> test_effect_preview.wav 3.071 s (3 s requested + ~0.07 s filter tail). Chunking: long test text -> 12 chunks, max chunk 499 chars at max_chars=500, final sentence preserved. Legacy concat + legacy effect still pass. Errors honest: missing file, bad trim, pitch +20 all return ok=False with the real error.
- NOT yet Voicebox parity (do not claim it): no GPU acceleration (all engines CPU), no remote mode, no video tutorials, no real-user testimonials, no live mic/system-capture/dictation-shortcut test on a user PC, no per-voice effect presets saved, no UI timeline editor (backend + endpoints only — app/index.html story/effect panels not wired to the new params yet), reverb is aecho-approx not Pedalboard/convolution. Test files in output/: test_timeline.wav, test_sequence_xfade.wav, test_sequence.wav, test_effect_full.wav, test_effect_preview.wav, test_endpoint_story.wav, test_endpoint_effect.wav.

# Qwen VoiceDesign — INVESTIGATION ONLY, NOT implemented, NOT tested (2026-10-27)

- What it is: Qwen3-TTS VoiceDesign creates a NEW voice from a natural-language description, with no reference audio and no preset speaker. Official repo: Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign, https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign . API (upstream qwen-tts package): Qwen3TTSModel.from_pretrained("Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign") then generate_voice_design(text=..., language=..., instruct="<voice description>").
- Open / licence: public HF repo, no gating/terms-acceptance evidence found (unlike Llama/IndicF5). Licence: Apache 2.0 for the Qwen3-TTS family per multiple secondary sources (HF card text fetch did NOT expose a licence field, so verify the licence tag on the HF repo before shipping — do not ship on secondary sources alone).
- Size (CHECKED, NOT downloaded): ~3.8-4.5 GB for the 1.7B weights — sources disagree (3.8 GB variant table, 3.9 GB measured, 4.54 GB family figure), so quote a range, not one exact byte count, until a real download lists file sizes. Plus the qwen-tts package + shared 12Hz tokenizer/codec. NOT bundled in any installer; must be an opt-in first-run download like other parity models.
- How it differs from Qwen CustomVoice (already tested in VoxLab): CustomVoice = 9 FIXED preset speakers (Ryan tested 5.04 s exact, other 8 untested) via generate_custom_voice(text, language, speaker, optional instruct), high consistency, 0.6B (2.4 GB in local cache) and 1.7B variants. VoiceDesign = NO preset speakers, NO speaker encoder, NO reference audio; voice comes only from the instruct description, so the same description does NOT guarantee the identical voice every time (consistency: medium/variable, vs CustomVoice high). Base (third variant) = clone from reference audio via generate_voice_clone, not VoiceDesign.
- Languages: 10 — Chinese, English, Japanese, Korean, German, French, Russian, Portuguese, Spanish, Italian. NO Bengali. VoiceDesign does NOT close the Bengali gap; Bengali stays Parler + Edge.
- Other limits (secondary sources, verify in test): VoiceDesign is 1.7B ONLY (no 0.6B VoiceDesign); upstream comparison says no streaming for VoiceDesign (Base streams, VoiceDesign does not); 1.7B needs ~4 GB VRAM in bf16 / 16 GB+ RAM for CPU batch work and is too slow for real-time on CPU — this VM (7.7 GB RAM, no GPU) is therefore a high OOM/slowness risk for a live test, same lesson as TADA (bf16 + low-memory load, never float32 on this VM).
- Concrete implementation plan for backend/parity.py (NOT done yet):
  1. Add PARITY_MODELS entry id "qwen-voicedesign", job "Design a voice from a text description", status "needs_download" — never "ready" until a real generation + transcript check passes.
  2. Add a lazy loader (no import at server start, no model in installer): pip package qwen-tts in a separate install note first, check its torch requirement against the chatterbox torch==2.6.0 pin BEFORE adding it to requirements.txt (conflict risk, unresolved).
  3. Add generate_voice_design(text, language, instruct) wrapper returning (wav, sr, model_id, engine="qwen-voicedesign"), with device_map="cpu", dtype=torch.bfloat16 on CPU (official examples use cuda:0 + flash_attention_2, which is NOT available on CPU — CPU fallback must be coded and tested, not assumed).
  4. Add API route e.g. POST /api/parity/voice-design {text, language, instruct} with honest response fields (model, designed_voice_note: same description may vary) and a saved-description/voice-prompt cache option (upstream supports saving voice prompts; reuse a description's prompt for repeatability instead of promising identical voices).
  5. App UI: a "Design a voice" panel — free-text voice description + language dropdown (10 languages only) + text box. NOT a speaker dropdown (there are no speakers), and NO Bengali option for this engine.
  6. Test protocol before any claim: 1 short English sentence + 1 description (e.g. warm confident female narrator in her 30s), record seconds/bytes/sr, transcript-check with faster-whisper, repeat the SAME description once and report whether the voice sounds the same or different. Only then flip status from needs_download to tested.
- Honest blockers: (a) ~4 GB download + CPU slowness/OOM risk on this VM; (b) torch-version conflict with qwen-tts untested; (c) licence tag not verified on the HF page itself; (d) voice-consistency is inherently variable, so the UI must never promise "same voice every time"; (e) no Bengali, no streaming (per upstream comparison). Until the test in step 6 passes, VoxLab must keep listing Qwen VoiceDesign as NOT in VoxLab / coming in parity phase.


# Status update 2026-10-27 ~01:44 — v1.0.3 results + glow theme live + v1.0.4 pending

- v1.0.3 release: https://github.com/ishtiaquehasib/VoxLab/releases/tag/v1.0.3, Latest, tag on main commit a3f25f5, created 2026-10-27 01:19 +06, 4 assets.
- macOS ARM64: SUCCESS, 5m 17s, release asset VoxLab-macOS-ARM64.zip 255 MB (artifact 253 MB).
- Windows: VoxLab-Windows-x64.zip 10.9 MB in v1.0.3 release.
- Linux: install + PyInstaller + package passed (12m 14s), but attach failed — Actions artifact VoxLab-Linux-x64 3.13 GB exceeds GitHub's 2 GiB release-asset limit, so NO Linux release asset yet. ResolutionImpossible install failure did NOT recur.
- macOS Intel (macos-13 x64): still QUEUED at 01:35 +06, no artifact, no failure recorded yet.
- Glow theme v3 LIVE: blogger-theme-v3-glow.xml (265,138 B) installed via Blogger Theme Restore on voxlabapp.blogspot.com (blog 5790026849845117931, hasibtechqore account), logged-out desktop verified — hero cyan-purple glow, glowing download button to /releases/latest, Languages 24, MCP, pricing split, no overlap observed. Mobile NOT checked, no mobile pass claimed.
- v1.0.4: Linux CPU-only torch + slim fix prepared (see section below); upload + tag v1.0.4 via browser task (ishtiaquehasib only) PENDING at time of this note. Real Linux size only proven by the v1.0.4 Actions run.
- No GitHub/Blogger changes were made by this status-note task; theme files and workflows untouched here.

# v1.0.4 patch (NOT pushed, NO release, NO tag) — Linux release size fix, prepared 2026-10-27

| Item | Exact result |
|---|---|
| v1.0.3 symptom | Linux Actions artifact VoxLab-Linux-x64 3.13 GB exceeded GitHub's 2 GiB release-asset limit, so the attach step failed and no Linux release asset was produced. macOS ARM64 artifact was only 253 MB and its 255 MB release asset succeeded; Windows was 10.9 MB. |
| Why Linux is 12x macOS (root cause) | All three workflows run the SAME PyInstaller command with no excludes, and server.py/parity.py import torch only lazily — but PyInstaller still analyses function-level imports, so torch/torchaudio/chatterbox/transformers get bundled on every platform. The platform delta is the torch wheel itself: default PyPI's Linux torch 2.6.0 wheel is CUDA-enabled and unpacks to ~2.5 GB of GPU libraries (libtorch_cuda, cuDNN/cuBLAS, NCCL, nvidia/* packages), while the macOS torch wheel is CPU-only with no CUDA libs. The 3.13 GB artifact is therefore almost entirely CUDA libraries VoxLab never uses. NOT the cause: venv/, models/, or output/ were never in dist/ — PyInstaller only bundles dist/VoxLab, and model files are not bundled by design. The Windows 10.9 MB figure remains unexplained by the same files and is NOT relied on. |
| Fix — linux-installer.yml ONLY | (1) Torch step changed: `pip install --index-url https://download.pytorch.org/whl/cpu "torch==2.6.0" "torchaudio==2.6.0"` (CPU index), plus a separate default-PyPI `pip install "numpy>=1.24,<2"` (the CPU index does not host numpy). chatterbox-tts still sees torch==2.6.0 satisfied, so it does not reinstall the CUDA wheel in the filtered-requirements step. CPU-only is honest: every VoxLab engine (Kokoro ONNX, Chatterbox, Parler, Whisper) is CPU-tested and no GPU is required or documented; a CPU build still works on a GPU machine, just without GPU acceleration — same as the macOS build. (2) New step "Slim packaged folder (v1.0.4)" after the PyInstaller build, before packaging: deletes `__pycache__`, `*.pyc`, `*.pyi`, torch test/testing dirs, torch include/share dirs, and any libtorch_cuda*/libcudnn*/libnccl*/nvidia leftovers (all guarded with `|| true`, so an absent path cannot fail the build); prints dist size before/after. No runtime .so/.py, app/ data, or logo is deleted. (3) New step "Check release size (v1.0.4)": fails with a clear message if VoxLab-Linux-x64.tar.gz is >= 1.8 GiB (headroom under the 2 GiB cap), instead of failing later at attach. (4) Release body now says "Linux 64-bit build, CPU-only (no GPU required)". Packaging stays tar.gz with the same artifact name VoxLab-Linux-x64.tar.gz (xz not used — not needed once CUDA is gone, and it would change nothing about the limit logic). |
| Expected size (reasoning, NOT a claim) | Removing ~2.5 GB of CUDA libraries from a 3.13 GB artifact leaves the common bundle (CPU torch/torchaudio + transformers/librosa/kokoro-onnx/faster-whisper deps + app data), i.e. roughly macOS-scale plus Linux .so overhead — estimated well under 1 GiB, comfortably under the 2 GiB cap. The REAL size is only proven by the v1.0.4 Actions run; no size is claimed here. Fallback if it still exceeds 1.8 GiB: switch packaging to xz, or add PyInstaller --exclude-module for unused heavy modules — neither is in this patch. |
| Unchanged | macOS and Windows workflows untouched (grep: no whl/cpu string in either); backend/requirements.txt untouched; no model bundling added; no push, no release, no tag from this task. |
| Browser-ready v1.0.4 file | [voice-studio-push-v104/.github/workflows/linux-installer.yml](sandbox://workspace/voice-studio-push-v104/.github/workflows/linux-installer.yml) (8,000 B), verified identical to the workspace file by `diff`. This is the ONLY file changed for v1.0.4; parent must upload it via a browser task signed in as ishtiaquehasib only, then create tag v1.0.4 to trigger the fixed build. |

## Theme v2 prepared — Blogger, NOT published (2026-10-27)
- New copy: website/blogger-theme-v2.xml (268,357 B; original blogger-theme.xml untouched at 261,185 B). XML well-formed (ElementTree parse OK), all #anchors resolve to an existing id, 0 profile-only github.com/ishtiaquehasib links remain, 0 hardcoded v1.0.x versions, 0 copied quotes/downloads.
- Download: Windows card + hero button -> https://github.com/ishtiaquehasib/VoxLab/releases/latest; macOS ARM/Intel + Linux = Installer build in progress + README build-from-source link; View all releases -> /VoxLab/releases.
- Anchors: nav Pricing -> #pricing, MCP -> #mcp, Docs -> #docs, Capture -> #clone; footer Source -> repo, Releases -> /releases, Documentation -> #docs, API -> #api (local API section now id=api).
- New sections: #languages (24 total on paper = 23 Chatterbox Multilingual listed + Bengali extra; honest note live-tested English and Bengali only), #mcp (POST /api/mcp/speak, per-agent mapping, local no-key; pill/ACP/WebSocket Coming soon), #docs (5-step quick-start, install, first-run model download, endpoint table, troubleshooting incl TADA dtype=torch.bfloat16 + low_cpu_mem_usage=True with encoder float32, video tutorials coming with no video linked), #faq (really free / encrypted / storage / cancel / Cloud-Studio not for sale), #testimonials (Be first to share -> GitHub Discussions only, no quotes/downloads).
- Pricing: Local card split Available now (cloning, presets, Bengali, unlimited local, open source, local-only) vs Coming soon (dictation, capture, MCP pill, personalities, stories timeline, full effects); Cloud/Studio notify = Watch repo link, no fake form.
- NOT done: no Blogger publish, no GitHub push, no release/tag. Remaining known stale copy in v2 (out of this task's scope): models table still says Parler/Edge generation wiring in progress.

# v1.0.3 patch (NOT pushed, NO release, NO tag) — Linux/macOS torch/numpy ResolutionImpossible fix, prepared 2026-10-27

| Item | Exact result |
|---|---|
| v1.0.2 failure | Linux + macOS failed at Install dependencies, exit 1, ResolutionImpossible: requirements.txt `torch>=2.8` vs chatterbox-tts `torch==2.6.0` (and, for chatterbox 0.1.4–0.1.6, `numpy<1.26.0` vs the v1.0.2 preinstalled numpy 1.26.4). No Linux/macOS artifacts; Windows zip 10.9 MB attached to v1.0.2. |
| Root cause, verified on PyPI 2026-10-27 | EVERY chatterbox-tts version pins `torch==2.6.0` / `torchaudio==2.6.0` on Python <3.14 (0.1: numpy==1.26.0; 0.1.2–0.1.3: numpy>=1.26.0; 0.1.4–0.1.6: numpy<1.26.0,>=1.24.0; 0.1.7: numpy<2.0.0,>=1.24.0). A single `pip install -r backend/requirements.txt` asking torch>=2.8 + torchaudio>=2.8 can NEVER resolve — torch cannot be both >=2.8 and ==2.6. The v1.0.2 framing ("numpy source build") was therefore incomplete: numpy was only half the conflict. |
| Fix — linux + macOS workflows ONLY | New step "Install chatterbox-compatible torch/numpy first": `pip install "torch==2.6.0" "torchaudio==2.6.0" "numpy>=1.24,<2"` (all ship prebuilt cp312 manylinux + macOS arm64/x64 wheels). Install dependencies now filters those three lines out of requirements.txt (`grep -v -E '^(torch|torchaudio|numpy)([>=<]|$)'`) and installs the filtered file with `--only-binary=numpy`, so pip sees the pins already satisfied and accepts chatterbox-tts. Filter verified: filtered file keeps fastapi, uvicorn, kokoro>=0.9, chatterbox-tts, soundfile, pynput, pyperclip. |
| requirements.txt | UNTOUCHED by design (parent constraint). Long-term note: requirements.txt itself is unsatisfiable as written and should eventually be aligned to torch==2.6.0 / torchaudio==2.6.0 / numpy>=1.24,<2 — that would also make the Windows build consistent. If a future Windows build ever fails the same way, that alignment is the fix. |
| Windows workflow | UNCHANGED. Windows success on v1.0.2 with the same unsatisfiable file is NOT explained by the evidence and is NOT relied on — a single-install resolution cannot succeed with torch>=2.8 vs ==2.6, so the Windows v1.0.2 success may reflect run/reporting confusion, not a resolvable install. Do not claim Windows "proves" the requirements file works. |
| YAML verification | PyYAML safe_load → YAML_OK for all three workflows. Linux/macOS step order: Check out, Set up Python 3.12, Install build tools (setuptools/wheel), Install chatterbox-compatible torch/numpy first, Install dependencies, Build with PyInstaller, Package installer folder, Upload build artifact (always), Attach to GitHub Release (tag builds only). |
| Browser-ready v1.0.3 files | [voice-studio-push-v103/.github/workflows/linux-installer.yml](sandbox://workspace/voice-studio-push-v103/.github/workflows/linux-installer.yml) (4,488 B) and [voice-studio-push-v103/.github/workflows/macos-installer.yml](sandbox://workspace/voice-studio-push-v103/.github/workflows/macos-installer.yml) (4,800 B), verified identical to the workspace files by `diff`. These are the ONLY files changed for v1.0.3; parent must upload them via a browser task signed in as ishtiaquehasib only, then create tag v1.0.3 to trigger the fixed builds. |
| NOT done | No git push from the VM, no release, no tag, no use of hasibtechqore, no other files changed. Real Linux/macOS build success is NOT claimed — it can only be proven by a real Actions run after the v1.0.3 push/tag. |

# v1.0.2 patch (NOT pushed, NO release, NO tag) — Linux/macOS numpy source-build fix, prepared 2026-10-27

| Item | Exact result |
|---|---|
| v1.0.1 failure fixed here | Linux and macOS builds failed at Install dependencies, exit 1, "Failed to build numpy when getting requirements to build wheel", AttributeError: module 'pkgutil' has no attribute 'ImpImporter'. The setuptools/wheel step itself passed. Windows workflow is unaffected (it succeeded at v1.0.0) and was NOT touched. |
| Root cause | requirements.txt pins bare `numpy`, so pip resolved a pre-3.12 numpy sdist and tried to build it from source on Python 3.12, where pkgutil.ImpImporter was removed from the stdlib — a source build can never succeed there. Pinning setuptools alone cannot fix it, because the missing symbol is in the Python 3.12 stdlib, not in setuptools. |
| Fix — linux-installer.yml | New step "Install prebuilt numpy wheel (Python 3.12)" inserted after Install build tools and before Install dependencies: run `python -m pip install --only-binary=numpy "numpy==1.26.4"`. Install dependencies changed to `pip install --only-binary=numpy -r backend/requirements.txt` + `pip install pyinstaller`. numpy 1.26.4 was chosen because it has prebuilt cp312 wheels (manylinux + macOS arm64/x64) and satisfies both <2 and >=1.26 caps; if a dependency requires >=2, pip upgrades to a newer wheel instead of building from source, and --only-binary=numpy forbids any numpy source build outright. |
| Fix — macos-installer.yml | Identical new step and identical Install dependencies change, applying to both matrix runners (macos-14 arm64, macos-13 x64). |
| Windows workflow | UNCHANGED — verified by grep: no numpy/setuptools strings in windows-installer.yml. |
| YAML verification | PyYAML safe_load → YAML_OK for all three workflows. Linux/macOS step order: Check out, Set up Python 3.12, Install build tools (setuptools/wheel), Install prebuilt numpy wheel (Python 3.12), Install dependencies, Build with PyInstaller, Package installer folder, Upload build artifact (always), Attach to GitHub Release (tag builds only). |
| Browser-ready v1.0.2 files | [voice-studio-push-v102/.github/workflows/linux-installer.yml](sandbox://workspace/voice-studio-push-v102/.github/workflows/linux-installer.yml) (4,116 B) and [voice-studio-push-v102/.github/workflows/macos-installer.yml](sandbox://workspace/voice-studio-push-v102/.github/workflows/macos-installer.yml) (4,428 B), verified identical to the workspace files by `diff`. These are the ONLY files changed for v1.0.2; parent must upload them via a browser task signed in as ishtiaquehasib only, then create tag v1.0.2 to trigger the fixed builds. |
| NOT done | No git push from the VM, no release, no tag, no use of hasibtechqore, no other files changed, requirements.txt untouched. Real Linux/macOS build success is NOT claimed — it can only be proven by a real Actions run after the v1.0.2 push/tag. |

# README language fix 2026-10-27 — NOT pushed, NO release, NO tag

| Item | Exact result |
|---|---|
| Stale contradiction removed | README.md Bengali bullet previously said both "Bengali server wiring is still pending — the voice list and filter UI exist, generation wiring does not yet" and "Bengali generation wiring is DONE". The pending sentence was deleted; the DONE sentence (Edge presets + Parler speakers via pinned venv_parler, tested via /api/generate) remains. |
| New Languages section added | README.md now has a `## Languages` section before `## Engines`: "24 total on paper: 23 Chatterbox Multilingual languages + Bengali extra" with the full 23 list (Arabic, Danish, German, Greek, English, Spanish, Finnish, French, Hebrew, Hindi, Italian, Japanese, Korean, Malay, Dutch, Norwegian, Polish, Portuguese, Russian, Swedish, Swahili, Turkish, Chinese), Bengali noted as the extra Voicebox does not have (Parler/Edge), and the honest note: live-tested in VoxLab are English and Bengali only; the other 22 are engine-listed, not individually generated. |
| NOT claimed | 24 tested is NOT claimed anywhere. This README change is local only; it is NOT in the v1.0.0 release and NOT in the v1.0.1 patch files (which contain only the two workflow files). It must be included in the next push after v1.0.1, or the release README will still lack the language count. |

# v1.0.1 patch (NOT pushed, NO release, NO tag) — Linux/macOS installer setuptools fix, prepared 2026-10-27

| Item | Exact result |
|---|---|
| v1.0.0 Windows artifact — SUCCEEDED | VoxLab-Windows-x64.zip, 10.9 MB, attached to the v1.0.0 release (per parent task). Windows workflow unchanged in this patch. |
| v1.0.0 failures fixed here | Linux build-linux failed at Install dependencies, exit 2, "Cannot import 'setuptools.build_meta'". macOS arm64 failed the same way, exit 2. macOS Intel was canceled (consequence of the arm64 failure, not a separate error). |
| Fix — linux-installer.yml | New step inserted before Install dependencies, at line 37: `- name: Install build tools (setuptools/wheel)`, run: `python -m pip install --upgrade pip setuptools wheel`. Install dependencies step now runs only `pip install -r backend/requirements.txt` + `pip install pyinstaller` (pip upgrade moved into the new step). |
| Fix — macos-installer.yml | Same new step inserted before Install dependencies, at line 46: `- name: Install build tools (setuptools/wheel)`, run: `python -m pip install --upgrade pip setuptools wheel`. Same Install dependencies simplification. Applies to both matrix runners (macos-14 arm64, macos-13 x64). |
| Windows workflow | UNCHANGED — no setuptools string in windows-installer.yml (verified by grep). It succeeded at v1.0.0, so it was not touched. |
| YAML verification | PyYAML safe_load → YAML_OK for all three workflows. Linux steps: Check out, Set up Python 3.12, Install build tools (setuptools/wheel), Install dependencies, Build with PyInstaller, Package installer folder, Upload build artifact (always), Attach to GitHub Release (tag builds only). macOS steps identical in order. Windows steps unchanged (no build-tools step). |
| Browser-ready v1.0.1 files | [voice-studio-push-v101/.github/workflows/linux-installer.yml](sandbox://workspace/voice-studio-push-v101/.github/workflows/linux-installer.yml) (3.0K) and [voice-studio-push-v101/.github/workflows/macos-installer.yml](sandbox://workspace/voice-studio-push-v101/.github/workflows/macos-installer.yml) (3.2K), paths preserved as .github/workflows/*. These are the ONLY files changed for v1.0.1; parent must upload them via a browser task signed in as ishtiaquehasib only, then create tag v1.0.1 to trigger the fixed builds. |
| NOT done | No git push from the VM (no VM git auth, per earlier finding), no release, no tag, no use of hasibtechqore, no other files changed. Real Linux/macOS build success is NOT claimed — it can only be proven by a real Actions run after the v1.0.1 push/tag. |

# VoxLab GitHub push attempt 2026-10-27 ~00:15 — NOT PUSHED, auth missing on VM (NO release, NO tag)

| Item | Exact result |
|---|---|
| Repo | https://github.com/ishtiaquehasib/VoxLab — confirmed still empty: `git ls-remote` returns no refs, GitHub API `list_commits` → 409 "Git Repository is empty". Network read path works (curl github.com 200 via egress proxy). |
| Local commit prepared (scratch only) | Clean copy in /tmp/voxlab-push (NOT in ~/workspace/voice-studio, which remains not a git repo): `git init -b main`, commit 5ceb09f "VoxLab: initial open-source release (local voice studio)", 36 files, 3,406,143 bytes (bundle grew ~5 KB vs the earlier 3,401,160 check from PARITY/README edits). Excluded, verified: venv_parler/, venv_tada/, output/ (incl. tada_clone.wav), github-profile/, tmp/, luxtts_src/, tada_src/, __pycache__/, *.pyc. No file over 100 MB; largest app/logo.png and assets/voxlab-logo.png at 1,445,267 B each. |
| Git push attempt | `GIT_TERMINAL_PROMPT=0 git push -u origin main` → `fatal: could not read Username for 'https://github.com': terminal prompts disabled`, exit 128. No credential was invented, printed, or embedded. |
| Why auth is missing | No ~/.gitconfig, no ~/.git-credentials, no credential helper configured; `gh auth status` → "You are not logged into any GitHub hosts"; SSH to git@github.com → connection reset via egress proxy (3128). No local git auth for ishtiaquehasib exists on this VM. |
| MCP route NOT used — wrong account | GitHub MCP status is "connected", but `get_me` → login **hasibtechqore** (id 254631688), NOT ishtiaquehasib. Per the strict scope rule, the hasibtechqore account must NOT be used for VoxLab, so no MCP push was attempted. Separately, the MCP snapshot-push route cannot carry this bundle anyway: it accepts UTF-8 files only, no binary contents, and the bundle contains binary PNGs (app/logo.png, assets/voxlab-logo.png, assets/voxlab-favicon.png). |
| Next legitimate route (parent to arrange, no token in chat) | Either (a) a browser task signed in as **ishtiaquehasib** only, uploading/pushing the prepared 36-file tree, or (b) a Secure Vault credential for the ishtiaquehasib GitHub account (PAT with repo scope, never in chat) made available to git/gh on the VM, then re-run `git push -u origin main` from the prepared commit. Until one of those exists, the push cannot complete from the VM. |
| NOT done | No release, no tag, no push to any branch, no change to ~/workspace/voice-studio git state, no use of the hasibtechqore account, no models/venvs/output pushed. |

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
