import { ThinkingLevel, FunctionCallingConfigMode, type Content, type FunctionDeclaration } from '@google/genai';
import { buildChecksSection, findProblems, scanForInjection } from './guardrails.js';
import type { Issue, MentorOptions, ReadLog, ToolContext } from '../types.js';
import { COMMENTS_IN_PROMPT, COMMENT_CHARS, ISSUE_BODY_CHARS, LIST_FILES_LIMIT, MAX_CACHED_TREES, MAX_LINES, MAX_PATH_LENGTH, MAX_TOOL_OUTPUT, MAX_TOOL_STEPS, MENTOR_TEMPERATURE, REPAIR_BONUS_STEPS, SEARCH_QUERY_MAX, SEARCH_RESULTS, SYSTEM_PROMPT, TOP_LEVEL_ENTRIES, TREE_TTL_MS } from '../constants.js';

/** Rejects absolute paths, parent traversal and odd characters so tools stay inside the repo. */
export function safeRepoPath(input: unknown): string {
  const p = String(input ?? '').replace(/^\.?\/+/, '').replace(/\/+$/, '');
  if (p.split('/').includes('..') || /[\0\\]/.test(p) || p.length > MAX_PATH_LENGTH) throw new Error(`Invalid path: ${String(input)}`);
  return p;
}

/** Model-supplied numbers can be strings, missing or NaN; fall back instead of returning nothing. */
function toLine(value: unknown, fallback: number): number {
  const n = Math.floor(Number(value));
  return Number.isFinite(n) ? n : fallback;
}

/** The 1-based, inclusive line window a read_file call will show (at most MAX_LINES lines). */
export function lineWindow(totalLines: number, start: unknown, end: unknown): { from: number; to: number } {
  const from = Math.max(1, toLine(start, 1));
  const to = Math.min(totalLines, Math.max(from, toLine(end, from + MAX_LINES - 1)), from + MAX_LINES - 1);
  return { from, to };
}

export function numberLines(text: string, start: unknown, end: unknown): string {
  const lines = text.split('\n');
  const { from, to } = lineWindow(lines.length, start, end);
  return lines
    .slice(from - 1, to)
    .map((line, i) => `${from + i}: ${line}`)
    .join('\n') + (to < lines.length ? `\n[... file has ${lines.length} lines; showing ${from}-${to}]` : '');
}

interface RepoTree {
  files: string[];
  /** GitHub cuts the tree off for very large repositories. */
  truncated: boolean;
}

const tree = new Map<string, { at: number; value: Promise<RepoTree> }>();

function repoFiles(ctx: ToolContext): Promise<RepoTree> {
  const key = `${ctx.repo}@${ctx.branch}`;
  const hit = tree.get(key);
  if (hit && Date.now() - hit.at < TREE_TTL_MS) return hit.value;

  const value = ctx.gh.getJson(`/repos/${ctx.repo}/git/trees/${encodeURIComponent(ctx.branch)}`, { recursive: 1 }).then((t: any) => ({
    files: (t.tree as { path: string; type: string }[]).filter((n) => n.type === 'blob').map((n) => n.path),
    truncated: Boolean(t.truncated),
  }));
  value.catch(() => tree.delete(key)); // never cache a failed request
  tree.set(key, { at: Date.now(), value });
  if (tree.size > MAX_CACHED_TREES) tree.delete(tree.keys().next().value!);
  return value;
}

/** Removes search qualifiers (repo:, org:, user:, path:, ...) so the model cannot search outside the chosen repository. */
export function sanitizeSearchQuery(query: unknown): string {
  return String(query ?? '')
    .replace(/\b[a-z-]+:\S*/gi, ' ')
    .replace(/[()"]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, SEARCH_QUERY_MAX);
}

const TOOLS: Record<string, (ctx: ToolContext, args: any) => Promise<unknown>> = {
  async list_files(ctx, { prefix }) {
    const dir = safeRepoPath(prefix);
    const { files, truncated } = await repoFiles(ctx);
    const under = dir ? files.filter((f) => f.startsWith(dir + '/')) : files;
    // Collapse to the immediate children of `dir` so the output stays small.
    const children = new Set<string>();
    for (const f of under) {
      const rest = dir ? f.slice(dir.length + 1) : f;
      const [head, ...tail] = rest.split('/');
      children.add(tail.length ? `${head}/` : head);
    }
    const listing: string[] = [...children].sort().slice(0, LIST_FILES_LIMIT);
    if (truncated) listing.push('[note: GitHub truncated the file list for this very large repository; some files are missing]');
    return listing;
  },

  async read_file(ctx, { path, start_line, end_line }) {
    const file = safeRepoPath(path);
    const text = await ctx.gh.getRaw(`/repos/${ctx.repo}/contents/${file.split('/').map(encodeURIComponent).join('/')}`, { ref: ctx.branch });
    if (ctx.reads) {
      const { from, to } = lineWindow(text.split('\n').length, start_line, end_line);
      const record = ctx.reads.get(file) ?? { text, ranges: [] };
      record.ranges.push([from, to]);
      ctx.reads.set(file, record);
    }
    return numberLines(text, start_line, end_line);
  },

  async search_code(ctx, { query }) {
    if (!ctx.gh.hasToken) return 'search_code is unavailable: GITHUB_TOKEN is not set.';
    const q = sanitizeSearchQuery(query);
    if (!q) return 'Error: give search words, not search qualifiers.';
    const result = await ctx.gh.getJson('/search/code', { q: `${q} repo:${ctx.repo}`, per_page: SEARCH_RESULTS });
    return (result.items ?? []).map((i: any) => i.path);
  },
};

const DECLARATIONS: FunctionDeclaration[] = [
  {
    name: 'list_files',
    description: 'List the files and folders directly inside a directory of the repository. Use "" for the repo root.',
    parametersJsonSchema: { type: 'object', properties: { prefix: { type: 'string', description: 'Directory path, e.g. "src/utils"' } }, required: ['prefix'] },
  },
  {
    name: 'read_file',
    description: `Read a file with line numbers (at most ${MAX_LINES} lines per call).`,
    parametersJsonSchema: {
      type: 'object',
      properties: {
        path: { type: 'string' },
        start_line: { type: 'integer', description: '1-based first line' },
        end_line: { type: 'integer', description: '1-based last line' },
      },
      required: ['path'],
    },
  },
  {
    name: 'search_code',
    description: 'Search this repository for a function name, identifier or error message. Returns matching file paths.',
    parametersJsonSchema: { type: 'object', properties: { query: { type: 'string' } }, required: ['query'] },
  },
];

/** Masks strings that look like API keys or tokens before anything is printed or saved. */
export function maskSecrets(text: string): string {
  return text
    .replace(/\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b/g, '[REDACTED]')
    .replace(/\bgithub_pat_[A-Za-z0-9_]{20,}\b/g, '[REDACTED]')
    .replace(/\bAIza[0-9A-Za-z_-]{30,}\b/g, '[REDACTED]')
    .replace(/\bAQ\.[A-Za-z0-9_-]{30,}\b/g, '[REDACTED]')
    .replace(/\bsk-[A-Za-z0-9_-]{20,}\b/g, '[REDACTED]');
}

export async function mentorIssue({ gemini, ctx, issue, comments, onStep, isCancelled }: MentorOptions): Promise<string> {
  const { files } = await repoFiles(ctx);
  const reads: ReadLog = new Map();
  const toolCtx: ToolContext = { ...ctx, reads };
  const injection = scanForInjection([issue.title, issue.body ?? '', ...comments.map((c) => c.body)].join('\n'));
  const topLevel = [...new Set(files.map((f) => (f.includes('/') ? f.split('/')[0] + '/' : f)))].sort().slice(0, TOP_LEVEL_ENTRIES);

  const briefing = [
    `Repository: ${ctx.repo} (branch ${ctx.branch})`,
    `Top-level layout: ${topLevel.join(', ')}`,
    `<issue_untrusted>`,
    `#${issue.number} ${issue.title}`,
    `Labels: ${issue.labels.map((l) => l.name).join(', ')}`,
    (issue.body ?? '').slice(0, ISSUE_BODY_CHARS),
    ...comments.slice(0, COMMENTS_IN_PROMPT).map((c) => `Comment by @${c.user}: ${c.body.slice(0, COMMENT_CHARS)}`),
    `</issue_untrusted>`,
  ].join('\n');

  const contents: Content[] = [{ role: 'user', parts: [{ text: briefing }] }];
  const baseConfig = { systemInstruction: SYSTEM_PROMPT, temperature: MENTOR_TEMPERATURE, thinkingConfig: { thinkingLevel: ThinkingLevel.LOW } };

  let steps = 0;
  let maxSteps = MAX_TOOL_STEPS;
  let emptyRetries = 0;
  let repaired = false;
  for (;;) {
    if (isCancelled?.()) throw new Error('Cancelled');
    const exhausted = steps >= maxSteps;
    const response = await gemini.generate({
      contents,
      config: {
        ...baseConfig,
        tools: [{ functionDeclarations: DECLARATIONS }],
        toolConfig: { functionCallingConfig: { mode: exhausted ? FunctionCallingConfigMode.NONE : FunctionCallingConfigMode.AUTO } },
      },
    });

    const calls = response.functionCalls ?? [];
    if (calls.length === 0 || exhausted) {
      if (response.text?.trim() && !repaired) {
        const problems = findProblems(response.text, reads, new Set(files));
        if (problems.length > 0) {
          // Verify, then repair once: tell the model exactly what is wrong and let it read the missing code.
          repaired = true;
          maxSteps = steps + REPAIR_BONUS_STEPS;
          onStep?.(`checking the answer found ${problems.length} problem${problems.length === 1 ? '' : 's'}; asking the mentor to fix them`);
          const modelTurn = response.candidates?.[0]?.content;
          if (modelTurn) contents.push(modelTurn);
          contents.push({
            role: 'user',
            parts: [{ text: `An automatic check found problems with your answer:\n- ${problems.join('\n- ')}\n\nYou may make up to ${REPAIR_BONUS_STEPS} more tool calls. Read the files you rely on with read_file, cite every claim as \`path:LINE\` using lines you have read, only propose a diff for files you have read, then write the complete answer again with all 8 sections.` }],
          });
          continue;
        }
      }
      if (response.text?.trim()) {
        return maskSecrets(`${response.text.trim()}\n\n${buildChecksSection(response.text, reads, new Set(files), injection)}`);
      }
      // Gemini occasionally returns an empty turn; ask once more for the final answer.
      if (emptyRetries++ >= 1) throw new Error('The mentor returned an empty answer twice. Please try again.');
      const modelTurn = response.candidates?.[0]?.content;
      if (modelTurn) contents.push(modelTurn);
      contents.push({ role: 'user', parts: [{ text: 'Please write your final answer now, using the 8 sections.' }] });
      continue;
    }

    // Keep the model's turn verbatim (it can carry thought signatures needed for the next call).
    const modelContent = response.candidates?.[0]?.content;
    if (modelContent) contents.push(modelContent);

    const results = [];
    for (const call of calls) {
      steps++;
      const name = call.name ?? '';
      onStep?.(`${name}(${Object.entries(call.args ?? {}).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(', ')})`);
      let output: unknown;
      try {
        const tool = TOOLS[name];
        if (!tool || steps > maxSteps) throw new Error(steps > maxSteps ? 'Tool step limit reached' : `Unknown tool: ${name}`);
        output = await tool(toolCtx, call.args ?? {});
      } catch (error) {
        output = `Error: ${(error as Error).message}`;
      }
      const text = typeof output === 'string' ? output : JSON.stringify(output);
      results.push({ functionResponse: { name, response: { result: text.slice(0, MAX_TOOL_OUTPUT) } } });
    }
    contents.push({ role: 'user', parts: results });
  }
}

/** No-AI fallback: a short pointer for developers without a Gemini key. */
export async function basicGuide(ctx: ToolContext, issue: Issue): Promise<string> {
  const words = new Set(issue.title.toLowerCase().match(/[a-z]{4,}/g) ?? []);
  const { files } = await repoFiles(ctx);
  const matches = files.filter((f) => [...words].some((w) => f.toLowerCase().includes(w))).slice(0, 10);
  return [
    `## ${issue.title}`,
    issue.html_url,
    '',
    '### Files whose names match the issue',
    ...(matches.length ? matches.map((f) => `- ${f}`) : ['- (no obvious matches)']),
    '',
    'Set GEMINI_API_KEY in .env to get the full AI explanation and suggested fix.',
  ].join('\n');
}
