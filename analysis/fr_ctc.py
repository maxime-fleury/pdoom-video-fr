"""Alignement mot à mot du chant FRANÇAIS : CTC forcé sur les émissions MMS_FA.

Même idée qu'align.py pour l'anglais, adaptée au français :

  * émissions MMS_FA (torchaudio) calculées sur la voix isolée par Demucs, une
    log-probabilité toutes les 20 ms, ramenées sur l'alphabet commun blank / a-z / ' ;
  * UNE passe de Viterbi sur toute la chanson, avec un jeton « garbage » (*) entre les
    lignes : il absorbe l'intro instrumentale, les ad-libs et l'outro, pendant que les
    mots chantés gagnent là où ils collent vraiment ;
  * chaque mot affiché est éclaté en sous-mots prononcés (pron_fr) : ce découpage donne
    les temps de syllabes (`syl`) que lisent les scènes.

Pourquoi deux passes
--------------------
Lâché sur trois minutes vingt, le Viterbi global dérive : à chaque respiration entre
deux lignes il place le début du texte un peu plus tard, et l'erreur s'accumule. La
première passe Whisper (fr_lyrics), elle, place au contraire les débuts SYSTÉMATIQUEMENT
trop tôt — c'est mesurable : sur « Je vois des éclats d'AGI », Whisper démarre à 15,78 s
alors que l'énergie de la voix isolée y est nulle (elle monte à 16,36 s, sur le temps).

Les deux erreurs vont dans des sens opposés et pour des raisons différentes. On prend
donc l'UNION des deux estimations comme fenêtre de chaque ligne, et le CTC arbitre à
l'intérieur, à la trame (20 ms). La fenêtre garantit qu'on ne peut pas dériver ; le CTC
choisit le meilleur placement acoustique dedans.

Sortie : data/lyrics.json et lyrics/lyrics.src.js (via fr_lyrics.write_src), plus un
contrôle ACOUSTIQUE (et non plus une comparaison à Whisper, qui mesure l'erreur de
Whisper) : où tombent les débuts de mots par rapport à l'enveloppe de la voix.

    ./.venv/Scripts/python.exe fr_ctc.py [--force] [--pad=0.30]
"""
import json
import sys

import numpy as np

import common

# la console Windows est en cp1252 : sans ça les accents et les flèches cassent l'affichage
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SR = 16000
HOP = 320                 # échantillons @16 kHz -> 20 ms par trame
FRAME = HOP / SR
ALPHA = ["-"] + list("abcdefghijklmnopqrstuvwxyz'")
AIDX = {c: i for i, c in enumerate(ALPHA)}
STAR = len(ALPHA)
MARGIN = 3.0              # le jeton * vaut (meilleur token − marge) : il gagne sur le bruit
FLOOR = -1e4
SIL = 0.10                # seuil de « c'est du silence » sur l'enveloppe RMS normalisée
MIN_RUN = 0.15            # calme minimal avant une attaque pour la compter comme telle


# ------------------------------------------------------------------ émissions
def emissions(source="vocals", chunk_s=20.0, ctx_s=3.0, force=False):
    """Log-probabilités [trames, ALPHA] de la voix isolée, mises en cache.

    Le calcul se fait par blocs qui se recouvrent : le modèle est convolutif, couper sec
    donnerait des faux bords à chaque raccord.
    """
    path = common.WORK / f"emission_fr_{source}.npy"
    if path.exists() and not force:
        return np.load(path)
    import torch
    import torchaudio

    bundle = torchaudio.pipelines.MMS_FA
    model = bundle.get_model(with_star=False)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device).eval()
    labs = list(bundle.get_labels(star=None))
    blank_cols = [labs.index("-")] + ([labs.index("|")] if "|" in labs else [])

    y, sr = common.load_vocal_source(source, sr=SR)
    assert sr == SR, sr
    y = y / (np.abs(y).max() + 1e-9)
    n_frames = len(y) // HOP
    out = np.full((n_frames, len(ALPHA)), FLOOR, np.float32)
    done = np.zeros(n_frames, bool)
    chunk, ctx = int(chunk_s * SR), int(ctx_s * SR)
    for s in range(0, len(y), chunk):
        a, b = max(0, s - ctx), min(len(y), s + chunk + ctx)
        x = torch.from_numpy(y[a:b].copy()).float()[None].to(device)
        with torch.inference_mode():
            em, _ = model(x)
            em = torch.log_softmax(em, dim=-1)[0].float().cpu().numpy()
        lo, hi, f0 = s // HOP, min(n_frames, (s + chunk) // HOP), a // HOP
        seg = em[lo - f0: hi - f0]
        block = np.full((len(seg), len(ALPHA)), FLOOR, np.float32)
        block[:, 0] = np.logaddexp.reduce(seg[:, blank_cols], axis=1)
        for i, c in enumerate(labs):
            k = c.lower()
            if k in AIDX and k != "-":
                block[:, AIDX[k]] = seg[:, i]
        block -= np.logaddexp.reduce(block, axis=1, keepdims=True)
        out[lo: lo + len(seg)] = block
        done[lo: lo + len(seg)] = True
        print(f"\r  émissions {100 * s / max(1, len(y)):5.1f} %", end="", flush=True)
    print(flush=True)
    if not done.any():
        raise RuntimeError("aucune trame calculée")
    last = int(np.where(done)[0].max())
    out[last + 1:] = out[last]
    np.save(path, out)
    return out


# ------------------------------------------------------------------ Viterbi
def build(lines_tokens, override=None):
    """Séquence cible : * [lettres du mot 0] * [lettres du mot 1] … *"""
    from pron_fr import pron
    tgt, index = [STAR], []
    for li, toks in enumerate(lines_tokens):
        for ti, tok in enumerate(toks):
            subs = (override or {}).get((li, ti)) or pron(tok)
            for si, sw in enumerate(subs):
                a = len(tgt)
                tgt.extend(AIDX[c] for c in sw if c in AIDX)
                index.append((li, ti, si, a, len(tgt)))
        tgt.append(STAR)
    return np.array(tgt, np.int64), index


def align(E, lines_tokens, override=None, line_windows=None, anchors=None, margin=None):
    """Viterbi global.

    line_windows : {li: (t0, t1)}  borne tous les caractères d'une ligne
    anchors      : {(li, ti, si): (t0, t1)}  borne les caractères d'un sous-mot
    """
    from ctcalign import _viterbi
    T = E.shape[0]
    tgt, index = build(lines_tokens, override)
    if len(tgt) < 2:
        raise RuntimeError("cible vide")
    Ex = np.concatenate([E, E.max(axis=1, keepdims=True) - (MARGIN if margin is None else margin)], axis=1)
    lo = np.zeros(len(tgt), np.int64)
    hi = np.full(len(tgt), T - 1, np.int64)
    for (li, ti, si, a, b) in index:
        if b <= a:
            continue
        w = (line_windows or {}).get(li)
        if w is not None:
            lo[a:b] = np.maximum(lo[a:b], int(w[0] / FRAME))
            hi[a:b] = np.minimum(hi[a:b], int(w[1] / FRAME))
        an = (anchors or {}).get((li, ti, si))
        if an is not None:
            lo[a:b] = np.maximum(lo[a:b], int(an[0] / FRAME))
            hi[a:b] = np.minimum(hi[a:b], int(an[1] / FRAME))
    path, score = _viterbi(Ex, tgt, lo, hi)
    tokpos = np.where(path % 2 == 1, (path - 1) // 2, -1)
    P = np.exp(Ex[np.arange(T), tgt[np.maximum(tokpos, 0)]])
    spans = {}
    for (li, ti, si, a, b) in index:
        fr = np.where((tokpos >= a) & (tokpos < b))[0]
        spans.setdefault((li, ti), []).append(
            None if len(fr) == 0 else (fr.min() * FRAME, (fr.max() + 1) * FRAME, float(P[fr].mean())))
    return spans, float(score), path, tgt


def word_times(spans, lines_tokens, n_sub=None):
    """(liste des [début, fin], confiances, sous-mots) dans l'ordre de la feuille."""
    from pron_fr import pron
    times, confs, syls = [], [], []
    for li, toks in enumerate(lines_tokens):
        for ti, tok in enumerate(toks):
            sp = spans[(li, ti)]
            if any(s is None for s in sp):
                times.append([None, None]); confs.append(0.0)
                syls.append(None if (n_sub is None or len(sp) != n_sub(tok)) else None)
                continue
            times.append([sp[0][0], sp[-1][1]])
            confs.append(float(np.mean([s[2] for s in sp])))
            syls.append([[round(s[0], 3), round(s[1], 3)] for s in sp] if len(sp) == len(pron(tok)) and len(sp) > 1 else None)
    return times, confs, syls


# ------------------------------------------------------------------ contrôle
def vocal_env():
    """Voix isolée et son enveloppe RMS normalisée (5 ms / trame)."""
    import librosa
    y, sr = common.load_stem("vocals", sr=22050)
    hop = 110
    r = librosa.feature.rms(y=y, frame_length=1024, hop_length=hop)[0]
    return y, sr, (r / (np.percentile(r, 99) + 1e-12)).astype(np.float64), sr / hop


def acoustic(env, fps, starts):
    """Pour chaque début de mot : silence juste avant, et écart à l'attaque qui suit.

    * `quiet` : longueur du silence qui colle au début du mot (0 s'il est en plein son).
      Un alignement trop en avance pose le mot dans le silence → `quiet` grandit.
    * `err` : seulement pour les mots qui DÉMARRENT une phrase (silence ≥ 100 ms devant),
      l'écart au premier échantillon audible qui suit. C'est l'attaque réelle : c'est là
      que se lit la précision en millisecondes.
    """
    quiet, lead, energy = [], [], []
    for s in starts:
        if s is None:
            continue
        i = min(len(env) - 1, max(0, int(s * fps)))
        j = i
        while j > 0 and env[j] <= SIL:          # marche arrière DANS le silence
            j -= 1
        quiet.append(env[i] < SIL)
        lead.append((i - j) / fps)
        energy.append(env[i])
    # attaques nettes de la voix : on entre dans du son après au moins `MIN_RUN` de calme
    att = []
    run = 0
    for i in range(len(env)):
        if env[i] <= SIL:
            run += 1
        else:
            if run / fps >= MIN_RUN:
                att.append(i / fps)
            run = 0
    return dict(med_lead=float(np.median(lead)), in_silence=100 * sum(quiet) / max(1, len(quiet)),
                mean_energy=float(np.mean(energy)), n=len(lead), attacks=att)


def whisper_times(lines_tokens):
    """Horodatages Whisper (première passe), appariés aux tokens par fr_lyrics.align."""
    import fr_lyrics
    words = fr_lyrics.vocal_mask([
        w for seg in json.loads((common.WORK / "whisper_fr_large-v3.json").read_text(encoding="utf-8"))["segments"]
        for w in seg["words"]])
    flat = [t for toks in lines_tokens for t in toks]
    idx, _, _ = fr_lyrics.align([fr_lyrics.norm(t) for t in flat], [fr_lyrics.norm(w["w"]) for w in words])
    return [None if i < 0 else (float(words[i]["start"]), float(words[i]["end"])) for i in idx]


def attacks(y, sr, env, fps):
    """Attaques de la voix : entrées dans le son, détectées de deux façons et fusionnées.

    * le flux spectral de librosa (c'est son métier), gardé seulement quand il suit un
      creux d'énergie — sinon on ramasse tous les phonèmes ;
    * les montées franches de l'enveloppe RMS, pour les cas où le flux spectral passe à
      côté (voix soutenue sans consonne d'attaque).
    """
    import librosa
    out = []
    for t in librosa.onset.onset_detect(y=y, sr=sr, hop_length=110, backtrack=True, units="time"):
        i = int(t * fps)
        before = env[max(0, i - int(0.30 * fps)):max(1, i - int(0.05 * fps))]
        if len(before) and env[i] >= 0.20 and before.min() <= 0.6 * env[i]:
            out.append(float(t))
    run = 0
    for i in range(len(env)):
        if env[i] <= SIL:
            run += 1
        else:
            if run / fps >= 0.10:
                out.append(i / fps)
            run = 0
    return np.unique(np.round(out, 3))


def line_bounds(ref, lines_tokens):
    """Bornes par ligne déduites de la passe Whisper : {li: (début, fin)}."""
    k, out = 0, {}
    for li, toks in enumerate(lines_tokens):
        rs = [ref[j] for j in range(k, k + len(toks)) if ref[j]]
        k += len(toks)
        if rs:
            out[li] = (min(r[0] for r in rs), max(r[1] for r in rs))
    return out


# ------------------------------------------------------------------ main
def main(force=False, pad=0.30):
    import fr_lyrics
    from pron_fr import pron

    sheet = common.load_lyrics_src()
    lines_tokens = [t.split() for _, _, t in sheet]
    flat = [t for toks in lines_tokens for t in toks]
    ref = whisper_times(lines_tokens)
    E = emissions(force=force)
    print(f"émissions {E.shape[0]} trames ({E.shape[0] * FRAME:.2f} s), {len(flat)} mots, "
          f"{len(build(lines_tokens)[0]) - 1} caractères", flush=True)

    # ---- passe 1 : CTC non contraint (borne haute de la dérive)
    free, score1, _, _ = align(E, lines_tokens)
    t1, _, _ = word_times(free, lines_tokens)
    # ---- ancrage du PREMIER mot de chaque ligne
    # Whisper donne une position approximative ; quand une attaque nette de la voix tombe
    # à moins de 0,7 s, c'est elle qui commande (l'énergie ne ment pas) ; sinon on garde
    # l'estimation du CTC libre. Le reste de la ligne est simplement borné.
    y, sr, env, fps = vocal_env()
    att = attacks(y, sr, env, fps)
    a = line_bounds(ref, lines_tokens)
    b = line_bounds([(t[0], t[1]) if t[0] is not None else None for t in t1], lines_tokens)
    win, anchors, n_att = {}, {}, 0
    order = sorted(set(a) | set(b))

    def anchor_of(li):
        """Début de la ligne : l'attaque vocale voisine si elle est crédible, sinon la plus
        précoce de deux estimations (Whisper démarre trop tôt, le CTC libre dérive vers
        l'arrière : leur minimum reste dans la bonne zone).

        Une attaque n'est retenue que dans [estimation − 0,5 s, estimation + 0,9 s] :
        plus tôt, c'est en général l'attaque interne du dernier mot de la ligne d'avant,
        et la prendre écrase cette ligne-là (mesuré sur « Piégé dans la Chinese room »).
        """
        w0 = a.get(li, b[li])[0]
        c0 = b.get(li, a[li])[0]
        near = float(att[int(np.argmin(np.abs(att - w0)))])
        if w0 - 0.5 <= near <= w0 + 0.9:
            return near, True
        return min(w0, c0), False

    for n, li in enumerate(order):
        anchor, hit = anchor_of(li)
        n_att += hit
        end = max(a.get(li, b[li])[1], b.get(li, a[li])[1])
        # une ligne ne peut pas empiéter sur l'ancre de la suivante : sans ça, le CTC
        # étale le dernier mot d'une ligne sur le silence et tasse tout ce qui suit.
        nxt = anchor_of(order[n + 1])[0] - 0.02 if n + 1 < len(order) else None
        hi = end + 0.30 if nxt is None else min(end + 0.30, nxt)
        win[li] = (anchor - 0.15, max(anchor - 0.10, hi))
        anchors[(li, 0, 0)] = (anchor - 0.15, anchor + 0.22)
    print(f"{len(win)} lignes · {n_att} ancrées sur une attaque vocale ({len(att)} attaques)", flush=True)

    # ---- passe 2 : CTC arbitré dans les fenêtres
    spans, score, path, tgt = align(E, lines_tokens, line_windows=win, anchors=anchors)
    times, confs, syls = word_times(spans, lines_tokens)
    print(f"score Viterbi {score:.1f}  ·  jeton * : "
          f"{100 * np.mean(np.isin(path, 2 * np.where(tgt == STAR)[0])):.1f} % des trames", flush=True)

    for k, (s, e) in enumerate(times):
        if s is None:
            times[k] = list(times[k - 1])
    for k, (s, e) in enumerate(times):
        times[k] = [s, max(e, s + 0.02)]

    # ---- finition : quand le début d'une ligne tombe dans le silence, on CONNAÎT l'attaque
    # vocale (le premier échantillon audible qui suit) : on cale le premier mot dessus.
    k = 0
    snapped = 0
    for li, toks in enumerate(lines_tokens):
        s = times[k][0]
        i = int(s * fps)
        if env[i] < SIL:
            while i < len(env) and env[i] <= SIL:
                i += 1
            if i < len(env) and abs(i / fps - s) <= 0.6:
                times[k] = [i / fps, max(times[k][1], i / fps + 0.05)]
                snapped += 1
        k += len(toks)
    print(f"{snapped} premiers mots calés pile sur l'attaque vocale", flush=True)

    for k in range(1, len(times)):
        if times[k][0] < times[k - 1][1]:
            mid = (times[k][0] + times[k - 1][1]) / 2
            times[k - 1][1] = mid
            times[k][0] = mid

    # ---- contrôle acoustique
    starts = [t[0] for t in times]
    new = acoustic(env, fps, starts)
    old = acoustic(env, fps, [r[0] if r else None for r in ref])
    print("\ncontrôle acoustique (voix isolée, RMS 5 ms) :", flush=True)
    print(f"  {'':36s}   CTC    Whisper", flush=True)
    print(f"  débuts posés dans le silence     {new['in_silence']:6.0f} %  {old['in_silence']:6.0f} %", flush=True)
    print(f"  silence médian collé au mot      {1000 * new['med_lead']:6.0f} ms {1000 * old['med_lead']:6.0f} ms", flush=True)
    print(f"  énergie moyenne au début du mot  {new['mean_energy']:6.2f}    {old['mean_energy']:6.2f}", flush=True)
    # les débuts de ligne qui tombent dans le silence : on sait alors où est l'attaque
    # vocale réelle, et c'est la seule mesure franche dont on dispose.
    ew, ec, n_sil = [], [], 0
    k = 0
    for li, toks in enumerate(lines_tokens):
        w0 = ref[k][0] if ref[k] else None
        if w0 is not None:
            i = int(w0 * fps)
            if env[i] < SIL:
                n_sil += 1
                while i < len(env) and env[i] <= SIL:
                    i += 1
                if i < len(env):
                    ew.append(1000 * (w0 - i / fps))
                    ec.append(1000 * (times[k][0] - i / fps))
        k += len(toks)
    print(f"  {n_sil:2d} débuts de ligne posés dans le silence → écart à l'attaque", flush=True)
    print(f"     Whisper : médiane {np.median(np.abs(ew)):5.0f} ms (il part trop tôt de "
          f"{abs(np.median(ew)):4.0f} ms)   ·   CTC : médiane {np.median(np.abs(ec)):5.0f} ms", flush=True)

    # le hook est slamé : chaque mot doit tomber sur un temps
    au = json.loads((common.DATA / "audio.json").read_text(encoding="utf-8"))
    beats = np.array(au["beats"])
    hooks = [k for k, t in enumerate(flat) if t.lower() in ("je", "monte") and k + 2 < len(flat)
             and flat[k + 1].lower() == "monte" and flat[k + 2].lower() == "mon"]
    off = [1000 * float(np.min(np.abs(beats - times[k][0]))) for k in hooks]
    if off:
        print(f"  écart des {len(hooks)} « Je » de hook au temps le plus proche : "
              f"médiane {np.median(off):.0f} ms  ·  max {max(off):.0f} ms", flush=True)

    # ---- écriture
    out_lines, k = [], 0
    for li, toks in enumerate(lines_tokens):
        ws = []
        for _ in toks:
            s, e = times[k]
            ws.append(dict(w=flat[k], start=round(s, 3), end=round(max(e, s + 0.02), 3),
                           conf=round(confs[k], 2), **({"syl": syls[k]} if syls[k] else {})))
            k += 1
        out_lines.append(dict(i=li, text=sheet[li][2], start=ws[0]["start"], end=ws[-1]["end"], words=ws))

    doc = dict(lines=out_lines, extras=[], notes=(
        "Paroles FR (adaptation). Alignement mot à mot : CTC forcé (Viterbi global) des émissions "
        "MMS_FA — torchaudio, trames de 20 ms — calculées sur la voix isolée par Demucs, avec un "
        "jeton « garbage » entre les lignes qui absorbe l'intro, les ad-libs et l'outro. Deux "
        "passes : la première sert à encadrer, la seconde arbitre chaque ligne dans l'union de "
        "l'estimation Whisper et de l'estimation CTC libre. Les mots sont éclatés en sous-mots "
        "prononcés (analysis/pron_fr.py), ce qui donne aussi les temps de syllabes (syl)."))
    (common.DATA / "lyrics.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nécrit", common.DATA / "lyrics.json", flush=True)
    for l in out_lines:
        print(f"{l['i']:2d} {l['start']:7.2f} {l['end']:7.2f}  {l['text']}", flush=True)
    fr_lyrics.write_src(doc)
    n_syl = sum(1 for l in out_lines for w in l["words"] if w.get("syl"))
    print(f"{n_syl} mots avec temps de syllabes", flush=True)
    return doc


if __name__ == "__main__":
    args = sys.argv[1:]
    pad = float(next((a.split("=", 1)[1] for a in args if a.startswith("--pad=")), 0.30))
    main(force="--force" in args, pad=pad)
