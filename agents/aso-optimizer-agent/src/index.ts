/**
 * ASO Optimizer Agent — CLI Entry Point
 * ======================================
 * Accepts input via interactive prompts or a built-in --demo flag.
 *
 * Usage:
 *   npm run dev          → interactive mode
 *   npm run demo         → demo mode (pre-loaded sample app)
 */

import * as readline from "readline";
import * as dotenv    from "dotenv";
import { AppListing, ASOReport } from "./shared/types";
import { runHubOrchestrator }    from "./hub/orchestrator";

dotenv.config();

// ── Report Printer ────────────────────────────────────────────

function printReport(report: ASOReport): void {
  const line  = "═".repeat(60);
  const dash  = "─".repeat(60);

  console.log("\n" + line);
  console.log("  📊  ASO OPTIMIZATION REPORT  —  " + report.appName);
  console.log(line);

  console.log(`\n🏷️  OPTIMIZED TITLE  [${report.optimizedTitle.content.length} chars | via ${report.optimizedTitle.modelUsed}]`);
  console.log(dash);
  console.log("  " + report.optimizedTitle.content);

  console.log(`\n🗝️  KEYWORDS  [via ${report.keywords.modelUsed}]`);
  console.log(dash);
  console.log("  " + report.keywords.content);

  console.log(`\n📝 OPTIMIZED DESCRIPTION  [via ${report.optimizedDescription.modelUsed}]`);
  console.log(dash);
  report.optimizedDescription.content
    .split("\n")
    .forEach(l => console.log("  " + l));

  if (report.guardrailNotes.length > 0) {
    console.log(`\n🛡️  GUARDRAIL NOTES`);
    console.log(dash);
    report.guardrailNotes.forEach(n => console.log("  " + n));
  }

  console.log("\n" + line);
  console.log("  ✅  " + report.summary);
  console.log(line + "\n");
}

// ── Interactive Input ─────────────────────────────────────────

async function promptForListing(): Promise<AppListing> {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  const ask = (q: string) => new Promise<string>(res => rl.question(q, res));

  console.log("\n" + "═".repeat(60));
  console.log("  🚀 ASO Optimizer Agent");
  console.log("  Hub & Spoke │ Guardrails │ Gemini → Gemma → Fallback");
  console.log("  GDG Cloud Bengaluru — Road to DevFest 2026");
  console.log("═".repeat(60));
  console.log("\nEnter your app details:\n");

  const appName           = await ask("App Name               : ");
  const currentTitle      = await ask("Current Play Store Title: ");
  const category          = await ask("Category (e.g. Finance) : ");
  const targetAudience    = await ask("Target Audience         : ");

  console.log("\nCurrent Description (paste below, then press Enter on an empty line):");
  let currentDescription = "";
  let blankCount = 0;

  // Temporarily switch to line-by-line reading
  rl.close();
  const rl2 = readline.createInterface({ input: process.stdin, output: process.stdout });
  
  await new Promise<void>(resolve => {
    rl2.on("line", line => {
      if (line.trim() === "") {
        blankCount++;
        if (blankCount >= 1) { rl2.close(); resolve(); return; }
      } else {
        blankCount = 0;
        currentDescription += line + "\n";
      }
    });
    rl2.on("close", resolve);
  });

  return { appName, currentTitle, category, targetAudience, currentDescription: currentDescription.trim() };
}

// ── Demo Listing ──────────────────────────────────────────────

function getDemoListing(): AppListing {
  return {
    appName:            "TaskFlow",
    currentTitle:       "TaskFlow - Best Todo List App & Planner in the World",
    category:           "Productivity",
    targetAudience:     "Professionals and students",
    currentDescription: `TaskFlow is a simple to-do list. You can add tasks and delete them.
It has reminders. It syncs to cloud. It is the best app ever made for tasks.
100% free and guaranteed to make you productive. Download now it is the #1 app!
Works on all Android phones and tablets.`,
  };
}

// ── Main ──────────────────────────────────────────────────────

async function main(): Promise<void> {
  const isDemo = process.argv.includes("--demo");

  const listing: AppListing = isDemo
    ? (() => { console.log("\n🎬 DEMO MODE — using sample app listing (TaskFlow)...\n"); return getDemoListing(); })()
    : await promptForListing();

  const report = await runHubOrchestrator(listing);

  if (report) {
    printReport(report);
  } else {
    console.log("\n❌ Optimization pipeline was blocked by the input guardrail.\n");
    process.exit(1);
  }
}

main().catch(err => {
  console.error("\n💥 Unexpected error:", err);
  process.exit(1);
});
