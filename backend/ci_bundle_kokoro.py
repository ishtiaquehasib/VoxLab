"""CI build step only (never shipped in the app): download the Kokoro
ONNX model + voices from hexgrad/Kokoro-82M and generate the bundled
clone reference, so PyInstaller --add-data has real files to bundle.

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
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUNDLED = os.path.join(ROOT, "bundled")
os.makedirs(BUNDLED, exist_ok=True)

from huggingface_hub import snapshot_download  # noqa: E402

snap = snapshot_download(
    "hexgrad/Kokoro-82M",
    allow_patterns=["kokoro-v1.0.onnx", "voices-v1.0.bin"],
)
for name, min_bytes in (("kokoro-v1.0.onnx", 100_000_000),
                        ("voices-v1.0.bin", 10_000_000)):
    src = os.path.join(snap, name)
    dst = os.path.join(BUNDLED, name)
    if not os.path.isfile(src):
        sys.exit(f"CI Kokoro bundle FAILED: {name} not in snapshot {snap}")
    shutil.copyfile(src, dst)
    size = os.path.getsize(dst)
    print(f"bundled {name}: {size} B")
    if size < min_bytes:
        sys.exit(f"CI Kokoro bundle FAILED: {name} too small ({size} B)")

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
