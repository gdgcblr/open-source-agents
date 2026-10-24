import {existsSync, readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {parseArgs} from 'node:util';
import {analyzeMessage, HIGH_RISK_AT, verdictFor} from './analyze.js';
import {failSafeMessage, fallbackExplanation} from './fallback.js';
import {defangLinks, guardExplanation, VERDICT_RANK} from './guardrails.js';
import {redact} from './privacy.js';
import type {Analysis, Verdict} from './types.js';

const USAGE = `Usage:
  npm run check -- "<message text>" [options]
  npm run check -- --file message.txt [options]
  echo "<message>" | npm run check [-- options]

Options:
  --file <path>   Read the message from a file
  --no-llm        Rule-based analysis only (offline, no API key)
  --no-redact     Send phone numbers / UPI IDs to Gemini unmasked
  --json          Print JSON
  -h, --help      Show this help`;

const BAR_WIDTH = 20;

interface Explanation {
  source: 'gemini' | 'fallback';
  model?: string;
  text: string;
  notes: string[];
  /** Set when Gemini judged the message riskier than the rules did. */
  raisedVerdict?: Verdict;
}

function render(a: Analysis, explanation?: Explanation): string {
  const filled = Math.round((a.score / 100) * BAR_WIDTH);
  const lines = [
    ...a.inputWarnings.map((w) => `! ${w}`),
    `Verdict: ${a.verdict.toUpperCase()}  [${'#'.repeat(filled)}${'.'.repeat(BAR_WIDTH - filled)}] ${a.score}/100`,
    ...(explanation?.raisedVerdict ? [`Gemini rated it higher: ${explanation.raisedVerdict.toUpperCase()}`] : []),
    ...(a.scamType ? [`Looks like: ${a.scamType}`] : []),
    '',
  ];
  if (a.signals.length) {
    lines.push('Red flags:');
    for (const s of a.signals) lines.push(`  - ${s.label}`, `      "${defangLinks(s.evidence, a)}"`);
    lines.push('');
  }
  if (a.urls.length) {
    lines.push('Links (inspected offline, never opened; risky ones shown non-clickable):');
    for (const u of a.urls) lines.push(`  - ${u.defanged}  ->  ${u.reasons.join('; ') || 'No issues found'}`);
    lines.push('');
  }
  lines.push('What to do:', ...a.advice.map((t) => `  - ${t}`));
  if (explanation) {
    lines.push('', explanation.source === 'gemini' ? `--- Gemini explanation (${explanation.model}, checked by guardrails) ---` : '--- Offline explanation ---', '');
    lines.push(explanation.text);
    for (const note of explanation.notes) lines.push(`  [guardrail] ${note}`);
  }
  return lines.join('\n');
}

async function explain(analysis: Analysis, message: string, sendRaw: boolean): Promise<Explanation> {
  if (!process.env.GEMINI_API_KEY && !process.env.GOOGLE_GENAI_API_KEY && !process.env.GOOGLE_GENAI_USE_VERTEXAI) {
    return {source: 'fallback', text: fallbackExplanation(analysis, message, 'no GEMINI_API_KEY set'), notes: []};
  }
  const {explainWithGemini, GeminiUnavailableError} = await import('./agent.js');
  try {
    const answer = await explainWithGemini(sendRaw ? message : redact(message));
    const guarded = guardExplanation(answer.text, analysis, message);
    if (guarded.rejected) {
      return {source: 'fallback', text: fallbackExplanation(analysis, message, `answer blocked: ${guarded.rejected}`), notes: []};
    }
    const raised =
      guarded.modelVerdict && VERDICT_RANK[guarded.modelVerdict] > VERDICT_RANK[analysis.verdict] ? guarded.modelVerdict : undefined;
    const notes = [...answer.skipped.map((s) => `model fallback: ${s}`), ...guarded.corrections];
    return {source: 'gemini', model: answer.model, text: guarded.text, notes, raisedVerdict: raised};
  } catch (err) {
    const reason = err instanceof GeminiUnavailableError ? err.message : 'unexpected error';
    return {source: 'fallback', text: fallbackExplanation(analysis, message, reason), notes: []};
  }
}

async function readStdin(): Promise<string> {
  if (process.stdin.isTTY) return '';
  const chunks: Buffer[] = [];
  for await (const chunk of process.stdin) chunks.push(chunk as Buffer);
  return Buffer.concat(chunks).toString('utf8');
}

async function main(): Promise<number> {
  const {values, positionals} = parseArgs({
    allowPositionals: true,
    options: {
      file: {type: 'string'},
      'no-llm': {type: 'boolean', default: false},
      'no-redact': {type: 'boolean', default: false},
      json: {type: 'boolean', default: false},
      help: {type: 'boolean', short: 'h', default: false},
    },
  });
  if (values.help) {
    console.log(USAGE);
    return 0;
  }
  if (existsSync('.env')) process.loadEnvFile('.env');

  // npm runs scripts from the package folder; INIT_CWD is where the user typed the command.
  const invokedFrom = process.env.INIT_CWD ?? process.cwd();
  const message = (
    values.file ? readFileSync(resolve(invokedFrom, values.file), 'utf8') : positionals.join(' ') || (await readStdin())
  ).trim();
  if (!message) {
    console.log(USAGE);
    return 2;
  }

  let analysis: Analysis;
  try {
    analysis = analyzeMessage(message);
  } catch {
    // Fail closed: an internal error must never look like "Likely safe".
    console.log(failSafeMessage());
    return 2;
  }

  const explanation = values['no-llm'] ? undefined : await explain(analysis, message, values['no-redact']);
  const finalVerdict = explanation?.raisedVerdict ?? analysis.verdict;

  console.log(
    values.json
      ? JSON.stringify({...analysis, finalVerdict, explanation: explanation ?? null}, null, 2)
      : render(analysis, explanation),
  );
  return VERDICT_RANK[finalVerdict] >= VERDICT_RANK[verdictFor(HIGH_RISK_AT)] ? 1 : 0;
}

main().then(
  (code) => process.exit(code),
  (err) => {
    console.error(`Error: ${err instanceof Error ? err.message : String(err)}`);
    console.log(failSafeMessage());
    process.exit(2);
  },
);
