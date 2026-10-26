"""Parler generation worker, run ONLY under venv_parler.

Why a separate process: the main (mahbub) venv has transformers 4.57,
under which ParlerTTS no longer inherits GenerationMixin and generation
fails (see PARITY.md). venv_parler pins transformers 4.46.1 (the version
parler-tts 0.2.2 requires exactly) with a matched torch/torchaudio pair,
and the cached RXD03/indic-parler-tts-pretrained model loads there.

Usage: python backend/parler_cli.py "<bengali text>" <speaker> <out.wav>
Writes the WAV and prints "parler_ok seconds=... sr=..." on success.
Any failure exits non-zero with the real error on stderr — never a
fake or silent audio file.
"""
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])


def main(argv):
    if len(argv) != 4:
        print("usage: parler_cli.py <text> <speaker> <out.wav>", file=sys.stderr)
        return 2
    text, speaker, out_path = argv[1], argv[2], argv[3]
    from bengali import generate_parler_inprocess
    import soundfile as sf

    audio, sr = generate_parler_inprocess(text, speaker)
    sf.write(out_path, audio, sr)
    print(f"parler_ok seconds={len(audio) / sr:.2f} sr={sr}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
