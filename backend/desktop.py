"""VoxLab native desktop window — NO browser tab, NO terminal window.

This is the PyInstaller entry point for the desktop app (workflows
build ``backend/desktop.py``, not ``backend/server.py``). The old
``server.py`` ``__main__`` block opens the UI in the user's default
browser via a 1.5 s ``webbrowser.open()`` timer and needs a console
window to stay alive; that is exactly the behaviour the user
rejected ("voicebox er to terminal open hoy na" — the competitor
opens its own app window, no terminal, no browser tab).

What this module does, in order:
  1. Probe http://127.0.0.1:8000/api/voices once. If a VoxLab server
     is ALREADY running there, reuse it — never crash with
     "[Errno 98/48] address already in use", and never kill the
     other server on window close (it is not ours).
  2. Otherwise start the FastAPI app (``backend/server.py``'s ``app``)
     with uvicorn in a daemon background thread.
  3. Open a pywebview window (title "VoxLab", 1280x800) on a splash
     page (VoxLab navy theme + VoxLab logo — never a blank window).
     A loader thread then runs the splash checks ONE BY ONE, in
     order, each step moving pending -> running -> done/failed with
     its REAL result (see SPLASH_STEPS): local server answering,
     /api/voices count, ffmpeg path, Bengali Edge package status
     from /api/bengali-status, model cache status from
     /api/parity/models, and output-folder writability checked by
     actually writing and deleting a test file. Nothing cycles
     through invented texts and nothing is marked done before its
     check returns. The window swaps to the real UI with
     ``load_url()`` ONLY when every step passes. If any step fails
     (other than the server itself), the splash stays on the failed
     step and shows a "Continue to the studio anyway" button, so a
     failed check can never trap the user; if the server itself
     failed, there is nothing to continue to, so the splash says
     to close the window (closing stops a server this process
     started).

NO-COPY RULE: the splash is VoxLab's own design only — dark navy
#05081f, gradient #00d4ff -> #4868D8 -> #8b5cf6, the VoxLab logo.
No competitor image, colour scheme, or splash wording is used
here: step labels are plain functional VoxLab wording ("Local
server starting", "Voice list loading", ...), and the step list is
driven by real checks, not by cycling invented status lines.
  4. On window close, stop ONLY a server this process started
     (uvicorn ``should_exit`` + thread join, 10 s cap) and exit.
     A reused external server is left running.

Window icon: pywebview's ``create_window`` takes no icon argument
in the versions VoxLab targets, so the window/taskbar icon comes
from the PyInstaller ``--icon assets/voxlab-logo.ico`` flag (already
in the Windows workflow) — do NOT add an ``icon=`` argument to
``create_window`` or the build will TypeError on some versions.
The splash logo is separate: ``assets/voxlab-favicon.png`` (256x256,
~60 KB, bundled via --add-data) embedded as a data URI, falling
back to ``app/logo.png``, falling back to text-only.

Fallback, honest and non-silent: if pywebview cannot be imported,
or window creation/start raises (on Windows this is almost always
"WebView2 runtime missing" — WebView2 ships with Windows 11 / Edge,
older Windows 10 installs may need the free Evergreen installer),
VoxLab does NOT silently open Edge. It shows an error dialog with
the localhost URL while the server stays up, so the user can open
that address manually in a browser if they choose; dismissing the
dialog stops our server and exits. Dialog chain: tkinter (stdlib)
-> Win32 MessageBoxW via ctypes -> a log file in output/ + exit 1
(no console is available in a --noconsole build to print to).

CI-only hook: ``VOXLAB_DESKTOP_NO_GUI=1`` starts the server thread
and blocks without creating a window. GitHub Actions runners have
no guaranteed interactive desktop session for a pywebview window,
so the CI smoke test uses this hook to prove the DESKTOP ENTRY
starts a working server; it does NOT prove the window itself.
Window creation is proven only by a real user-PC run (see
PARITY.md). This hook is never set by the installer or shortcuts.

server.py is NOT imported at module import time (lazy import in
``_start_server_thread``), so ``import desktop`` works on a
headless machine without pywebview, torch, or a display — the
poll/reuse logic can be unit-tested without a GUI.
"""

import base64
import json
import os
import shutil
import sys
import threading
import time
import urllib.request
import urllib.error

TITLE = "VoxLab"
WIDTH = 1280
HEIGHT = 800
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
SERVER_START_TIMEOUT_S = 60.0
POLL_INTERVAL_S = 0.5
SHUTDOWN_JOIN_TIMEOUT_S = 10.0

# CI-only, see module docstring. Never set by installer/shortcuts.
NO_GUI_ENV = "VOXLAB_DESKTOP_NO_GUI"


def host_port():
    """Server bind address: env overrides, else localhost:8000.

    Desktop mode binds localhost by design (the window is local);
    the remote/network toggle in Settings applies to remote mode,
    not to this window.
    """
    host = os.environ.get("VOXLAB_SERVER_HOST", DEFAULT_HOST).strip() or DEFAULT_HOST
    try:
        port = int(os.environ.get("VOXLAB_SERVER_PORT", str(DEFAULT_PORT)))
    except ValueError:
        port = DEFAULT_PORT
    return host, port


def server_url(host=None, port=None):
    if host is None or port is None:
        host, port = host_port()
    return f"http://{host}:{port}"


def _data_dir():
    """Read-only bundled-data dir: _MEIPASS when frozen, repo root's
    parent (backend/ -> project root) when unfrozen — same split as
    server.py."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS",
                       os.path.dirname(os.path.abspath(sys.executable)))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _writable_dir():
    """Writable dir beside the exe when frozen, project root unfrozen
    (same split as server.py's OUT parent)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _logo_data_uri():
    """Small logo for the splash, or None for a text-only splash.

    Prefers assets/voxlab-favicon.png (256x256, ~60 KB, bundled by
    the workflows); falls back to app/logo.png (1.4 MB — embedded
    only as a last resort, it is a one-time splash load).
    """
    base = _data_dir()
    for rel in ("assets/voxlab-favicon.png", "app/logo.png",
                "assets/voxlab-logo.png"):
        path = os.path.join(base, rel)
        try:
            if os.path.isfile(path):
                with open(path, "rb") as fh:
                    data = base64.b64encode(fh.read()).decode("ascii")
                return f"data:image/png;base64,{data}"
        except OSError:
            continue
    return None


# Splash steps, in the order the loader thread checks them. Labels
# are plain functional VoxLab wording — deliberately NOT the
# competitor's splash lines, and there is no cycling/fake text: a
# step changes state only when its check (see
# _evaluate_splash_checks) returns.
SPLASH_STEPS = (
    ("server", "Local server starting"),
    ("voices", "Voice list loading"),
    ("ffmpeg", "Audio tools (ffmpeg)"),
    ("bengali_edge", "Bengali Edge voices"),
    ("models", "Model availability"),
    ("output", "Output folder writable"),
)

# Steps whose failure blocks the automatic swap to the main UI are
# all of them: _evaluate_splash_checks only returns all_pass=True
# when every step is done. A failed non-server step shows the
# Continue button instead (see splash_html), so the gate can never
# trap the user; a failed server step shows no Continue button,
# because there is no working UI to continue to.


def splash_html(url, steps=SPLASH_STEPS):
    """Splash page: VoxLab navy theme, logo, real 1-by-1 step list.

    There is deliberately NO animated progress bar and NO cycling
    status text: each <li id="step-<id>"> starts "pending" and is
    moved to "running" then "done"/"failed" by
    ``window.voxlabSetStep(id, state, detail)`` from the loader
    thread, only when that step's real check returns. The <button
    id="continue-btn"> is hidden until the loader calls
    ``window.voxlabShowContinue()`` (a failed non-server step);
    clicking it navigates the window itself to the main UI URL —
    no Python callback is needed, and no browser tab is opened.
    The <p id="status"> line is the loader's summary, updated the
    same way; a load failure is visible there instead of a silent
    blank page.
    """
    logo = _logo_data_uri()
    logo_tag = (f'<img src="{logo}" alt="VoxLab" '
                'style="width:140px;height:140px;border-radius:24px;">'
                if logo else
                '<div style="font-size:64px;font-weight:800;'
                'background:linear-gradient(90deg,#00d4ff,#4868D8,#8b5cf6);'
                '-webkit-background-clip:text;background-clip:text;'
                'color:transparent;">VoxLab</div>')
    rows = "".join(
        f'<li id="step-{sid}" class="step pending">'
        f'<span class="mark">…</span><span class="label">{label}</span>'
        f'<span class="detail"></span></li>'
        for sid, label in steps)
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>VoxLab — starting</title>
<style>
body{{margin:0;min-height:100vh;display:flex;flex-direction:column;align-items:center;
justify-content:center;background:#05081f;color:#fff;
font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;}}
h1{{margin:16px 0 4px;font-size:32px;}}
p{{color:#aab4d6;margin:4px 0;}}
ul{{list-style:none;padding:0;margin:20px 0;width:520px;max-width:92vw;}}
li.step{{display:flex;gap:10px;align-items:baseline;padding:7px 12px;
border:1px solid #1a2450;border-radius:10px;margin:6px 0;background:#0d1433;}}
li.step .mark{{width:22px;text-align:center;font-weight:700;}}
li.step.pending .mark{{color:#aab4d6;}}
li.step.running .mark{{color:#00d4ff;}}
li.step.done .mark{{color:#00d4ff;}}
li.step.failed .mark{{color:#ff6b6b;}}
li.step .label{{flex:0 0 auto;}}
li.step .detail{{color:#aab4d6;font-size:13px;overflow-wrap:anywhere;}}
#continue-btn{{display:none;margin-top:16px;padding:10px 22px;border:0;border-radius:10px;
color:#fff;font-size:15px;cursor:pointer;
background:linear-gradient(90deg,#00d4ff,#4868D8,#8b5cf6);}}
</style>
<script>
function voxlabSetStep(id, state, detail){{
  var el = document.getElementById('step-' + id);
  if (!el) return;
  el.className = 'step ' + state;
  el.querySelector('.mark').textContent =
    state === 'done' ? '✓' : state === 'failed' ? '✗' : state === 'running' ? '›' : '…';
  el.querySelector('.detail').textContent = detail || '';
}}
function voxlabSetStatus(text){{
  var el = document.getElementById('status');
  if (el) el.textContent = text;
}}
function voxlabShowContinue(){{
  var btn = document.getElementById('continue-btn');
  if (btn) btn.style.display = 'inline-block';
}}
</script></head><body>{logo_tag}
<h1>VoxLab</h1>
<p id="status">Starting the local voice studio…</p>
<p style="font-size:13px;">{url} — free, local, no account</p>
<ul>{rows}</ul>
<button id="continue-btn" onclick="window.location.href={json.dumps(url)};">Continue to the studio anyway</button>
</body></html>"""


def _get_json(url, path, timeout_s=5.0):
    """GET <url><path> as JSON, or None on any failure (never raises)."""
    try:
        req = urllib.request.Request(url.rstrip("/") + path, method="GET")
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:
        return None


def _set_step(window, step_id, state, detail=""):
    """Push one splash step state to the window; never raises.

    ``window`` is a pywebview window in production; in tests it may
    be any object with an evaluate_js method (a fake records calls).
    """
    try:
        window.evaluate_js(
            "voxlabSetStep(%s, %s, %s);" % (
                json.dumps(step_id), json.dumps(state), json.dumps(detail)))
    except Exception:
        pass


def _set_status(window, text):
    try:
        window.evaluate_js("voxlabSetStatus(%s);" % json.dumps(text))
    except Exception:
        pass


def _show_continue(window):
    try:
        window.evaluate_js("voxlabShowContinue();")
    except Exception:
        pass


def _ffmpeg_exe_local():
    """ffmpeg exe for the DESKTOP process: bundled imageio-ffmpeg
    first, else system PATH — the same rule as server.py/parity.py,
    checked here so the splash step is the desktop entry's own
    result, not a copy of a server string."""
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.isfile(exe):
            return exe
    except Exception:
        pass
    return shutil.which("ffmpeg")


def _check_output_writable():
    """Output writability, proven by writing + deleting a test file
    (not by os.access alone, which can lie on some filesystems)."""
    out_dir = os.path.join(_writable_dir(), "output")
    try:
        os.makedirs(out_dir, exist_ok=True)
        probe = os.path.join(out_dir, ".voxlab-splash-write-test")
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("voxlab splash write test")
        os.remove(probe)
        return True, f"Output folder: {out_dir}"
    except Exception as exc:  # noqa: BLE001 - detail is the failure
        return False, f"Output folder not writable: {out_dir} ({exc})"


def _evaluate_splash_checks(window, url, reused):
    """Run SPLASH_STEPS 1-by-1, pushing each real result to the
    splash. Returns (all_pass, server_ok).

    Order matters: server first (nothing else can be checked
    without it), then voices, ffmpeg, Bengali Edge, models, output.
    Each step is set to "running" before its check and to "done"
    or "failed" only from that check's result — no step is ever
    marked done speculatively, and no invented text is shown.
    Models are cache-status only (lazy load): "done" means the
    model list answered with entries, NOT that every model is
    downloaded or loaded. Edge "done" means the edge-tts package
    is installed in this build, NOT that a Bengali generation
    succeeded (Edge still needs network to its service).
    """
    # 1. Server.
    _set_step(window, "server", "running", "Waiting for the local server…")
    if reused:
        server_ok = True
        _set_step(window, "server", "done",
                  f"Reusing the server already running at {url}.")
    else:
        server_ok = wait_for_server(url)
        _set_step(window, "server",
                  "done" if server_ok else "failed",
                  f"Server answered at {url}." if server_ok else
                  "Server did not answer in 60 s — see output/voxlab-server.log.")
    if not server_ok:
        for sid, _label in SPLASH_STEPS[1:]:
            _set_step(window, sid, "failed",
                      "Not checked — the server did not start.")
        _set_status(window, "Local server did not start. "
                            "Close this window to stop VoxLab.")
        return False, False
    # 2. Voices.
    _set_step(window, "voices", "running", "Loading the voice list…")
    data = _get_json(url, "/api/voices")
    voices = data.get("voices") if isinstance(data, dict) else None
    if isinstance(voices, list) and len(voices) == 19:
        _set_step(window, "voices", "done",
                  f"{len(voices)} voices (11 Kokoro + 8 Bengali).")
        voices_ok = True
    elif isinstance(voices, list) and voices:
        _set_step(window, "voices", "failed",
                  f"{len(voices)} voices, expected 19.")
        voices_ok = False
    else:
        _set_step(window, "voices", "failed",
                  "Voice list did not answer.")
        voices_ok = False
    # 3. ffmpeg (desktop process's own check).
    _set_step(window, "ffmpeg", "running", "Finding ffmpeg…")
    ffmpeg_exe = _ffmpeg_exe_local()
    if ffmpeg_exe:
        _set_step(window, "ffmpeg", "done", f"ffmpeg found: {ffmpeg_exe}")
        ffmpeg_ok = True
    else:
        _set_step(window, "ffmpeg", "failed",
                  "ffmpeg not found (no bundled imageio-ffmpeg, none on PATH).")
        ffmpeg_ok = False
    # 4. Bengali Edge.
    _set_step(window, "bengali_edge", "running",
              "Checking Bengali Edge voices…")
    bn = _get_json(url, "/api/bengali-status")
    if isinstance(bn, dict) and bn.get("edge_tts_installed"):
        _set_step(window, "bengali_edge", "done",
                  "edge-tts installed"
                  + (f" ({bn.get('edge_tts_version')})"
                     if bn.get("edge_tts_version") else "")
                  + f"; {bn.get('bn_count', '?')} Bengali voices listed.")
        edge_ok = True
    elif isinstance(bn, dict):
        _set_step(window, "bengali_edge", "failed",
                  "edge-tts package not installed in this build.")
        edge_ok = False
    else:
        _set_step(window, "bengali_edge", "failed",
                  "Bengali status did not answer.")
        edge_ok = False
    # 5. Models (cache status only — no download, no model load).
    _set_step(window, "models", "running", "Checking model availability…")
    md = _get_json(url, "/api/parity/models")
    models = md.get("models") if isinstance(md, dict) else None
    if isinstance(models, list) and models:
        cached = sum(1 for m in models if not m.get("needs_download"))
        _set_step(window, "models", "done",
                  f"{cached} of {len(models)} models cached; "
                  "the rest download on first use.")
        models_ok = True
    else:
        _set_step(window, "models", "failed",
                  "Model list did not answer.")
        models_ok = False
    # 6. Output writable.
    _set_step(window, "output", "running", "Testing the output folder…")
    output_ok, output_detail = _check_output_writable()
    _set_step(window, "output", "done" if output_ok else "failed",
              output_detail)
    all_pass = all([server_ok, voices_ok, ffmpeg_ok, edge_ok,
                    models_ok, output_ok])
    if all_pass:
        _set_status(window, "All checks passed — opening the studio…")
    else:
        _set_status(window, "One or more checks failed — see above. "
                            "You can continue to the studio anyway, "
                            "but the failed item will not work until fixed.")
        _show_continue(window)
    return all_pass, server_ok


def _splash_and_swap(window, url, reused):
    """Loader thread: run the checks, swap ONLY on a full pass.

    On a full pass, load_url() navigates the window to the real UI.
    On any failed step, the splash stays visible with the failed
    step + the Continue button — the loader never swaps past a
    failure on its own, and never closes the window for the user.
    """
    try:
        all_pass, _server_ok = _evaluate_splash_checks(window, url, reused)
    except Exception as exc:  # noqa: BLE001 - surface, don't hang
        _set_status(window, f"Startup check failed: {exc}")
        _show_continue(window)
        return
    if not all_pass:
        return
    try:
        window.load_url(url)
    except Exception as exc:  # noqa: BLE001 - surface in splash
        _set_status(window, f"Could not load the studio UI: {exc}")
        _show_continue(window)


def voices_ok(url, timeout_s=5.0):
    """True iff GET <url>/api/voices answers 200 with a voices list."""
    try:
        req = urllib.request.Request(url.rstrip("/") + "/api/voices",
                                     method="GET")
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            if resp.status != 200:
                return False
            import json
            data = json.loads(resp.read().decode("utf-8", "replace"))
            return isinstance(data.get("voices"), list) and len(data["voices"]) > 0
    except Exception:
        return False


def wait_for_server(url, timeout_s=SERVER_START_TIMEOUT_S):
    """Poll /api/voices until 200 (or timeout). Returns True/False."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if voices_ok(url, timeout_s=2.0):
            return True
        time.sleep(POLL_INTERVAL_S)
    return False


class ServerThread:
    """uvicorn server in a daemon thread; stop() is idempotent."""

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self._server = None
        self._thread = None
        self._started = False

    def start(self):
        # Lazy import: importing server.py pulls FastAPI + the parity
        # router attempt; it must not happen at desktop import time.
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        from server import app as fastapi_app
        import uvicorn
        config = uvicorn.Config(fastapi_app, host=self.host, port=self.port,
                                log_level="warning")
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run,
                                        name="voxlab-uvicorn", daemon=True)
        self._thread.start()
        self._started = True
        return self

    def stop(self):
        if not self._started:
            return
        self._started = False
        try:
            if self._server is not None:
                self._server.should_exit = True
        except Exception:
            pass
        try:
            if self._thread is not None:
                self._thread.join(timeout=SHUTDOWN_JOIN_TIMEOUT_S)
        except Exception:
            pass

    @property
    def alive(self):
        return self._thread is not None and self._thread.is_alive()


def _log_error(message):
    """Best-effort error log (a --noconsole build has no console)."""
    try:
        out_dir = os.path.join(_writable_dir(), "output")
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "voxlab-desktop-error.log"),
                  "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except Exception:
        pass
    try:
        print(f"[VoxLab desktop] {message}", file=sys.stderr, flush=True)
    except Exception:
        pass


def show_error_dialog(title, message):
    """Honest fallback dialog — NEVER opens a browser silently.

    The server stays up while the dialog is open, so the user can
    open the localhost URL in a browser themselves if they choose;
    dismissing the dialog returns control to main(), which stops
    our server (if any) and exits.
    """
    # 1. tkinter (stdlib, present on Windows/macOS CPython installs).
    try:
        import tkinter
        from tkinter import messagebox
        root = tkinter.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except Exception:
            pass
        messagebox.showerror(title, message, parent=root)
        try:
            root.destroy()
        except Exception:
            pass
        return True
    except Exception:
        pass
    # 2. Win32 MessageBoxW (no tkinter, no console needed).
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, title, 0x10)
            return True
        except Exception:
            pass
    # 3. Last resort: log file + exit code (documented, not silent —
    # the caller logs the same message before returning 1).
    _log_error(f"{title}: {message}")
    return False


def _webview_missing_message(url):
    return (
        "VoxLab could not open its own app window.\n\n"
        "The native window needs pywebview and, on Windows, the "
        "Microsoft Edge WebView2 runtime. WebView2 ships with "
        "Windows 11 and Microsoft Edge; on older Windows 10 install "
        "the free WebView2 Evergreen runtime from Microsoft and "
        "relaunch VoxLab.\n\n"
        f"The local server is running at:\n{url}\n\n"
        "You may open that address in a browser yourself while this "
        "dialog is open. Click OK to close VoxLab (the server will "
        "then stop)."
    )


def _server_failed_message(url):
    return (
        "VoxLab's local server did not start in time.\n\n"
        f"Expected it at {url} (/api/voices never answered 200).\n"
        "Another program may already use port 8000, or the server "
        "crashed at startup — see output/voxlab-server.log next to "
        "the app for the startup lines.\n\n"
        "Click OK to close VoxLab."
    )


def run_desktop():
    """Full desktop lifecycle. Returns a process exit code."""
    host, port = host_port()
    url = server_url(host, port)
    reused = voices_ok(url, timeout_s=2.0)
    server_thread = None
    if not reused:
        try:
            server_thread = ServerThread(host, port).start()
        except Exception as exc:  # noqa: BLE001 - show, don't traceback
            msg = f"Could not start the local server: {exc}"
            _log_error(msg)
            show_error_dialog("VoxLab — server failed", _server_failed_message(url))
            return 1
    # NOTE: unlike the previous version, the server is NOT waited
    # for here in the GUI path — the splash window opens first and
    # its loader thread runs the 1-by-1 checks (server step first),
    # so a slow first start is visible as steps, not as a blank
    # wait. The NO_GUI path below still waits, because it has no
    # window to show progress in.
    # CI-only hook: server up, no window (see module docstring).
    if os.environ.get(NO_GUI_ENV, "").strip() == "1":
        if not wait_for_server(url):
            if server_thread is not None:
                server_thread.stop()
            _log_error("Desktop server did not start in time (NO_GUI).")
            return 1
        try:
            while True:
                time.sleep(1.0)
                if server_thread is not None:
                    if not server_thread.alive:
                        break
                elif not voices_ok(url, timeout_s=2.0):
                    # Reused external server went away.
                    break
        except KeyboardInterrupt:
            pass
        if server_thread is not None:
            server_thread.stop()
        return 0
    # Native window. Import is lazy so --help/import tests and the
    # server-only path never require pywebview or a display.
    try:
        import webview
    except Exception as exc:  # noqa: BLE001 - fallback dialog, not a crash
        _log_error(f"pywebview import failed: {exc}")
        # Wait first so the fallback dialog's "server is running"
        # claim is true; if the server never comes up, say so.
        if not wait_for_server(url):
            if server_thread is not None:
                server_thread.stop()
            show_error_dialog("VoxLab — server failed",
                              _server_failed_message(url))
            return 1
        show_error_dialog("VoxLab — window unavailable",
                          _webview_missing_message(url))
        if server_thread is not None:
            server_thread.stop()
        return 1
    window = None
    try:
        window = webview.create_window(TITLE, html=splash_html(url),
                                       width=WIDTH, height=HEIGHT)
    except Exception as exc:  # noqa: BLE001 - WebView2 missing etc.
        _log_error(f"pywebview window creation failed: {exc}")
        show_error_dialog("VoxLab — window unavailable",
                          _webview_missing_message(url))
        if server_thread is not None:
            server_thread.stop()
        return 1

    # Loader thread: 1-by-1 splash checks, swapping to the real UI
    # ONLY on a full pass (load_url from a worker thread is the
    # documented pywebview pattern for server-backed apps).
    threading.Thread(target=_splash_and_swap, args=(window, url, reused),
                     name="voxlab-window-loader", daemon=True).start()
    try:
        # Blocks until the window is closed. On Windows this uses
        # Edge Chromium WebView2; on macOS WKWebView; on Linux
        # GTK/WebKit. No browser tab is opened anywhere in this path.
        webview.start(debug=False)
    except Exception as exc:  # noqa: BLE001 - e.g. WebView2 absent
        _log_error(f"pywebview start failed: {exc}")
        show_error_dialog("VoxLab — window unavailable",
                          _webview_missing_message(url))
        if server_thread is not None:
            server_thread.stop()
        return 1
    finally:
        # Window closed: stop ONLY our own server. A reused external
        # server keeps running — it was not started by this window.
        if server_thread is not None:
            server_thread.stop()
    return 0


if __name__ == "__main__":
    sys.exit(run_desktop())
