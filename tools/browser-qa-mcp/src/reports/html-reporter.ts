import { existsSync, readFileSync } from "node:fs";
import type { NetworkEvidenceEntry, RunResult, StepResult, TestResult } from "../types/test-plan.js";

/**
 * Renders a RunResult as a single, self-contained HTML file: screenshots are
 * inlined as base64 data URIs so the report has no external file
 * dependencies and can be opened, emailed, or attached anywhere on its own.
 *
 * Every piece of text that originated outside this codebase - console
 * messages, network URLs, assertion error text, selectors from the test
 * plan - is run through escapeHtml() before being placed in the output.
 * None of that text is trusted: it can come from the page under test (an
 * attacker-controlled app could put `<script>` in a console.error call) or
 * from an AI-generated test plan, so unescaped interpolation here would be a
 * stored-XSS hole in a file this tool itself generates.
 */
export function renderHtmlReport(result: RunResult): string {
  const passCount = result.tests.filter((t) => t.status === "PASS").length;
  const failCount = result.tests.filter((t) => t.status === "FAIL").length;
  const blockedCount = result.tests.filter((t) => t.status === "BLOCKED").length;

  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>QA Report - ${escapeHtml(result.planName)}</title>
<style>${CSS}</style>
</head>
<body>
  <header>
    <h1>${escapeHtml(result.planName)}</h1>
    <p class="meta">Run <code>${escapeHtml(result.runId)}</code> against ${escapeHtml(result.baseUrl)} - ${formatRange(result.startedAt, result.finishedAt)}</p>
    <div class="summary">
      <span class="badge status-${result.status.toLowerCase()}">${escapeHtml(result.status)}</span>
      <span class="count pass">${passCount} passed</span>
      <span class="count fail">${failCount} failed</span>
      <span class="count blocked">${blockedCount} blocked</span>
    </div>
  </header>
  <main>
${result.tests.map(renderTest).join("\n")}
  </main>
</body>
</html>
`;
}

function renderTest(test: TestResult): string {
  const stepsHtml = test.steps.map(renderStep).join("\n");
  const screenshotsHtml = test.screenshotPaths.map(renderScreenshot).join("\n");

  const consoleHtml = test.consoleErrors.length
    ? `<div class="evidence-block">
      <h4>Console Errors</h4>
      <ul>${test.consoleErrors.map((e) => `<li><code>[${escapeHtml(e.type)}]</code> ${escapeHtml(e.text)}</li>`).join("")}</ul>
    </div>`
    : "";

  const networkHtml = test.networkFailures.length
    ? `<div class="evidence-block">
      <h4>Network Failures</h4>
      <ul>${test.networkFailures.map(renderNetworkEntry).join("")}</ul>
    </div>`
    : "";

  const traceHtml = test.tracePath
    ? `<p class="trace-link">Trace saved at <code>${escapeHtml(test.tracePath)}</code> - view it with <code>npx playwright show-trace ${escapeHtml(test.tracePath)}</code> (runs entirely locally; no data leaves this machine).</p>`
    : "";

  return `    <section class="test status-${test.status.toLowerCase()}">
      <h2><span class="badge status-${test.status.toLowerCase()}">${escapeHtml(test.status)}</span> ${escapeHtml(test.name)} <span class="test-id">${escapeHtml(test.id)}</span></h2>
      ${test.error ? `<p class="error">${escapeHtml(test.error)}</p>` : ""}
      <ol class="steps">
${stepsHtml}
      </ol>
      ${screenshotsHtml}
      ${consoleHtml}
      ${networkHtml}
      ${traceHtml}
    </section>`;
}

function renderStep(step: StepResult): string {
  return `        <li class="step status-${step.status}">
          <span class="step-action">${escapeHtml(step.action)}</span>
          ${step.selector ? `<code>${escapeHtml(step.selector)}</code>` : ""}
          <span class="step-duration">${step.durationMs}ms</span>
          ${step.message ? `<p class="step-message">${escapeHtml(step.message)}</p>` : ""}
        </li>`;
}

function renderNetworkEntry(entry: NetworkEvidenceEntry): string {
  const status = entry.status ? `&rarr; ${entry.status}` : "";
  const failure = entry.failureText ? ` (${escapeHtml(entry.failureText)})` : "";
  return `<li><code>${escapeHtml(entry.method)}</code> ${escapeHtml(entry.url)} ${status}${failure}</li>`;
}

function renderScreenshot(path: string): string {
  if (!existsSync(path)) {
    return `<p class="screenshot-missing">Screenshot not found on disk: <code>${escapeHtml(path)}</code></p>`;
  }
  const data = readFileSync(path).toString("base64");
  return `<figure class="screenshot"><img src="data:image/png;base64,${data}" alt="Screenshot captured during the test" /><figcaption>${escapeHtml(path)}</figcaption></figure>`;
}

function formatRange(startedAt: string, finishedAt: string): string {
  const durationMs = new Date(finishedAt).getTime() - new Date(startedAt).getTime();
  return `${new Date(startedAt).toLocaleString()} (${durationMs}ms)`;
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

const CSS = `
  :root { --pass: #15803d; --fail: #b91c1c; --blocked: #b45309; --bg: #ffffff; --fg: #1f2937; --muted: #6b7280; --border: #e5e7eb; --code-bg: #f3f4f6; }
  @media (prefers-color-scheme: dark) {
    :root { --bg: #0f172a; --fg: #e2e8f0; --muted: #94a3b8; --border: #1e293b; --code-bg: #1e293b; }
  }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: var(--bg); color: var(--fg); margin: 0; padding: 2rem 1rem; }
  main, header { max-width: 860px; margin-inline: auto; }
  header { margin-bottom: 2rem; }
  header h1 { margin: 0 0 0.25rem; font-size: 1.4rem; word-break: break-word; }
  .meta { color: var(--muted); font-size: 0.85rem; margin: 0 0 1rem; }
  .meta code { background: var(--code-bg); padding: 0.1rem 0.35rem; border-radius: 4px; }
  .summary { display: flex; flex-wrap: wrap; gap: 0.75rem; align-items: center; }
  .badge { display: inline-block; padding: 0.2rem 0.6rem; border-radius: 999px; font-size: 0.75rem; font-weight: 600; letter-spacing: 0.02em; color: #fff; }
  .badge.status-pass { background: var(--pass); }
  .badge.status-fail { background: var(--fail); }
  .badge.status-blocked { background: var(--blocked); }
  .count { font-size: 0.85rem; color: var(--muted); }
  .count.pass { color: var(--pass); }
  .count.fail { color: var(--fail); }
  .count.blocked { color: var(--blocked); }
  .test { border: 1px solid var(--border); border-left: 4px solid var(--border); border-radius: 8px; padding: 1rem 1.25rem; margin-bottom: 1.25rem; }
  .test.status-pass { border-left-color: var(--pass); }
  .test.status-fail { border-left-color: var(--fail); }
  .test.status-blocked { border-left-color: var(--blocked); }
  .test h2 { font-size: 1.05rem; margin: 0 0 0.5rem; display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
  .test-id { color: var(--muted); font-size: 0.8rem; font-weight: 400; }
  .error { color: var(--fail); font-weight: 500; }
  .steps { padding-left: 1.25rem; margin: 0.75rem 0; }
  .step { margin-bottom: 0.4rem; font-size: 0.875rem; }
  .step code { background: var(--code-bg); padding: 0.1rem 0.35rem; border-radius: 4px; font-size: 0.8rem; word-break: break-all; }
  .step.status-failed .step-action, .step.status-blocked .step-action { color: var(--fail); font-weight: 600; }
  .step-duration { color: var(--muted); font-size: 0.75rem; margin-left: 0.4rem; }
  .step-message { margin: 0.15rem 0 0; color: var(--muted); font-size: 0.8rem; }
  .evidence-block { margin-top: 0.75rem; font-size: 0.85rem; }
  .evidence-block h4 { margin: 0 0 0.3rem; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.03em; color: var(--muted); }
  .evidence-block ul { margin: 0; padding-left: 1.1rem; word-break: break-word; }
  .screenshot { margin: 0.75rem 0; }
  .screenshot img { max-width: 100%; border: 1px solid var(--border); border-radius: 6px; display: block; }
  .screenshot figcaption { font-size: 0.75rem; color: var(--muted); margin-top: 0.25rem; word-break: break-all; }
  .trace-link { font-size: 0.8rem; color: var(--muted); }
  .trace-link code { background: var(--code-bg); padding: 0.1rem 0.35rem; border-radius: 4px; word-break: break-all; }
  .screenshot-missing { font-size: 0.8rem; color: var(--muted); font-style: italic; }
`;
