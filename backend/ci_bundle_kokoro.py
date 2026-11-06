"""CI build step only (never shipped in the app): download the Kokoro
ONNX model + voices from the kokoro-onnx release assets and generate
the bundled clone reference, so PyInstaller --add-data has real files
to bundle.

Why this exists (A-Z GATE 2026-10-28): output/kokoro-v1.0.onnx (311 MB)
+ voices-v1.0.bin (27 MB) + kokoro_af_heart.wav (382 KB) cannot be
committed to git (GitHub blocks files >100 MB, and output/ is
gitignored), and v1.1.5 shipped WITHOUT them — so main Generate 500'd
on every fresh install once KPipeline failed, and every clone engine
failed "reference not found". This script runs in CI before
PyInstaller, fails the job if any file is missing/small, and proves
the ONNX route generates real audio on the runner itself.
Output: bundled/kokoro-v1.0.onnx, bundled/voices-v1.0.bin,
bundled/kokoro_af_heart.wav (added to the exe via --add-data).

Download method (2026-11-07 CI fix): plain-HTTPS via urllib (stdlib
only). The script previously used huggingface_hub.snapshot_download,
but Windows CI #19 failed with "ModuleNotFoundError: huggingface_hub"
even though the install step had passed — the bundle step must not
depend on any package the resolver may or may not have installed.
urllib has zero package dependencies, so this step cannot fail that
way again. The files come from the kokoro-onnx project's own
release assets (thewh1teagle/kokoro-onnx, tag model-files-v1.0) —
NOT from hexgrad/Kokoro-82M: that repo does not contain
kokoro-v1.0.onnx or voices-v1.0.bin at all (verified 2026-11-07 via
the Hugging Face API; it holds kokoro-v1_0.pth + voices/*.pt only),
so the old snapshot_download would have failed next with "not in
snapshot" even with the import fixed. The release files match the
lab's local copies byte-for-byte in size (325,532,387 B /
28,214,398 B).
"""
import os
import shutil
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUNDLED = os.path.join(ROOT, "bundled")
os.makedirs(BUNDLED, exist_ok=True)

# kokoro-onnx model files, hosted by the kokoro-onnx project itself.
KOKORO_RELEASE = ("https://github.com/thewh1teagle/kokoro-onnx"
                  "/releases/download/model-files-v1.0")


def download_file(url, dst, min_bytes, attempts=3):
    """Download url -> dst with retries; fail loudly if it never lands
    whole. Streams to disk (no whole-file buffering)."""
    last_err = None
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "VoxLab-CI/1.0"})
            with urllib.request.urlopen(req, timeout=120) as resp, \
                    open(dst, "wb") as f:
                shutil.copyfileobj(resp, f, length=1024 * 1024)
            size = os.path.getsize(dst)
            print(f"downloaded {os.path.basename(dst)}: {size} B "
                  f"(attempt {attempt})")
            if size < min_bytes:
                raise IOError(f"{dst} too small ({size} B, "
                              f"need >= {min_bytes})")
            return size
        except Exception as e:  # noqa: BLE001 - retry, then fail loudly
            last_err = e
            print(f"download attempt {attempt}/{attempts} for {url} "
                  f"failed: {e}")
            if os.path.exists(dst):
                os.remove(dst)
            if attempt < attempts:
                time.sleep(5 * attempt)
    sys.exit(f"CI Kokoro bundle FAILED: could not download {url}: "
             f"{last_err}")


for name, min_bytes in (("kokoro-v1.0.onnx", 100_000_000),
                        ("voices-v1.0.bin", 10_000_000)):
    download_file(f"{KOKORO_RELEASE}/{name}",
                  os.path.join(BUNDLED, name), min_bytes)

from kokoro_onnx import Kokoro  # noqa: E402
import soundfile as sf  # noqa: E402

kokoro = Kokoro(os.path.join(BUNDLED, "kokoro-v1.0.onnx"),
                os.path.join(BUNDLED, "voices-v1.0.bin"))
samples, sr = kokoro.create(
    "Hello, this is a free voice studio running on my own computer. "
    "No account, no subscription, just open models and my own voice.",
    voice="af_heart", speed=1.0, lang="en-us")
ref = os.path.join(BUNDLED, "kokoro_af_heart.wav")
sf.write(ref, samples, sr)
seconds = len(samples) / sr
size = os.path.getsize(ref)
print(f"bundled kokoro_af_heart.wav: {seconds:.2f} s, {size} B, sr={sr}")
if size < 100_000 or seconds < 3:
    sys.exit("CI Kokoro bundle FAILED: reference wav too small/short")
print("CI Kokoro bundle OK")
