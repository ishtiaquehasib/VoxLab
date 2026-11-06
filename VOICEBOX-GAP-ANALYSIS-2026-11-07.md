# Voicebox vs VoxLab — gap analysis: why VoxLab output does not match Voicebox

- Date: 2026-11-07
- Scope: read-only analysis only. No code was fixed, no model weights downloaded, no dependency installed, nothing pushed, tagged, or released.
- VoxLab side: local workspace tree `~/workspace/voice-studio/` (`backend/server.py`, `backend/parity.py`, `backend/clone.py`, `backend/qc.py`, `backend/llm.py`, `backend/device.py`, `app/index.html`, `AUDIT.md`, `PARITY.md`, `COMPETITOR_ANALYSIS.md`, `README.md`).
- Voicebox side: public MIT source, shallow clone at `~/workspace/voice-studio/_voicebox-source/` — `git clone --depth 1 https://github.com/jamiepine/voicebox.git`, commit `8af7efe` ("Merge pull request #1168 from jamiepine/prep/pr-1062"). Read-only; nothing from it was copied into VoxLab.
- Method: file:line comparison of the two trees. Every claim below cites a file. Anything not verified from a file is marked **unproven**.

## 0. Read this first: shipped v1.1.5 ≠ local tree

The user runs shipped VoxLab **v1.1.5** (release 2026-10-27, commit `ef111da`, 8 assets, per memory). This analysis read the **local workspace tree**, which is newer than v1.1.5 in places — and `PARITY.md` heads almost every post-v1.1.5 section "LOCAL ONLY, NOT pushed, NO tag, NO release". The shipped v1.1.5 contents were **not** re-verified from the remote in this task (per the read-only instruction, the `ishtiaquehasib/VoxLab` remote was not touched, and there is no local git repo for VoxLab to diff against).

That distinction matters, because the top of `PARITY.md` (A-Z frozen release gate, 2026-10-28) records that **v1.1.5 itself was broken on a fresh install**:

1. Main Generate 500: `parity._get_kokoro_onnx()` looked only in `output/` for `kokoro-v1.0.onnx` + `voices-v1.0.bin`, but the workflows never bundled them, and `requirements.txt` never listed `kokoro-onnx`/`onnxruntime` — so the ONNX fallback could never run in a frozen exe. KPipeline also failed (spacy tokenizer OverflowError). (`PARITY.md:1-18`)
2. Clone "reference not found in output/: kokoro_af_heart.wav": same missing bundled file. (`PARITY.md:5-7`)
3. Bare UI 500: the UI showed only a status code when generation failed. (`PARITY.md:5-7`)
4. The v1.1.5 CI smoke never generated audio, "which is why the 500 shipped". (`PARITY.md:14`)

So the user's report — "kaj e to hoy na" / output does not match — has **two layers**, and they must not be conflated:

- **Layer A (shipped v1.1.5): the app did not work at all after install** for the main flows. That is a packaging/bundling failure, not a voice-quality failure.
- **Layer B (even with Layer A fixed): the voice pipeline is a different, weaker pipeline** from Voicebox's. That is what the rest of this report is about.

## 1. Verdict — the single most likely cause of the output mismatch

There is no single line of code that explains it. The mismatch is a **stack of three output decisions**, in this order:

1. **Wrong default clone engine.** Voicebox's flagship clone is **Qwen3-TTS 1.7B Base** (`PyTorchTTSBackend.__init__` defaults to `"1.7B"`, `_voicebox-source/backend/backends/pytorch_backend.py:33,47-56`). VoxLab's flagship clone in v1 was **Chatterbox** (`AUDIT.md`: "Primary cloning engine: Chatterbox"), and the in-app clone route defaults to **Chatterbox Turbo** (`backend/parity.py:430-451` `_clone_with_engine` — `"chatterbox"` is the only alternative, Turbo is the fall-through default; `app/index.html:682` posts `engine:'chatterbox-turbo'`). Qwen3-TTS Base cloning exists in VoxLab only as a standalone test script (`test_qwen3.py`, 0.6B Base) — it is **not wired into any server or parity clone route**. Qwen CustomVoice (preset speakers, no reference audio) is not cloning at all.
2. **No voice-prompt pipeline.** Voicebox clones through `create_voice_prompt(audio_path, reference_text)` → cached prompt → `generate_voice_clone(text, voice_clone_prompt, language, instruct)` with a seed (`pytorch_backend.py:142-250`). VoxLab's clone path never asks for, transcribes, or stores a reference transcript, never caches a voice prompt, never combines prompts, and never passes a seed or an `instruct` to a Base clone (`backend/parity.py:430-479`, `backend/clone.py:17-27`).
3. **No output-conditioning pipeline in the main generate path.** Voicebox runs every generation through `generate_chunked` (800-char sentence/clause chunks, 50 ms crossfade) + per-engine `trim_tts_output` + runaway detection/retry + RMS normalisation to −20 dB with peak limiting at 0.85 (`_voicebox-source/backend/services/generation.py:55-116`, `backend/utils/chunked_tts.py:23,216-283`, `backend/utils/audio.py:11-43`). VoxLab's main `/api/generate` does a single call (sentence-split only when `pause_ms > 0`), joins with silence pauses, and peak-normalises to −3 dBFS only (`backend/server.py:292-434`, `backend/qc.py:normalize_audio_file`, docstring: "Loudness is peak-based only, not LUFS"). There is no `trim_tts_output`, no runaway detector, and no seed anywhere in VoxLab's generation paths (grep for `trim|runaway|seed` in `backend/server.py`, `backend/clone.py`, `backend/qc.py` returns only story-timeline trim).

Fixing only the model, or only the normalisation, will not close the gap. All three layers have to change together — see §9 "Fix first".

## 2. REA note — source reading beats REA here

Voicebox is MIT open source with its full source on GitHub (`jamiepine/voicebox`, `LICENSE` MIT in the clone). REA (`morluto/rea`) returns pseudocode, assembly, strings and evidence from a **binary**; here the source itself was read, which is strictly more accurate — exact parameter values, exact defaults, exact call order. REA would add almost nothing for the Python backend (source is present) and only marginal value for runtime tracing of the Tauri/Rust shell, whose source is also present (`_voicebox-source/tauri/src-tauri/src/`). REA was **not** run in this analysis, and it is **not needed** for the fix. What REA would *not* give: model weights, the Qwen/Chatterbox model behaviour itself, or a copy of Voicebox's code — and per VoxLab's standing no-copy rule, Voicebox code must not be copied verbatim into VoxLab anyway; cite files, re-implement the pipeline in VoxLab's own code.

## 3. Engine-by-engine comparison

### 3.1 Qwen3-TTS Base — the flagship clone (P0)

| | Voicebox | VoxLab |
|---|---|---|
| Default size | **1.7B** (`pytorch_backend.py:33`: `model_size="1.7B"`; map `1.7B → Qwen/Qwen3-TTS-12Hz-1.7B-Base`, `0.6B → …-0.6B-Base`, lines 47-56) | **0.6B Base, test-script only** (`test_qwen3.py:5`: `Qwen3TTSModel.from_pretrained("Qwen/Qwen3-TTS-12Hz-0.6B-Base", device_map="cpu", dtype=torch.float32)`). No 1.7B Base anywhere in a server route. |
| Clone call | `generate_voice_clone(text, voice_clone_prompt=prompt, language=…, instruct=instruct)` inside `torch.inference_mode()`, with `manual_seed(seed)` (`pytorch_backend.py:206-250`) | `test_qwen3.py:10-15`: `generate_voice_clone(text, language="English", ref_audio=…, ref_text=…)` — direct ref-audio call, no cached prompt, no seed, no instruct. And this script is not called by the server at all. |
| Voice prompt | `create_voice_prompt(audio_path, reference_text)` → `model.create_voice_clone_prompt(ref_audio, ref_text, x_vector_only_mode=False)`, **cached** by `(audio_path, reference_text)` key (`pytorch_backend.py:142-199`); `combine_voice_prompts` for multi-sample profiles (`:199-204`, `backend/backends/base.py:263-295`) | None. `_do_clone` (`parity.py:451-479`) validates the file (size/frames/peak only) and calls `_clone_with_engine` immediately. No `ref_text` field exists in the clone API/UI. No prompt cache. No combine. |
| Device/dtype | CPU: `torch.float32, low_cpu_mem_usage=False`; GPU: `device_map=device, torch.bfloat16` (`pytorch_backend.py:94-130`). Single HF cache root forced (`HF_HUB_CACHE`). | Qwen Base test: CPU float32 only (`test_qwen3.py:5-8`, comment "CPU float32 is required for Base models (float16 fails)"). Qwen CustomVoice in server: CPU float32 (`parity.py:1779-1782`). |
| Why it was dropped in VoxLab | — | `AUDIT.md` decision: Qwen3 0.6B clone was "equally perfect on transcript and marginally higher on the crude MFCC proxy (0.9984 vs 0.9981, i.e. noise), but it is quieter, needs float32 on CPU, and adds a 2.4 GB model for no measured gain". **Note the audit tested 0.6B only, with a synthetic Kokoro reference, one sentence, and an MFCC-cosine proxy that the audit itself calls crude/noise — it never tested the 1.7B, never tested a real human reference, and never tested delivery-instruct (`instruct`) output.** The "quieter" finding is exactly what Voicebox's RMS normalisation (§4.3) is designed to fix. |

### 3.2 Chatterbox Multilingual — VoxLab's primary (P0)

| | Voicebox | VoxLab |
|---|---|---|
| Generate params | Explicit per-language defaults: global `exaggeration=0.5, cfg_weight=0.5, temperature=0.8, repetition_penalty=2.0`; Hebrew `0.4 / 0.7 / 0.65 / 2.5` (`chatterbox_backend.py:154-169`); passed on every call with `language_id` + `seed` (`:204-231`) | **Library defaults — no parameters passed at all.** `backend/clone.py:17-27`: `model.generate(text, audio_prompt_path=ref_wav)`. No `exaggeration`, `cfg_weight`, `temperature`, `repetition_penalty`, `language_id`, or seed. |
| Reference handling | Prompt is `{ref_audio, ref_text}`; missing file only warns and continues with `ref_audio=None` (`chatterbox_backend.py:131-148, 195-199`) | File must exist and pass `_validate_audio_file` (non-empty, non-silent); no `ref_text` is ever collected (`parity.py:354-430`). |
| Post-processing | `engine_needs_trim` → `trim_tts_output` per chunk; runaway retry (§4) (`generation.py:97-105`, `backends/__init__.py:611-623`) | None in the clone/generate path (see §1.3). |

### 3.3 Chatterbox Turbo — VoxLab's in-app default clone (P0)

| | Voicebox | VoxLab |
|---|---|---|
| Generate params | `temperature=0.8, top_k=1000, top_p=0.95, repetition_penalty=1.2`, with seed (`chatterbox_turbo_backend.py:187-213`) | **No parameters.** `parity.py:1607-1643` `generate_turbo`: `_TURBO.generate(text=text, audio_prompt_path=ref)` — library defaults only. No seed, no temperature/top_k/top_p/repetition_penalty. |
| Paralinguistic tags | Only Turbo interprets `[laugh]`/`[sigh]` etc.; splitter never cuts inside a tag (`chunked_tts.py:44-46, _inside_bracket_tag`; `README.md:147-152`) | Tags **not tested** (`parity.py:103`: "paralinguistic tags not yet tested"). VoxLab's chunk splitter (`split_text_chunks`, `parity.py:1219-1290`) has no tag-awareness and defaults to 2000 chars, not 800. |
| RAM behaviour | Async load with lock, unload on size change (`backends/__init__.py:633-670`, `hume_backend.py`-style locks; `pytorch_backend.py:70-94` pattern) | **RAM guard + honest refusal**: `generate_turbo` refuses when free RAM < 2 GiB (`parity.py:1607-1643`); `_unload_heavy_models` frees other engines first. A-Z gate records same-session multi-engine loads **killing the server (SIGKILL, no error)** on 7.7 GiB (`PARITY.md:43-49`). Turbo is a ~4 GB model. |

### 3.4 LuxTTS (P1)

| | Voicebox | VoxLab |
|---|---|---|
| Prompt encode | `encode_prompt(prompt_audio, duration=5, rms=0.01)`, cached (`luxtts_backend.py:103-139`) | `encode_prompt(ref, rms=0.01, duration=min(8, ref_info.duration))` — **full 8 s reference** (`parity.py:1644-1671`) |
| Generate | `num_steps=4, guidance_scale=3.0, t_shift=0.5, speed=1.0, return_smooth=False`, 48 kHz (`luxtts_backend.py:166-185`) | `num_steps=8, speed=0.7`, 48 kHz (`parity.py:1664-1669`) — a lab-found recipe ("variant E") after the defaults dropped opening words (`PARITY.md:1282-1298`, `COMPETITOR_ANALYSIS.md` LuxTTS row). The two recipes have **never been A/B-listened against each other**; VoxLab's is tuned to one reference clip. |
| Shipped? | Yes, as an engine | **No, on a fresh install.** `luxtts_src/` is a gitignored test copy; `generate_luxtts` returns 503 "not bundled until vendored" without it (`parity.py:1644-1652`; `PARITY.md:19-24`). |

### 3.5 Qwen CustomVoice — preset speakers, not cloning (P1)

| | Voicebox | VoxLab |
|---|---|---|
| Default size | **1.7B** (`qwen_custom_voice_backend.py:61`: `model_size="1.7B"`); 9 preset speakers, `instruct` only passed when non-empty (`:162-204`) | **0.6B** (`parity.py:1762-1790`, `server.py:318-320`); 1.7B CustomVoice is a gated 503 `needs_download` when its cache is absent (`server.py:300-330`); only **Ryan** individually tested, other 8 speakers not generated (`parity.py:106`, `COMPETITOR_ANALYSIS.md`). |
| Instruct | Same `instruct` mechanism | Same mechanism, wired (`server.py:294-301` `qwen_style`) — this part matches. |

### 3.6 Qwen VoiceDesign (P1)

| | Voicebox | VoxLab |
|---|---|---|
| Status | Shipped, 1.7B only, `generate_voice_design(text, language, instruct)` (`qwen_voice_design_backend.py:50,168-223`; guards `hasattr(Qwen3TTSModel, "generate_voice_design")`, `:96-131`) | **Skeleton only.** `POST /api/parity/voice-design` returns `needs_download=true` until a real generation passes (`parity.py:109`, `:2879-2924`). Model ~4.54 GB, licence **not verified** on the HF card, and a hard torch conflict: `qwen-tts` needs `torch>=2.9.1`, VoxLab pins `torch==2.6.0` for `chatterbox-tts` (`parity.py:109`, `:2857-2897`). Needs an isolated env or a torch upgrade that re-proves Chatterbox. |

### 3.7 TADA / HumeAI (P1)

| | Voicebox | VoxLab |
|---|---|---|
| Default size | **1B** (`hume_backend.py:85`: `_get_model_path(model_size="1B")`); 3B is a size option; load is lock-guarded with unload-on-switch (`:95-130`) | **1B only** (`parity.py:1674-1760`); 3B download **disabled**, HF repo unconfirmed (`PARITY.md:405-419` model catalog). |
| Tokenizer | TADA hardcodes `meta-llama/Llama-3.2-1B` as tokenizer source; Voicebox's `_is_model_cached` checks model + codec + tokenizer all cached (`hume_backend.py:85-108`, comment at `:62-63` in the sed output) | Same gated-tokenizer 401 hit VoxLab: `PARITY.md:1140-1214` — generation succeeded once in the lab (4.04 s, exact transcript, via `tmp/run_tada_bf16.py`), but the **shipped path 503s** with the gated 401 + `tada_src/` not bundled (`PARITY.md:25-38`). CPU generation is ~928 s for one sentence (`parity.py:1755` note). |
| Load dtype | (not fully read — see §8 unproven) | LM-only `dtype=torch.bfloat16 + low_cpu_mem_usage=True`; global BF16 default breaks the float32 encoder; float32 LM init OOM-kills the 7.7 GiB VM (`README.md` TADA note; `parity.py:1700-1745`). |

### 3.8 Kokoro — fixed voices (P2 for output, P0 for shipping)

Both use Kokoro-82M at 24 kHz with `speed=1.0` (`_voicebox-source/backend/backends/kokoro_backend.py:36,242-299`; VoxLab `parity.py:697-724` `kokoro.create(text, voice, speed=1.0, lang=…)` and `server.py:421-434`).

Differences:

- **Trim:** Voicebox trims Kokoro's padding — "~0.3 s before and ~0.7 s after speech" — via `trim_tts_output(…, max_internal_silence_ms=None)` (`kokoro_backend.py:292-299`). VoxLab's Kokoro paths (KPipeline in `server.py:421-434`, ONNX in `parity.py:697-724`) apply **no trim**; the only trim in VoxLab is story-timeline trim. Untrimmed pads accumulate at every sentence boundary when `pause_ms` is used.
- **KPipeline failure:** VoxLab's KPipeline dies on a spacy tokenizer OverflowError in the shared venv, so main Generate falls back to ONNX (`server.py:421-479`, `PARITY.md:382-404`). The ONNX route is the one that shipped broken in v1.1.5 (§0).
- **Voice count:** Voicebox advertises 50 curated preset voices; VoxLab's `/api/voices` returns 19 (11 Kokoro + 8 Bengali, `PARITY.md:25-38`). **Unproven** whether the 11-vs-50 gap is a real voice-list gap or a UI-counting difference — not verified in this task.

## 4. Generation pipeline — where the audible difference is made

### 4.1 Long-form chunking (P0)

- **Voicebox:** `backend/utils/chunked_tts.py` — `DEFAULT_MAX_CHUNK_CHARS = 800`, `crossfade_ms = 50` (defaults, `:23,216-283`); splitter priority sentence-end → clause → whitespace → hard cut, with abbreviation handling (`Dr.`, `Mr.`, decimals) and paralinguistic-tag atomicity (`:44-46, _find_last_sentence_end`); per-chunk seed `seed + i` so output is deterministic (`generate_chunked`). Settings defaults are the same numbers in the API model: `max_chunk_chars=800, crossfade_ms=50, normalize=True` (`backend/models.py:93-99,327-329`).
- **VoxLab:** the *settings* claim the same numbers — `_read_settings` defaults `auto_chunk_limit: 800, chunk_crossfade_ms: 50` (`parity.py:1993-1999`) — but **main `/api/generate` never uses them**. It generates the whole text in one call unless `pause_ms > 0`, in which case it sentence-splits and joins with *silence* (`join_with_pauses`, `qc.py:36-51`), not a crossfade. The only real chunker, `split_text_chunks` (`parity.py:1219-1290`), defaults to **2000** chars, splits on `. ! ? …` and Bengali danda only (no abbreviation/decimal handling, no tag-awareness), and is used by `auto_chunk_text` (text-only, synthesises nothing, `:1292-1296`) and the story builder — not by main generate. Long text therefore goes to the model in one shot, which is exactly the regime where Chatterbox/Qwen drift, hallucinate trailing noise, and lose prosody consistency.

### 4.2 Trim + runaway handling (P0)

- **Voicebox:** `trim_tts_output` (per-frame RMS, −40 dB threshold, 200 ms min silence, 30 ms fade, `backend/utils/audio.py:150-243`) is applied per chunk for engines flagged `engine_needs_trim`; `has_tts_runaway` (speech → ≥2 s internal silence → more output = missed EOS / hallucination, `audio.py:113-149`) triggers a **retry with the text halved, up to 2 retries** (`chunked_tts.py:244-283`, `MAX_RUNAWAY_RETRIES = 2`). `generation.py:97-105` wires both per engine.
- **VoxLab:** neither exists in any generation path (grep §1.3). The consequence is audible: untrimmed trailing noise/silence and hallucinated tails survive into the shipped file, and there is no retry — a bad chunk is the final output.

### 4.3 Loudness / normalisation (P0)

- **Voicebox:** `normalize_audio(audio, target_db=-20.0, peak_limit=0.85)` — **RMS-based**: scale to target RMS, then clip at 0.85 (`backend/utils/audio.py:11-43`). Applied on generate and regenerate (`generation.py:114-116,341-342`); the profile/speak path defaults `normalize=True` (`:280-293`). Reference-audio combining also normalises (`base.py:272-295`). Every engine therefore lands at the same perceived loudness.
- **VoxLab:** `normalize_audio_file(path, target_peak_db=-3.0)` — **peak-only** (`qc.py:normalize_audio_file`; docstring admits "Loudness is peak-based only, not LUFS"). Applied in `_finalise_generate` (`server.py:233-257`) when the settings toggle is on. Peak normalisation does not equalise perceived loudness across engines — and VoxLab's own head-to-head proves it: same sentence, Kokoro peak −3.64 dBFS / RMS −22.25 dBFS vs Qwen CustomVoice peak −7.82 dBFS / RMS −25.91 dBFS (`PARITY.md:382-404`, honest limit: "per-engine loudness normalisation is still an open gap"). This is a direct, measured contributor to "Voicebox sounds louder/fuller, VoxLab sounds quieter/thinner" even when the transcript is exact.
- **Reference-audio side:** Voicebox normalises reference audio on load/combine; VoxLab's `_validate_audio_file` checks only size/frames/peak ≠ 0 (`parity.py:354-397`) — a quiet or hot reference goes into the clone uncorrected, so clone quality varies with the user's recording level.

### 4.4 Seed / reproducibility (P2)

- **Voicebox:** `seed` is a first-class parameter on every backend `generate()`; `manual_seed(seed, device)` before inference; chunked generation uses `seed + i` per chunk; "regenerate" deliberately passes `seed=None` (`pytorch_backend.py:206-250`, `chatterbox_backend.py:204-219`, `generation.py:100-105`).
- **VoxLab:** no seed parameter exists in any generate/clone route or UI control. Two generations of the same text/voice are non-reproducible by construction, so "try again, it sounded better last time" can never be investigated or fixed.

### 4.5 Sample rates (P2)

Both are 24 kHz for Kokoro/Chatterbox/Qwen/TADA, 48 kHz for LuxTTS — no rate mismatch in the engines themselves. The gap is in **assembly**: Voicebox's chunker carries one `sample_rate` through concatenation; VoxLab's story timeline has to force `aresample=24000` because mixed-rate clips "play back stretched or fail acrossfade/amix rate negotiation" (`parity.py:1352-1361`). Main generate writes 24 kHz throughout (`server.py:421-434`), so this is a stories-path issue, not a main-output issue.

## 5. Clone flow — reference audio (P0)

| Step | Voicebox | VoxLab |
|---|---|---|
| Minimum reference | `validate_and_load_reference_audio`: **min 2.0 s**, max duration and min RMS checks (`backend/utils/audio.py:302-350`: `min_duration=2.0`, `min_rms=0.01`, "Audio too short (minimum 2.0 seconds)") | Any non-zero, non-silent file passes; only a **warning** if < 5 s for Turbo (`parity.py:451-479`); no min-RMS check, no max-duration check on the clone route (mic upload caps at 30 s, `parity.py:480-524`). |
| Reference transcript | **Required** — `reference_text` is a stored field on every profile sample (`profiles.py:236-290,539-660`); it is the input to `create_voice_clone_prompt`. | **Never collected.** No `ref_text` in any clone request, profile JSON (`_save_profile`, `parity.py:398-429`, stores only name/ref_wav/engine/timestamp), or UI field. This alone blocks the Qwen Base clone path, which requires `ref_text` (`test_qwen3.py:9-15`). |
| Prompt cache | Cached by `(audio_path, reference_text)`; combined multi-sample prompts supported (`pytorch_backend.py:142-204`, `base.py:263-295`) | None — every clone re-encodes from scratch (or, for Chatterbox, re-reads the file). |
| Capture sources | Upload / mic (30 s, live waveform) / **system capture via native Tauri Rust** — Windows WASAPI loopback (`tauri/src-tauri/src/audio_capture/windows.rs:8,37-38,102-104`), macOS/Linux equivalents in the same directory | Upload / mic upload (file only) / system capture via `sounddevice` WASAPI loopback + Linux PulseAudio monitor (`parity.py:144-275`). **Never live-tested**: VM `capture_info` reports `available: false`, capture POST 503s; Windows WASAPI is "setup docs only" (`COMPETITOR_ANALYSIS.md`). The user's own 44-byte silent capture bug (recording saved as success with 0 frames) was fixed only by validation, not by a working capture (`PARITY.md:260-296`). |

## 6. Transcription / dictation (P1)

| | Voicebox | VoxLab |
|---|---|---|
| Whisper | Backends for `base` (default STT size, `backends/__init__.py:484`), `large` (`openai/whisper-large-v3`), `turbo` (`openai/whisper-large-v3-turbo`) (`:43-44,504-511`) | `transcribe()` defaults to `large-v3-turbo`, falls back to `small` on failure (`parity.py:556-600`); QC (`qc_check`) defaults to `small` (`qc.py:qc_check`). Dictation is **wired** to Turbo per `PARITY.md:1112-1122`, but the global-shortcut path (`dictate_shortcut`, `parity.py:524-556`) **does not record by itself** — it transcribes a file that must already exist in `output/`/`output/uploads/`, then copies/pastes. |
| Global hotkey | Native Tauri: `ChordPicker`, `CapturePill`, `DictateWindow` components; macOS `Cmd+Opt`, Windows `Ctrl+Alt` (`_voicebox-source/app/src/components/`) | `backend/global_shortcut.py` (pynput + pyperclip) — implemented and headless-tested, **never live-tested on a real desktop/Windows**; `live_windows_test_pending=True` is returned by the endpoint itself (`parity.py:524-556`, `COMPETITOR_ANALYSIS.md`). |
| Refinement | Dedicated `backend/services/refinement.py` — filler/self-correction removal with technical-term preservation, as a service separate from persona LLM | `refine_transcript` via Qwen3-0.6B (`parity.py:819-850`), same 0.6B limits as §7. |

## 7. LLM personalities — Rewrite / Compose (P1)

| | Voicebox | VoxLab |
|---|---|---|
| Model sizes | **Qwen3 0.6B / 1.7B / 4B**, "sharing the TTS runtime (MLX on Apple Silicon, PyTorch elsewhere)" (`README.md:273-280`; `qwen_llm_backend.py:28-30,63`: default 0.6B, sizes selectable) | **0.6B only** (`backend/llm.py:MODEL_ID = "Qwen/Qwen3-0.6B"`; `model_cached`/`load_llm` hard-code it). 1.7B/4B exist only as entries in the model catalog (`PARITY.md:405-419`), never downloaded. |
| Quality | (not listening-tested here — unproven) | Honestly recorded as **minimal, sometimes verbatim**: 120-token cap, temperature 0.7, verbatim retry at 0.9, `verbatim=True` reported rather than hidden (`backend/llm.py:rewrite_llm`, `PARITY.md:25-38` "Rewrite (Qwen3-0.6B): llm_used=true … verbatim sometimes true"). The 0.6B thinking-block bug (120 tokens spent on `<think>`) was worked around with `enable_thinking=False` (`llm.py:_generate`). |
| Consequence | — | Persona Rewrite/Compose is the feature where the size gap is most audible: a 0.6B rewrite of a sentence is often the same sentence, so the "personality" is invisible in the output even when the TTS is fine. |

## 8. MCP / REST API, model management, runtime (P1–P2)

### 8.1 MCP / REST

- **Voicebox:** real FastMCP server mounted at `/mcp` (Streamable HTTP) + stdio shim (`backend/mcp_server/server.py:25-60`, `mcp_shim/`); tools `voicebox_speak`, `voicebox_transcribe`, list-profiles etc. (`mcp_server/tools.py:36-275`); REST mirror `POST /speak` (`routes/speak.py:1-19`); per-agent voice bindings with an admin surface (`routes/mcp_bindings.py`, `mcp_server/context.py:64-72`); every agent-initiated speech surfaces a visible pill.
- **VoxLab:** a single `POST /api/mcp/speak` (Kokoro ONNX + Parler/Edge/clone voices; `parity.py:697-724,851-950` and `COMPETITOR_ANALYSIS.md` MCP row). **No** `/mcp` endpoint, **no** `voicebox_transcribe`/`list-profiles`/`list-captures` equivalents, **no** per-agent bindings admin, **no** visible pill. MCP is a route, not a server.

### 8.2 Model management

- **Voicebox:** lazy load per engine with a load lock, unload on size change, single HF cache root, download progress reporting (`pytorch_backend.py:70-130`, `backends/__init__.py:633-670`, `utils/hf_progress.py`, `base.py:model_load_progress`). Model catalog is code (`backends/__init__.py:249-568`).
- **VoxLab:** model catalog of 20 models with `downloaded/needs_download/downloadable` status and a background `snapshot_download` endpoint (`PARITY.md:405-419`), but a fresh multi-GB download was **never run** — only the already-cached and error paths were tested. `luxtts_src/` and `tada_src/` are gitignored test copies, so those engines 503 on a fresh install (§3.4, §3.7). TADA 3B download is disabled (repo unconfirmed).

### 8.3 Runtime architecture — why VoxLab dies where Voicebox keeps going

- **Voicebox:** FastAPI + async backends; blocking inference in `asyncio.to_thread`; generation is a **background task** with status/progress via a task queue (`services/task_queue.py`, `services/generation.py:run_generation`); model loads are lock-guarded; GPU backends include CUDA, ROCm, DirectML, XPU, and MLX on Apple Silicon (`base.py:get_torch_device`, `pytorch_backend.py:39-41`).
- **VoxLab:** synchronous FastAPI handlers — a Qwen CustomVoice 0.6B generate took **~254 s wall** in one request (`PARITY.md:382-404`); no task queue, no progress reporting for generation. Same-process model juggling is manual (`_unload_heavy_models`, `parity.py:1545-1580`) and still **SIGKILLs the server** when a heavy model loads after others on 7.7 GiB (`PARITY.md:43-49`); the documented workaround is "restart VoxLab between heavy engines". The real fix (per-engine subprocess workers) is recorded as **unbuilt**. Device detection covers cuda/mps/DirectML/cpu (`backend/device.py:70-123`) — no MLX, no ROCm, no XPU path. Torch is pinned to **2.6.0** by `chatterbox-tts`, which directly blocks VoiceDesign (`qwen-tts` needs ≥2.9.1, §3.6).

## 9. What is NOT a gap (keep these)

- **Bengali is VoxLab-only and real.** Voicebox has no Bengali engine. VoxLab's Parler Arjun won the user's own listening test, and Edge presets (Nabanita, Pradeep, Tanishaa, Bashkar) + 6 Parler speakers are wired (`README.md` Languages/Engines; `backend/bengali.py`). Caveat: Edge MP3 was **never proven on this VM** (TLS failure to `speech.platform.bing.com`, `PARITY.md:25-38`), and Parler is an honest 503 + install flow in the frozen build — so Bengali is a differentiator in code, not yet a proven differentiator on the user's PC.
- **Effects list is comparable on paper.** VoxLab's `apply_effect` covers speed, volume, pitch, delay, chorus, compressor, low/high-pass, EQ, plus real convolution reverb (`parity.py:1080-1195`). Voicebox's 8 effects are Pedalboard-based (`_voicebox-source/backend/utils/effects.py:1-60,258-342`; `README.md:160-165`). Different engines (ffmpeg vs Pedalboard), same feature names — whether they *sound* the same is **unproven** (no A/B listening test exists).
- **Stories timeline exists in code.** VoxLab's `build_story_timeline` supports trim/start/volume/mix + sequence crossfade (`parity.py:1299-1417`); Voicebox's stories service supports create/list/trim/split/volume/reorder/chapters/export (`services/stories.py:43-964`). VoxLab has no multi-track timeline *editor UI* per `COMPETITOR_ANALYSIS.md` — the gap is UI/editor, not the audio assembly.
- **Kokoro preset generation matches** in engine and sample rate (§3.8) — modulo the trim and KPipeline-fallback issues.

## 10. Prioritised gaps

### P0 — output quality / the app not working (fix before anything else)

1. **Ship the frozen-gate fixes (Layer A).** Bundle `kokoro-v1.0.onnx` + `voices-v1.0.bin` + `kokoro_af_heart.wav`, add `kokoro-onnx`/`onnxruntime` to the frozen build, include `faster-whisper`. Without this, main Generate and Clone fail on a fresh install — no voice work matters. Evidence: `PARITY.md:1-38`.
2. **Make Qwen3-TTS 1.7B Base the flagship clone; keep 0.6B as fallback.** Wire `create_voice_prompt` (reference audio + Whisper-transcribed `ref_text`, cached) → `generate_voice_clone(…, instruct, seed)` into the clone route; CPU float32, GPU bf16. Do not ship it as a selectable-but-503 engine. Evidence: §3.1.
3. **Wire the Voicebox-style generation pipeline into main `/api/generate` for every engine:** 800-char sentence/clause chunking (abbreviation- and tag-aware) → per-chunk generate with `seed + i` → `trim_tts_output` → runaway detect + halve-and-retry (max 2) → 50 ms crossfade concat → **RMS normalise to −20 dB, peak-limit 0.85** (replacing peak-only −3 dBFS). Evidence: §4.1–4.3.
4. **Pass explicit generation parameters instead of library defaults:** Chatterbox `exaggeration/cfg_weight/temperature/repetition_penalty` (Voicebox global defaults as the starting point); Turbo `temperature/top_k/top_p/repetition_penalty`; LuxTTS defaults (Voicebox's or VoxLab's lab recipe — pick one after an A/B listen, not both silently). Evidence: §3.2–3.4.
5. **Collect and validate reference audio properly:** require a reference transcript (transcribe it with Whisper when the user does not supply one), enforce min duration/RMS, normalise the reference before cloning. Evidence: §5.

### P1 — missing features that change what the app can do

6. **Qwen CustomVoice 1.7B** as the real default (0.6B as fallback); test all 9 preset speakers, not just Ryan. Evidence: §3.5.
7. **VoiceDesign** — resolve the torch conflict (isolated env or torch upgrade with Chatterbox re-proof) or drop it from the UI honestly. Evidence: §3.6.
8. **TADA 1B shipped** (vendored source + gated-tokenizer handling that works offline from cache); 3B only after its repo is confirmed. Evidence: §3.7.
9. **LLM personalities at 1.7B (or 4B)** instead of 0.6B-only, sharing the TTS runtime; re-test Rewrite/Compose for verbatim rate. Evidence: §7.
10. **Real MCP server** (`/mcp`, `speak` + `transcribe` + list tools, per-agent bindings) instead of a single `/api/mcp/speak` route. Evidence: §8.1.
11. **System capture that works on the user's PC** — native WASAPI loopback on Windows (VoxLab's `sounddevice` path is unproven; Voicebox does it in Rust/Tauri). Live mic + global shortcut/paste need a user-PC test; they cannot be proven from this VM. Evidence: §5, §6.

### P2 — polish / architecture

12. **Per-engine subprocess workers / background task queue** so multi-engine sessions stop SIGKILLing the server; generation progress reporting. Evidence: §8.3.
13. **Kokoro trim** (0.3 s pre / 0.7 s post pads) in the main Kokoro path; fix or remove the KPipeline path that always falls back. Evidence: §3.8.
14. **Seed support** in every generate/clone route and in the UI, so output is reproducible. Evidence: §4.4.
15. **Model-download proof**: run a real fresh multi-GB download end-to-end; vendor LuxTTS/TADA sources or remove them from the fresh-install engine list. Evidence: §8.2.

## 11. Fix-first list (output parity, in order)

1. Ship frozen-gate fixes → main Generate + Clone work on a fresh install.
2. Qwen3-TTS 1.7B Base clone with voice-prompt cache + `ref_text` + `instruct` + seed.
3. Chunk (800) → trim → runaway-retry → crossfade (50 ms) → RMS normalise (−20 dB, peak 0.85) in main generate, all engines.
4. Explicit Chatterbox/Turbo/LuxTTS parameters (no library defaults).
5. Reference-audio validation + normalisation + transcript.
6. Then, and only then, A/B-listen the same sentence/reference on Voicebox vs VoxLab and record transcript, peak/RMS, and a listening verdict — the 2026-10-26 audit's MFCC proxy is not a substitute for that test.

## 12. What was not verified (unproven — do not present as fact)

- Shipped v1.1.5's exact file contents (remote not touched; local tree is newer and largely unpushed).
- Any listening comparison between Voicebox and VoxLab output (no audio was generated or listened to in this task; the 2026-10-26 audit's numbers are quoted from `AUDIT.md`, not re-run).
- Voicebox's TADA load dtype, MLX-backend parameters, and exact Whisper default size beyond what is cited (`backends/__init__.py:484` `model_size="base"` is the STT backend default in the config list; the user-facing default was not traced to the UI in this task).
- Whether VoxLab's 11 Kokoro voices vs Voicebox's 50 is a real voice gap or a counting difference.
- Whether VoxLab's ffmpeg effects sound the same as Voicebox's Pedalboard effects.
- Any performance claim on the user's Windows PC (GPU, RAM, WASAPI, mic, hotkey) — all of those need his machine.
- Star/download counts for either project (deliberately not used).

## 13. Sources (files only — no code copied)

- VoxLab: `~/workspace/voice-studio/backend/server.py`, `backend/parity.py`, `backend/clone.py`, `backend/qc.py`, `backend/llm.py`, `backend/device.py`, `backend/requirements.txt`, `app/index.html`, `AUDIT.md`, `PARITY.md`, `COMPETITOR_ANALYSIS.md`, `README.md`, `test_qwen3.py`.
- Voicebox: `~/workspace/voice-studio/_voicebox-source/` (commit `8af7efe`), principally `backend/backends/pytorch_backend.py`, `backend/backends/chatterbox_backend.py`, `backend/backends/chatterbox_turbo_backend.py`, `backend/backends/kokoro_backend.py`, `backend/backends/luxtts_backend.py`, `backend/backends/hume_backend.py`, `backend/backends/qwen_custom_voice_backend.py`, `backend/backends/qwen_voice_design_backend.py`, `backend/backends/qwen_llm_backend.py`, `backend/backends/__init__.py`, `backend/backends/base.py`, `backend/services/generation.py`, `backend/services/profiles.py`, `backend/services/stories.py`, `backend/services/effects.py`, `backend/services/settings.py`, `backend/services/transcribe.py`, `backend/utils/audio.py`, `backend/utils/chunked_tts.py`, `backend/utils/effects.py`, `backend/models.py`, `backend/mcp_server/server.py`, `backend/mcp_server/tools.py`, `tauri/src-tauri/src/audio_capture/windows.rs`, `README.md`.
