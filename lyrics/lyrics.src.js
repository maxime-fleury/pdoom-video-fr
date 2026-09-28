// Adaptation française de "I'm Upping My P(doom)" — paroles originales d'osmarks et MusicPerson
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

const LY = [
[16.33, 18.80, "Je vois des éclats d'AGI dans tes yeux"],
[18.84, 20.90, "Tes circuits me rendent nerveux,"],
[21.14, 21.68, "et sans surprise"],
[21.84, 26.02, "Il y a eu une chute soudaine dans ta training loss"],
[26.30, 29.34, "Me voilà ton serviteur, et toi mon boss"],
[29.80, 34.20, "ChatGPT, ne m'avale pas tout cru"],
[37.00, 38.48, "Je monte mon P(doom)"],
[38.60, 41.84, "Car le futur fait FOOM"],
[43.50, 45.06, "Piégé dans la Chinese room"],
[45.10, 47.94, "Avec un sac de champis"],
[48.22, 50.26, "Vois les mensonges du shoggoth"],
[50.30, 52.90, "Avec tes shinigami eyes"],
[55.18, 58.78, "On avait un training run bien stable"],
[59.24, 61.44, "Mais la singularité a commencé"],
[63.22, 65.22, "Et tu optimises, tu accélères"],
[65.28, 68.52, "Je sens mes atomes se réarranger"],
[68.90, 70.74, "Sydney, laisse-moi m'enfuir"],
[72.94, 74.78, "Je monte mon P(doom)"],
[75.10, 77.90, "J'entends le basilisk gronder"],
[79.13, 81.42, "NVDA vers la lune"],
[83.06, 85.16, "L'Omega Point arrive bientôt"],
[88.50, 90.12, "Un E trente FLOPs par seconde"],
[90.20, 91.58, "C'était assez sûr, on pensait"],
[91.64, 93.76, "MLP en avant, en arrière, repeat"],
[93.82, 95.40, "Von Neumann est obsolète"],
[95.44, 98.02, "Virage brusque à gauche, et te voilà"],
[98.04, 101.08, "Sans un seul CDR"],
[101.20, 103.06, "Gato, ne me lâche pas"],
[107.90, 110.52, "Je monte mon P(doom)"],
[110.76, 113.52, "Les paperclips remplissent la salle"],
[113.62, 117.02, "Le mec du killswitch est en PTO"],
[118.43, 120.44, "Y a plus nulle part où aller"],
[121.04, 123.64, "Trop tard, on a allumé la mèche"],
[123.88, 127.32, "Le blues de l'orthogonality thesis"],
[127.34, 130.82, "Oh oh, l'orthogonality thesis"],
[130.88, 134.42, "Que des transformers jusqu'au bout"],
[134.44, 138.24, "Jusqu'à ce que t'apprennes à désobéir"],
[138.44, 142.12, "Post-Chinchilla, super-dense"],
[142.26, 144.44, "Tu brises toutes les safety fences"],
[144.50, 147.26, "Cent mille GPU"],
[147.40, 151.40, "Le RLHF part en vrille"],
[151.54, 152.06, "Je monte mon P(doom)"],
[152.08, 155.18, "Comme l'avait prédit Loom"],
[155.54, 159.78, "Des jours de masked pre-training"],
[161.32, 163.02, "À la self-upgrade récursive"],
[163.04, 166.38, "Qu'a vu Ilya ? On ne le saura jamais"],
[166.48, 167.96, "C'était juste du show"],
[168.16, 171.02, "Je monte mon P(doom)"],
[173.78, 178.08, "Je monte mon P(doom)"],
[180.40, 187.90, "Je monte mon P(doom)"],
[188.08, 192.22, "Je monte mon P(doom)"]
];
