"""Whisper (faster-whisper) sur la voix FR : transcription + horodatage par mot.

Remplace whisper_run.py (mlx-whisper, réservé à Apple Silicon) sur cette machine. Sert de
contrôle indépendant à l'alignement CTC et, surtout, à savoir comment Suno a découpé le
morceau (répétitions, sections).

Écrit work/whisper_fr.json et affiche les segments.

    ./.venv/Scripts/python.exe fr_whisper.py [modele] [--prompt]
"""
import common
import json
import sys

import numpy as np
import soundfile as sf


def vocals16k():
    """Voix seule, 16 kHz mono, dans la timeline du mp3."""
    p = common.WORK / "vocals16k.wav"
    if not p.exists():
        y, sr = common.load_vocal_source("vocals", sr=16000)
        sf.write(p, (y / (np.abs(y).max() + 1e-9) * 0.99).astype(np.float32), sr)
    return p


def cuda_dlls():
    """Sous Windows, ctranslate2 (faster-whisper) charge cublas / cudnn dynamiquement et ne les
    trouve pas tout seul : les DLL CUDA livrées avec torch font l'affaire. À appeler AVANT
    d'importer faster_whisper."""
    import os
    import pathlib

    import torch
    lib = pathlib.Path(torch.__file__).parent / "lib"
    if lib.is_dir():
        os.add_dll_directory(str(lib))
        os.environ["PATH"] = str(lib) + os.pathsep + os.environ.get("PATH", "")


def main(tag="large-v3", prompt=False):
    cuda_dlls()
    from faster_whisper import WhisperModel

    text = " ".join(t for _, _, t in common.load_lyrics_src())
    init = ("Chanson française sur le doom de l'IA : P(doom), FOOM, shoggoth, shinigami, "
            "Chinchilla, basilique, Omega Point, RLHF, GPU, CDR, MLP, NVDA, Gato, Sydney, "
            "Ilya, Loom, paperclips, transformers. " + text) if prompt else text
    model = WhisperModel(tag, device="cuda", compute_type="float16")
    segments, info = model.transcribe(
        str(vocals16k()), language="fr", word_timestamps=True,
        initial_prompt=init[:1000], condition_on_previous_text=False, temperature=0.0,
        vad_filter=False, no_speech_threshold=None, hallucination_silence_threshold=None,
    )
    out = {"language": info.language, "duration": info.duration, "segments": []}
    for s in segments:
        out["segments"].append(dict(
            start=s.start, end=s.end, text=s.text,
            words=[dict(w=w.word, start=w.start, end=w.end, p=w.probability) for w in (s.words or [])],
        ))
        print(f"{s.start:7.2f} {s.end:7.2f} {s.text}", flush=True)
    suf = "_prompt" if prompt else ""
    # write_text() sans encoding ecrit en cp1252 sous Windows : le JSON doit rester de l'UTF-8
    (common.WORK / f"whisper_fr_{tag}{suf}.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
    print("ecrit", common.WORK / f"whisper_fr_{tag}{suf}.json", flush=True)


if __name__ == "__main__":
    tag = next((a for a in sys.argv[1:] if not a.startswith("-")), "large-v3")
    main(tag, "--prompt" in sys.argv)
