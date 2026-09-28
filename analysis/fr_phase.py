"""Lève l'ambiguïté de demi-mesure de la grille par les changements d'harmonie.

La batterie ne fixe la phase qu'à une demi-mesure près (snare sur les temps 2 et 4). Les
changements d'accord, eux, tombent sur les contretemps de mesure : on agrège la chroma par
temps, on mesure la nouveauté à chaque frontière de temps, et on compare la moyenne de cette
nouveauté selon la classe de temps (indice mod 4). La classe gagnante est celle des
contretemps de mesure.

    ./.venv/Scripts/python.exe fr_phase.py
"""
import common
import json

import librosa
import numpy as np

SR = 22050


def main():
    au = json.loads((common.DATA / "audio.json").read_text(encoding="utf-8"))
    beats = np.array(au["beats"])
    y, sr = librosa.load(str(common.AUDIO), sr=SR, mono=True)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=1024, bins_per_octave=36)
    t = np.arange(chroma.shape[1]) * 1024 / sr
    # chroma par temps (moyenne de la trame précédant chaque temps)
    bt = np.clip(np.searchsorted(t, beats), 1, chroma.shape[1] - 1)
    beat_chroma = np.stack([chroma[:, max(0, b - 14):b + 2].mean(axis=1) for b in bt])
    nov = np.maximum(np.diff(beat_chroma, axis=0), 0).sum(axis=1)  # nouveauté à la frontière i
    idx = np.arange(len(nov))
    print("nouveauté harmonique moyenne par classe de temps (mod 4) :")
    means = []
    for p in range(4):
        m = nov[idx % 4 == p].mean()
        means.append(m)
        print(f"  temps {p} : {m:.4f}   (n={np.sum(idx % 4 == p)})")
    best = int(np.argmax(means))
    print(f"\nclasse gagnante : {best}")
    print("=> la grille d'analyze.py place les contretemps de mesure sur les temps "
          f"{'0 mod 4' if best == 0 else f'{best} mod 4'}")
    if best == 0:
        print("   (phase actuelle correcte, aucun décalage à appliquer)")
    else:
        print(f"   (il faut décaler la grille de {best} temps, ou de {best - 4} temps)")
    # contrôle décisif : les attaques de basse (une note de basse attaque presque toujours
    # sur un contretemps de mesure ou sur le "et" du temps 4)
    import analyze as A
    yb, _ = common.load_stem("bass", sr=44100)
    bt2, bdb = A.band_onsets(yb, 44100, 40, 250, win=0.012, min_gap=0.12, rel_db=8)
    keep = bdb > np.percentile(bdb, 60)  # les attaques fortes seules
    bt2 = bt2[keep]
    lab = np.round((bt2 - au["beats"][0]) / au["beat_period"]).astype(int)
    print(f"basse  par classe de temps mod 4 : {np.bincount(lab % 4, minlength=4).tolist()}"
          f"   ({len(bt2)} attaques)")
    fine = ((bt2 - au["beats"][0]) / au["beat_period"]) % 4
    hist, edges = np.histogram(fine, bins=16, range=(0, 4))
    print("  distribution fine (doubles croches) :", hist.tolist())

    # contrôle : où tombent les onsets de basse par classe
    ons = au["onsets"]
    for kind in ("kick", "snare", "hat"):
        ts = np.array([o[0] for o in ons[kind]])
        if len(ts) == 0:
            continue
        b = np.round((ts - au["beats"][0]) / au["beat_period"]).astype(int)
        h = np.bincount(b % 4, minlength=4)
        print(f"{kind:6s} par classe de temps mod 4 : {h.tolist()}")


if __name__ == "__main__":
    main()
