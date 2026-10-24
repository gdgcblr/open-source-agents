import {existsSync, writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {parseArgs} from 'node:util';
import {runAllChecks} from './checks/index.js';
import {parsePullRequestUrl} from './github.js';
import {renderMarkdown} from './report.js';
import {loadSource} from './source.js';

const USAGE = `Usage: npm run review -- <project-folder | github-pr-url> [options]

Options:
  --no-llm       Run only the rule checks (no API key needed)
  --json         Print the report as JSON
  --out <file>   Also write the report to a file
  -h, --help     Show this help`;

function hasModelCredentials(): boolean {
  return Boolean(process.env.GEMINI_API_KEY || process.env.GOOGLE_GENAI_API_KEY || process.env.GOOGLE_GENAI_USE_VERTEXAI);
}

async function main(): Promise<number> {
  const {values, positionals} = parseArgs({
    allowPositionals: true,
    options: {
      'no-llm': {type: 'boolean', default: false},
      json: {type: 'boolean', default: false},
      out: {type: 'string'},
      help: {type: 'boolean', short: 'h', default: false},
    },
  });
  if (values.help || positionals.length !== 1) {
    console.log(USAGE);
    return values.help ? 0 : 2;
  }
  if (existsSync('.env')) process.loadEnvFile('.env');

  // npm runs scripts from the package folder; INIT_CWD is where the user typed the command.
  const invokedFrom = process.env.INIT_CWD ?? process.cwd();
  const raw = positionals[0];
  const target = parsePullRequestUrl(raw) ? raw : resolve(invokedFrom, raw);

  const report = await runAllChecks(await loadSource(target));

  if (!values['no-llm']) {
    if (hasModelCredentials()) {
      const {runAiReview} = await import('./agent.js');
      report.aiReview = await runAiReview(target);
    } else {
      console.error('AI review skipped: set GEMINI_API_KEY in .env, or pass --no-llm.\n');
    }
  }

  const output = values.json ? JSON.stringify(report, null, 2) : renderMarkdown(report);
  console.log(output);
  if (values.out) writeFileSync(resolve(invokedFrom, values.out), output);
  return report.errors > 0 ? 1 : 0;
}

main().then(
  (code) => process.exit(code),
  (err) => {
    console.error(`Error: ${err instanceof Error ? err.message : String(err)}`);
    process.exit(2);
  },
);
