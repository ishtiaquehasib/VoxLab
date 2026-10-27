"""Self-contained Parler Bengali worker — NO imports from VoxLab code.

Why standalone: in a frozen (PyInstaller) build, backend/*.py sources
do not exist on disk (modules live as .pyc in the PYZ archive), so a
worker subprocess cannot `from bengali import ...`. This file is
bundled as data (--add-data) and run under an isolated Parler venv
(transformers 4.46.1, pinned by parler-tts 0.2.2), so it imports only
parler_tts / transformers / torch / soundfile.

Usage: python parler_worker.py "<bengali text>" <speaker> <out.wav>
Speaker is one of arjun, aditi, tapan, rashmi, arnav, riya.
Writes the WAV and prints "parler_ok seconds=... sr=..." on success.
Any failure exits non-zero with the real error on stderr — never a
fake file, never another voice substituted.
"""
import sys

PARLER_MODEL = "RXD03/indic-parler-tts-pretrained"
SPEAKERS = ["arjun", "aditi", "tapan", "rashmi", "arnav", "riya"]


def main(argv):
    if len(argv) != 4:
        print("usage: parler_worker.py <text> <speaker> <out.wav>", file=sys.stderr)
        return 2
    text, speaker, out_path = argv[1], argv[2].lower(), argv[3]
    if speaker not in SPEAKERS:
        print(f"unknown Parler speaker: {speaker}", file=sys.stderr)
        return 2
    from parler_tts import ParlerTTSForConditionalGeneration
    from transformers import AutoTokenizer
    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = ParlerTTSForConditionalGeneration.from_pretrained(PARLER_MODEL).to(device)
    tokenizer = AutoTokenizer.from_pretrained(PARLER_MODEL)
    desc_tok = AutoTokenizer.from_pretrained(model.config.text_encoder._name_or_path)
    name = speaker.capitalize()
    description = (
        f"{name} speaks at a moderate pace with a calm, narrative tone. "
        "The recording is clear, with a close sound and only minimal ambient noise."
    )
    desc_ids = desc_tok(description, return_tensors="pt").to(device)
    prompt_ids = tokenizer(text, return_tensors="pt").to(device)
    gen = model.generate(
        input_ids=desc_ids.input_ids, attention_mask=desc_ids.attention_mask,
        prompt_input_ids=prompt_ids.input_ids,
        prompt_attention_mask=prompt_ids.attention_mask,
    )
    audio = gen.cpu().numpy().squeeze()
    import soundfile as sf

    sf.write(out_path, audio, int(model.config.sampling_rate))
    print(f"parler_ok seconds={len(audio) / int(model.config.sampling_rate):.2f} "
          f"sr={int(model.config.sampling_rate)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
