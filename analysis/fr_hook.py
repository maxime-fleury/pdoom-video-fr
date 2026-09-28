"""Positions rythmiques des mots du hook ("Je monte mon P(doom)") et des fins de ligne.

Sert à lever l'ambiguïté de demi-mesure de la grille (la batterie ne fixe la phase qu'à une
demi-mesure près : snare sur les temps 2 et 4). Si le mot "doom" tombe sur un contretemps de
mesure, la phase d'analyze.py est la bonne.

    ./.venv/Scripts/python.exe fr_hook.py
"""
import common
import json

j = json.loads((common.WORK / "whisper_fr_large-v3.json").read_text(encoding="utf-8"))
au = json.loads((common.DATA / "audio.json").read_text(encoding="utf-8"))
P = au["beat_period"]
OFF = au["beats"][0]


def beatpos(t):
    x = (t - OFF) / P
    return x


def barpos(t):
    return beatpos(t) / 4


KEY = ("monte", "pindou", "pédo", "crétin", "pété", "m'étonne")


def main():
    print(f"grille: {au['bpm']} BPM, premier temps {OFF:.4f} s\n")
    for i, s in enumerate(j["segments"]):
        txt = s["text"].lower()
        if not any(k in txt for k in KEY):
            continue
        print(f"--- segment {i}  {s['start']:.2f}-{s['end']:.2f}  {s['text'][:60]}")
        for w in s["words"]:
            x = beatpos(w["start"])
            print(f"    {w['start']:7.2f} beat {x:7.3f} (mes {x / 4:6.3f}, "
                  f"pos dans la mesure {x % 4:5.2f})  {w['w']}")


if __name__ == "__main__":
    main()
