import type { CandidatePair, LoadedTool } from "./types.js";

const STOPWORDS = new Set(
  (
    "a an and are as at be by can do does for from has have if in into is it its of on or that the this to " +
    "use used using when which will with you your their them they these those any all also only one more " +
    "e g i ie eg via etc should must may tool tools return returns given provided specified based optional " +
    "default string number boolean object array value values field fields parameter parameter id"
  ).split(" "),
);

/** Common verb and noun synonyms in tool descriptions, folded to one form so "find" and "search" match. */
const SYNONYMS: Record<string, string> = {
  find: "search", lookup: "search", query: "search", look: "search", locate: "search",
  fetch: "get", retrieve: "get", read: "get", load: "get", obtain: "get", show: "get", view: "get",
  add: "create", new: "create", make: "create", insert: "create", write: "create", post: "create",
  remove: "delete", erase: "delete", destroy: "delete", drop: "delete", trash: "delete",
  edit: "update", modify: "update", change: "update", patch: "update", amend: "update",
  enumerate: "list", browse: "list",
  doc: "document", docs: "document", file: "document", files: "document", page: "document", pages: "document",
  note: "document", notes: "document",
  message: "message", msg: "message", email: "message", mail: "message",
  issue: "ticket", issues: "ticket", task: "ticket", tasks: "ticket", todo: "ticket",
  user: "person", users: "person", member: "person", people: "person", contact: "person",
  repo: "repository", repos: "repository",
};

function stem(word: string): string {
  if (word.length <= 3) return word;
  if (word.endsWith("ies") && word.length > 4) return word.slice(0, -3) + "y";
  if (word.endsWith("ing") && word.length > 5) return word.slice(0, -3);
  if (word.endsWith("ed") && word.length > 4) return word.slice(0, -2);
  if (word.endsWith("es") && /(ss|x|ch|sh)es$/.test(word)) return word.slice(0, -2);
  if (word.endsWith("s") && !word.endsWith("ss")) return word.slice(0, -1);
  return word;
}

export function tokenize(text: string): string[] {
  const spaced = text
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/[_\-./:]+/g, " ")
    .toLowerCase();
  const out: string[] = [];
  for (const raw of spaced.split(/[^a-z0-9]+/)) {
    if (raw.length < 2 || STOPWORDS.has(raw) || /^\d+$/.test(raw)) continue;
    const canon = SYNONYMS[raw] ?? SYNONYMS[stem(raw)] ?? stem(raw);
    if (!STOPWORDS.has(canon)) out.push(canon);
  }
  return out;
}

export function paramNames(schema: Record<string, unknown>): string[] {
  const props = (schema as { properties?: Record<string, unknown> }).properties;
  return props && typeof props === "object" ? Object.keys(props) : [];
}

/** Text the model actually reads for a tool: its name, description and parameter names/descriptions. */
export function toolText(t: { name: string; description: string; inputSchema: Record<string, unknown> }): string {
  const props = ((t.inputSchema as { properties?: Record<string, { description?: string }> }).properties ?? {}) as Record<
    string,
    { description?: string }
  >;
  const paramText = Object.entries(props)
    .map(([k, v]) => `${k} ${typeof v?.description === "string" ? v.description : ""}`)
    .join(" ");
  return `${t.name} ${t.name} ${t.description} ${paramText}`;
}

type Vector = Map<string, number>;

/** Small TF-IDF index. Fine for the few hundred tools a real agent loads. */
export class TfIdfIndex {
  private idf = new Map<string, number>();
  readonly vectors: Vector[];

  constructor(docs: string[][]) {
    const df = new Map<string, number>();
    for (const doc of docs) for (const term of new Set(doc)) df.set(term, (df.get(term) ?? 0) + 1);
    const n = docs.length;
    for (const [term, count] of df) this.idf.set(term, Math.log((n + 1) / (count + 1)) + 1);
    this.vectors = docs.map((d) => this.vectorize(d));
  }

  vectorize(tokens: string[]): Vector {
    const tf = new Map<string, number>();
    for (const t of tokens) tf.set(t, (tf.get(t) ?? 0) + 1);
    const v: Vector = new Map();
    let norm = 0;
    for (const [term, count] of tf) {
      const w = (1 + Math.log(count)) * (this.idf.get(term) ?? Math.log(this.vectors?.length ?? 1) + 1);
      v.set(term, w);
      norm += w * w;
    }
    norm = Math.sqrt(norm) || 1;
    for (const [term, w] of v) v.set(term, w / norm);
    return v;
  }

  static cosine(a: Vector, b: Vector): number {
    const [small, large] = a.size < b.size ? [a, b] : [b, a];
    let dot = 0;
    for (const [term, w] of small) dot += w * (large.get(term) ?? 0);
    return dot;
  }
}

function jaccard(a: string[], b: string[]): number {
  const A = new Set(a);
  const B = new Set(b);
  if (A.size === 0 && B.size === 0) return 0;
  let inter = 0;
  for (const x of A) if (B.has(x)) inter++;
  return inter / (A.size + B.size - inter);
}

function normName(name: string): string {
  return tokenize(name).join("_");
}

export interface CandidateOptions {
  /** Only report pairs at or above this combined score. */
  threshold?: number;
  /** Also compare tools that live on the same server. */
  includeSameServer?: boolean;
}

export function findCandidates(tools: LoadedTool[], opts: CandidateOptions = {}): CandidatePair[] {
  const threshold = opts.threshold ?? 0.3;
  const docs = tools.map((t) => tokenize(toolText(t)));
  const index = new TfIdfIndex(docs);
  const nameTokens = tools.map((t) => tokenize(t.name));
  const params = tools.map((t) => paramNames(t.inputSchema).map((p) => tokenize(p).join("_")));

  const pairs: CandidatePair[] = [];
  for (let i = 0; i < tools.length; i++) {
    for (let j = i + 1; j < tools.length; j++) {
      const a = tools[i]!;
      const b = tools[j]!;
      if (!opts.includeSameServer && a.server === b.server) continue;

      const descriptionSimilarity = TfIdfIndex.cosine(index.vectors[i]!, index.vectors[j]!);
      const nameOverlap = jaccard(nameTokens[i]!, nameTokens[j]!);
      const paramOverlap = jaccard(params[i]!, params[j]!);
      const sameName = normName(a.name) === normName(b.name);

      let score = 0.6 * descriptionSimilarity + 0.25 * nameOverlap + 0.15 * paramOverlap;
      if (sameName) score = Math.min(1, score + 0.1);
      if (score < threshold) continue;

      const sharedTerms = [...new Set(docs[i])]
        .filter((term) => docs[j]!.includes(term))
        .sort((x, y) => (index.vectors[j]!.get(y) ?? 0) - (index.vectors[j]!.get(x) ?? 0))
        .slice(0, 8);

      pairs.push({
        a,
        b,
        score: round(score),
        signals: {
          descriptionSimilarity: round(descriptionSimilarity),
          nameOverlap: round(nameOverlap),
          paramOverlap: round(paramOverlap),
          sameName,
          sharedTerms,
        },
      });
    }
  }
  return pairs.sort((x, y) => y.score - x.score);
}

export function round(n: number, digits = 3): number {
  const f = 10 ** digits;
  return Math.round(n * f) / f;
}
