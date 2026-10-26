# VoxLab vs Voicebox — Competitor Analysis
Date first written: 2026-10-26. Source: voicebox.sh homepage + /pricing, read live same day.
Refreshed: 2026-10-26 late. Sources re-checked via web search only (no live browser task, no sign-in):
voicebox.sh/pricing (unchanged tiers), docs.voicebox.sh (feature list), voicebox.sh homepage.
Rule: no fake claims. No copied star/download counts, no testimonials, no invented numbers.
VoxLab status is honest: Tested / Code-only / Not live-tested / Not built. "Tested" means a test
ran on this VM with an exact result recorded in PARITY.md; it does not mean tested on a user's PC.

## Competitor: Voicebox (jamiepine/voicebox, MIT)
- Positioning: "Clone, dictate and create", free local alternative to ElevenLabs + WisprFlow,
  entirely on your machine.
- Platforms (docs/homepage): macOS Apple Silicon, macOS Intel, Windows 64-bit MSI, Linux,
  plus Docker. Voicebox's own Linux packaged-release note (third-party summary of its docs):
  Linux packaged releases are more limited than macOS/Windows; source build may be needed.
- Pricing (voicebox.sh/pricing, re-checked 2026-10-26 late, unchanged): Local $0 free forever,
  no account. Cloud $12/year coming soon (encrypted backup/sync, 25 GB, 5 devices, 30-day
  history). Studio $48/year coming soon, explicitly "Placeholder — pricing TBD" (250 GB,
  unlimited devices, 1-year history, priority support).
- Feature set (docs.voicebox.sh): clone from upload / mic / system capture (from 3 s);
  dictation anywhere with a global hotkey, transcript pasted into any app or clipboard;
  MCP server (voicebox.speak, per-agent voice); voice personalities (Rewrite / Compose,
  local LLM); multi-voice stories (multi-track timeline); audio effects (pitch shift,
  reverb, delay, chorus, compression, filters); expressive paralinguistic tags;
  long-form auto-chunking with crossfade; local REST + WebSocket API; 23 languages.
- Engine count — note a discrepancy, do not paper over it: the homepage copy found in
  search says 7 TTS engines; the docs page lists 8 (Qwen3-TTS, Qwen CustomVoice,
  Qwen VoiceDesign, LuxTTS, Chatterbox Multilingual, Chatterbox Turbo, HumeAI TADA,
  Kokoro). VoxLab does NOT have Qwen VoiceDesign, and has not tested a multi-track
  stories timeline, auto-chunking with crossfade, or the full effects list above.
- Star/download counts: third-party posts in this refresh claimed 50K+ stars / 2.6M
  downloads, while the original analysis recorded ~58.6k stars. These are NOT copied
  into VoxLab's site or README as VoxLab numbers, and are not treated as verified
  Voicebox figures here — VoxLab's own count stays blank/auto from its own repo API.

## Other free local studios in the same viral niche (why Voicebox is the benchmark, not the only rival)
- VoiceStudio (debpalash/VoiceStudio, AGPL-3.0, third-party summary): free local app,
  macOS/Windows/Linux/Docker, cloning, dubbing, dictation, audiobooks; default model
  non-commercial terms for its OmniVoice model; "646 languages" is a language-count
  claim, not a quality claim per language. VoxLab does not copy its claims.
- Engine-only rivals (not full studios): Coqui XTTS v2 (17 languages, non-commercial
  weights), F5-TTS (EN/ZH, non-commercial weights), Fish Speech S1-mini (non-commercial),
  Piper (lightweight, no cloning), Bark (non-speech audio), Orpheus 3B (expressive).
  VoxLab's engine choices (Chatterbox MIT, Kokoro Apache-2.0, LuxTTS, Qwen, TADA) are
  chosen for commercial-safe licences where possible; XTTS/F5/Fish are NOT in VoxLab.
- Hosted incumbents (for pricing contrast only): ElevenLabs free tier is character-capped
  with no cloning on free; paid tiers are monthly subscriptions. VoxLab, like Voicebox,
  charges $0 for local use — that is the whole pitch, so the release must not add any
  fake payment form or paid tier that does not exist.

## Feature comparison — refreshed

| Feature | Voicebox | VoxLab now | Gap / next step |
|---|---|---|---|
| Voice cloning, upload clip (WAV/MP3/FLAC/WebM) | Yes, from 3 s | Chatterbox clone module + MCP clone route, tested (direct 1.4 s, endpoint 0.72 s, same text, sampling variance) | Wire clone into the main app UI end-to-end; app UI clone is not yet a tested user flow |
| Mic record, live waveform, up to 30 s | Yes | Code only: MediaRecorder UI, 30 s auto-stop, live waveform, upload endpoint tested for file upload; live mic NEVER tested (no mic/browser in this VM) | User's Windows laptop test only |
| System audio capture | Yes | Code only: Linux PulseAudio monitor path; VM has no audio server, capture-info `available: false`, capture POST 503 with real error; Windows WASAPI / macOS BlackHole are setup docs only | User's Windows WASAPI test only; do not claim capture works |
| Dictation anywhere, shortcut, paste to any app/clipboard | Yes (Cmd+Opt macOS, Ctrl+Alt Windows) | In-page dictation tested (faster-whisper, librosa path, exact transcript); global-shortcut module implemented + headless-tested (Ctrl+Alt+V / Cmd+Option+V, copy, paste only on explicit paste=True) but live hotkey/paste NOT tested, and it triggers dictation on a supplied file — it does not record by itself, and packaged-shell recording wiring is NOT built | User's Windows live test; do not claim "dictation anywhere" end-to-end |
| MCP agent voices, voicebox.speak, per-agent voice | Yes, day one | MCP `/api/mcp/speak` tested for Kokoro (af_bella 1.365 s, af_heart 3.925 s), Parler Arjun (2.961 s, 261,164 B), Edge Pradeep (3.12 s, 18,720 B), and Chatterbox clone; non-synthesizing voices return `synthesized: false` with the real error, no silent fallback in MCP | MCP transcribe/list-captures/list-profiles tools that Voicebox docs list are NOT in VoxLab; add only if scoped |
| Personalities Rewrite / Compose | Yes, local LLM | Real Qwen3-0.6B path, `llm_used: true` only on real generation, template fallback with real error otherwise; rewrite quality MINIMAL, sometimes verbatim at 0.6B | Do not claim strong rewriting; a larger Qwen3 was NOT downloaded |
| Multi-voice stories | Yes, multi-track timeline | Scaffold only: ffmpeg concat tested (8.128 s x2 = 16.256 s exact); NO multi-track timeline, no trim/split editor | Timeline editor is a post-v1 gap, not a v1 claim |
| Audio effects | Pitch, reverb, delay, chorus, compression, filters | Scaffold only: ffmpeg speed 1.25 + volume 0.9 + echo tested (6.574 s); NOT the full Voicebox effects list | Full effects list is a gap |
| Long-form auto-chunking with crossfade | Yes | No — not built, not tested | Gap; TADA long-form is the engine for it, and TADA itself is still blocked (below) |
| Built-in local REST API, no keys, offline | Yes, every engine an endpoint | Partial but real: /api/voices, /api/generate (Kokoro, Edge, Parler), /api/mcp/speak, /api/parity/* (dictate, capture-info, stories, effects, personalities) | Qwen CustomVoice / Turbo / LuxTTS are tested as scripts, NOT yet wired as server engines — wire before claiming "every engine an endpoint" |
| Video tutorials | Yes, community walkthroughs | No | Record after v1 works on a real PC |
| Testimonials / social proof | Yes, user quotes + download claims | None, deliberately. 0 users yet, no fake numbers, no fake quotes | Earn after release only; demo/sample only if labelled Demo, never as a testimonial |
| Download installers | macOS ARM/Intel DMG, Windows MSI, Linux (limited packaged) | Website cards only, NO installer binary yet. Workflows for Windows/macOS/Linux exist, YAML-validated, 7 steps each, models NOT bundled, Release attach on v* tags only | Real Actions run only after first push; Windows first for the user's test |
| Donate button | Yes | Yes, SupportKori $1.50 (card ৳195), real checkout link only, no fake form, verified live on the website | Done on website |
| Star count | Auto from GitHub | Auto from GitHub API for ishtiaquehasib/VoxLab, blank until repo publishes; never a hardcoded number | Done on website |
| Favicon, logo, motion | Yes | Yes, logo + animated gradient/wave, favicon set; curl-verified /favicon.ico is the VoxLab logo, but the user's own fresh-tab check was never explicitly confirmed | Last website all-OK item, still open |
| Pricing page | Local $0, Cloud $12/yr soon, Studio $48/yr soon | Same 3 tiers on website, Cloud/Studio not for sale yet, no payment taken | Done on website; service not built, and 25/250 GB cloud storage conflicts with zero-cost operation — do not sell them |

## Model comparison — refreshed

| Model | Voicebox | VoxLab |
|---|---|---|
| Qwen3-TTS (Base, 0.6B) | Yes (1.7B/0.6B in its list) | Tested, DROPPED from v1 (equal transcript, quieter, float32-on-CPU, 2.4 GB for no measured gain) |
| Chatterbox (Multilingual) | Yes | Primary cloning engine, audit winner, in v1 |
| Chatterbox Turbo (350M, [laugh] tags) | Yes | Tested: 3.80 s, 182,444 bytes, exact transcript; [laugh]/paralinguistic tags NOT tested |
| LuxTTS (48 kHz, CPU claim 150x realtime on GPU) | Yes | Tested EXACT with a proven recipe only: full 8 s reference + steps=8 + speed=0.7 → 5.37 s, 515,116 bytes, exact on two transcribers; old defaults drop the opening words; GPU speed claim NOT verified (no GPU here) |
| Qwen CustomVoice (9 presets) | Yes | Tested: Ryan only, 5.04 s, 241,964 bytes, exact transcript; other 8 speakers NOT individually generated; 1.7B instruct NOT tested |
| Qwen VoiceDesign | Yes (docs list) | NOT in VoxLab at all |
| TADA (HumeAI, 1B/3B, 700 s+ long-form) | Yes | BLOCKED on generation: weights 3.7 GB + codec 2.1 GB downloaded and verified, venv_tada + hume-tada 0.1.8 ready, but generation has NEVER run — gated Llama tokenizer was missing (401s). 4 tokenizer files have now arrived on the VM (output/llama_tokenizer/, see PARITY.md latest) and a TADA rerun is in progress separately; until that rerun produces a verified wav, TADA stays NOT DONE |
| Kokoro-82M (CPU realtime, presets) | Yes | In v1, fixed voices; ONNX route tested (af_heart 8.13 s) |
| Whisper (transcription) | Yes | Used in testing; in-page dictation via faster-whisper small, exact transcript |
| Whisper Turbo (large-v3-turbo) | Yes | Tested as a transcriber: load 12.2 s, transcribe 25.2 s, exact transcript; NOT yet wired as the dictation engine (dictation still defaults to small) |
| Qwen3 LLM (refinement/persona) | Yes (bundled local LLM) | Tested at 0.6B only (1.5 GB); real but minimal/sometimes verbatim; larger sizes NOT downloaded |
| Bengali voices | None in any Voicebox engine | VoxLab advantage, real and tested: Parler Arjun (direct 2.97 s, via server 200 / 26,079 bytes MP3, no fallback header) + Edge presets (18,720 bytes, 3.12 s). Other 5 Parler speakers use the same code path but were NOT individually generated; the Parler→Edge fallback header path is coded but NEVER live-triggered |

## VoxLab advantages (honest, not copied)
- Bengali voices, which Voicebox has none of — the single clearest differentiation, and
  the one the user chose by ear (Parler Arjun ranked first of Edge/Parler/IndicVoice).
- SupportKori donate in BDT context ($1.50 / ৳195 card), where Voicebox has no such route.
- Same free-local model, plus an ElevenLabs-style Bengali filter UI in the app.
- Viral-niche timing: the local voice-studio niche is visibly trending (Voicebox as the
  #1 trending repo in third-party posts this month), which makes a clean, honest,
  working release more valuable than a rushed one with fake claims — a fake count or
  fake testimonial found on day one would destroy the differentiation.

## VoxLab disadvantages (honest, refreshed)
- No published code yet: repo reported created (empty), code NOT pushed, no installer
  binary, no star count, no users/testimonials yet. (Repo state not re-verified live
  in this refresh — GitHub was deliberately not touched.)
- No live-tested mic, system capture, or global shortcut/paste on a real PC.
- No multi-track stories timeline, no full effects list, no auto-chunking/crossfade,
  no Qwen VoiceDesign, no Whisper Turbo dictation wiring.
- LLM persona quality is minimal at 0.6B; TADA generation is still unproven.
- Cloud/Studio pricing is website-only; no server, billing, or encrypted sync built,
  and that conflicts with zero-cost operation for storage.
- Favicon fresh-tab confirmation by the user is still the last open website item.

## Release-readiness checklist (release gate: all-OK announced by the parent, THEN release — do NOT release from this refresh)
- [ ] TADA generation produces a verified wav (exact transcript/duration/bytes) — rerun in progress separately; NOT done until that wav exists
- [ ] Whisper Turbo wired as the dictation engine (or the dictation default honestly labelled small)
- [ ] Push bundle re-verified (30 files, ~3.3 MB at last check; blogger-theme now under website/, github-profile/ gitignored, no venvs/output/models) — re-check before push, do not push from here
- [ ] First push to ishtiaquehasib/VoxLab, then set About homepage (https://voxlabapp.blogspot.com) + topics (ai, voice-clone, tts, bengali-tts, chatterbox, kokoro, parler-tts, whisper, voice-ai, open-source) via the About editor (only possible after first push)
- [ ] Tag a v* release, verify real Windows/macOS/Linux Actions artifacts (Windows first for the user's laptop test)
- [ ] Update the Blogger download/release links to the real repo; keep star count auto (no hardcoded number)
- [ ] User's own tests after release (his Windows laptop only): installer install, live mic record, WASAPI system capture, global shortcut/paste live — these cannot be claimed done from this VM
- [ ] Favicon fresh-tab confirmation by the user
- [ ] Testimonials: none until real users exist; demo/sample only if labelled Demo

## Sequence agreed with user
1. Competitor analysis (this file) — refreshed 2026-10-26 late.
2. All-OK check on website + TADA test (in progress separately).
3. Only after all-OK is announced: GitHub release — repo on ishtiaquehasib (this-chat-only),
   About + website + topics, README, MIT license, Contributing, Security, GitHub Actions
   Windows installer first, Release, then update website download/releases links to the
   real repo. Do NOT start the release before that all-OK point.
