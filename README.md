# VoxLab (free PC voice studio)

A free, local-first voice studio in the spirit of Voicebox / ElevenLabs,
built with open models only. No account, no subscription, no cloud:
everything runs on the user's own PC.

## Scope v1 (agreed 2026-10-26, updated 2026-10-26 ~04:00)
- PC only. The Android APK was cancelled by the user (2026-10-26 ~03:59).
- English + Bengali. Bengali was added back after the user saw ElevenLabs'
  Bengali filter: Bengali comes from open models, never from ElevenLabs'
  own voices.
- This is NOT a copy of Voicebox's code. Voicebox is a local alternative
  to ElevenLabs, not a clone of ElevenLabs' code, and this studio follows
  the same idea: existing open engines, wrapped in one simple app.
- Design: ideas taken from the reference app's design elements
  (inspiration only, not a copy), in VoxLab's own logo theme.
- Logo: `assets/voxlab-logo.png` — used as the PC app icon.
- Theme: dark navy background, cyan → blue → purple gradient (logo colours).
- Credit inside the app: "Developed by Ishtiaque Hasib · VoxLab".

## Engines (v1) — audit decision 2026-10-26, see AUDIT.md
- **Primary cloning engine: Chatterbox** (zero-shot cloning from a
  reference audio file). Audit winner over Qwen3-TTS: perfect transcript,
  loudness closest to the reference, same engine family Voicebox uses.
- Kokoro-82M: fixed preset voices, fast on CPU (ONNX route), English and
  7 other languages. Same engine Voicebox ships. Kokoro cannot clone, so
  it is not the cloning engine.
- Qwen3-TTS: tested, dropped from v1 (equal transcript, quieter, float32
  on CPU, 2.4 GB for no measured gain). Can return later.
- Bengali (from Hugging Face open models, NOT ElevenLabs voices):
  Indic Parler-TTS Bengali speakers (Arjun, Aditi, Tapan, Rashmi, Arnav,
  Riya) + Edge Bengali base voices (Nabanita, Pradeep, Tanishaa, Bashkar)
  with presets. Parler Arjun already won the user's Bengali listening
  test. Bengali server wiring is still pending — the voice list and
  filter UI exist, generation wiring does not yet.
  IndicF5 Bengali cloning later, if its gated terms are accepted.
  Bengali generation wiring is DONE (see PARITY.md): Edge presets and
  Parler speakers (via a pinned venv_parler) both tested via /api/generate.
- Later: effects, stories editor.

## How to run (v1, on your PC)
1. Install Python 3.12 and espeak-ng.
2. `pip install -r backend/requirements.txt`
3. `python backend/server.py`
4. Open http://127.0.0.1:8000 in a browser.
5. Type text, pick a voice, Generate, Play, Download MP3.

## TADA low-RAM load note (2026-10-26, see PARITY.md top section)
- TADA generation is tested: `output/tada_clone.wav`, 4.04 s, exact
  transcript. The working run script is `tmp/run_tada_bf16.py`, NOT
  `test_tada.py` (target sentence unchanged in both).
- On a low-RAM PC, load the LM ONLY with
  `TadaForCausalLM.from_pretrained("HumeAI/tada-1b",
  dtype=torch.bfloat16, low_cpu_mem_usage=True)`.
- Do NOT set a global BF16 default dtype: the encoder's wav2vec2
  path takes float32 reference audio and fails with a
  FloatTensor/CPUBFloat16Type mismatch if the default is BF16.
- Unpatched float32 init is OOM-killed (exit 137) on a 7.7 GiB,
  no-swap VM, even with `low_cpu_mem_usage=True` alone.

## Parity scaffold (2026-10-26, see PARITY.md)
- backend/parity.py — mic-record upload, system-capture, dictation,
  MCP /api/mcp/speak (Kokoro, Parler, Edge, Chatterbox clone),
  Qwen3-0.6B Rewrite/Compose, ffmpeg stories and effects, plus
  backend/global_shortcut.py (desktop hotkey + clipboard paste).
  No model downloads at import; dictation now defaults to Whisper
  Turbo (large-v3-turbo) with a small-model fallback (2026-10-27,
  see PARITY.md). Chatterbox Turbo, LuxTTS, TADA and Qwen CustomVoice
  are tested (see PARITY.md). Qwen3 LLM is tested at 0.6B. Wired
  into server.py behind a guarded
  import so v1 still starts if it fails.

## Layout
- backend/server.py — FastAPI server, /api/voices, /api/generate
  (backend/clone.py is a standalone Chatterbox module, not an API route)
- backend/parity.py — parity routes (see PARITY.md)
- app/index.html — single-page studio UI (no build step)
- backend/requirements.txt — Python deps

## Licence
App code: MIT (like Voicebox). Each TTS model keeps its own licence
(Kokoro Apache 2.0, Chatterbox MIT, Qwen as per its repo).
Voice cloning: only clone a voice you own or have explicit permission
to use. Never clone someone else's voice for a public service.
