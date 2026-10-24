#!/usr/bin/env node
import { readFile, writeFile } from 'node:fs/promises';
import { parseArgs } from 'node:util';
import { analyzeCreditCase } from './underwrite.js';
import { toMarkdown } from './report.js';

const help = `Usage: credit-covenant-compass <case.json> [options]

Options:
  --format <markdown|json>  Report format (default: markdown)
  --report-file <path>      Write the report to a file
  -h, --help                Show this help

The agent calculates transparent ratios and scenarios; a human analyst makes every credit decision.
`;

async function main() {
  let args;
  try {
    args = parseArgs({
      options: {
        format: { type: 'string', default: 'markdown' },
        'report-file': { type: 'string' },
        help: { type: 'boolean', short: 'h' },
      },
      allowPositionals: true,
    });
  } catch (error) {
    console.error(`credit-covenant-compass: ${error.message}`);
    process.exitCode = 2;
    return;
  }

  if (args.values.help) {
    console.log(help);
    return;
  }
  if (args.positionals.length !== 1) {
    console.error(help);
    process.exitCode = 2;
    return;
  }
  if (!['markdown', 'json'].includes(args.values.format)) {
    console.error('credit-covenant-compass: --format must be markdown or json.');
    process.exitCode = 2;
    return;
  }

  try {
    const raw = await readFile(args.positionals[0], 'utf8');
    const input = JSON.parse(raw);
    const report = analyzeCreditCase(input);
    const formatted = args.values.format === 'json'
      ? `${JSON.stringify(report, null, 2)}\n`
      : `${toMarkdown(report)}\n`;
    if (args.values['report-file']) {
      await writeFile(args.values['report-file'], formatted, 'utf8');
    } else {
      process.stdout.write(formatted);
    }
  } catch (error) {
    console.error(`credit-covenant-compass: ${error.message}`);
    process.exitCode = 2;
  }
}

await main();