#!/usr/bin/env node
/**
 * PR Sentinel - Command Line Interface
 * Autonomous Multi-Agent Pull Request Review, Security Triage, and Auto-Patch System.
 */

import path from 'node:path';
import fs from 'node:fs';
import readline from 'node:readline';
import { Orchestrator } from './agents/orchestrator.js';
import { banner, printReport, printStep, colors } from './ui/terminal.js';
import { startDashboardServer } from './ui/dashboard.js';
import { config } from './config.js';

async function main() {
  const args = process.argv.slice(2);

  // Help flag
  if (args.includes('--help') || args.includes('-h')) {
    banner();
    console.log(`
Usage:
  pr-sentinel [command] [options]

Commands:
  audit [path]         Audit repository, pull request diff, or project folder (default)
  demo                 Run instant multi-agent demonstration with sample test vectors
  serve                Launch embedded local web dashboard (http://localhost:3737)
  interactive          Launch interactive terminal prompt session

Options:
  --path <dir>         Target directory to review (default: current directory)
  --base <branch>      Git base branch for diff comparison (e.g. "main", "upstream/main")
  --staged             Only analyze staged git changes
  --json               Output machine-readable JSON report
  --markdown           Output formatted GitHub PR review comment
  --output, -o <file>  Save review report as a downloadable/local Markdown file
  --port <port>        Port for web dashboard (default: 3737)
  --demo               Force mock/demo execution mode (bypasses live API keys)
  -h, --help           Show this help message

Examples:
  pr-sentinel demo
  pr-sentinel audit --path agents/pr-sentinel
  pr-sentinel audit --output pr-review.md
  pr-sentinel serve --port 3737
`);
    process.exit(0);
  }

  const isDemo = args.includes('demo') || args.includes('--demo');
  const isServe = args.includes('serve') || args.includes('--serve');
  const isInteractive = args.includes('interactive') || args.includes('--interactive');
  const isJson = args.includes('--json');
  const isMarkdown = args.includes('--markdown');

  // Direct API Key health check
  if (args.includes('--check-key')) {
    banner();
    console.log(`${colors.cyan}Testing Google Gemini API Key connection...${colors.reset}\n`);
    if (!config.geminiApiKey) {
      console.log(`❌ ${colors.brightRed}No GEMINI_API_KEY configured in .env!${colors.reset}`);
      process.exit(1);
    }
    try {
      const { GoogleGenAI } = await import('@google/genai');
      const ai = new GoogleGenAI({ apiKey: config.geminiApiKey });
      const res = await ai.models.generateContent({
        model: config.geminiModel,
        contents: 'Respond with the exact word: CONNECTED',
      });
      console.log(`✅ ${colors.brightGreen}Gemini API Key is ACTIVE and verified!${colors.reset}`);
      console.log(`   Model:    ${colors.bold}${config.geminiModel}${colors.reset}`);
      console.log(`   Response: ${colors.dim}${res.text.trim()}${colors.reset}\n`);
      process.exit(0);
    } catch (err) {
      console.log(`❌ ${colors.brightRed}Gemini API Key verification failed:${colors.reset} ${err.message}\n`);
      process.exit(1);
    }
  }

  // Parse output file
  let outputFile = null;
  const outIdx = args.indexOf('--output') !== -1 ? args.indexOf('--output') : args.indexOf('-o');
  if (outIdx !== -1 && args[outIdx + 1]) {
    outputFile = args[outIdx + 1];
  }

  // Parse path
  let targetDir = '.';
  const pathIdx = args.indexOf('--path');
  if (pathIdx !== -1 && args[pathIdx + 1]) {
    targetDir = args[pathIdx + 1];
  } else {
    const nonFlags = args.filter(a => !a.startsWith('-') && !['audit', 'demo', 'serve', 'interactive'].includes(a) && a !== outputFile);
    if (nonFlags.length > 0) targetDir = nonFlags[0];
  }

  // Parse base branch
  let baseBranch = null;
  const baseIdx = args.indexOf('--base');
  if (baseIdx !== -1 && args[baseIdx + 1]) {
    baseBranch = args[baseIdx + 1];
  }

  const staged = args.includes('--staged');

  if (isDemo) {
    config.mockMode = true;
  }

  if (isInteractive) {
    return runInteractiveMode();
  }

  const orchestrator = new Orchestrator({
    onProgress: (event) => {
      if (!isJson && !isMarkdown) {
        printStep(event.agent, event.message);
      }
    },
  });

  if (!isJson && !isMarkdown) {
    banner();
    console.log(`${colors.cyan}Initiating Multi-Agent Pipeline...${colors.reset}\n`);
  }

  // For demo mode, create realistic sample context if directory is empty of diffs
  let demoDiff = null;
  if (isDemo) {
    demoDiff = `diff --git a/agents/sample-agent/agent.js b/agents/sample-agent/agent.js
new file mode 100644
index 0000000..8a3f912
--- /dev/null
+++ b/agents/sample-agent/agent.js
@@ -0,0 +1,18 @@
+import { GoogleGenAI } from '@google/genai';
+
+// Hardcoded secret for demo scanner detection
+const GEMINI_API_KEY = "AIza" + "Sy" + "DEMO_KEY_123456789012345678901234";
+
+export async function runQuery(prompt) {
+  console.log("Using API key:", GEMINI_API_KEY);
+  const ai = new GoogleGenAI({ apiKey: GEMINI_API_KEY });
+  // Potential injection vulnerability
+  eval("var safePrompt = " + JSON.stringify(prompt));
+  return "Agent response completed";
+}`;
  }

  let serverInstance = null;
  if (isServe) {
    const port = config.port;
    serverInstance = startDashboardServer({ port, host: config.host, initialReport: null, targetDir });
    console.log(`${colors.cyan}Running initial PR review in background...${colors.reset}\n`);
  }

  const report = await orchestrator.runReview({
    targetDir,
    baseBranch,
    staged,
    rawDiff: demoDiff,
  });

  if (serverInstance) {
    serverInstance.updateReport(report);
  }

  if (isJson) {
    console.log(JSON.stringify(report, null, 2));
    process.exit(0);
  }

  if (isMarkdown) {
    console.log(report.markdownReview);
    process.exit(0);
  }

  if (outputFile) {
    fs.writeFileSync(outputFile, report.markdownReview, 'utf8');
    console.log(`\n  💾 ${colors.brightGreen}Markdown review report saved to:${colors.reset} ${path.resolve(outputFile)}`);
  }

  printReport(report);

  if (isServe) {
    console.log(`\n  ✨ ${colors.brightGreen}Dashboard ready! Open http://${config.host}:${config.port} in your browser.${colors.reset}\n`);
  }
}

async function runInteractiveMode() {
  banner();
  console.log(`${colors.bold}${colors.brightCyan}Interactive PR Sentinel Console${colors.reset}\n`);

  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });

  console.log('Select an action:');
  console.log('1. Run Demo Audit (Simulated Multi-Agent Review with Vulnerability Vectors)');
  console.log('2. Audit Current Working Directory');
  console.log('3. Audit Specific Directory');
  console.log('4. Launch Local Web Dashboard (:3737)');
  console.log('5. Exit\n');

  rl.question(`${colors.bold}Enter choice [1-5]: ${colors.reset}`, async (choice) => {
    rl.close();
    switch (choice.trim()) {
      case '1':
        process.argv = ['node', 'cli.js', '--demo'];
        return main();
      case '2':
        process.argv = ['node', 'cli.js', 'audit'];
        return main();
      case '3': {
        const rl2 = readline.createInterface({ input: process.stdin, output: process.stdout });
        rl2.question('Enter path to audit: ', (dir) => {
          rl2.close();
          process.argv = ['node', 'cli.js', 'audit', '--path', dir.trim() || '.'];
          main();
        });
        break;
      }
      case '4':
        process.argv = ['node', 'cli.js', '--demo', '--serve'];
        return main();
      case '5':
        console.log('Exiting PR Sentinel.');
        process.exit(0);
      default:
        console.log('Invalid choice.');
        process.exit(1);
    }
  });
}

main().catch((err) => {
  console.error(`${colors.brightRed}Error in PR Sentinel:${colors.reset}`, err);
  process.exit(1);
});
