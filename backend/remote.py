"""VoxLab remote mode + one-click local server (2026-10-27).

Voicebox-style "Local or Remote": VoxLab can run against a local
server on this machine, or against a VoxLab server on another machine
on the same network. This module is ONLY configuration, discovery
and health-checking — it never invents a remote server, and it never
proxies arbitrary paths.

Modes (VOXLAB_REMOTE_MODE):
- "local" (default): the app talks to the server started by
  `python backend/server.py` on this machine.
- "remote": the app talks to VOXLAB_REMOTE_BASE_URL instead, e.g.
  http://192.168.1.20:8000. No auth is added here: a remote VoxLab
  server is trusted only on a network the user controls, exactly
  like Voicebox's local API — do NOT expose it to the public
  internet. There is no cloud account, no key, no encryption in
  this mode, and the health response says so.

Local server (one-click start):
- start_local_server() runs backend/server.py as a subprocess with
  VOXLAB_SERVER_HOST / VOXLAB_SERVER_PORT from the environment (or
  the caller's host/port args), then polls /api/voices until it
  answers or the timeout expires. It returns already_running=True
  if a server is already answering on that host:port, so starting
  twice never launches a second server.
- server.py binds VOXLAB_SERVER_HOST (default 127.0.0.1) and
  VOXLAB_SERVER_PORT (default 8000) in its __main__ block.

Remote health / proxy allowlist:
- check_server(base_url) GETs {base}/api/voices and reports
  reachable + status + voices count, or the real error.
- fetch_remote_json(path) only allows GET /api/voices and
  /api/parity/status — any other path is rejected, so a caller
  cannot use this as an open proxy to a remote machine.

Honest limits, do NOT over-claim:
- Remote GPU acceleration is NOT a property of this module: the
  remote machine accelerates only if its own device.py detects a
  GPU (CUDA/MPS) — see backend/device.py. A CPU remote stays CPU.
- Remote dictation/cloning/voices work only if the remote server
  actually has those engines/models; this module reports
  reachability, it does not prove a remote engine exists.
- No automatic discovery (no mDNS / LAN scan): the user types the
  remote host:port. Voicebox-style one-click remote setup with
  automatic discovery is still an open item.
"""

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_SCRIPT = os.path.join(BASE, "backend", "server.py")

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000

# Only these GET paths may be fetched from a remote server.
_ALLOWED_REMOTE_PATHS = ("/api/voices", "/api/parity/status")

_local_server_proc = None


def get_remote_config():
    """Remote-mode config from env, validated, never a guessed URL."""
    mode = os.environ.get("VOXLAB_REMOTE_MODE", "local").strip().lower()
    if mode not in ("local", "remote"):
        mode = "local"
    base_url = os.environ.get("VOXLAB_REMOTE_BASE_URL", "").strip().rstrip("/")
    if mode == "remote":
        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return {
                "mode": "remote",
                "base_url": base_url or None,
                "valid": False,
                "error": "VOXLAB_REMOTE_BASE_URL must be a full http(s) URL, e.g. http://192.168.1.20:8000",
                "local_host": os.environ.get("VOXLAB_SERVER_HOST", DEFAULT_HOST),
                "local_port": int(os.environ.get("VOXLAB_SERVER_PORT", DEFAULT_PORT)),
                "auth": None,
                "encrypted": False,
                "note": "Remote mode has no auth and no encryption; use only on a network you control. Do not expose a VoxLab server to the public internet.",
            }
        return {
            "mode": "remote",
            "base_url": base_url,
            "valid": True,
            "error": None,
            "local_host": os.environ.get("VOXLAB_SERVER_HOST", DEFAULT_HOST),
            "local_port": int(os.environ.get("VOXLAB_SERVER_PORT", DEFAULT_PORT)),
            "auth": None,
            "encrypted": False,
            "note": "Remote mode has no auth and no encryption; use only on a network you control. Do not expose a VoxLab server to the public internet.",
        }
    host = os.environ.get("VOXLAB_SERVER_HOST", DEFAULT_HOST)
    try:
        port = int(os.environ.get("VOXLAB_SERVER_PORT", DEFAULT_PORT))
    except ValueError:
        port = DEFAULT_PORT
    return {
        "mode": "local",
        "base_url": f"http://{host}:{port}",
        "valid": True,
        "error": None,
        "local_host": host,
        "local_port": port,
        "auth": None,
        "encrypted": False,
        "note": "Local mode: server runs on this machine, no account, no key.",
    }


def local_server_url(path=""):
    cfg = get_remote_config()
    base = f"http://{cfg['local_host']}:{cfg['local_port']}"
    return base + path


def remote_url(path=""):
    cfg = get_remote_config()
    return cfg["base_url"] + path if cfg.get("base_url") else None


def check_server(base_url, timeout=5):
    """Probe {base_url}/api/voices. Returns reachable/status/count/error."""
    if not base_url:
        return {"reachable": False, "base_url": None, "error": "no base URL configured"}
    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return {"reachable": False, "base_url": base_url, "error": "base URL must be a full http(s) URL"}
    url = base_url.rstrip("/") + "/api/voices"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            import json
            data = json.loads(resp.read().decode("utf-8", "replace"))
            voices = data.get("voices", []) if isinstance(data, dict) else []
            return {"reachable": True, "base_url": base_url,
                    "status": resp.status, "voices_count": len(voices),
                    "error": None}
    except urllib.error.HTTPError as exc:
        return {"reachable": False, "base_url": base_url,
                "status": exc.code, "error": f"HTTP {exc.code}"}
    except Exception as exc:  # noqa: BLE001 - report the real reason
        return {"reachable": False, "base_url": base_url, "error": str(exc)}


def is_local_server_running(host=None, port=None):
    cfg = get_remote_config()
    host = host or cfg["local_host"]
    port = port or cfg["local_port"]
    result = check_server(f"http://{host}:{port}", timeout=2)
    return bool(result.get("reachable"))


def start_local_server(host=None, port=None, timeout=20):
    """One-click local server start. Returns pid/url/already_running.

    Returns {"ok": False, "error": ...} if the server script is missing
    or does not answer within timeout — never a claim of a running
    server that is not answering /api/voices.
    """
    global _local_server_proc
    cfg = get_remote_config()
    host = host or cfg["local_host"]
    port = int(port or cfg["local_port"])
    base_url = f"http://{host}:{port}"
    if is_local_server_running(host, port):
        return {"ok": True, "already_running": True, "pid": None,
                "url": base_url, "host": host, "port": port}
    if not os.path.exists(SERVER_SCRIPT):
        return {"ok": False, "error": f"server script missing: {SERVER_SCRIPT}"}
    env = dict(os.environ)
    env["VOXLAB_SERVER_HOST"] = host
    env["VOXLAB_SERVER_PORT"] = str(port)
    try:
        _local_server_proc = subprocess.Popen(
            [sys.executable, SERVER_SCRIPT],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"failed to start server: {exc}"}
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _local_server_proc.poll() is not None:
            return {"ok": False, "error": "server process exited during startup; see server logs",
                    "exit_code": _local_server_proc.returncode}
        if is_local_server_running(host, port):
            return {"ok": True, "already_running": False,
                    "pid": _local_server_proc.pid, "url": base_url,
                    "host": host, "port": port}
        time.sleep(0.5)
    return {"ok": False, "error": f"server did not answer /api/voices within {timeout}s",
            "pid": _local_server_proc.pid if _local_server_proc else None}


def stop_local_server():
    """Stop a server started by start_local_server() in this process."""
    global _local_server_proc
    if _local_server_proc is None:
        return {"ok": False, "error": "no server started by this process"}
    try:
        _local_server_proc.terminate()
        _local_server_proc.wait(timeout=10)
    except Exception:
        try:
            _local_server_proc.kill()
        except Exception:
            pass
    _local_server_proc = None
    return {"ok": True, "stopped": True}


def fetch_remote_json(path, base_url=None, timeout=5):
    """Fetch one allowlisted GET path from a remote/local server."""
    if path not in _ALLOWED_REMOTE_PATHS:
        return {"ok": False, "error": f"path not in remote allowlist: {path}"}
    cfg = get_remote_config()
    base = base_url or cfg.get("base_url")
    if not base:
        return {"ok": False, "error": "no remote base URL configured"}
    url = base.rstrip("/") + path
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            import json
            return {"ok": True, "status": resp.status,
                    "data": json.loads(resp.read().decode("utf-8", "replace"))}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
