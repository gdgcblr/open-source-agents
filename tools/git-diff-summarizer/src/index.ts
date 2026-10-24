#!/usr/bin/env node

import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import fs from 'node:fs';
import path from 'node:path';
import dotenv from 'dotenv';
import { GoogleGenAI } from '@google/genai';

const execFileAsync = promisify(execFile);

// Load environment variables from .env file
dotenv.config();

export interface CliOptions {
  repoPath: string;
  outputPath?: string;
  model: string;
  help: boolean;
  staged: boolean;
}

export interface DiffResult {
  hasChanges: boolean;
  stat: string;
  diff: string;
  fileCount: number;
}

export const MAX_DIFF_BYTES = 100 * 1024; // 100 KB safety limit
export const DEFAULT_MODEL = 'gemini-3.5-flash';

export function parseArgs(argv: string[]): CliOptions {
  let repoPath = process.cwd();
  let outputPath: string | undefined;
  let model = process.env.GEMINI_MODEL || DEFAULT_MODEL;
  let help = false;
  let staged = false;

  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--help' || arg === '-h') {
      help = true;
    } else if (arg === '--repo' || arg === '-r') {
      i++;
      if (i >= argv.length || argv[i].startsWith('-')) {
        throw new Error('Error: Missing value for --repo flag.');
      }
      repoPath = path.resolve(process.cwd(), argv[i]);
    } else if (arg === '--output' || arg === '-o') {
      i++;
      if (i >= argv.length || argv[i].startsWith('-')) {
        throw new Error('Error: Missing value for --output flag.');
      }
      outputPath = path.resolve(process.cwd(), argv[i]);
    } else if (arg === '--model' || arg === '-m') {
      i++;
      if (i >= argv.length || argv[i].startsWith('-')) {
        throw new Error('Error: Missing value for --model flag.');
      }
      model = argv[i];
    } else if (arg === '--staged') {
      staged = true;
    } else {
      throw new Error(`Error: Unknown argument "${arg}". Run with --help for usage.`);
    }
  }

  return { repoPath, outputPath, model, help, staged };
}

export function getHelpText(): string {
  return `
git-diff-summarizer - A lightweight CLI tool that summarizes Git diffs using Google Gemini.

Usage:
  npm run start -- [options]
  node dist/index.js [options]

Options:
  -r, --repo <path>     Path to the Git repository to inspect (default: current working directory)
  -o, --output <file>   Save the generated Markdown summary to a file
  -m, --model <name>    Gemini model to use (default: gemini-3.5-flash or GEMINI_MODEL env var)
      --staged          Inspect staged changes instead of unstaged tracked changes
  -h, --help            Show this help message and exit

Environment Variables:
  GEMINI_API_KEY        Required. Your Google Gemini API key.
  GEMINI_MODEL          Optional. Default model to use (default: gemini-3.5-flash).

Examples:
  npm run start
  npm run start -- --repo /path/to/project
  npm run start -- --output summary.md
  npm run start -- --model gemini-3.5-flash
`.trim();
}

/**
 * Step 1: Observe - inspect the git repository safely using read-only git commands.
 */
export async function observeGitDiff(repoPath: string, staged: boolean = false): Promise<DiffResult> {
  // Validate path existence
  if (!fs.existsSync(repoPath)) {
    throw new Error(`Invalid repository path: Directory "${repoPath}" does not exist.`);
  }

  const statInfo = fs.statSync(repoPath);
  if (!statInfo.isDirectory()) {
    throw new Error(`Invalid repository path: "${repoPath}" is not a directory.`);
  }

  // Verify git repository
  try {
    const { stdout: isGitRepo } = await execFileAsync('git', ['rev-parse', '--is-inside-work-tree'], {
      cwd: repoPath,
    });
    if (isGitRepo.trim() !== 'true') {
      throw new Error(`The path "${repoPath}" is not inside a Git work tree.`);
    }
  } catch (err: any) {
    throw new Error(`The path "${repoPath}" is not a valid Git repository.`);
  }

  // Get diff stats and full diff using safe execFile
  const diffArgs = staged ? ['diff', '--cached'] : ['diff'];
  const statArgs = staged ? ['diff', '--cached', '--stat'] : ['diff', '--stat'];

  let diffOutput: string;
  let statOutput: string;

  try {
    const [statRes, diffRes] = await Promise.all([
      execFileAsync('git', statArgs, { cwd: repoPath, maxBuffer: 10 * 1024 * 1024 }),
      execFileAsync('git', diffArgs, { cwd: repoPath, maxBuffer: 10 * 1024 * 1024 }),
    ]);
    statOutput = statRes.stdout.trim();
    diffOutput = diffRes.stdout.trim();
  } catch (err: any) {
    throw new Error(`Failed to execute Git command: ${err.message}`);
  }

  if (!diffOutput) {
    return {
      hasChanges: false,
      stat: '',
      diff: '',
      fileCount: 0,
    };
  }

  // Safety check on diff size
  const diffByteSize = Buffer.byteLength(diffOutput, 'utf8');
  if (diffByteSize > MAX_DIFF_BYTES) {
    throw new Error(
      `Diff size (${(diffByteSize / 1024).toFixed(1)} KB) exceeds safety threshold (${MAX_DIFF_BYTES / 1024} KB). ` +
      `To avoid unexpected token consumption, please review a smaller subset of changes or commit partial changes before summarizing.`
    );
  }

  const fileCount = statOutput ? statOutput.split('\n').length - 1 : 1;

  return {
    hasChanges: true,
    stat: statOutput,
    diff: diffOutput,
    fileCount: Math.max(1, fileCount),
  };
}

/**
 * Step 2: Analyze - prompt Gemini to summarize the diff and generate a PR description.
 */
export async function analyzeWithGemini(
  diff: string,
  stat: string,
  options: {
    apiKey?: string;
    model?: string;
    client?: GoogleGenAI;
  } = {}
): Promise<string> {
  const apiKey = options.apiKey || process.env.GEMINI_API_KEY;
  if (!apiKey) {
    throw new Error(
      'Missing GEMINI_API_KEY.\n' +
      'Please set your GEMINI_API_KEY in a .env file or in your environment variables.\n' +
      'To get an API key, visit https://aistudio.google.com/'
    );
  }

  const modelName = options.model || process.env.GEMINI_MODEL || DEFAULT_MODEL;
  const ai = options.client || new GoogleGenAI({ apiKey });

  const prompt = `You are an expert software developer assisting with a code review.
Analyze the following Git diff and file statistics, and produce a concise, structured report in clean Markdown format.

Follow these strict requirements:
1. Provide a concise summary of what was changed and why (1-2 short paragraphs).
2. List the key changed files and briefly explain the role of each change.
3. Suggest a ready-to-use Pull Request description (including suggested PR title, change highlights, and testing suggestions).
4. Strictly base your analysis only on the changes present in the diff. Do not invent unmentioned features, files, or test results.
5. Format the output with clear Markdown headers (## Summary of Changes, ## Key Changed Files, ## Suggested Pull Request Description).

Git Diff Stats:
\`\`\`
${stat}
\`\`\`

Git Diff:
\`\`\`diff
${diff}
\`\`\`
`;

  const maxRetries = 2;
  let lastError: any;

  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      const response = await ai.models.generateContent({
        model: modelName,
        contents: prompt,
      });

      const text = response.text?.trim();
      if (!text) {
        throw new Error('Gemini returned an empty response. Please try again.');
      }
      return text;
    } catch (err: any) {
      lastError = err;
      const isUnavailable = err.message && (err.message.includes('503') || err.message.includes('UNAVAILABLE') || err.message.includes('high demand'));
      if (isUnavailable && attempt < maxRetries) {
        console.log(`   ⏳ Model "${modelName}" experienced temporary high demand (503). Retrying in 2s (attempt ${attempt}/${maxRetries})...`);
        await new Promise((resolve) => setTimeout(resolve, 2000));
        continue;
      }
      break;
    }
  }

  const msg = lastError?.message || String(lastError);
  if (msg.includes('API_KEY_INVALID')) {
    throw new Error('Gemini API Error: The provided GEMINI_API_KEY is invalid.');
  }
  if (msg.includes('503') || msg.includes('UNAVAILABLE') || msg.includes('high demand')) {
    throw new Error(
      `Gemini API Error: Model "${modelName}" is currently experiencing high demand (503 Service Unavailable).\n` +
      `Tip: Try switching to the stable "gemini-3.5-flash" in your .env or run with: npm run start -- --model gemini-3.5-flash`
    );
  }
  if (msg.includes('RESOURCE_EXHAUSTED') || msg.includes('429')) {
    throw new Error('Gemini API Error: Quota exceeded or rate limit reached. Please retry shortly.');
  }
  throw new Error(`Gemini API Error: ${msg}`);
}

/**
 * Step 3: Report - format the output and optionally save to file.
 */
export function formatReport(analysis: string, meta: { repoPath: string; model: string }): string {
  const header = `# Git Diff Summary\n\n*Generated by \`git-diff-summarizer\` using ${meta.model}*\n*Repository: \`${meta.repoPath}\`*\n\n---\n\n`;
  return `${header}${analysis}\n`;
}

/**
 * Main orchestrator executing the 3-step workflow.
 */
export async function runSummarizer(argv: string[] = process.argv.slice(2)): Promise<void> {
  const options = parseArgs(argv);

  if (options.help) {
    console.log(getHelpText());
    return;
  }

  console.log(`🔍 [Observe] Inspecting Git changes in: ${options.repoPath}`);
  const diffResult = await observeGitDiff(options.repoPath, options.staged);

  if (!diffResult.hasChanges) {
    const typeLabel = options.staged ? 'staged' : 'unstaged tracked';
    console.log(`\n✨ No ${typeLabel} changes found in repository: ${options.repoPath}`);
    return;
  }

  console.log(`📊 Found changes in repository:\n${diffResult.stat}\n`);
  console.log(`🤖 [Analyze] Sending diff (${Buffer.byteLength(diffResult.diff, 'utf8')} bytes) to Gemini (${options.model})...`);
  console.log('   (Note: Code diff is sent to Google Gemini API for analysis)');

  const analysis = await analyzeWithGemini(diffResult.diff, diffResult.stat, {
    model: options.model,
  });

  const fullReport = formatReport(analysis, {
    repoPath: options.repoPath,
    model: options.model,
  });

  console.log('\n=================== SUMMARY REPORT ===================\n');
  console.log(fullReport);
  console.log('======================================================\n');

  if (options.outputPath) {
    fs.writeFileSync(options.outputPath, fullReport, 'utf8');
    console.log(`💾 Saved summary report to: ${options.outputPath}`);
  }
}

// Execute when invoked directly
const isDirectExecution =
  process.argv[1] &&
  (process.argv[1].endsWith('dist/index.js') ||
   process.argv[1].endsWith('src/index.ts') ||
   process.argv[1].endsWith('git-diff-summarizer'));

if (isDirectExecution) {
  runSummarizer().catch((err) => {
    console.error(`\n❌ ${err.message || err}\n`);
    process.exit(1);
  });
}
