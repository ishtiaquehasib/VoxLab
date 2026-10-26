"""VoxLab real LLM personalities — Qwen3-0.6B, local only.

Model: Qwen/Qwen3-0.6B (chat model, ~0.6B params, CPU float32).
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
    """Load (or return the cached) Qwen3-0.6B on CPU. Returns (model, tok, err)."""
    global _model, _tokenizer, _load_error
    if _model is not None:
        return _model, _tokenizer, None
    if _load_error is not None:
        return None, None, _load_error
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        _tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
        _model = AutoModelForCausalLM.from_pretrained(
            MODEL_ID, torch_dtype=torch.float32, device_map="cpu")
        _model.eval()
        return _model, _tokenizer, None
    except Exception as exc:  # noqa: BLE001 - caller reports the real error
        _load_error = str(exc)
        return None, None, _load_error


def _generate(system_prompt, user_prompt, max_new_tokens=120):
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
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=max_new_tokens,
                              temperature=0.7, top_p=0.9, do_sample=True,
                              pad_token_id=tok.eos_token_id)
    generated = out[0][inputs["input_ids"].shape[1]:]
    decoded = tok.decode(generated, skip_special_tokens=True).strip()
    import re
    decoded = re.sub(r"<think>.*?</think>", "", decoded, flags=re.DOTALL).strip()
    return decoded


def rewrite_llm(text, persona):
    """Persona Rewrite via Qwen3 LLM. Raises on any failure."""
    system = (f"You are a voice persona named {persona}. Rewrite the user's "
              "text in that persona's voice, keeping the meaning, facts and "
              "names exactly the same, but CHANGE the wording — do not copy "
              "the input sentence verbatim. Reply with only the rewritten "
              "text, no explanation, no quotation marks around it.")
    return _generate(system, text)


def compose_llm(persona, topic):
    """Persona Compose via Qwen3 LLM. Raises on any failure."""
    system = (f"You are a voice persona named {persona}. Write one short "
              "spoken line (at most 3 sentences) on the given topic, in "
              "that persona's voice. Reply with only the line, no "
              "explanation.")
    return _generate(system, f"Topic: {topic}")
