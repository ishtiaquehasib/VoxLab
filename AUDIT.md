# VoxLab engine audit — 2026-10-26 (user asleep, audit run by assistant)

## Question
Which engine gives the best output, Voicebox-like, for VoxLab's PC app?
The user had not listened to Voicebox, so the choice was delegated to an
objective audit, not to ear judgement alone.

## Samples (same reference, same target text)
- Reference voice: Kokoro af_heart, synthetic (no real person, permission-safe)
  - Reference text: "Hello, this is a free voice studio running on my own computer. No account, no subscription, just open models and my own voice."
- Target text for both clones: "This is VoxLab, a free voice studio running on my own computer."
- Files in `output/`: `kokoro_af_heart.mp3` (8.13 s), `chatterbox_clone.mp3` (4.12 s), `qwen3_clone.mp3` (4.16 s), all 24 kHz.

## Method (no ear judgement)
1. Speech-to-text with faster-whisper "small" (CPU, int8), English, beam 5.
2. Volume with ffmpeg volumedetect.
3. Timbre proxy: mean MFCC (20 coeffs) cosine vs the Kokoro reference.
   This is a crude proxy, not a speaker-embedding score — a 0.0003 gap is noise.

## Results

| Engine | Whisper transcript vs target | Mean volume | Max volume | MFCC cosine vs ref |
|---|---|---|---|---|
| Kokoro af_heart (fixed voice, NOT cloning) | Exact, full reference text | -22.9 dB | -6.6 dB | — (reference itself) |
| Chatterbox clone | Exact: "This is VoxLab, a free voice studio running on my own computer." | -22.3 dB | -6.3 dB | 0.9981 |
| Qwen3-TTS 0.6B Base clone | Exact: same sentence | -24.4 dB | -5.4 dB | 0.9984 |

RMS: Kokoro 0.0759, Chatterbox 0.081, Qwen3 0.0637 — Chatterbox is closest
to the reference loudness; Qwen3 is noticeably quieter.

## Decision for VoxLab v1 (PC only)
- **Primary cloning engine: Chatterbox.** Perfect transcript, loudness closest
  to the reference, and it is the same engine family Voicebox itself uses
  for multilingual cloning — so "Voicebox er moto same" in the truest sense.
  Its API is also the simplest for cloning (reference wav only, no transcript
  needed for the clone call).
- **Fixed built-in voices: Kokoro** (ONNX route, fast, proven af_heart etc.).
  Kokoro alone cannot clone a user's voice, so it cannot be the cloning
  engine, but it stays as ready-made voices.
- **Qwen3-TTS: dropped from v1, not deleted from the record.** Its clone was
  equally perfect on transcript and marginally higher on the crude MFCC
  proxy (0.9984 vs 0.9981, i.e. noise), but it is quieter, needs float32
  on CPU, and adds a 2.4 GB model for no measured gain. It can return later
  if the user wants a second cloning engine.
- **Bengali: Parler (Arjun first, from the Mahbub test) + Edge presets.**
  Parler already won the user's own Bengali listening test (55 s Arjun
  sample, 2026-10-26). Bengali generation is listed in the app but its
  server wiring is still pending — see README. This audit does not claim
  Bengali generation is wired yet.

## Honest limits
- No human listening panel was used; the user was asleep and had not heard
  Voicebox. The user can still overrule this choice by ear in the morning.
- MFCC cosine is not speaker verification; it is reported only to show the
  two clones are indistinguishable on that crude measure.
- CPU generation is slow (Chatterbox ~16 min and Qwen3 ~13 min wall time
  here, including first model downloads). On a user's PC with a GPU it will
  be far faster; on CPU it is slow but free.
- Android APK is cancelled by the user (2026-10-26 ~03:59). VoxLab is PC-only.
