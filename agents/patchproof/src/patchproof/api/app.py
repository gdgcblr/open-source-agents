"""FastAPI server and minimalistic interactive dashboard for PatchProof."""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse

from patchproof.config import PatchProofConfig
from patchproof.core.enums import ExecutionMode, ModelMode, SourceKind
from patchproof.core.models import RunInput, VerificationReport
from patchproof.ingestion.fixture_loader import FixtureIngestionError
from patchproof.ingestion.github_loader import GitHubIngestionError
from patchproof.orchestration.pipeline import GRAPH_NODE_ORDER, PatchProofOrchestrator
from patchproof.reporting.composer import ReportComposer

_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>PatchProof — Multi-Agent Software-Change Verification</title>
  <style>
    :root {
      --bg: #0b0f17;
      --surface: #111827;
      --surface-2: #1e293b;
      --border: #2e3b4e;
      --text: #f1f5f9;
      --muted: #94a3b8;
      --accent: #38bdf8;
      --accent-dim: rgba(56, 189, 248, 0.14);
      --green: #22c55e;
      --green-bg: rgba(34, 197, 94, 0.14);
      --red: #ef4444;
      --red-bg: rgba(239, 68, 68, 0.14);
      --amber: #f59e0b;
      --amber-bg: rgba(245, 158, 11, 0.14);
      --purple: #a855f7;
      --purple-bg: rgba(168, 85, 247, 0.14);
      --mono: "JetBrains Mono", "Fira Code", Consolas, monospace;
      --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, sans-serif;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: var(--sans);
      line-height: 1.5;
      padding-bottom: 60px;
    }
    header {
      border-bottom: 1px solid var(--border);
      background: rgba(17, 24, 39, 0.9);
      backdrop-filter: blur(8px);
      position: sticky;
      top: 0;
      z-index: 20;
      padding: 14px 28px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .brand-badge {
      background: var(--accent-dim);
      color: var(--accent);
      border: 1px solid var(--accent);
      font-family: var(--mono);
      font-size: 12px;
      font-weight: 700;
      padding: 3px 8px;
      border-radius: 6px;
    }
    .brand h1 {
      font-size: 18px;
      font-weight: 700;
      letter-spacing: -0.02em;
    }
    .brand p {
      color: var(--muted);
      font-size: 13px;
    }
    .nav-tabs {
      display: flex;
      gap: 8px;
    }
    .tab-btn {
      background: transparent;
      color: var(--muted);
      border: 1px solid var(--border);
      padding: 7px 14px;
      border-radius: 6px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s;
    }
    .tab-btn.active, .tab-btn:hover {
      color: var(--text);
      border-color: var(--accent);
      background: var(--accent-dim);
    }
    .container {
      max-width: 1260px;
      margin: 24px auto;
      padding: 0 24px;
    }
    .card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 20px;
      margin-bottom: 20px;
    }
    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 14px;
    }
    .card-title {
      font-size: 15px;
      font-weight: 700;
      color: var(--text);
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .subtitle {
      font-size: 12px;
      color: var(--muted);
    }
    /* Architecture Pipeline */
    .arch-grid {
      display: grid;
      grid-template-columns: repeat(6, 1fr);
      gap: 10px;
      align-items: stretch;
      margin-top: 12px;
    }
    .arch-node {
      background: var(--surface-2);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      position: relative;
      transition: border-color 0.2s, transform 0.15s;
    }
    .arch-node.active-node {
      border-color: var(--green);
      box-shadow: 0 0 0 1px rgba(34, 197, 94, 0.25);
    }
    .arch-step {
      font-family: var(--mono);
      font-size: 10px;
      color: var(--accent);
      text-transform: uppercase;
      letter-spacing: 0.06em;
      margin-bottom: 4px;
    }
    .arch-name {
      font-size: 13px;
      font-weight: 700;
      margin-bottom: 6px;
    }
    .arch-desc {
      font-size: 11px;
      color: var(--muted);
      margin-bottom: 8px;
    }
    .arch-contract {
      font-family: var(--mono);
      font-size: 10px;
      background: rgba(15, 23, 42, 0.7);
      padding: 4px 6px;
      border-radius: 4px;
      color: #cbd5e1;
      border: 1px solid rgba(148, 163, 184, 0.15);
    }
    /* Controls */
    .controls-bar {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
      justify-content: space-between;
    }
    .preset-group {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }
    .btn {
      background: var(--surface-2);
      color: var(--text);
      border: 1px solid var(--border);
      padding: 9px 15px;
      border-radius: 7px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      transition: all 0.15s;
    }
    .btn:hover {
      border-color: var(--accent);
      background: var(--accent-dim);
    }
    .btn-primary {
      background: var(--accent);
      color: #090d16;
      border-color: var(--accent);
    }
    .btn-primary:hover {
      background: #7dd3fc;
      color: #090d16;
    }
    .gh-input-group {
      display: flex;
      gap: 8px;
      flex: 1;
      max-width: 460px;
    }
    .gh-input {
      flex: 1;
      background: #090d16;
      border: 1px solid var(--border);
      color: var(--text);
      padding: 8px 12px;
      border-radius: 6px;
      font-family: var(--mono);
      font-size: 12px;
    }
    /* Banner */
    .verdict-banner {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 16px 20px;
      border-radius: 10px;
      margin-bottom: 20px;
      border: 1px solid var(--border);
    }
    .verdict-CHANGES_REQUESTED {
      background: var(--red-bg);
      border-color: var(--red);
    }
    .verdict-READY_FOR_HUMAN_REVIEW {
      background: var(--green-bg);
      border-color: var(--green);
    }
    .verdict-INCONCLUSIVE, .verdict-BLOCKED {
      background: var(--amber-bg);
      border-color: var(--amber);
    }
    .badge {
      font-family: var(--mono);
      font-size: 11px;
      font-weight: 700;
      padding: 3px 8px;
      border-radius: 5px;
      display: inline-block;
    }
    .badge-red { background: var(--red-bg); color: #fca5a5; border: 1px solid var(--red); }
    .badge-green { background: var(--green-bg); color: #86efac; border: 1px solid var(--green); }
    .badge-amber { background: var(--amber-bg); color: #fcd34d; border: 1px solid var(--amber); }
    .badge-purple { background: var(--purple-bg); color: #d8b4fe; border: 1px solid var(--purple); }
    .badge-blue { background: var(--accent-dim); color: var(--accent); border: 1px solid var(--accent); }
    /* Tables & Lists */
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    th, td {
      text-align: left;
      padding: 10px 12px;
      border-bottom: 1px solid var(--border);
      vertical-align: top;
    }
    th {
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      font-weight: 600;
    }
    code {
      font-family: var(--mono);
      font-size: 12px;
      background: rgba(15, 23, 42, 0.8);
      padding: 2px 5px;
      border-radius: 4px;
      color: #e2e8f0;
    }
    .grid-2 {
      display: grid;
      grid-template-columns: 1.2fr 0.8fr;
      gap: 20px;
    }
    .finding-item {
      background: var(--surface-2);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 14px;
      margin-bottom: 12px;
    }
    .finding-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
      gap: 8px;
    }
    .finding-title {
      font-weight: 700;
      font-size: 14px;
    }
    .finding-meta {
      font-size: 12px;
      color: var(--muted);
      margin-top: 8px;
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
    }
    .evidence-item {
      border-bottom: 1px solid var(--border);
      padding: 10px 0;
      font-size: 12px;
    }
    .evidence-item:last-child { border-bottom: none; }
    .excerpt-box {
      font-family: var(--mono);
      font-size: 11px;
      background: #090d16;
      border: 1px solid var(--border);
      padding: 8px;
      border-radius: 6px;
      margin-top: 6px;
      white-space: pre-wrap;
      max-height: 110px;
      overflow-y: auto;
      color: #cbd5e1;
    }
    .principles-row {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
      margin-top: 12px;
    }
    .principle-box {
      background: rgba(15, 23, 42, 0.6);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px;
    }
    .principle-box h4 {
      font-size: 12px;
      color: var(--accent);
      margin-bottom: 4px;
    }
    .principle-box p {
      font-size: 11px;
      color: var(--muted);
    }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <span class="brand-badge">PATCHPROOF v0.1</span>
      <div>
        <h1>PatchProof Verification Studio</h1>
        <p>Evidence-driven, multi-agent software-change verification orchestrated with LangGraph</p>
      </div>
    </div>
    <div class="nav-tabs">
      <button class="tab-btn active" onclick="scrollToSection('arch-section')">1. Architecture & Graph</button>
      <button class="tab-btn" onclick="scrollToSection('demo-section')">2. Live Verification Demo</button>
      <button class="tab-btn" onclick="scrollToSection('evidence-section')">3. Evidence Ledger</button>
    </div>
  </header>

  <div class="container">
    <!-- SECTION 1: ARCHITECTURE & LANGGRAPH WORKFLOW -->
    <div id="arch-section" class="card">
      <div class="card-header">
        <div>
          <div class="card-title">Multi-Agent LangGraph Verification Architecture</div>
          <div class="subtitle">Core Principle: A model's confidence is not proof. Every claim must cite immutable Evidence IDs (E-001..) or be marked as a Hypothesis.</div>
        </div>
        <span class="badge badge-blue">LangGraph StateGraph (9 Nodes)</span>
      </div>

      <div class="arch-grid">
        <div class="arch-node" id="node-ingest">
          <div>
            <div class="arch-step">Step 1 • Ingestion</div>
            <div class="arch-name">Confined Snapshot</div>
            <div class="arch-desc">Loads local fixture or read-only GitHub PR. Enforces path confinement, SSRF guards, byte bounds & secret scrubbing.</div>
          </div>
          <div class="arch-contract">Out: ContextSnapshot + E-001..E-005</div>
        </div>

        <div class="arch-node" id="node-intent_analyst">
          <div>
            <div class="arch-step">Step 2 • Agent 1</div>
            <div class="arch-name">Intent Analyst</div>
            <div class="arch-desc">Extracts atomic, testable requirements & invariants. Strips prompt injections & flags vague text as AMBIGUOUS.</div>
          </div>
          <div class="arch-contract">Out: IntentAnalystOutput (R-001..)</div>
        </div>

        <div class="arch-node" id="node-change_investigator">
          <div>
            <div class="arch-step">Step 3 • Agent 2</div>
            <div class="arch-name">Change Investigator</div>
            <div class="arch-desc">Parses unified diff hunks & Python AST symbols, mapping modified lines to extracted requirements.</div>
          </div>
          <div class="arch-contract">Out: ChangeInvestigatorOutput</div>
        </div>

        <div class="arch-node" id="node-parallel">
          <div>
            <div class="arch-step">Step 4 • Parallel Agents 3 & 4</div>
            <div class="arch-name">Test Coverage + Adversarial Reviewer</div>
            <div class="arch-desc">Concurrent dispatch: inventories test assertions (T-001..), flags TEST_GAPs, and formulates falsifiable hypotheses (H-001..).</div>
          </div>
          <div class="arch-contract">Out: Proposals + Hypotheses</div>
        </div>

        <div class="arch-node" id="node-verification_agent">
          <div>
            <div class="arch-step">Step 5 • Agent 5 + Policy</div>
            <div class="arch-name">Verification Agent</div>
            <div class="arch-desc">Enforces allowlisted check profiles (static AST retry bound). Marks sandbox checks NOT_RUN without host fallback.</div>
          </div>
          <div class="arch-contract">Out: CheckResult[] (C-001..) + E-006</div>
        </div>

        <div class="arch-node" id="node-evidence_adjudicator">
          <div>
            <div class="arch-step">Step 6 • Agent 6 + Validator</div>
            <div class="arch-name">Evidence Adjudicator</div>
            <div class="arch-desc">Applies strict evidence precedence. Confirms defects only with non-model evidence; validates report invariants.</div>
          </div>
          <div class="arch-contract">Out: VerificationReport</div>
        </div>
      </div>

      <div class="principles-row">
        <div class="principle-box">
          <h4>Zero Fabricated Execution</h4>
          <p>Unrun container checks are strictly labeled <code>NOT_RUN</code> (<code>exit_code=null</code>)—never faked or run on the host.</p>
        </div>
        <div class="principle-box">
          <h4>Confirmed vs. Hypothesis</h4>
          <p>Adversarial counterexamples remain <code>HYPOTHESIS</code> unless corroborated by deterministic check or source evidence.</p>
        </div>
        <div class="principle-box">
          <h4>Untrusted Data Boundary</h4>
          <p>Prompt injections in issues/PRs are stripped and leaked tokens (<code>ghp_...</code>, <code>sk-...</code>) are redacted to <code>[REDACTED_SECRET]</code>.</p>
        </div>
        <div class="principle-box">
          <h4>Pydantic v2 Fail-Closed</h4>
          <p>Cross-entity validator enforces that every finding, requirement, and check cites resolvable Evidence IDs.</p>
        </div>
      </div>
    </div>

    <!-- SECTION 2: LIVE INTERACTIVE DEMO -->
    <div id="demo-section" class="card">
      <div class="card-header">
        <div>
          <div class="card-title">Live Verification Runner</div>
          <div class="subtitle">Select a checked-in benchmark fixture or verify a public GitHub Pull Request URL in real time</div>
        </div>
        <span id="run-status-pill" class="badge badge-green">Ready</span>
      </div>

      <div class="controls-bar">
        <div class="preset-group">
          <button class="btn btn-primary" onclick="runFixture('retry-limit-bug')">
            ▶ 1. Seeded Defect (retry-limit-bug)
          </button>
          <button class="btn" onclick="runFixture('clean-retry-implementation')">
            ▶ 2. Clean Control (clean-retry-implementation)
          </button>
          <button class="btn" onclick="runFixture('prompt-injection-issue')">
            ▶ 3. Prompt Injection & Secret Redaction
          </button>
        </div>

        <div class="gh-input-group">
          <input id="gh-url-input" class="gh-input" type="text" placeholder="https://github.com/owner/repo/pull/123" />
          <button class="btn" onclick="runGitHubPR()">Verify PR</button>
        </div>
      </div>
    </div>

    <!-- DYNAMIC REPORT VIEW -->
    <div id="report-container" style="display: none;">
      <div id="verdict-banner" class="verdict-banner">
        <div>
          <div style="font-size: 12px; color: var(--muted); font-family: var(--mono);" id="report-meta"></div>
          <div style="font-size: 20px; font-weight: 800; margin-top: 2px;" id="report-verdict"></div>
          <div style="font-size: 13px; margin-top: 4px;" id="report-summary"></div>
        </div>
        <div style="text-align: right;">
          <div class="badge badge-blue" id="report-hash"></div>
        </div>
      </div>

      <!-- Requirements Matrix -->
      <div class="card">
        <div class="card-header">
          <div class="card-title">Requirements & Traceability Matrix</div>
          <div class="subtitle">Atomic criteria linked to AST code locations, inventoried unit tests, and Evidence IDs</div>
        </div>
        <table>
          <thead>
            <tr>
              <th style="width: 90px;">ID</th>
              <th style="width: 95px;">Origin</th>
              <th style="width: 120px;">Status</th>
              <th>Requirement Statement</th>
              <th style="width: 190px;">Code Locations</th>
              <th style="width: 95px;">Tests</th>
              <th style="width: 150px;">Evidence IDs</th>
            </tr>
          </thead>
          <tbody id="requirements-tbody"></tbody>
        </table>
      </div>

      <div class="grid-2">
        <!-- Findings & Checks -->
        <div>
          <div class="card">
            <div class="card-header">
              <div class="card-title">Findings (Confirmed vs. Hypotheses)</div>
              <div class="subtitle">Every confirmed defect requires non-model tool/source evidence</div>
            </div>
            <div id="findings-list"></div>
          </div>

          <div class="card">
            <div class="card-header">
              <div class="card-title">Policy-Reviewed Verification Checks</div>
              <div class="subtitle">Allowlisted static AST & sandbox check profiles</div>
            </div>
            <table>
              <thead>
                <tr>
                  <th>Check</th>
                  <th>Status</th>
                  <th>Exit Code</th>
                  <th>Evidence</th>
                  <th>Output / Reason Not Run</th>
                </tr>
              </thead>
              <tbody id="checks-tbody"></tbody>
            </table>
          </div>
        </div>

        <!-- Agent Timeline & Evidence Ledger -->
        <div>
          <div class="card">
            <div class="card-header">
              <div class="card-title">LangGraph Agent Execution Trace</div>
              <div class="subtitle">Real-time node execution status & summaries</div>
            </div>
            <div id="agent-timeline"></div>
          </div>

          <div id="evidence-section" class="card">
            <div class="card-header">
              <div class="card-title">Append-Only Evidence Ledger</div>
              <div class="subtitle">Immutable SHA-256 hashed excerpts with secret redaction</div>
            </div>
            <div id="evidence-list"></div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <script>
    function scrollToSection(id) {
      const el = document.getElementById(id);
      if (el) el.scrollIntoView({ behavior: 'smooth' });
    }

    function statusBadge(status) {
      const map = {
        'VIOLATED': 'badge-red',
        'FAILED': 'badge-red',
        'CONFIRMED': 'badge-red',
        'CHANGES_REQUESTED': 'badge-red',
        'SATISFIED': 'badge-green',
        'PASSED': 'badge-green',
        'SUCCEEDED': 'badge-green',
        'READY_FOR_HUMAN_REVIEW': 'badge-green',
        'HYPOTHESIS': 'badge-purple',
        'NOT_RUN': 'badge-amber',
        'AMBIGUOUS': 'badge-amber',
        'UNVERIFIED': 'badge-amber',
        'INCONCLUSIVE': 'badge-amber',
      };
      const cls = map[status] || 'badge-blue';
      return `<span class="badge ${cls}">${status}</span>`;
    }

    function escapeHtml(str) {
      if (!str) return '';
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
    }

    async function runFixture(fixtureId) {
      await executeRun({ source: 'fixture', fixture_id: fixtureId });
    }

    async function runGitHubPR() {
      const url = document.getElementById('gh-url-input').value.trim();
      if (!url) {
        alert('Please enter a public GitHub Pull Request URL.');
        return;
      }
      await executeRun({ source: 'github', pull_request_url: url });
    }

    async function executeRun(payload) {
      const pill = document.getElementById('run-status-pill');
      pill.className = 'badge badge-amber';
      pill.textContent = 'Running LangGraph Pipeline...';

      document.querySelectorAll('.arch-node').forEach(el => el.classList.remove('active-node'));

      try {
        const res = await fetch('/api/v1/runs', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.detail || 'Verification run failed');
        }
        renderReport(data);
        pill.className = 'badge badge-green';
        pill.textContent = `Completed (${data.run_id})`;
      } catch (err) {
        pill.className = 'badge badge-red';
        pill.textContent = 'Error';
        alert(err.message);
      }
    }

    function renderReport(report) {
      document.getElementById('report-container').style.display = 'block';
      document.querySelectorAll('.arch-node').forEach(el => el.classList.add('active-node'));

      const banner = document.getElementById('verdict-banner');
      banner.className = `verdict-banner verdict-${report.verdict}`;
      document.getElementById('report-meta').textContent =
        `RUN: ${report.run_id}  •  SOURCE: ${report.source.kind.toUpperCase()} (${report.source.repository})  •  SYNTHETIC: ${report.source.synthetic}`;
      document.getElementById('report-verdict').innerHTML =
        `Advisory Verdict: ${statusBadge(report.verdict)}`;
      document.getElementById('report-summary').textContent = report.summary;
      document.getElementById('report-hash').textContent =
        report.source.snapshot_hash.slice(0, 23) + '...';

      // Requirements
      const reqBody = document.getElementById('requirements-tbody');
      reqBody.innerHTML = report.requirements.map(r => {
        const locs = (r.code_locations || []).map(l => `<code>${escapeHtml(l.path)}:${l.line_start}-${l.line_end}</code>`).join('<br/>') || '<span class="subtitle">none</span>';
        const tests = (r.test_ids || []).map(t => `<code>${escapeHtml(t)}</code>`).join(', ') || '<span class="subtitle">none</span>';
        const evs = (r.evidence_ids || []).map(e => `<code>${escapeHtml(e)}</code>`).join(', ');
        return `<tr>
          <td><code>${escapeHtml(r.requirement_id)}</code></td>
          <td><code>${escapeHtml(r.origin)}</code></td>
          <td>${statusBadge(r.status)}</td>
          <td>${escapeHtml(r.text)}</td>
          <td>${locs}</td>
          <td>${tests}</td>
          <td>${evs}</td>
        </tr>`;
      }).join('');

      // Findings
      const fList = document.getElementById('findings-list');
      if (!report.findings || report.findings.length === 0) {
        fList.innerHTML = '<div class="subtitle">No findings recorded.</div>';
      } else {
        fList.innerHTML = report.findings.map(f => `
          <div class="finding-item">
            <div class="finding-header">
              <div class="finding-title"><code>${escapeHtml(f.finding_id)}</code> ${escapeHtml(f.title)}</div>
              <div>${statusBadge(f.status)} <span class="badge badge-blue">${escapeHtml(f.category)}</span></div>
            </div>
            <div style="font-size: 13px; color: #e2e8f0;">${escapeHtml(f.description)}</div>
            <div style="font-size: 12px; color: #93c5fd; margin-top: 6px;"><strong>Recommended Action:</strong> ${escapeHtml(f.recommended_action)}</div>
            ${f.disproof_criteria ? `<div style="font-size: 11px; color: var(--muted); margin-top: 4px;"><strong>Disproof Criteria:</strong> ${escapeHtml(f.disproof_criteria)}</div>` : ''}
            <div class="finding-meta">
              <span>Severity: <code>${escapeHtml(f.severity)}</code></span>
              <span>Confidence: <code>${escapeHtml(f.confidence)}</code></span>
              <span>Requirements: ${(f.requirement_ids || []).map(r => `<code>${r}</code>`).join(', ') || 'none'}</span>
              <span>Evidence: ${(f.evidence_ids || []).map(e => `<code>${e}</code>`).join(', ')}</span>
            </div>
          </div>
        `).join('');
      }

      // Checks
      const cBody = document.getElementById('checks-tbody');
      cBody.innerHTML = (report.checks || []).map(c => `
        <tr>
          <td><code>${escapeHtml(c.check_id)}</code><br/><span class="subtitle">${escapeHtml(c.name)}</span></td>
          <td>${statusBadge(c.status)}</td>
          <td><code>${c.exit_code !== null && c.exit_code !== undefined ? c.exit_code : 'N/A'}</code></td>
          <td>${(c.evidence_ids || []).map(e => `<code>${e}</code>`).join(', ') || '<span class="subtitle">none</span>'}</td>
          <td style="font-size: 12px;">${escapeHtml(c.reason_not_run || c.output_excerpt || '')}</td>
        </tr>
      `).join('');

      // Agent timeline
      const aTimeline = document.getElementById('agent-timeline');
      aTimeline.innerHTML = (report.agent_runs || []).map(a => `
        <div class="evidence-item">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <strong><code>${escapeHtml(a.agent_name)}</code></strong>
            <div>${statusBadge(a.status)} <span class="subtitle">${a.duration_ms}ms</span></div>
          </div>
          <div style="color: #cbd5e1; margin-top: 4px;">${escapeHtml(a.summary)}</div>
        </div>
      `).join('');

      // Evidence ledger
      const evList = document.getElementById('evidence-list');
      evList.innerHTML = (report.evidence || []).map(ev => `
        <div class="evidence-item">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
              <strong><code>${escapeHtml(ev.evidence_id)}</code></strong>
              <span class="badge badge-blue">${escapeHtml(ev.kind)}</span>
              ${ev.redacted ? '<span class="badge badge-red">REDACTED SECRET</span>' : ''}
            </div>
            <span class="subtitle"><code>${escapeHtml(ev.path || '')}${ev.line_start ? ':' + ev.line_start + '-' + ev.line_end : ''}</code></span>
          </div>
          <div class="excerpt-box">${escapeHtml(ev.content_excerpt)}</div>
        </div>
      `).join('');
    }

    // Auto-run the seeded defect fixture on load so the dashboard is immediately populated
    window.addEventListener('DOMContentLoaded', () => {
      runFixture('retry-limit-bug');
    });
  </script>
</body>
</html>
"""


def create_app(config: PatchProofConfig | None = None) -> FastAPI:
    """Create the FastAPI application serving the PatchProof API and interactive dashboard."""
    cfg = config or PatchProofConfig.from_env()
    app = FastAPI(
        title="PatchProof Verification API",
        version="0.1.0",
        description="Evidence-driven, multi-agent software-change verification.",
    )
    runs_store: dict[str, VerificationReport] = {}
    composer = ReportComposer()

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        return HTMLResponse(content=_DASHBOARD_HTML)

    @app.get("/api/v1/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": "0.1.0",
            "graph_nodes": list(GRAPH_NODE_ORDER),
            "fixtures": [
                "retry-limit-bug",
                "clean-retry-implementation",
                "prompt-injection-issue",
            ],
        }

    @app.post("/api/v1/runs")
    def create_run(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            source = SourceKind(str(payload.get("source", "fixture")))
            run_input = RunInput(
                source=source,
                fixture_id=payload.get("fixture_id"),
                pull_request_url=payload.get("pull_request_url"),
                execution_mode=ExecutionMode(str(payload.get("execution_mode", "static_only"))),
                model_mode=ModelMode(str(payload.get("model_mode", "deterministic"))),
            )
            orchestrator = PatchProofOrchestrator(config=cfg)
            report = orchestrator.execute(run_input)
            runs_store[report.run_id] = report
            return report.model_dump(mode="json")
        except (
            ValueError,
            FixtureIngestionError,
            GitHubIngestionError,
        ) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/v1/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        report = runs_store.get(run_id)
        if report is None:
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
        return report.model_dump(mode="json")

    @app.get("/api/v1/runs/{run_id}/report.md", response_class=PlainTextResponse)
    def get_run_markdown(run_id: str) -> PlainTextResponse:
        report = runs_store.get(run_id)
        if report is None:
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
        return PlainTextResponse(content=composer.render_markdown(report))

    return app

