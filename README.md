# Je monte mon P(doom) — clip musical rendu par code *(adaptation française)*

Clip musical génératif, rendu intégralement par du code, avec une typographie karaoké
calée mot à mot. Chaque image est une fonction déterministe du temps de la chanson : la
prévisualisation dans le navigateur et l'export hors ligne en 1080p60 (ou 4K60) sont
identiques.

> **Ce dépôt est une adaptation française non officielle de
> [mexicat/pdoom-video](https://github.com/mexicat/pdoom-video)**, le clip de
> *« I'm Upping My P(doom) »*. Les paroles ont été traduites en français, chantées par
> Suno, et tout le texte codé en dur des plaques (formulaire du bureau, télémétrie,
> Gantt du virage à gauche, salle d'Ilya, faux extraits web…) a été traduit.
>
> Les traductions et le lancement de ce fork — reprise du dépôt d'origine, traduction des
> paroles, adaptation des scènes, nouvel alignement mot à mot, génération — ont été faits
> par **DeepSeek V4.1 Flash Max**, à partir de `mexicat/pdoom-video`. Le concept, le
> moteur de rendu et les scènes viennent du projet d'origine (voir [Crédits](#crédits)).

## Ce que ce fork change

- **Paroles françaises** (`lyrics/lyrics.src.js`, `data/lyrics.json`). La version Suno du
  morceau ajoute neuf mesures d'intro, une reprise de plus de « l'orthogonality thesis »
  dans le refrain 3, et un outro où le hook est chanté seul quatre fois : les trois sont
  dans la feuille de paroles et dans l'alignement.
- **Audio français** : `audio/pdoom.mp3` est la prise Suno française (133,481 BPM). La
  version anglaise d'origine est conservée à côté, en `audio/pdoom.en.mp3`, à titre de
  référence uniquement.
- **Alignement mot à mot refait** : CTC forcé (Viterbi global) sur les émissions MMS_FA,
  trames de 20 ms, avec découpage des mots en sous-mots prononcés
  (`analysis/pron_fr.py`) — c'est ce découpage qui fournit les temps de syllabes attendus
  par les scènes. Voir [Régénérer les données de timing](#régénérer-les-données-de-timing).
- **Plaques traduites** dans les 20 scènes, mise en page inchangée : les libellés
  proviennent toujours des mêmes chaînes, seuls les textes ont changé.
- **Rendu hors ligne réparé pour Windows** : `app/scripts/render.ts` choisit le bon
  backend ANGLE selon la plateforme et tourne sous Node (playwright-core ne parvient pas à
  piloter Chrome depuis Bun). Le préfiltre de bloom compilait par ailleurs un `int`
  fractionnaire — donc échouait — dès que `--scale` valait autre chose qu'un entier.
- **Rendu en parallèle** : `app/scripts/render-chunks.sh` découpe la chanson en tranches
  rendues simultanément puis les recolle, l'audio par-dessus. Le rendu étant limité par le
  CPU, c'est une dizaine de fois plus rapide qu'une seule instance (voir
  [Rendre la vidéo](#rendre-la-vidéo)).

Le concept d'origine, la bible de style et le traitement plaque par plaque restent dans
[`docs/TREATMENT.md`](docs/TREATMENT.md) (en anglais). Le moteur et l'API des scènes sont
documentés dans [`docs/ENGINE.md`](docs/ENGINE.md).

**Regarder la version d'origine :** https://www.youtube.com/watch?v=5EoO5413dBY

## Organisation

- `audio/pdoom.mp3` — la chanson (version française, voir Crédits) ; `audio/pdoom.en.mp3` — la version anglaise d'origine, pour comparaison.
- `lyrics/lyrics.src.js` — la feuille de paroles française, ligne à ligne (temps alignés).
- `analysis/` — outils Python (uv) qui produisent les données de temps : séparation des
  stems par Demucs, alignement forcé CTC recoupé avec Whisper, analyse tempo/mesures/onsets.
  Voir `analysis/fr_ctc.py`, `analysis/fr_lyrics.py` et `analysis/analyze.py`.
- `data/lyrics.json` — les temps mot à mot (et les temps de syllabes pour les sigles).
- `data/audio.json` — tempo (133,481 BPM), temps, mesures, sections, onsets batterie/voix.
- `app/` — le rendu : TypeScript + three.js, bun + Vite.
  - `src/engine/` — cœur du rendu : lecture de la timeline, post-traitement (bloom, halation, grain), typographie (Archivo, IBM Plex Mono, Cormorant Garamond, polices traceur), lots de lignes GPU, HUD.
  - `src/scenes/` — un module par plaque (`open`, `loss`, `prompt`, `hook`, `room`, `shoggoth`, `spacetime`, `ascent`, `bureau`, `leftturn`, `paperclips`, `fuse`, `stack`, `dense`, `loom`, `ilya`, `outro`) et les motifs partagés.
  - `src/timeline.ts` — le montage : fenêtres de scènes ancrées sur les lignes de paroles et calées sur la grille rythmique.
  - `scripts/render.ts` — rendu hors ligne (Chrome sans interface → images brutes par WebSocket → ffmpeg).
  - `scripts/render-chunks.sh` — le même rendu en tranches parallèles, puis la jointure et l'audio (options en tête de fichier).
- `out/` — les rendus (hors dépôt).

## Prérequis

[bun](https://bun.sh), Google Chrome (le rendu hors ligne le pilote sans interface via
playwright-core) et ffmpeg avec libx264. Les outils d'analyse ont besoin de
[uv](https://docs.astral.sh/uv/) ; le rendu, non.

Sous Windows, lancez `app/scripts/render.ts` avec **node** (et non `bun`) : la couche CDP
de playwright-core ne fonctionne pas sous Bun, la poignée de main n'aboutit jamais.

## Aperçu

```sh
cd app
bun install
bunx vite
```

Ouvrez http://localhost:5173 et utilisez les touches ci-dessous. `?t=23` démarre à un
instant donné.

| Touche | Action |
|---|---|
| espace | lecture / pause |
| ← / → | reculer / avancer de 1 s (5 s avec maj) |
| `,` / `.` | image par image |
| `[` / `]` | scène précédente / suivante |
| `l` | boucler la scène courante |
| `h` | masquer l'interface |

L'aperçu se rend en temps réel sur une machine récente. L'export, lui, n'est pas temps réel
et coûte beaucoup plus cher.

## Rendre la vidéo

```sh
cd app
bash scripts/render-chunks.sh --out ../out/pdoom.mp4 -- --samples 12 --shutter 0.2 --crf 20
```

Le rendu hors ligne passe l'essentiel de son temps dans le **CPU**, pas dans le GPU : chaque
sous-image reconstruit les plaques en JavaScript, et une image 1080p coûte à peu près autant
qu'une image 4K (`--samples 4` ≈ 180 ms, `--samples 12` ≈ 450 ms, mesuré avec le mode
`perf`). Une seule instance laisse donc quinze cœurs inoccupés.

- **Sortie :** 1920×1080 à 60 i/s, x264, audio AAC 320 kbit/s.
- **Découpage :** `render-chunks.sh` découpe la chanson en tranches de temps indépendantes
  (16 par défaut, `--chunks`), chacune avec son Chrome sans interface et son ffmpeg, puis
  recolle le tout. Sur un 8 cœurs / 16 threads chaque tranche tourne ~1,6× plus lentement et
  l'ensemble va une dizaine de fois plus vite qu'une seule instance : la chanson entière en
  une vingtaine de minutes au lieu de plusieurs heures. Les tranches sont rendues sans audio
  (`--noaudio` — l'encodage AAC ajouterait un clic à chaque jointure) et l'audio est muxé une
  seule fois, à la fin.
- **Flou de mouvement :** chaque image est la moyenne de plusieurs sous-images réparties
  sur un obturateur court (`--shutter 0.2`, un cinquième du temps d'image) : un mouvement
  rapide laisse une traînée continue au lieu de quelques copies décalées. `--samples auto`
  choisit le nombre par image : 12 pour une image fixe, 36 pour un mouvement de caméra
  ordinaire, 108 ou 324 pour les coups de fouet, les slams et les zooms rapides ; il
  s'arrête quand davantage de sous-images ne changeraient plus l'image de plus de `--tol`
  niveaux sur 255 (3 par défaut). `--samples N` prend un N fixe (`--samples 4` donne un
  brouillon rapide). C'est le seul levier vraiment coûteux : douze sous-images coûtent trois
  fois plus cher que quatre, et `--samples auto` grimpe jusqu'à 108 ou 324 sur les coups de
  fouet. `--samples 12` est le bon compromis pour un rendu complet.
- **Autres modes :** `stills`, `sheet` (planches-contacts, `--cuts` pour chaque frontière
  de scène), `perf`, et `plates` (régénère `public/plates/`, les arrêts sur image utilisés
  par le rembobinage de l'outro ; à relancer après avoir touché une scène).
- **`--url`** évite de démarrer un serveur Vite privé ; sans lui, le script en lance un
  (sans rechargement à chaud, pour qu'une sauvegarde de fichier ne recharge pas la page en
  plein rendu).

### 2K / 4K

`--scale` accepte aussi une valeur fractionnaire : `--scale 1.3333` rend en **2560×1440
natif** et `--scale 2` en **3840×2160** (pas un agrandissement — chaque calque, chaque ligne
et chaque shader sont calculés à la résolution physique ; la taille physique est arrondie au
pixel entier). Comme le coût vient du CPU et non du nombre de pixels, monter en résolution
rallonge étonnamment peu : ce sont la mémoire des tranches et l'encodage qui augmentent, pas
le calcul des plaques. Pour un master 2K :

```sh
cd app
bash scripts/render-chunks.sh --chunks 8 --out ../out/pdoom-2k.mp4 -- \
  --scale 1.3333 --samples 12 --shutter 0.2 --crf 21 --preset fast
```

Moins de tranches (`--chunks 8`) parce qu'un Chrome en 1440p tient plus de mémoire, et un CRF
un cran plus haut parce qu'une image 2K coûte plus cher à encoder.

- **Coût :** sur une RTX 4060 Ti, une image 4K à 12 sous-images coûte environ 380 ms — à peu
  près autant qu'une image 1080p, puisque c'est le CPU qui travaille. La chanson entière
  (200 s à 60 i/s, 12 000 images) se compte donc en heures avec une seule instance, et en
  une vingtaine de minutes avec `render-chunks.sh`.
- **Encodage :** le grain coûte cher à encoder : en CRF 17 le fichier 1080p60 monte à
  ~58 Mbit/s (1,4 Go). `--crf 20` donne ~20-25 Mbit/s, ce qui tient sous la limite de 512 Mo
  d'un envoi sur X tout en restant très au-dessus des 12 Mbit/s recommandés par YouTube en
  1080p60.
- `--scale 2` marche avec tous les modes (`stills` enregistre alors des PNG pleine
  résolution, `perf` mesure les temps d'image en 4K). Dans l'aperçu navigateur, ajoutez
  `&scale=2` à l'URL.

## Régénérer les données de timing

Les `data/*.json` versionnés suffisent au rendu. Les régénérer demande les stems et les
intermédiaires, qui ne sont pas dans le dépôt :

- **Stems :** Demucs `htdemucs_ft` dans `analysis/stems/htdemucs_ft/pdoom/`
  (`uv run python -m demucs -n htdemucs_ft -o stems ../audio/pdoom.mp3`). Le dépôt
  d'origine corrigeait un décalage de 1015 échantillons entre les stems et le décodage du
  mp3 ; sur la prise française ce décalage est nul
  (`STEM_OFFSET_SAMPLES = 0` dans `analysis/common.py`, mesuré par corrélation croisée).
- **Intermédiaires :** `fr_whisper.py` (transcription + horodatage mot à mot),
  `vocal_feats.py` et `fr_ctc.py` écrivent dans `analysis/work/`.

```sh
cd analysis
uv sync --no-install-package mlx-whisper   # mlx-whisper est réservé à Apple : on utilise faster-whisper
uv run python fr_whisper.py                # work/whisper_fr_large-v3.json
uv run python fr_ctc.py                    # data/lyrics.json + lyrics/lyrics.src.js
uv run python analyze.py                   # data/audio.json
```

`fr_ctc.py` fait deux passes : la première aligne tout le texte d'un seul Viterbi avec un
jeton « garbage » entre les lignes (il absorbe l'intro, les ad-libs et l'outro), la
seconde rejoue l'alignement dans des fenêtres construites à partir de l'union de cette
estimation et des horodatages Whisper. Ce détour est nécessaire : lâché sur trois minutes,
le Viterbi global dérive vers l'arrière, et Whisper place au contraire les débuts
systématiquement trop tôt. Le script mesure les deux sur l'enveloppe de la voix isolée —
sur les neuf débuts de ligne qui tombent dans un silence, Whisper se trompe de 578 ms en
médiane, le CTC de 88 ms — et recale les quatre cas les plus nets pile sur l'attaque.

Les modèles téléchargent environ 5 Go de poids dans `analysis/.cache/` ; supprimez ce
dossier ensuite.

## Crédits

- **Chanson d'origine :** « I'm Upping My P(doom) ». Paroles d'[osmarks](https://docs.osmarks.net/hypha/p%28doom%29_song_objectively_correct_interpretation),
  à partir d'un premier couplet et d'un refrain de [MusicPerson](https://www.udio.com/creators/MusicPerson),
  avec des vers suggérés sur le Discord d'EleutherAI et l'aide de Claude sur l'outro et le
  dernier refrain. Original généré avec Udio, publié en novembre 2024
  ([YouTube](https://www.youtube.com/watch?v=uEB5E67vcPA)).
- **Clip d'origine :** [mexicat/pdoom-video](https://github.com/mexicat/pdoom-video), écrit
  avec Claude (Opus 5.5) dans Claude Code — concept, traitement, analyse audio, moteur de
  rendu, scènes et rendus. La version Suno « Claude-Pop » du morceau a été publiée par
  [deckard (@slimer48484)](https://x.com/slimer48484/status/2097752569212756134).
- **Cette adaptation :** paroles françaises chantées par Suno ; traductions, adaptation des
  scènes et nouvel alignement par **DeepSeek V4.1 Flash Max**, à partir du dépôt
  `mexicat/pdoom-video`. Adaptation **non officielle**, sans lien avec les auteurs
  d'origine.
- **Polices :** Archivo, IBM Plex Mono et Cormorant Garamond (SIL Open Font License).
  Polices traceur EMS et Hershey via le paquet `hersheytext` (OFL / domaine public).

## Licence

Le code est publié sous [licence MIT](LICENSE). Les polices de `app/public/fonts/`
gardent leurs licences propres (voir Crédits), et la chanson comme les paroles
(`audio/`, `lyrics/`, `data/lyrics.json`) n'en relèvent pas : elles appartiennent à leurs
auteurs (voir Crédits).
