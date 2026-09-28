"""Paroles FR alignées mot à mot -> data/lyrics.json

Première passe : appariement global (programmation dynamique) des mots horodatés par Whisper
avec les tokens de lyrics/lyrics.src.js, puis interpolation des tokens non appariés.

Ce n'est plus la sortie utilisée par le clip : fr_ctc.py reprend ces horodatages comme
ancrage grossier et raffiné à la trame (20 ms) par CTC forcé sur les émissions MMS_FA.
Le présent module fournit aussi à fr_ctc l'appariement token <-> mot Whisper et l'écriture
de lyrics/lyrics.src.js.

Whisper se trompe sur le jargon (P(doom) -> « pindou », paperclips -> « flappeurs »,
Loom -> « Lou ») mais jamais sur l'ordre des lignes : l'appariement se fait donc sur la
position, avec une similarité de texte en bonus. C'est le même principe que le jeton
« garbage » de align.py.

Deuxième passe : fr_ctc.py (émissions CTC MMS_FA, comme align.py pour l'anglais).

    ./.venv/Scripts/python.exe fr_lyrics.py
"""
import common
import difflib
import json
import re
import sys
import unicodedata

import numpy as np

# Scores ENTIERS : la remontée du chemin compare des sommes, et des valeurs comme 1.2 ou -0.4
# ne sont pas exactes en flottant binaire — un == qui échoue donne un chemin faux.
# Un désappariement doit coûter plus cher que de laisser un trou simple (mais moins cher que
# deux trous, sinon le jargon que Whisper déforme — P(doom) -> « pindou » — ne s'apparierait
# plus du tout par la position).
MATCH, CLOSE, FUZZ, BAD = 10, 6, 5, -8
GAP = -5


def norm(s):
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", s)


def sim(a, b):
    if not a or not b:
        return BAD
    if a == b:
        return MATCH
    if len(a) >= 3 and len(b) >= 3 and (a.startswith(b) or b.startswith(a)):
        return CLOSE
    if difflib.SequenceMatcher(None, a, b).ratio() >= 0.6:
        return FUZZ
    return BAD


def align(tokens, words):
    """Needleman-Wunsch : tokens (lignes) x words (Whisper). Renvoie l'index de mot par token."""
    n, m = len(tokens), len(words)
    # score[i][j] = meilleur score en alignant tokens[:i] et words[:j]
    S = np.full((n + 1, m + 1), -10 ** 9, dtype=np.int64)
    S[0, 0] = 0
    S[:, 0] = np.arange(n + 1) * GAP
    S[0, :] = np.arange(m + 1) * GAP
    W = np.array([[sim(t, w) for w in words] for t in tokens], dtype=np.int64)
    for i in range(1, n + 1):
        row, prev = S[i], S[i - 1]
        for j in range(1, m + 1):
            a, b, c = prev[j] + GAP, row[j - 1] + GAP, prev[j - 1] + W[i - 1, j - 1]
            best = c
            if a > best:
                best = a
            if b > best:
                best = b
            row[j] = best
    # remontée
    i, j = n, m
    idx = [-1] * n
    while i > 0 or j > 0:
        if i > 0 and j > 0 and S[i, j] == S[i - 1, j - 1] + W[i - 1, j - 1]:
            idx[i - 1] = j - 1
            i -= 1
            j -= 1
        elif i > 0 and S[i, j] == S[i - 1, j] + GAP:
            i -= 1
        else:
            j -= 1
    # contrôle : le score du chemin reconstruit doit égaler celui du DP (sinon la remontée est fausse)
    matched = sum(1 for x in idx if x >= 0)
    path_score = sum(W[i, idx[i]] if idx[i] >= 0 else GAP for i in range(n)) + (m - matched) * GAP
    if path_score != int(S[n, m]):
        print(f"ATTENTION : score du chemin {path_score} != score du DP {int(S[n, m])}", flush=True)
    return idx, int(S[n, m]), W


HEADER = '''// Adaptation française de "I'm Upping My P(doom)" — paroles originales d'osmarks et MusicPerson
// (voir les Credits du README). Traduction non officielle, faite pour ce fork.
//
// Le texte doit rester IDENTIQUE à ce qui a été donné à Suno (suno-lyrics.txt) : l'alignement
// forcé cherche exactement ces mots dans le chant.
//
// Les temps ci-dessous sont GÉNÉRÉS par analysis/fr_ctc.py à partir de l'alignement mot à mot
// (data/lyrics.json) : ne pas les retoucher à la main, relancer le script.
//
// Deux passages ne figurent pas dans la version anglaise : la reprise "Oh oh, l'orthogonality
// thesis" que Suno a ajoutée dans le refrain 3, et l'outro où le hook est chanté seul quatre fois.
//
// Contrainte à ne pas casser : le hook fait 4 mots (Je / monte / mon / P(doom)), un par slam.
//
// ATTENTION : common.load_lyrics_src() extrait tout ce qui se trouve entre le tout premier
// crochet ouvrant et le tout dernier crochet fermant du fichier, et le parse comme du JSON.
// Aucun crochet (ni ouvrant ni fermant) ne doit donc apparaitre au-dessus du tableau.

const LY = '''


def write_src(doc):
    """Réécrit lyrics/lyrics.src.js avec les temps alignés (la feuille de paroles reste la même)."""
    body = "\n".join(
        f'[{l["start"]:.2f}, {l["end"]:.2f}, {json.dumps(l["text"], ensure_ascii=False)}],'
        for l in doc["lines"])
    body = body.rstrip(",")
    (common.LYRICS_SRC).write_text(f"{HEADER}[\n{body}\n];\n", encoding="utf-8")
    print("écrit", common.LYRICS_SRC, flush=True)


def vocal_mask(words):
    """Garde les mots réellement chantés : Whisper invente parfois du texte sur un silence
    (ici un « Sous-titrage ST' 501 » à la fin). On teste l'énergie de la voix isolée."""
    import librosa
    y, sr = common.load_stem("vocals", sr=22050)
    hop = 110  # 5 ms
    rms = librosa.feature.rms(y=y, frame_length=1024, hop_length=hop, center=True)[0]
    rms = rms / (np.percentile(rms, 99) + 1e-12)

    def act(a, b):
        # max local, fenêtre élargie : Whisper place souvent le début d'un mot juste avant
        # l'attaque réelle, donc la moyenne sur le mot seul rejetterait de vrais mots chantés.
        i = max(0, int((a - 0.3) * sr / hop))
        j = min(len(rms), max(int((b + 0.3) * sr / hop), i + 1))
        return float(rms[i:j].max())

    keep = [w for w in words if act(w["start"], w["end"]) > 0.10]
    dropped = [w for w in words if w not in keep]
    if dropped:
        print("mots ignorés (silence) :", [(round(w["start"], 2), w["w"]) for w in dropped][:12], flush=True)
    return keep


def main(write=True):
    wj = json.loads((common.WORK / "whisper_fr_large-v3.json").read_text(encoding="utf-8"))
    words = vocal_mask([w for seg in wj["segments"] for w in seg["words"]])
    sheet = common.load_lyrics_src()
    lines = [[(li, ti, t) for ti, t in enumerate(text.split())] for li, (_, _, text) in enumerate(sheet)]
    tokens = [tok for ln in lines for _, _, tok in ln]
    ntok = [norm(t) for t in tokens]
    nword = [norm(w["w"]) for w in words]
    idx, score, W = align(ntok, nword)
    print(f"{len(tokens)} tokens, {len(words)} mots Whisper, score {score}", flush=True)

    # temps par token, puis interpolation des non appariés
    times = [[None, None] for _ in tokens]
    for k, wi in enumerate(idx):
        if wi >= 0:
            times[k] = [float(words[wi]["start"]), float(words[wi]["end"])]
    # bornes : premier mot apparié du début, dernier de la fin
    known = [k for k in range(len(tokens)) if times[k][0] is not None]
    for k in range(known[0]):
        times[k] = [times[known[0]][0], times[known[0]][0]]
    for k in range(known[-1] + 1, len(tokens)):
        times[k] = [times[known[-1]][1], times[known[-1]][1]]
    for a, b in zip(known, known[1:]):
        if b == a + 1:
            continue
        # Placement vers l'arrière depuis le mot apparié suivant : les tokens manquants se
        # collent juste avant lui. Étaler sur tout l'intervalle ferait démarrer une ligne dans
        # le silence qui précède (transition entre deux sections, par ex.).
        cur = times[b][0]
        for k in range(b - 1, a, -1):
            d = min(0.9, max(0.15, len(tokens[k]) * 0.05))
            st = cur - d
            if st < times[a][1]:
                st = times[a][1]
            times[k] = [st, cur]
            cur = st
    # monotonie stricte
    for k in range(1, len(tokens)):
        if times[k][0] < times[k - 1][1]:
            mid = (times[k][0] + times[k - 1][1]) / 2
            times[k - 1][1] = mid
            times[k][0] = mid

    out_lines = []
    k = 0
    tot_sim, n_match = 0.0, 0
    for li, ln in enumerate(lines):
        ws = []
        for _, _, tok in ln:
            a, b = times[k]
            wi = idx[k]
            conf = float(words[wi]["p"]) if wi >= 0 else 0.0
            ws.append(dict(w=tok, start=round(a, 3), end=round(max(b, a + 0.02), 3), conf=round(conf, 2)))
            if wi >= 0:
                tot_sim += W[k, wi] / MATCH
                n_match += 1
            k += 1
        out_lines.append(dict(i=li, text=sheet[li][2], start=ws[0]["start"], end=ws[-1]["end"], words=ws))

    # rapport : lignes dont peu de mots ont été appariés
    print(f"appariés {n_match}/{len(tokens)} tokens, similarité moyenne {tot_sim / max(1, n_match):.2f} "
          f"(1 = identique, 0.5 = approximatif, < 0 = appariement de position)", flush=True)
    k = 0
    for li, ln in enumerate(lines):
        miss = [tokens[k + i] for i in range(len(ln)) if idx[k + i] < 0]
        k += len(ln)
        if miss:
            print(f"  ligne {li:2d} non appariés : {miss}   | {sheet[li][2][:44]}", flush=True)
    print("lignes par ordre croissant de début :", all(out_lines[i]["start"] <= out_lines[i + 1]["start"] for i in range(len(out_lines) - 1)), flush=True)

    doc = dict(lines=out_lines, extras=[], notes=(
        "Paroles FR (adaptation). Alignement mot à mot : appariement global des mots horodatés "
        "de faster-whisper large-v3 (voix isolée, langue fr) sur lyrics/lyrics.src.js, puis "
        "interpolation des tokens non appariés. Première passe seulement — c'est fr_ctc.py "
        "(CTC MMS_FA) qui produit data/lyrics.json."))
    (common.DATA / "lyrics.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print("écrit", common.DATA / "lyrics.json", flush=True)
    if write:
        print("\nlignes alignées :", flush=True)
        for l in out_lines:
            print(f"{l['i']:2d} {l['start']:7.2f} {l['end']:7.2f}  {l['text']}", flush=True)
        write_src(doc)
    return doc


if __name__ == "__main__":
    main()
