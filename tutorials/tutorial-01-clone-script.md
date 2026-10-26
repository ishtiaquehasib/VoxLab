# Tutorial 01 — Clone your voice in VoxLab (SCRIPT + RENDER PLAN ONLY)

Status: RENDERED 2026-10-27, labelled Demo. Video: tutorial-01-clone.mp4,
22.500 s, 551,144 B, 1920x1080@30, h264 + aac 24 kHz. Narration:
tutorial-01-clone-narration.wav, 22.528 s, Kokoro ONNX af_heart en-us.
Frames at 2/6/11/15/20 s viewed and clean. No real UI screenshots yet,
so the video stays labelled "Demo — UI screenshots pending" until real
app screenshots from a running build replace the text step cards.

## What the viewer learns (60-90 s target, one feature only)
1. Open VoxLab, go to Clone.
2. Upload a clear 30-second voice sample (or record in the app).
3. Type text, pick the cloned voice, generate.
4. Play it back, then download the WAV.
Honest on-screen note (must stay in the final video): cloning works with
your own voice or a voice you have permission to use. No other person's
voice is used in this tutorial.

## Narration script (neutral opening — no religious greeting)
- [0-8s] "VoxLab e nijer voice clone kora khub shohoj. Prothome Clone e jan."
- [8-20s] "Ekhane 30 second er ekta porishkar voice sample upload korun, ba mic diye record korun."
- [20-35s] "Ebar je lekha bolate chan, seta likhun, ar cloned voice ta select korun."
- [35-50s] "Generate chap din. Audio toiri hole play kore shunun, thik lagle download korun."
- [50-60s] "Etai VoxLab Clone. Porer tutorial e dictation dekhbo."

## Visual plan (NOT a screen recording claim)
- Title card: "VoxLab — Clone" + VoxLab logo (assets/voxlab-logo.png).
- Step cards 1-4, one per narration block, with the app UI described in
  text. Real app screenshots are added ONLY from a real running VoxLab
  build (v1.0.6 smoke or later); no mock UI, no stock screenshot, no
  Voicebox screenshot is ever used.
- If no real screenshot is available on render day, render title +
  step cards only and label the video "Demo — UI screenshots pending".

## Render plan (proven pipeline, ~/workspace/cartoon_meme/)
- Frames: PIL, 1920x1080 @ 30 fps, dark navy #05081f background,
  VoxLab gradient #00d4ff -> #4868D8 -> #8b5cf6 for title/accents.
- Bengali text: PIL + raqm, NotoSansBengali-Bold
  (/usr/share/fonts/truetype/noto/NotoSansBengali-Bold.ttf, verified present).
  Multi-line bubbles via explicit \n, centred lines.
- Emoji (only if needed): NotoColorEmoji.ttf at 109 px only, crop bbox,
  downscale to target — the size-109 strike limit from the cartoon pipeline.
- Narration audio: generate with VoxLab Kokoro af_heart (already tested:
  8.128 s / 390,188 B sample, exact transcript) OR a real cloned voice
  from the tutorial presenter's own sample. Never use a demo voice and
  present it as a cloned user voice.
- Mux: ffmpeg, video + narration WAV, 24 kHz common rate (see the
  legacy-concat lesson in PARITY.md: resample, never -c copy mixed rates).
- QC before any publish: ffprobe seconds, file bytes, watch the full
  render once, check every Bengali conjunct renders correctly, check
  the narration matches the on-screen step at each timestamp.
  A render that fails QC is NOT published, and is NOT counted as a tutorial.

## Files created on render day (2026-10-27)
- tutorials/tutorial-01-clone-script.md (this file)
- tutorials/tutorial-01-clone.mp4 — 22.500 s, 551,144 B
- tutorials/tutorial-01-clone-narration.wav — 22.528 s, 1,081,388 B

## Later tutorials (planned, NOT made)
- 02 Dictation anywhere (shortcut + paste) — needs a real Windows
  hotkey/paste test first.
- 03 Stories timeline + crossfade.
- 04 Effects (with the aecho label, never called convolution reverb).
- 05 Bengali voices (Parler Arjun + Edge) — presenter's own Bengali sample only.
- 06 MCP agent voices.
