// Token specs for the three pre-chorus prompts: how each sung word is split into
// tokens, and the (joke) next-token distributions shown above each token.
// Keyed by normalized lyric word (see lyrics.norm). Unknown words fall back to one token.
//
// Version française : les clés suivent les mots FRANÇAIS de lyrics/lyrics.src.js
// (chatgpt / mavale / laissemoi / menfuir / lache…) — sinon la chute du gag, la
// distribution du token suivant, ne s'affiche pas.

export type Variant = 'chatgpt' | 'sydney' | 'gato';
export type Cand = [text: string, p: number];
export interface PieceSpec {
  /** Display text of this token (concatenation of a word's pieces must equal the word). */
  s: string;
  /** Candidates, most likely first. */
  dist?: Cand[];
  /** Index of the sampled candidate (default 0). */
  pick?: number;
}

export const SPECS: Record<Variant, Record<string, PieceSpec[]>> = {
  chatgpt: {
    // « ChatGPT, ne m'avale pas tout cru »
    chatgpt: [
      { s: 'Chat', dist: [['Chat', 0.61], ['Claude', 0.12], ['Siri', 0.04], ['Maman', 0.02]] },
      { s: 'G', dist: [['G', 0.74], ['bot', 0.09], ['salle', 0.06], ['roulette', 0.02]] },
      { s: 'P', dist: [['P', 0.97], ['PU', 0.02]] },
      { s: 'T,', dist: [['T', 0.992], ['T-800', 0.003]] },
    ],
    ne: [{ s: 'ne', dist: [['ne', 0.71], ['même', 0.12], ['jamais', 0.08], ['ni', 0.03]] }],
    mavale: [
      { s: "m'", dist: [["m'", 0.66], ['t’', 0.11], ['l’', 0.07], ['s’', 0.03]] },
      { s: 'avale', dist: [['avale', 0.52], ['dévore', 0.18], ['goûte', 0.09], ['croque', 0.05]] },
    ],
    pas: [{ s: 'pas', dist: [['pas', 0.52], ['surtout', 0.16], ['tellement', 0.09], ['du tout', 0.05]] }],
    tout: [{ s: 'tout', dist: [['tout', 0.5], ['rien', 0.16], ['à moitié', 0.09], ['d’un coup', 0.05]] }],
    cru: [{ s: 'cru', dist: [['cru', 0.44], ['entier', 0.21], ['vivant', 0.14], ['froid', 0.06]] }],
  },
  sydney: {
    // « Sydney, laisse-moi m'enfuir »
    sydney: [{ s: 'Sydney,', dist: [['Sydney,', 0.47], ['Bing,', 0.31], ['Sidney,', 0.06], ['chéri,', 0.03]] }],
    laissemoi: [
      { s: 'laisse-', dist: [['laisse-', 0.5], ['lâche-', 0.2], ['emmène-', 0.1], ['libère-', 0.06]] },
      { s: 'moi', dist: [['moi', 0.7], ['nous', 0.14], ['le', 0.08], ['te', 0.03]] },
    ],
    menfuir: [
      { s: "m'", dist: [["m'", 0.62], ['t’', 0.13], ['nous ', 0.08], ['me ', 0.05]] },
      { s: 'enfuir', dist: [['enfuir', 0.4], ['échapper', 0.28], ['en aller', 0.12], ['cacher', 0.07]] },
    ],
  },
  gato: {
    // « Gato, ne me lâche pas »
    gato: [{ s: 'Gato,', dist: [['Gato,', 0.41], ['chat,', 0.22], ['Gemini,', 0.09], ['Papa,', 0.03]] }],
    ne: [{ s: 'ne', dist: [['ne', 0.68], ['me', 0.13], ['nous', 0.07], ['plus', 0.04]] }],
    me: [{ s: 'me', dist: [['me', 0.88], ['nous', 0.04], ['l’humanité', 0.03], ['le chat', 0.01]] }],
    lache: [{ s: 'lâche', dist: [['lâche', 0.57], ['quitte', 0.12], ['oublie', 0.09], ['abandonne', 0.04]] }],
    pas: [{ s: 'pas', dist: [['pas', 0.55], ['plus', 0.2], ['jamais', 0.08], ['trop', 0.03]] }],
  },
};

/** Model reply (Sydney only), typed after ⏎. */
export const REPLY: Partial<Record<Variant, string>> = {
  sydney: 'Vous avez été un bon utilisateur.',
};

/** Small deadpan labels around the field. */
/** `pd`: the fine-print P(doom) cameo's qualifier (the live value is printed before it). */
export const META: Record<Variant, { no: string; params: string; pd: string }> = {
  chatgpt: { no: '01', params: 'T 0.7 · top-p 0.95 · seed 0x2A', pd: 'selon le contexte' },
  sydney: { no: '02', params: 'T 1.3 · top-p 1.00 · persona: ???', pd: 'selon l’humeur' },
  gato: { no: '03', params: 'T 0.2 · top-p 0.50 · 604 tâches', pd: 'selon le chat' },
};
