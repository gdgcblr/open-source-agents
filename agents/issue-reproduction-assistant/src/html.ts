import type { Investigation } from "./pipeline.js";

export interface HtmlReportMeta {
  title: string;
  issueUrl?: string;
  repoUrl?: string;
  commit?: string;
  issueText?: string;
  generatedAt?: Date;
}

const UI_PATTERN =
  /\b(ui|css|layout|screenshot|image|images|button|page|render(?:s|ed|ing)?|display(?:s|ed)?|broken|404|visible|style|styles|responsive|mobile|dark mode|overflow|alignment|font|icon|modal|navbar|menu)\b/i;

export function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

const e = escapeHtml;

function list(items: string[], ordered = false): string {
  if (items.length === 0) {
    return '<p class="muted">None identified.</p>';
  }
  const tag = ordered ? "ol" : "ul";
  return `<${tag}>${items.map((item) => `<li>${e(item)}</li>`).join("")}</${tag}>`;
}

function codeBlock(code: string): string {
  return `<pre><code>${e(code)}</code></pre>`;
}

/** Page routes or asset paths the reporter put in backticks, e.g. `/learnt`. */
export function extractRoutes(issueText: string): string[] {
  const found = new Set<string>();
  for (const match of issueText.matchAll(/`(\/[A-Za-z0-9_\-./*[\]{}]*)`/g)) {
    if (match[1].length > 1 && !/\.(?:ts|tsx|js|jsx|md)$/.test(match[1])) {
      found.add(match[1]);
    }
  }
  return [...found].slice(0, 6);
}

export function isVisualIssue(text: string): boolean {
  return UI_PATTERN.test(text);
}

/** Deterministic "from scratch" steps; none of them are executed by the agent. */
export function buildScratchSteps(investigation: Investigation, meta: HtmlReportMeta): string[] {
  const { setup } = investigation;
  const steps: string[] = [];
  const repoName = meta.repoUrl?.split("/").pop()?.replace(/\.git$/, "") ?? "project";

  steps.push(
    `Prerequisites: git${setup.ecosystem === "node" ? ` and Node.js${setup.nodeVersion ? ` ${setup.nodeVersion}` : " (current LTS)"}${setup.packageManager && setup.packageManager !== "npm" ? `, plus ${setup.packageManager}` : ""}` : ""}, and a web browser.`,
  );
  if (meta.repoUrl) {
    steps.push(
      `Get the code at the revision this analysis used: ${`git clone ${meta.repoUrl}.git && cd ${repoName}`}${meta.commit ? ` && git checkout ${meta.commit}` : ""}`,
    );
  }
  if (setup.installCommand) {
    steps.push(`Install dependencies: ${setup.installCommand}`);
  }
  if (setup.runCommand) {
    steps.push(
      `Start the app: ${setup.runCommand}${setup.defaultUrl ? ` (it usually serves ${setup.defaultUrl}; use the URL printed in the terminal)` : ""}`,
    );
  } else {
    steps.push("Start the app using the instructions in the project README (no dev/start script was detected).");
  }

  const text = meta.issueText ?? "";
  const routes = extractRoutes(text);
  const visual = isVisualIssue(`${meta.title}\n${text}`);
  const base = setup.defaultUrl ?? "http://localhost:<port>";

  if (visual) {
    steps.push(
      `Open ${base}${routes.find((r) => !r.includes(".") && !r.includes("*")) ?? ""} in your browser${routes.length > 1 ? ", and also visit the other pages/paths named in the issue" : ""}.`,
    );
    steps.push(
      "Open DevTools (F12): check the Console for errors and the Network tab (filter by Img or sort by Status) for 404s or failed requests.",
    );
    steps.push(`Look for the symptom reported in the issue: "${meta.title}".`);
  } else {
    steps.push(`Trigger the behaviour described in the issue: "${meta.title}".`);
  }

  const reporterSteps = [...text.matchAll(/^\s*\d+[.)]\s+(.+)$/gm)].map((m) => m[1].trim()).slice(0, 8);
  if (reporterSteps.length > 0) {
    steps.push(`Follow the reporter's own steps: ${reporterSteps.join(" → ")}`);
  }
  for (const step of investigation.report.reproductionSteps) {
    if (!steps.includes(step) && !/does not list numbered steps/i.test(step)) {
      steps.push(step);
    }
  }
  return steps;
}

const STYLE = `
:root{color-scheme:light dark;--bg:#0f1115;--card:#171a21;--line:#2a2f3a;--text:#e6e8ee;--muted:#9aa3b2;--accent:#7aa2ff}
@media (prefers-color-scheme:light){:root{--bg:#f6f7fb;--card:#fff;--line:#dfe3ec;--text:#1b1f2a;--muted:#5b6475;--accent:#2f5bea}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:16px/1.6 system-ui,sans-serif}
main{max-width:920px;margin:0 auto;padding:32px 20px 80px}
h1{font-size:1.7rem;margin:0 0 6px}h2{font-size:1.2rem;margin:0 0 10px}
section{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 22px;margin:18px 0}
a{color:var(--accent)}.muted{color:var(--muted)}
.badge{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:2px 10px;font-size:.8rem;margin-right:6px}
pre{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:12px;overflow:auto;font-size:.85rem}
code{font-family:ui-monospace,Menlo,monospace;font-size:.88em}
li{margin:6px 0}.steps li::marker{font-weight:700;color:var(--accent)}
.hero{border-color:var(--accent)}.ev{margin:8px 0 14px}
table{width:100%;border-collapse:collapse;font-size:.9rem}td,th{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
`;

export function renderReportHtml(investigation: Investigation, meta: HtmlReportMeta): string {
  const { report } = investigation;
  const mode =
    investigation.mode === "llm"
      ? `Model-assisted (${investigation.provider}/${investigation.model})`
      : "Offline evidence-only";
  const steps = buildScratchSteps(investigation, meta);

  const areas = report.likelyAreas.length
    ? `<table><tr><th>File</th><th>Confidence</th><th>Why</th></tr>${report.likelyAreas
        .map((a) => `<tr><td><code>${e(a.path)}</code></td><td>${e(a.confidence)}</td><td>${e(a.reason)}</td></tr>`)
        .join("")}</table>`
    : '<p class="muted">No code location could be identified.</p>';

  const evidence = investigation.candidates
    .slice(0, 5)
    .map((candidate) => {
      const lines = candidate.evidence
        .slice(0, 4)
        .map((item) => `L${item.line}: ${item.text}  // ${item.reason}`)
        .join("\n");
      const commits = (investigation.history[candidate.path] ?? [])
        .map((c) => `<li><code>${e(c.hash)}</code> ${e(c.date)} — ${e(c.subject)}</li>`)
        .join("");
      return `<div class="ev"><strong><code>${e(candidate.path)}</code></strong> <span class="muted">score ${candidate.score}</span>${codeBlock(lines)}${commits ? `<ul>${commits}</ul>` : ""}</div>`;
    })
    .join("");

  const test = report.reproductionTest
    ? `<section><h2>Draft failing test <span class="muted">(not executed)</span></h2><p>Suggested file: <code>${e(report.reproductionTest.suggestedPath)}</code> · ${e(report.reproductionTest.framework)}</p>${codeBlock(report.reproductionTest.code)}</section>`
    : "";

  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Reproduction brief — ${e(meta.title)}</title><style>${STYLE}</style></head>
<body><main>
<h1>${e(meta.title)}</h1>
<p>${meta.issueUrl ? `<a href="${e(meta.issueUrl)}" rel="noopener noreferrer">${e(meta.issueUrl)}</a> · ` : ""}<span class="badge">${e(mode)}</span><span class="badge">severity: ${e(report.severity)}</span>${meta.commit ? `<span class="badge">commit ${e(meta.commit.slice(0, 9))}</span>` : ""}</p>
<p class="muted">Hypotheses and steps are unverified suggestions; the agent never ran the project's code.</p>

<section class="hero"><h2>Reproduce it from scratch</h2><ol class="steps">${steps.map((s) => `<li>${e(s)}</li>`).join("")}</ol></section>

<section><h2>Summary</h2><p>${e(report.summary)}</p></section>
<section><h2>Likely areas</h2>${areas}</section>
<section><h2>Hypotheses</h2>${list(report.hypotheses)}</section>
<section><h2>What would confirm or rule this out</h2>${list(report.confirmationCriteria)}</section>
<section><h2>Questions for the reporter</h2>${list(report.questionsForReporter)}</section>
<section><h2>Candidate tests</h2>${list(report.candidateTests)}</section>
${test}
<section><h2>Evidence from the repository</h2>${evidence || '<p class="muted">No matching files.</p>'}</section>
${investigation.warnings.length ? `<section><h2>Warnings</h2>${list(investigation.warnings)}</section>` : ""}
<p class="muted">Generated ${e((meta.generatedAt ?? new Date()).toISOString())} by Issue Reproduction Assistant.</p>
</main></body></html>
`;
}
