"""Segments Whisper ramenés à la grille de mesures : sert à écrire SECTION_BARS.

    ./.venv/Scripts/python.exe fr_bars.py
"""
import common
import json

BPM = 133.50
OFF = 0.18
P = 60 / BPM
BAR = 4 * P


def main():
    j = json.loads((common.WORK / "whisper_fr_large-v3.json").read_text(encoding="utf-8"))
    print(f"grid: {BPM} BPM, off {OFF}, {BAR:.4f} s/mesure")
    print("seg |  debut  |  fin   | mes debut | mes fin | debut mot | fin mot")
    for i, s in enumerate(j["segments"]):
        w = s["words"]
        a = w[0]["start"] if w else s["start"]
        b = w[-1]["end"] if w else s["end"]
        print(f"{i:3d} | {s['start']:7.2f} | {s['end']:6.2f} | {(a - OFF) / BAR:9.2f} | "
              f"{(b - OFF) / BAR:7.2f} | {a:9.2f} | {b:7.2f}  {s['text'][:52]}")


if __name__ == "__main__":
    main()
