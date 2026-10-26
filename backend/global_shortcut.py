"""VoxLab global dictation shortcut + paste — desktop-side module.

What this does, honestly:
- On a real desktop (Windows/macOS/Linux with a GUI session), it can
  register a global hotkey, run dictation on a supplied audio file,
  copy the transcript to the system clipboard, and — only if the
  caller explicitly asks — simulate Ctrl+V / Cmd+V to paste it into
  the currently focused app.
- On a headless system (no DISPLAY on Linux, no GUI session, no
  clipboard tool, no pynput) it returns an error dict instead of
  pretending to work. Nothing here invents a transcript, a clipboard
  write, or a paste.

Dependencies are optional and never imported at module level except
stdlib: pynput (hotkey + paste simulation) and pyperclip are tried
only when a function needs them. Install on a desktop with:
    pip install pynput pyperclip
On Linux a clipboard tool is also needed: xclip, xsel, or wl-copy
(Wayland). On macOS pbcopy is built in; on Windows, `clip` /
PowerShell Set-Clipboard are built in.

Default hotkey: Ctrl+Alt+V (Windows/Linux) / Cmd+Option+V (macOS).
The hotkey only *triggers* dictation; it does not record audio by
itself — the caller supplies an audio file (e.g. a mic recording
saved by the app) or a transcribe callable. Recording + shortcut
wiring into a packaged desktop shell is still needed for a true
"dictate anywhere" hotkey in the shipped app (see PARITY.md).

Usage:
    from global_shortcut import trigger_dictation, start_hotkey_listener
    result = trigger_dictation("recording.wav", paste=False)
    # result: {"ok": True, "transcript": ..., "clipboard": True, ...}
    #      or {"ok": False, "error": <real reason>}
"""
import os
import platform
import shutil
import subprocess
import sys

DEFAULT_HOTKEY_WINDOWS_LINUX = "<ctrl>+<alt>+v"
DEFAULT_HOTKEY_MACOS = "<cmd>+<alt>+v"


def default_hotkey():
    return DEFAULT_HOTKEY_MACOS if platform.system() == "Darwin" else DEFAULT_HOTKEY_WINDOWS_LINUX


def is_headless():
    """True when no GUI session is available to listen/paste into."""
    if platform.system() == "Linux":
        return not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY")
    return False


def _clipboard_tool():
    """Return (tool, args) for a native clipboard writer, or (None, None)."""
    system = platform.system()
    if system == "Darwin":
        return ("pbcopy", [])
    if system == "Windows":
        return ("clip", [])
    for tool in ("wl-copy", "xclip", "xsel"):
        if shutil.which(tool):
            if tool == "xclip":
                return (tool, ["-selection", "clipboard"])
            if tool == "xsel":
                return (tool, ["--clipboard", "--input"])
            return (tool, [])
    return (None, None)


def copy_to_clipboard(text):
    """Copy text to the system clipboard. Returns {"ok": bool, ...}.

    Tries, in order: pyperclip (if installed), then the native tool.
    Never reports success unless a writer actually ran without error.
    """
    if text is None:
        return {"ok": False, "error": "nothing to copy (text is None)"}
    try:
        import pyperclip
        pyperclip.copy(str(text))
        return {"ok": True, "method": "pyperclip"}
    except ImportError:
        pass
    except Exception as exc:  # noqa: BLE001 - fall through to native tool
        last_error = str(exc)
    else:
        last_error = None
    tool, args = _clipboard_tool()
    if tool is None:
        return {"ok": False,
                "error": "no clipboard tool available (install xclip/xsel/wl-copy on Linux, or pyperclip)"}
    try:
        proc = subprocess.run([tool] + args, input=str(text).encode("utf-8"),
                              capture_output=True, timeout=15)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"clipboard tool failed: {exc}"}
    if proc.returncode != 0:
        return {"ok": False,
                "error": f"clipboard tool {tool} exited {proc.returncode}: {proc.stderr.decode(errors='replace').strip()}"}
    return {"ok": True, "method": tool}


def paste_into_focused_app():
    """Simulate Ctrl+V (Cmd+V on macOS) in the focused app.

    Requires pynput and a GUI session. Returns {"ok": bool, ...}.
    This is deliberately a separate, explicit step: trigger_dictation()
    only pastes when paste=True is passed by the caller.
    """
    if is_headless():
        return {"ok": False, "error": "headless system: no GUI session to paste into"}
    try:
        from pynput.keyboard import Controller, Key
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"pynput not available: {exc}"}
    try:
        kb = Controller()
        mod = Key.cmd if platform.system() == "Darwin" else Key.ctrl
        with kb.pressed(mod):
            kb.press("v")
            kb.release("v")
        return {"ok": True, "method": "pynput Ctrl/Cmd+V"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"paste simulation failed: {exc}"}


def trigger_dictation(audio_path, transcribe_fn=None, paste=False):
    """Dictate one audio file, copy transcript to clipboard, optionally paste.

    transcribe_fn, if given, must be a callable(audio_path) -> dict with
    "available" and "transcript" (the shape of parity.transcribe()).
    If not given, parity.transcribe() is tried — that needs
    faster-whisper + librosa and will return its real error if absent.
    Returns {"ok": True, "transcript", "clipboard", "pasted"} or
    {"ok": False, "error": <real reason>} — never an invented transcript.
    """
    if not audio_path or not os.path.exists(audio_path):
        return {"ok": False, "error": f"audio file not found: {audio_path}"}
    if transcribe_fn is None:
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from parity import transcribe as transcribe_fn  # noqa: N813
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"dictation engine unavailable: {exc}"}
    try:
        result = transcribe_fn(audio_path)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"transcription failed: {exc}"}
    if not result.get("available") or not result.get("transcript"):
        return {"ok": False,
                "error": result.get("error") or "transcription produced no transcript"}
    transcript = result["transcript"]
    copied = copy_to_clipboard(transcript)
    if not copied.get("ok"):
        return {"ok": False, "transcript": transcript,
                "error": f"transcript produced but clipboard copy failed: {copied.get('error')}"}
    pasted = None
    if paste:
        pasted = paste_into_focused_app()
        if not pasted.get("ok"):
            return {"ok": True, "transcript": transcript, "clipboard": True,
                    "pasted": False, "paste_error": pasted.get("error")}
    return {"ok": True, "transcript": transcript, "clipboard": True,
            "pasted": bool(paste)}


def start_hotkey_listener(on_trigger, hotkey=None):
    """Start a global hotkey listener in a background thread.

    on_trigger: callable with no arguments, called on each hotkey press.
    Returns {"ok": True, "listener": <GlobalHotKeys>} on a GUI desktop,
    or {"ok": False, "error": <real reason>} headless / without pynput.
    The caller owns the listener (call .stop() to stop it). This is
    not started at import time and never runs on a headless system.
    """
    if is_headless():
        return {"ok": False, "error": "headless system: no GUI session for a global hotkey"}
    try:
        from pynput import keyboard
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"pynput not available: {exc}"}
    hotkey = hotkey or default_hotkey()
    try:
        listener = keyboard.GlobalHotKeys({hotkey: on_trigger})
        listener.start()
        return {"ok": True, "hotkey": hotkey, "listener": listener}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"hotkey listener failed to start: {exc}"}


if __name__ == "__main__":
    # Self-check only: no recording, no real dictation, no paste.
    print(f"platform={platform.system()} headless={is_headless()} default_hotkey={default_hotkey()}")
    print(f"clipboard_tool={_clipboard_tool()}")
    print(f"copy_test={copy_to_clipboard('VoxLab clipboard self-check')}")
    print(f"hotkey_test_ok={start_hotkey_listener(lambda: None)['ok']} "
          f"(expected False on a headless system)")
