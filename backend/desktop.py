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
``ServerThread.start``), so ``import desktop`` works on a
headless machine without pywebview, torch, or a display — the
poll/reuse logic can be unit-tested without a GUI.

SERVER-FAILED FIX (v1.1.1 user-PC bug, dialog "VoxLab — server
failed"): the old code had three compounding flaws, all fixed
here. (1) A uvicorn bind failure (port 8000 already held, e.g.
by a previous VoxLab instance or another program — the user's
earlier video showed exactly [Errno 10048] on 8000) dies
silently inside the uvicorn thread: ``ServerThread.start``
returned success, ``wait_for_server`` then polled for 60 s, and
the dialog guessed "another program may already use port 8000,
or the server crashed" without ever knowing which. (2) The
dialog pointed at a relative "output/voxlab-server.log next to
the app", but in a --noconsole frozen build uvicorn's bind
error went to a discarded stderr and was never written to that
file, so the user had no real error to report. (3) The reused
probe was a single 2 s check on port 8000 only, and a failed
start was never retried on another port. New behaviour:
``start_server_with_retry`` first scans ports 8000-8010 for an
answering VoxLab server and reuses it; otherwise it binds the
first free port in that range and opens the window on THAT
url (never the occupied 8000); a thread that dies during
startup (bind error, crash) is detected immediately via
``ServerThread.error`` instead of waiting 60 s, and the next
free port is tried at once. The real error — bind error,
import traceback, or thread traceback, truncated — is appended
to output/voxlab-server.log AND shown in the dialog with the
absolute log path, so the dialog never again says only "may
already use port 8000". A server thread that stays alive but
never answers after 60 s is a hang, not a bind failure: it is
stopped and reported, not retried port-by-port (the same binary
would hang the same way on every port). The GUI path now waits
for this start+retry to succeed BEFORE opening the window (the
splash steps then run against a live server); previously the
window opened first and only the splash loader waited, which is
why the user saw a dialog instead of a splash on failure.
"""

import base64
import json
import os
import shutil
import socket
import sys
import threading
import time
import traceback
import urllib.request
import urllib.error
import uuid

TITLE = "VoxLab"
WIDTH = 1280
HEIGHT = 800
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
SERVER_START_TIMEOUT_S = 60.0
POLL_INTERVAL_S = 0.5
SHUTDOWN_JOIN_TIMEOUT_S = 10.0
# Port scan range for reuse + auto-retry: start port .. start+10.
MAX_PORT_OFFSET = 10
# Short probe timeout when scanning for an already-running server:
# a refused connection fails fast; only a listening-but-silent
# port pays the full timeout, so the scan stays fast in practice.
REUSE_PROBE_TIMEOUT_S = 1.0

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


def _server_log_path():
    """Absolute path of output/voxlab-server.log (beside the exe
    when frozen, project root unfrozen) — shown in dialogs so the
    user can actually find it, never a relative guess."""
    return os.path.join(_writable_dir(), "output", "voxlab-server.log")


def _append_server_log(message):
    """Append one timestamped line to voxlab-server.log, best
    effort (a --noconsole build has no console to fall back to)."""
    try:
        out_dir = os.path.join(_writable_dir(), "output")
        os.makedirs(out_dir, exist_ok=True)
        with open(_server_log_path(), "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except Exception:
        pass


class _DiscardStream:
    """Write-only sink for a --noconsole build whose log file
    cannot be opened: accepts writes, never raises, isatty False."""

    def write(self, data):
        return len(data) if isinstance(data, str) else 0

    def flush(self):
        pass

    def isatty(self):
        return False

    def writable(self):
        return True

    encoding = "utf-8"
    errors = "replace"


class _SafeStream:
    """File-backed stdout/stderr replacement for a --noconsole
    build: writes go to voxlab-server.log, isatty() is False
    (never a colour/TTY code path), flush/write never raise."""

    def __init__(self, fileobj):
        self._file = fileobj

    def write(self, data):
        try:
            return self._file.write(data)
        except Exception:
            return len(data) if isinstance(data, str) else 0

    def flush(self):
        try:
            self._file.flush()
        except Exception:
            pass

    def isatty(self):
        return False

    def writable(self):
        return True

    @property
    def encoding(self):
        return getattr(self._file, "encoding", "utf-8")

    @property
    def errors(self):
        return getattr(self._file, "errors", "replace")

    def fileno(self):
        return self._file.fileno()


# Kept alive for the process lifetime: if this handle were
# garbage-collected, sys.stdout/sys.stderr would point at a
# closed file and the next write would raise.
_STD_STREAM_FILE = None


def _ensure_std_streams():
    """Guarantee sys.stdout/sys.stderr are real, writable streams
    BEFORE uvicorn is configured.

    v1.1.2 user-PC crash (dialog proved it): in a PyInstaller
    --noconsole frozen build on Windows, sys.stdout and
    sys.stderr are None. uvicorn's DefaultFormatter and
    AccessFormatter, with use_colors=None (the default), call
    sys.stdout.isatty() in __init__ during dictConfig, so
    uvicorn.Config.__init__ raised
    AttributeError: 'NoneType' object has no attribute 'isatty',
    wrapped as ValueError: Unable to configure formatter
    'default' — before the server ever bound a port. This
    replaces a None (or isatty-less) stream with a file-backed
    stream to voxlab-server.log; if that file cannot be opened,
    a discarding stream. A stream that already exists and has
    isatty() is left untouched.
    """
    global _STD_STREAM_FILE
    needs = []
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None or not hasattr(stream, "isatty"):
            needs.append(name)
    if not needs:
        return
    safe = None
    try:
        out_dir = os.path.join(_writable_dir(), "output")
        os.makedirs(out_dir, exist_ok=True)
        _STD_STREAM_FILE = open(_server_log_path(), "a", encoding="utf-8")
        safe = _SafeStream(_STD_STREAM_FILE)
    except Exception:
        safe = _DiscardStream()
    for name in needs:
        setattr(sys, name, safe)


def _uvicorn_log_config():
    """uvicorn logging dict with colours forced OFF, or None.

    With use_colors=False, both uvicorn formatters skip the
    sys.stdout.isatty() call that crashed the v1.1.2 build, so
    this alone would fix the crash even if sys.stdout were
    still None. It is used together with _ensure_std_streams()
    (belt and braces: other code in server.py may still print
    or log to stderr). A deepcopy is used so uvicorn's global
    LOGGING_CONFIG is never mutated in place."""
    try:
        import copy
        import uvicorn
        cfg = copy.deepcopy(uvicorn.config.LOGGING_CONFIG)
        for fmt in cfg.get("formatters", {}).values():
            if isinstance(fmt, dict):
                fmt["use_colors"] = False
        return cfg
    except Exception:
        return None


def _truncate_detail(text, limit=600):
    """Last <limit> chars of an error, for dialogs: the tail of a
    traceback is the useful part (exception line), not the head."""
    if not text:
        return ""
    text = str(text).strip()
    if len(text) > limit:
        return "… " + text[-limit:]
    return text


def _port_free(host, port):
    """True iff nothing is listening on (host, port) right now.

    A bind test, not a connect test: a port held by another
    program fails here even when that program answers nothing
    on /api/voices — exactly the [Errno 10048] case that used to
    kill the server thread silently. The socket is closed
    immediately; a race (another process grabbing the port in
    between) is still possible, and is caught by the thread-death
    path in start_server_with_retry, not by this check alone."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        try:
            sock.close()
        except Exception:
            pass


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


def _is_lock_error(exc):
    """True iff an error looks like a transient file lock, not a
    genuinely unwritable folder: Windows WinError 32 ("being used
    by another process") is the v1.1.3 user's exact failure. Only
    lock errors are retried; a truly read-only folder fails fast
    instead of burning retries that can never succeed."""
    if getattr(exc, "winerror", None) == 32:
        return True
    text = str(exc)
    return ("being used by another process" in text
            or "[WinError 32]" in text
            or "Resource temporarily unavailable" in text)


def _check_output_writable(out_dir=None, attempts=5):
    """Output writability, proven by writing + deleting a test file
    (not by os.access alone, which can lie on some filesystems).

    The probe name is UNIQUE per attempt (uuid suffix). The old
    code used one fixed name, ``.voxlab-splash-write-test``: on
    Windows, another VoxLab instance, a previous splash run, or
    antivirus holding that one file makes open() fail with
    WinError 32 even though the folder itself is perfectly
    writable — and that single locked file failed the whole
    splash (v1.1.3 user: server/voices/ffmpeg/Edge/models all
    passed, output alone failed on WinError 32). A fixed name is
    a shared lock target, so it is never used again: each attempt
    gets a fresh name, a locked name is never retried and never
    deleted (it is not ours to remove while another process holds
    it), and lock errors are retried with a new name. A probe
    that writes but cannot be deleted still proves writability
    (delete is best-effort — e.g. antivirus scanning the new
    file — and a leftover probe is harmless). Only if every
    attempt fails is the folder reported unwritable, with the
    last error. The server writes generations to this same
    output dir (server.py OUT), so a passing probe means
    generations can save there too.
    """
    out_dir = out_dir or os.path.join(_writable_dir(), "output")
    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception as exc:  # noqa: BLE001 - detail is the failure
        return False, (f"Output folder not writable: {out_dir} "
                       f"(cannot create folder: {exc})")
    last_exc = None
    for attempt in range(max(1, attempts)):
        probe = os.path.join(
            out_dir, f".voxlab-splash-write-test-{uuid.uuid4().hex}")
        try:
            with open(probe, "w", encoding="utf-8") as fh:
                fh.write("voxlab splash write test")
            try:
                os.remove(probe)
            except Exception:
                pass  # write already proved the folder writable
            return True, f"Output folder: {out_dir}"
        except Exception as exc:  # noqa: BLE001 - retried or reported
            last_exc = exc
            if not _is_lock_error(exc):
                break
            # Lock contention (another instance / antivirus): wait
            # briefly, then retry with a brand-new probe name.
            time.sleep(0.2 * (attempt + 1))
    return False, f"Output folder not writable: {out_dir} ({last_exc})"


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
                  f"Server did not answer in 60 s — see {_server_log_path()}.")
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


def wait_for_server(url, timeout_s=SERVER_START_TIMEOUT_S,
                    server_thread=None):
    """Poll /api/voices until 200 (or timeout). Returns True/False.

    With server_thread given, returns False IMMEDIATELY when the
    thread has died (bind failure / crash) instead of polling for
    the full timeout against a server that will never answer —
    this is what makes port retry fast instead of 60 s per port."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if voices_ok(url, timeout_s=2.0):
            return True
        if server_thread is not None and server_thread.died:
            return False
        time.sleep(POLL_INTERVAL_S)
    return False


class ServerThread:
    """uvicorn server in a daemon thread; stop() is idempotent.

    The old version let a uvicorn bind failure die silently in
    the thread: start() returned success and nobody ever saw the
    error. Now the thread target is wrapped: any exception is
    stored on ``error``/``traceback_text`` and ``died`` is set,
    so callers can report the REAL error and retry another port
    at once. The FastAPI app import happens synchronously in
    start() (main thread), so an import crash is raised to the
    caller with its traceback instead of vanishing into a thread.
    uvicorn's own loggers also get a FileHandler to
    voxlab-server.log, because in a --noconsole frozen build
    stderr is discarded and the bind error otherwise goes
    nowhere."""

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self._server = None
        self._thread = None
        self._started = False
        self._died = threading.Event()
        self.error = None
        self.traceback_text = ""

    def _run(self):
        try:
            self._server.run()
        except Exception as exc:  # noqa: BLE001 - stored, not lost
            self.error = exc
            self.traceback_text = traceback.format_exc()
            _append_server_log(
                f"VoxLab server thread failed on {self.host}:{self.port}: "
                f"{exc}\n{self.traceback_text}")
        finally:
            self._died.set()

    def start(self):
        # First thing, before ANY import that might log/print:
        # a --noconsole frozen build has sys.stdout/sys.stderr
        # None, and anything calling isatty() on them dies.
        _ensure_std_streams()
        # Lazy import: importing server.py pulls FastAPI + the parity
        # router attempt; it must not happen at desktop import time.
        # Synchronous here on purpose: an import crash must surface
        # to the caller, not die in a thread.
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        from server import app as fastapi_app
        import uvicorn
        # v1.1.2 crash fix: MUST run before uvicorn.Config, whose
        # dictConfig instantiates the colour formatters (see
        # _ensure_std_streams docstring). Without this, a
        # --noconsole frozen build dies here with
        # AttributeError: 'NoneType' object has no attribute
        # 'isatty' -> ValueError: Unable to configure formatter
        # 'default', before any port is bound.
        _ensure_std_streams()
        try:
            import logging as _logging
            out_dir = os.path.join(_writable_dir(), "output")
            os.makedirs(out_dir, exist_ok=True)
            _fh = _logging.FileHandler(_server_log_path(), encoding="utf-8")
            _fh.setFormatter(
                _logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            for _name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
                _lg = _logging.getLogger(_name)
                if not any(isinstance(h, _logging.FileHandler)
                           and getattr(h, "baseFilename", None)
                           == _server_log_path() for h in _lg.handlers):
                    _lg.addHandler(_fh)
        except Exception:
            pass
        _log_config = _uvicorn_log_config()
        if _log_config is not None:
            config = uvicorn.Config(fastapi_app, host=self.host,
                                    port=self.port, log_level="warning",
                                    log_config=_log_config)
        else:
            # Fallback: use_colors=False makes configure_logging
            # set both formatters' use_colors=False, which also
            # skips the isatty() call.
            config = uvicorn.Config(fastapi_app, host=self.host,
                                    port=self.port, log_level="warning",
                                    use_colors=False)
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._run,
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
    def died(self):
        return self._died.is_set()

    @property
    def alive(self):
        return (self._thread is not None and self._thread.is_alive()
                and not self._died.is_set())


def find_reused_url(host, start_port):
    """First port in start_port..start_port+MAX_PORT_OFFSET whose
    server answers /api/voices, or None. The old code probed only
    the start port once; a first instance that itself moved to
    8001 (occupied 8000) was invisible to a second instance."""
    for offset in range(MAX_PORT_OFFSET + 1):
        port = start_port + offset
        if voices_ok(server_url(host, port),
                      timeout_s=REUSE_PROBE_TIMEOUT_S):
            return server_url(host, port)
    return None


def start_server_with_retry(host, start_port):
    """Start a VoxLab server, reusing or retrying ports as needed.

    Returns (server_thread, url, reused, detail): thread is None
    when reusing an external server or when nothing could start.
    detail is "" on success and the real failure text otherwise
    (import traceback tail, thread error, or hang description),
    already written to voxlab-server.log by the caller paths that
    need it — this function itself logs thread deaths via
    ServerThread._run and import failures are raised to it here
    and logged before returning. Retry rule: a thread that DIES
    (bind failure / crash) tries the next free port at once; a
    thread that stays ALIVE but never answers after 60 s is a
    hang and is NOT retried port-by-port (same binary, same
    hang). An import failure is port-independent and is never
    retried."""
    reused_url = find_reused_url(host, start_port)
    if reused_url is not None:
        return None, reused_url, True, ""
    tried = []
    last_error = ""
    for offset in range(MAX_PORT_OFFSET + 1):
        port = start_port + offset
        if not _port_free(host, port):
            tried.append(port)
            last_error = (f"Port {port} is already in use by another "
                          "program (bind test failed) and no VoxLab "
                          "server answers /api/voices on it.")
            continue
        tried.append(port)
        thread = ServerThread(host, port)
        try:
            thread.start()
        except Exception as exc:  # noqa: BLE001 - import crash
            detail = _truncate_detail(traceback.format_exc())
            _append_server_log(
                f"VoxLab server import/start failed on {host}:{port}: "
                f"{exc}\n{traceback.format_exc()}")
            return None, None, False, detail
        if wait_for_server(server_url(host, port),
                           server_thread=thread):
            return thread, server_url(host, port), False, ""
        if thread.died:
            last_error = _truncate_detail(
                thread.traceback_text or thread.error
                or f"Server thread died on port {port} with no error.")
            _append_server_log(
                f"VoxLab server on {host}:{port} died during startup; "
                "trying the next free port.")
            thread.stop()
            continue
        # Alive but silent after 60 s: hang, not a bind failure.
        last_error = (f"Server on port {port} stayed running but "
                      "/api/voices never answered in 60 s "
                      "(startup hang — see the server log).")
        thread.stop()
        break
    detail = (f"Tried ports {tried}. {last_error} "
              f"Server log: {_server_log_path()}")
    _append_server_log(f"VoxLab server failed to start: {detail}")
    return None, None, False, detail


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


def _server_failed_message(url, detail=""):
    """Server-failed dialog: the REAL error, not a guess.

    url may be "" when no port could even be started. detail is
    the truncated traceback / bind / hang text from
    start_server_with_retry (already in voxlab-server.log); when
    it is empty the dialog says so instead of inventing a cause
    ("may already use port 8000" was the old guess that hid the
    real failure)."""
    body = (
        "VoxLab's local server did not start.\n\n"
    )
    if url:
        body += f"Expected it at {url} (/api/voices never answered 200).\n\n"
    if detail:
        body += f"What actually happened:\n{_truncate_detail(detail)}\n\n"
    else:
        body += ("No startup error was captured — check the log below "
                 "for the startup lines.\n\n")
    body += (
        f"Full startup log:\n{_server_log_path()}\n\n"
        "If a port is in use, close the other program (or the "
        "other VoxLab window) and relaunch VoxLab — it will reuse "
        "a running VoxLab server or move to a free port "
        "(8001, 8002, …) on its own.\n\n"
        "Click OK to close VoxLab."
    )
    return body


def run_desktop():
    """Full desktop lifecycle. Returns a process exit code.

    Startup order (changed by the server-failed fix): reuse-or-
    start WITH port retry happens FIRST, before any window is
    opened. The old GUI path opened the window first and only
    the splash loader waited, so a startup failure surfaced as
    a bare dialog with a guessed cause. Now a failure reaches
    the dialog only after reuse scan + free-port retry + real
    error capture, and the dialog shows that error. The splash
    steps then run against a server that is already answering
    (server step passes fast); the splash still gates the swap
    on voices/ffmpeg/Edge/models/output.
    """
    host, port = host_port()
    server_thread, url, reused, detail = start_server_with_retry(host, port)
    if url is None:
        _log_error(f"Desktop server failed to start: {detail}")
        show_error_dialog("VoxLab — server failed",
                          _server_failed_message("", detail))
        return 1
    # CI-only hook: server up, no window (see module docstring).
    if os.environ.get(NO_GUI_ENV, "").strip() == "1":
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
    # The server is already answering here (start_server_with_
    # retry waited for it), so the fallback dialog's "server is
    # running" claim is true without another 60 s wait; if the
    # thread died in the meantime, report its real error.
    try:
        import webview
    except Exception as exc:  # noqa: BLE001 - fallback dialog, not a crash
        _log_error(f"pywebview import failed: {exc}")
        if server_thread is not None and server_thread.died:
            detail = _truncate_detail(
                server_thread.traceback_text or server_thread.error
                or "Server thread died.")
            server_thread.stop()
            show_error_dialog("VoxLab — server failed",
                              _server_failed_message(url, detail))
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
