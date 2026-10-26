"""VoxLab real LLM personalities — Qwen3-0.6B, local only.

Model: Qwen/Qwen3-0.6B (chat model, ~0.6B params, float32).
Device is auto (cuda -> mps -> cpu, see backend/device.py);
VOXLAB_DEVICE overrides. GPU paths are untested on a real GPU —
this VM has none, so only the CPU path is live-tested here.
It is NOT loaded at import time. load_llm() downloads/loads it on
first use (the 0.6B checkpoint only — no larger model), and any
failure is returned honestly; callers must fall back to the
template path with llm_used=False, never invent an LLM output.

Rewrite/Compose prompts are deliberately small: a persona rewrite
must preserve the user's meaning, a compose must stay on topic.
Generation is capped (max 120 new tokens) so CPU runs stay short.
"""
import os

MODEL_ID = "Qwen/Qwen3-0.6B"

_model = None
_tokenizer = None
_load_error = None


def model_cached():
    """True only if a Qwen3-0.6B snapshot is already in the HF cache."""
    try:
        from huggingface_hub import scan_cache_dir
        for repo in scan_cache_dir().repos:
            if repo.repo_id == MODEL_ID and repo.size_on_disk > 0:
                return True
    except Exception:
        pass
    # Fallback: directory name check, no network involved.
    cache = os.path.expanduser("~/.cache/huggingface/hub")
    return os.path.isdir(os.path.join(cache, "models--Qwen--Qwen3-0.6B"))


def load_llm():
    """Load (or return the cached) Qwen3-0.6B. Returns (model, tok, err).

    Device auto-detected (cuda -> mps -> cpu); an OOM while loading
    on GPU retries once on CPU instead of caching a permanent error.
    float32 is kept on GPU too — no fp16 quality risk for a 0.6B model.
    """
    global _model, _tokenizer, _load_error
    if _model is not None:
        return _model, _tokenizer, None
    if _load_error is not None:
        return None, None, _load_error
    from device import get_device, is_oom_error
    device = get_device()
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        _tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
        # No device_map: that requires the `accelerate` package, which
        # is not a VoxLab dependency (proven 2026-10-27: load failed
        # with "device_map ... requires accelerate"). Load on CPU
        # memory, then .to(device) — same result, no extra dependency.
        _model = AutoModelForCausalLM.from_pretrained(
            MODEL_ID, torch_dtype=torch.float32)
        _model.to(device)
        _model.eval()
        return _model, _tokenizer, None
    except Exception as exc:  # noqa: BLE001 - OOM falls back to CPU once
        if device == "cpu" or not is_oom_error(exc):
            _load_error = str(exc)
            return None, None, _load_error
    try:
        import torch
        from transformers import AutoModelForCausalLM
        _model = AutoModelForCausalLM.from_pretrained(
            MODEL_ID, torch_dtype=torch.float32)
        _model.to("cpu")
        _model.eval()
        return _model, _tokenizer, None
    except Exception as exc:  # noqa: BLE001 - caller reports the real error
        _load_error = str(exc)
        return None, None, _load_error


def _is_verbatim(a, b):
    """True if two texts match after lowercasing / punctuation / space."""
    import re
    norm = lambda s: re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()
    return bool(norm(a)) and norm(a) == norm(b)


def _generate(system_prompt, user_prompt, max_new_tokens=120, temperature=0.7):
    model, tok, err = load_llm()
    if model is None:
        raise RuntimeError(f"Qwen3 LLM unavailable: {err}")
    import torch
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    # Qwen3 is a thinking model: its <think> block would eat the whole
    # token budget (proven 2026-10-26: 120 tokens spent on thinking,
    # answer truncated). Disable thinking so the budget goes to the
    # answer, and strip any think block defensively anyway.
    try:
        text = tok.apply_chat_template(messages, tokenize=False,
                                       add_generation_prompt=True,
                                       enable_thinking=False)
    except TypeError:
        text = tok.apply_chat_template(messages, tokenize=False,
                                       add_generation_prompt=True)
    inputs = tok([text], return_tensors="pt")
    try:
        _model_device = next(model.parameters()).device
        inputs = {k: v.to(_model_device) for k, v in inputs.items()}
    except Exception:
        pass
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=max_new_tokens,
                              temperature=temperature, top_p=0.9, do_sample=True,
                              pad_token_id=tok.eos_token_id)
    generated = out[0][inputs["input_ids"].shape[1]:]
    decoded = tok.decode(generated, skip_special_tokens=True).strip()
    import re
    decoded = re.sub(r"<think>.*?</think>", "", decoded, flags=re.DOTALL).strip()
    return decoded


def rewrite_llm(text, persona, persona_trait=None):
    """Persona Rewrite via Qwen3 LLM. Raises on any failure.

    Returns (rewritten_text, verbatim_bool). At 0.6B the first pass is
    sometimes verbatim despite the prompt, so a verbatim first pass is
    retried once at higher temperature with a stronger instruction;
    if it is still verbatim, the caller must report verbatim=True —
    never silently present a copy as a rewrite.
    """
    trait = f" ({persona_trait})" if persona_trait else ""
    system = (f"You are a voice persona named {persona}{trait}. Rewrite the user's "
              "text in that persona's voice, keeping the meaning, facts and "
              "names exactly the same, but CHANGE the wording — do not copy "
              "the input sentence verbatim. Reply with only the rewritten "
              "text, no explanation, no quotation marks around it.")
    first = _generate(system, text)
    if not _is_verbatim(first, text):
        return first, False
    retry_system = system + " This is important: use completely different words and sentence structure from the input."
    second = _generate(retry_system, text, max_new_tokens=150, temperature=0.9)
    return second, _is_verbatim(second, text)


def compose_llm(persona, topic, persona_trait=None):
    """Persona Compose via Qwen3 LLM. Raises on any failure."""
    trait = f" ({persona_trait})" if persona_trait else ""
    system = (f"You are a voice persona named {persona}{trait}. Write one short "
              "spoken line (at most 3 sentences) on the given topic, in "
              "that persona's voice. Reply with only the line, no "
              "explanation.")
    return _generate(system, f"Topic: {topic}")


def refine_transcript_llm(text):
    """Transcript refinement via Qwen3 LLM. Raises on any failure.

    Cleans filler words (um, uh, er), false starts and self-corrections
    and fixes punctuation, while preserving meaning, names, numbers
    and facts exactly — it must not add content, summarise, or invent
    words the speaker did not say. Returns the cleaned transcript.
    """
    system = ("You clean up a spoken transcript. Remove filler words "
              "(um, uh, er, you know), false starts and repeated "
              "self-corrections, and fix punctuation and capitalisation. "
              "Keep the meaning, names, numbers and facts exactly the "
              "same. Do NOT add new content, do NOT summarise, do NOT "
              "change what the speaker said. Reply with only the cleaned "
              "transcript, no explanation.")
    return _generate(system, text, max_new_tokens=200)
