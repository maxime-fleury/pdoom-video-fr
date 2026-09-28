"""Mot affiché -> graphie prononcée (romanisée) pour l'alignement CTC MMS_FA.

Même rôle que pron.py pour l'anglais. MMS_FA est entraîné sur du texte ROMANISÉ
(alphabet `a`-`z` + apostrophe) : on lui donne donc des lettres nues, accents retirés,
et on épelle les sigles / le jargon qu'il ne saurait pas deviner.

Le découpage en « sous-mots » est ce qui donne les temps de syllabes (`syl`) attendus
par les scènes : c'est aussi lui qui doit coller aux découpages codés en dur du clip
(`prompt-data.ts` : « ChatGPT, » en 4 jetons, « m'avale » en 2, « laisse-moi » en 2…).
"""
import re
import unicodedata

# Sigles, jargon et mots que le modèle ne prononcerait pas correctement.
PRON = {
    "P(doom)": "pe doum", "P(doom),": "pe doum",
    "ChatGPT,": "chat ge pe te",
    "AGI": "a ge i", "d'AGI": "a ge i",
    "NVDA": "en ve de a",
    "MLP": "em el pe",
    "CDR": "se de er",
    "GPU": "ge pe u",
    "RLHF": "er el ash ef",
    "FLOPs": "flops",
    "FOOM": "foum",
    "E": "eu",
    "Loom": "loume",
    "Ilya": "ilya",
    "Gato,": "gato",
    "Sydney,": "sidne",
    "Von": "von",
    "Chinchilla,": "chinchila",
    "Killswitch": "killsouitch",
}

# Prononciations alternatives à tester (le score d'alignement tranche).
ALT = {
    "P(doom)": ["pe doum", "pe doom", "p doum"],
    "E": ["eu", "e"],
    "FOOM": ["foum", "fum"],
    "Loom": ["loume", "loum"],
}


def fold(w: str) -> str:
    """Minuscules, accents et ligatures retirés, ponctuation réduite à `'` et `-`."""
    w = w.replace("’", "'").replace("œ", "oe").replace("Œ", "oe").replace("æ", "ae")
    w = unicodedata.normalize("NFD", w)
    w = "".join(c for c in w if not unicodedata.combining(c))
    w = w.lower().replace("’", "'")
    return re.sub(r"[^a-z'\-]", "", w)


def split(seq: str) -> list[str]:
    """Coupe aux apostrophes et aux traits d'union, en gardant le signe à gauche.

    « m'avale » -> ['m'', 'avale']   « laisse-moi » -> ['laisse-', 'moi']
    « Jusqu'à » -> ['jusqu'', 'a']   « l'orthogonality » -> ['l'', 'orthogonality']
    """
    out, cur = [], ""
    for ch in seq:
        if ch in "'-":
            cur += ch
            out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur:
        out.append(cur)
    return [p for p in out if re.search(r"[a-z]", p)]


def pron(token: str) -> list[str]:
    """Un mot affiché -> une liste de sous-mots faits de lettres (et d'apostrophes)."""
    if token in PRON:
        return PRON[token].split()
    d = fold(token)
    if d in PRON:
        return PRON[d].split()
    # un jeton sans lettre (« ? ») reste un jeton vide : il n'ajoute aucun caractère à
    # la cible CTC, et son temps est repris du voisin par fr_ctc.
    return split(d) or [""]


def variants(token: str) -> list[list[str]]:
    """Toutes les graphies à essayer, la principale en premier."""
    out = [pron(token)]
    for key, alts in ALT.items():
        if token in (key, fold(key)) or fold(token) == fold(key):
            out = [a.split() for a in alts]
            break
    return out


if __name__ == "__main__":
    import common
    for li, (_, _, t) in enumerate(common.load_lyrics_src()):
        print(f"{li:2d}", " | ".join(" ".join(pron(w)) for w in t.split()))
