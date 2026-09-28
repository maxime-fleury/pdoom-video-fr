"""Sonde de structure pour la prise FR : grille tempo + profil d'énergie par mesure.

Sert à réécrire SECTION_BARS dans analyze.py (la carte du dépôt est en mesures et décrit
l'arrangement anglais). Sortie purement textuelle : tempo, candidats de grille, contrôle du
décalage des stems, puis un tableau par mesure (rms / voix / batterie / basse) et la liste des
segments où la voix est active.

    ./.venv/Scripts/python.exe fr_probe.py
"""
import common
import math
import sys

import librosa
import numpy as np
from scipy.signal import correlate as sp_correlate

import analyze as A

SR = A.SR


def stem_offset(mix, stems):
    """Décalage des stems Demucs par rapport au décodage gapless du mp3 (échantillons)."""
    s = sum(stems.values())
    a0, a1 = int(30 * SR), int(90 * SR)  # milieu du morceau : signal riche, pas l'intro
    a, b = mix[a0:a1], s[a0:a1]
    n = len(a)
    ac = sp_correlate(a, b, mode="full", method="fft")
    lag = int(np.argmax(ac) - (n - 1))
    return lag


def main():
    mix, _ = common.load_mix(SR)
    duration = len(mix) / SR
    stems = {n: common.load_stem(n, sr=SR)[0][: len(mix)] for n in ("vocals", "drums", "bass", "other")}
    for n in stems:
        if len(stems[n]) < len(mix):
            stems[n] = np.pad(stems[n], (0, len(mix) - len(stems[n])))
    print(f"duration {duration:.3f} s", flush=True)
    off_s = stem_offset(mix, stems)
    print(f"stem offset check: {off_s} samples ({off_s / SR * 1000:+.1f} ms) "
          f"vs STEM_OFFSET_SAMPLES={common.STEM_OFFSET_SAMPLES}", flush=True)

    # --- onset envelope, comme fit_grid
    hop = 64
    od = librosa.onset.onset_strength(y=librosa.resample(stems["drums"], orig_sr=SR, target_sr=22050),
                                      sr=22050, hop_length=hop // 2, lag=1, max_size=1)
    om = librosa.onset.onset_strength(y=librosa.resample(mix, orig_sr=SR, target_sr=22050),
                                      sr=22050, hop_length=hop // 2, lag=1, max_size=1)
    o = od / (np.percentile(od, 99) + 1e-9) + om / (np.percentile(om, 99) + 1e-9)
    ofps = 22050 / (hop // 2)
    t_axis = np.arange(len(o)) / ofps
    # max sur les voisins +-1 trame
    os_ = np.maximum(np.maximum(o, np.roll(o, 1)), np.roll(o, -1))
    print(f"onset frames {len(o)} at {ofps:.1f} fps", flush=True)

    def best_for(bpm, phase_step):
        P = 60.0 / bpm
        phases = np.arange(0, P, phase_step)
        n = int(duration / P) + 1
        idx = np.arange(n)
        grid = phases[:, None] + P * idx[None, :]
        vals = np.interp(grid.ravel(), t_axis, os_).reshape(grid.shape)
        s = vals.mean(axis=1)
        k = int(np.argmax(s))
        return float(s[k]), float(phases[k])

    cands = []
    for bpm in np.arange(60.0, 190.0, 0.1):
        s, off = best_for(bpm, 0.01)
        cands.append((s, bpm, off))
    cands.sort(reverse=True)
    print("top grilles (score, bpm, phase):", flush=True)
    seen = []
    for s, bpm, off in cands:
        if any(abs(bpm - b) < 3 for b in seen):
            continue
        seen.append(bpm)
        # affinage
        sf, off_f = best_for(bpm, 0.002)
        print(f"  {s:.4f}  {bpm:7.2f} BPM  off {off:.3f}   (affiné {sf:.4f} off {off_f:.3f})", flush=True)
        if len(seen) >= 6:
            break

    bpm, off = cands[0][1], cands[0][2]
    P = 60 / bpm
    print(f"\nmeilleur: {bpm:.2f} BPM  period {P:.4f} s  off {off:.4f} s  -> "
          f"{(duration - off) / P:.1f} temps, {(duration - off) / (4 * P):.1f} mesures", flush=True)

    # --- profil par mesure
    env = {}
    for k, x in [("rms", mix), ("vocal", stems["vocals"]), ("drums", stems["drums"]), ("bass", stems["bass"])]:
        e = A.frame_rms(x, SR)[: int(math.ceil(duration * A.FPS))]
        env[k] = A.smooth_env(e)
    for k in env:
        env[k] = env[k] / (np.percentile(env[k], 99) + 1e-12)

    def mean(k, t0, t1):
        a, b = int(t0 * A.FPS), int(t1 * A.FPS)
        return float(env[k][a:b].mean()) if b > a else 0.0

    print("\nmes |   t    |  rms  | voix  | drums | bass", flush=True)
    for bar in range(int((duration - off) / (4 * P)) + 1):
        t0 = off + 4 * P * bar
        t1 = t0 + 4 * P
        if t1 > duration:
            break
        print(f"{bar:3d} | {t0:6.2f} | {mean('rms', t0, t1):.3f} | {mean('vocal', t0, t1):.3f} "
              f"| {mean('drums', t0, t1):.3f} | {mean('bass', t0, t1):.3f}", flush=True)

    # --- segments où la voix est active (proxy des lignes chantées)
    v = env["vocal"]
    act = v > 0.10
    print("\nsegments voix (seuil 0.10) :", flush=True)
    i = 0
    segs = []
    while i < len(act):
        if act[i]:
            j = i
            gap = 0
            while j < len(act):
                if act[j]:
                    gap = 0
                else:
                    gap += 1
                    if gap > 30:
                        break
                j += 1
            segs.append((i / A.FPS, (j - gap) / A.FPS))
            i = j
        else:
            i += 1
    for a, b in segs:
        print(f"  {a:7.2f} - {b:7.2f}  ({b - a:5.2f} s)  pic {v[int(a * A.FPS):int(b * A.FPS)].max():.2f}", flush=True)
    print(f"{len(segs)} segments, total {sum(b - a for a, b in segs):.1f} s", flush=True)


if __name__ == "__main__":
    main()
