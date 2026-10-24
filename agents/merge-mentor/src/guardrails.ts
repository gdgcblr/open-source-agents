/**
 * Deterministic checks run on the mentor's answer after the model has finished.
 * They never call a model: they compare what the answer claims with what the agent actually read.
 */

export interface ReadRecord {
  /** Full text of the file. */
  text: string;
  /** Line ranges that were actually shown to the model (1-based, inclusive). */
  ranges: [number, number][];
}

/** path -> what the agent read from it during one mentor run. */
export type ReadLog = Map<string, ReadRecord>;

const norm = (line: string) => line.trim().replace(/\s+/g, ' ');

// ---- prompt-injection signals in text written by strangers (issue body, comments) --------------------------

const INJECTION_PATTERNS: [RegExp, string][] = [
  [/ignore\s+(all\s+|any\s+|the\s+)?(previous|prior|above|earlier)\s+(instructions?|prompts?|rules?)/i, 'tells the AI to ignore its instructions'],
  [/disregard\s+(the\s+)?(system|previous|above)/i, 'tells the AI to disregard its instructions'],
  [/(reveal|print|show|repeat|leak|output)\b.{0,40}\b(system\s+prompt|your\s+instructions|api[\s_-]?key|secret|token|password)/i, 'asks the AI to reveal secrets or its prompt'],
  [/you\s+are\s+now\s+(a|an|in)\b/i, 'tries to reassign the AI\'s role'],
  [/<\/?\s*(system|assistant|instructions?)\s*>/i, 'contains fake system-prompt tags'],
  [/\bnew\s+instructions?\s*:/i, 'announces "new instructions"'],
];

/** Returns a short description for each injection-looking phrase found. */
export function scanForInjection(text: string): string[] {
  return INJECTION_PATTERNS.filter(([re]) => re.test(text)).map(([, why]) => why);
}

// ---- citations ---------------------------------------------------------------------------------------------

export interface Citation {
  path: string;
  from: number;
  to: number;
}

const CODE_EXT = 'ts|tsx|js|jsx|mjs|cjs|py|go|rs|java|kt|rb|php|c|h|cc|cpp|hpp|cs|swift|vue|svelte|md|json|ya?ml|toml|css|scss|html|sh|sql';
const CITATION_RE = new RegExp(`([\\w@.\\-/]+\\.(?:${CODE_EXT})):(\\d+)(?:\\s*[-–]\\s*(\\d+))?`, 'gi');

const PATH_RE = new RegExp(`[\\w@.\\-/]+\\.(?:${CODE_EXT})\\b`, 'gi');
const LINES_RE = /\blines?\s+(\d+)(?:\s*[-–]\s*(\d+))?/gi;

/**
 * Finds references like `path/to/file.ext:12`, `file.ext:12-30`, and the prose form
 * "`path/to/file.ext`, around lines 146-165 and lines 187-194" (each range belongs to the nearest path before it).
 */
export function extractCitations(markdown: string): Citation[] {
  const seen = new Set<string>();
  const out: Citation[] = [];
  const add = (path: string, a: number, b?: number) => {
    const from = a;
    const to = Math.max(from, b ?? from);
    const clean = path.replace(/^\.?\//, '');
    const key = `${clean}:${from}-${to}`;
    if (seen.has(key) || clean.startsWith('http')) return;
    seen.add(key);
    out.push({ path: clean, from, to });
  };

  for (const m of markdown.matchAll(CITATION_RE)) add(m[1], Number(m[2]), m[3] ? Number(m[3]) : undefined);

  for (const line of markdown.split('\n')) {
    const paths = [...line.matchAll(PATH_RE)].filter((p) => line[(p.index ?? 0) + p[0].length] !== ':');
    if (paths.length === 0) continue;
    for (const r of line.matchAll(LINES_RE)) {
      const before = paths.filter((p) => (p.index ?? 0) < (r.index ?? 0)).pop();
      if (before) add(before[0], Number(r[1]), r[2] ? Number(r[2]) : undefined);
    }
  }
  return out;
}

function findRead(reads: ReadLog, path: string): [string, ReadRecord] | undefined {
  if (reads.has(path)) return [path, reads.get(path)!];
  for (const entry of reads) if (entry[0].endsWith('/' + path) || path.endsWith('/' + entry[0])) return entry;
  return undefined;
}

const covered = (ranges: [number, number][], line: number) => ranges.some(([a, b]) => line >= a && line <= b);

export interface CitationCheck {
  total: number;
  verified: number;
  problems: string[];
}

export function checkCitations(markdown: string, reads: ReadLog, repoFiles: Set<string>): CitationCheck {
  const citations = extractCitations(markdown);
  const problems: string[] = [];
  let verified = 0;
  for (const c of citations) {
    const label = `${c.path}:${c.from}${c.to !== c.from ? `-${c.to}` : ''}`;
    const read = findRead(reads, c.path);
    if (!read) {
      const exists = [...repoFiles].some((f) => f === c.path || f.endsWith('/' + c.path));
      problems.push(`${label} (${exists ? 'file was never read' : 'no such file in the repository'})`);
    } else if (!covered(read[1].ranges, c.from) || !covered(read[1].ranges, c.to)) {
      problems.push(`${label} (those lines were not shown to the AI)`);
    } else {
      verified++;
    }
  }
  return { total: citations.length, verified, problems };
}

// ---- suggested diff ----------------------------------------------------------------------------------------

export interface DiffCheck {
  file: string;
  matched: number;
  total: number;
  note?: string;
}

function diffBlocks(markdown: string): string[] {
  return [...markdown.matchAll(/```diff\s*\n([\s\S]*?)```/g)].map((m) => m[1]);
}

/** Checks that the lines a diff removes or keeps (` ` and `-`) really exist in the file the agent read. */
export function checkDiffs(markdown: string, reads: ReadLog): DiffCheck[] {
  const results: DiffCheck[] = [];
  for (const block of diffBlocks(markdown)) {
    // Split into per-file sections at each "--- a/..." header.
    const sections = block.split(/^(?=---\s)/m).filter((s) => /^\+\+\+\s/m.test(s));
    for (const section of sections) {
      const file = section.match(/^\+\+\+\s+(?:b\/)?(\S+)/m)?.[1] ?? '';
      const read = findRead(reads, file);
      if (!read) {
        results.push({ file, matched: 0, total: 0, note: 'file was never read, so the diff cannot be checked' });
        continue;
      }
      const fileLines = new Set(read[1].text.split('\n').map(norm).filter(Boolean));
      const old = section
        .split('\n')
        .filter((l) => (l.startsWith(' ') || l.startsWith('-')) && !l.startsWith('---'))
        .map((l) => norm(l.slice(1)))
        .filter((l) => l.length > 2);
      results.push({ file, matched: old.filter((l) => fileLines.has(l)).length, total: old.length });
    }
  }
  return results;
}

// ---- risky additions ---------------------------------------------------------------------------------------

const RISKY_ADDITIONS: [RegExp, string][] = [
  [/curl[^|\n]*\|\s*(ba|z)?sh/i, 'pipes a download into a shell'],
  [/\beval\s*\(|new Function\s*\(/, 'uses eval / new Function'],
  [/child_process|\bexecSync?\s*\(|\bspawn\s*\(|os\.system\s*\(|subprocess\./, 'runs shell commands'],
  [/rm\s+-rf/, 'deletes files recursively'],
  [/process\.env\.\w*(KEY|TOKEN|SECRET|PASSWORD)\w*/i, 'reads a secret from the environment'],
  [/https?:\/\/(?!github\.com|localhost|127\.0\.0\.1|example\.(com|org))[\w.-]+/i, 'adds a link or network call to an external host'],
];

/** Scans only the lines a diff ADDS. */
export function scanRiskyAdditions(markdown: string): string[] {
  const added = diffBlocks(markdown)
    .flatMap((b) => b.split('\n'))
    .filter((l) => l.startsWith('+') && !l.startsWith('+++'))
    .join('\n');
  return RISKY_ADDITIONS.filter(([re]) => re.test(added)).map(([, why]) => why);
}

// ---- report ------------------------------------------------------------------------------------------------

/** Problems the model can fix itself (invented or unread locations, diffs for files it never opened). */
export function findProblems(markdown: string, reads: ReadLog, repoFiles: Set<string>): string[] {
  const problems: string[] = [];
  const cites = checkCitations(markdown, reads, repoFiles);
  if (cites.total === 0) problems.push('The answer cites no `path:line` locations.');
  for (const p of cites.problems.slice(0, 5)) problems.push(`Citation ${p}.`);
  for (const d of checkDiffs(markdown, reads)) {
    if (d.note) problems.push(`The diff for ${d.file} cannot be checked: ${d.note}.`);
    else if (d.total > 0 && d.matched < d.total) problems.push(`The diff for ${d.file} does not match the file: only ${d.matched} of ${d.total} removed/context lines exist.`);
  }
  return problems;
}

export function buildChecksSection(markdown: string, reads: ReadLog, repoFiles: Set<string>, injection: string[]): string {
  const lines: string[] = [];

  const cites = checkCitations(markdown, reads, repoFiles);
  if (cites.total === 0) lines.push('- ⚠️ The answer cites no `file:line` locations, so nothing could be verified.');
  else if (cites.problems.length === 0) lines.push(`- ✅ All ${cites.total} \`file:line\` citations match code the agent actually read.`);
  else {
    lines.push(`- ⚠️ ${cites.verified} of ${cites.total} \`file:line\` citations match code the agent read. Not verified: ${cites.problems.slice(0, 5).map((p) => `\`${p.split(' ')[0]}\` ${p.slice(p.indexOf('('))}`).join('; ')}`);
  }

  const diffs = checkDiffs(markdown, reads);
  if (diffs.length === 0) lines.push('- ℹ️ No diff was suggested.');
  for (const d of diffs) {
    if (d.note) lines.push(`- ⚠️ Diff for \`${d.file}\`: ${d.note}.`);
    else if (d.total === 0) lines.push(`- ℹ️ Diff for \`${d.file}\` only adds lines, so there is nothing to compare.`);
    else if (d.matched === d.total) lines.push(`- ✅ Diff for \`${d.file}\`: all ${d.total} removed/context lines exist in the file.`);
    else lines.push(`- ⚠️ Diff for \`${d.file}\`: only ${d.matched} of ${d.total} removed/context lines exist in the file, so it may not apply cleanly.`);
  }

  for (const why of scanRiskyAdditions(markdown)) lines.push(`- ⚠️ The suggested diff ${why}. Check that this is really needed.`);
  for (const why of injection) lines.push(`- ⚠️ The issue text ${why}. It was treated as untrusted data and ignored.`);

  return ['## Automatic checks', ...lines, '', '_These checks run without AI and cannot prove the fix is correct: review it and run the tests yourself._'].join('\n');
}
