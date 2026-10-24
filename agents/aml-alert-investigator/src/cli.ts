import {existsSync} from 'node:fs';
import {resolve} from 'node:path';
import {parseArgs} from 'node:util';
import {loadRuleConfig} from './config.js';
import {fallbackInvestigation} from './fallback.js';
import {guardInvestigation} from './guardrails.js';
import {alertCase, alertQueue, buildWorkspace, type CaseFile, type Workspace} from './investigation.js';

const USAGE = `Usage:
  npm run detect [-- options]                      Load CSVs, run detection, print the alert queue
  npm run investigate -- [--alert ALT-0001] [opts] Investigate one alert (default: highest risk)

Options:
  --data <dir>    Folder with customers.csv, accounts.csv, transactions.csv (default: ./data)
  --rules <file>  JSON file overriding rule thresholds/toggles (see README)
  --no-llm        Rule-based investigation only (offline, no API key)
  --json          Print JSON
  -h, --help      Show this help`;

function renderQueue(ws: Workspace): string {
  const {dataset, run} = ws;
  const lines = [
    `Loaded ${dataset.customers.size} customers, ${dataset.accounts.size} accounts, ${dataset.transactions.length} transactions` +
      ` (${dataset.errors.length} rejected, ${dataset.duplicatesSkipped} duplicates skipped).`,
    ...dataset.errors.map((e) => `  ! ${e}`),
    `Evaluated ${run.transactionsEvaluated} transactions in ${run.elapsedMs} ms → ${run.alerts.length} alert(s).`,
    '',
    '| Alert | Risk | Rules | Account | Customer | Evidence |',
    '| :--- | ---: | :--- | :--- | :--- | ---: |',
    ...alertQueue(ws).map((a) => `| ${a.alertId} | ${a.riskScore} | ${a.ruleCodes.join(', ')} | ${a.accountId} | ${a.customerId} (${a.customerName}) | ${a.evidenceCount} |`),
  ];
  return lines.join('\n');
}

interface Investigation {
  source: 'gemini' | 'fallback';
  model?: string;
  recommendation: string;
  text: string;
  notes: string[];
}

async function investigate(ws: Workspace, file: CaseFile, useLlm: boolean): Promise<Investigation> {
  const fallback = (reason: string): Investigation => ({
    source: 'fallback',
    recommendation: file.alert.minimumRecommendation,
    text: fallbackInvestigation(file, reason),
    notes: [],
  });
  if (!useLlm) return fallback('--no-llm was set');
  if (!process.env.GEMINI_API_KEY && !process.env.GOOGLE_GENAI_API_KEY && !process.env.GOOGLE_GENAI_USE_VERTEXAI) {
    return fallback('no GEMINI_API_KEY set');
  }
  const {investigateWithGemini, setWorkspace, GeminiUnavailableError} = await import('./agent.js');
  setWorkspace(ws);
  try {
    const answer = await investigateWithGemini(file.alert.alertId);
    const guarded = guardInvestigation(answer.text, file, ws.dataset.customers.values());
    if (guarded.rejected) return fallback(`answer blocked by guardrail: ${guarded.rejected}`);
    return {
      source: 'gemini',
      model: answer.model,
      recommendation: guarded.recommendation,
      text: guarded.text,
      notes: [...answer.skipped.map((s) => `model fallback: ${s}`), ...guarded.corrections],
    };
  } catch (err) {
    return fallback(err instanceof GeminiUnavailableError ? err.message : 'unexpected error');
  }
}

function renderInvestigation(file: CaseFile, result: Investigation): string {
  const a = file.alert;
  return [
    `# Investigation: ${a.alertId}  (risk ${a.riskScore}/100, ${a.ruleCodes.join(', ')})`,
    `Account ${file.account?.accountId} · Customer ${file.customer?.customerId} (${file.customer?.maskedName}) · minimum recommendation ${a.minimumRecommendation}`,
    `Rule explanation: ${a.explanation}`,
    '',
    `## Recommendation: ${result.recommendation}  (${result.source === 'gemini' ? `Gemini ${result.model}, checked by guardrails` : 'offline'})`,
    '',
    result.text,
    ...result.notes.map((n) => `  [guardrail] ${n}`),
    '',
    '_A human analyst must review and record the disposition. Alerts are never closed by this tool._',
  ].join('\n');
}

async function main(): Promise<number> {
  const {values} = parseArgs({
    options: {
      investigate: {type: 'boolean', default: false},
      alert: {type: 'string'},
      data: {type: 'string'},
      rules: {type: 'string'},
      'no-llm': {type: 'boolean', default: false},
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
  const from = process.env.INIT_CWD ?? process.cwd();
  const dataDir = values.data ? resolve(from, values.data) : resolve('data');
  const ws = buildWorkspace(dataDir, loadRuleConfig(values.rules ? resolve(from, values.rules) : undefined));

  if (!values.investigate) {
    console.log(values.json ? JSON.stringify({queue: alertQueue(ws), errors: ws.dataset.errors}, null, 2) : renderQueue(ws));
    return 0;
  }

  const alertId = values.alert ?? ws.run.alerts[0]?.alertId;
  const file = alertId ? alertCase(ws, alertId) : null;
  if (!file) {
    console.error(alertId ? `No alert with ID ${alertId}. Run "npm run detect" to list alerts.` : 'No alerts were generated.');
    return 2;
  }
  const result = await investigate(ws, file, !values['no-llm']);
  console.log(values.json ? JSON.stringify({caseFile: file, investigation: result}, null, 2) : renderInvestigation(file, result));
  return 0;
}

main().then(
  (code) => process.exit(code),
  (err) => {
    console.error(`Error: ${err instanceof Error ? err.message : String(err)}`);
    process.exit(2);
  },
);
