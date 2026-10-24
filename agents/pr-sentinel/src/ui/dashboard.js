/**
 * PR Sentinel - Embedded Web Dashboard
 * Lightweight, zero-dependency, local visual UI for interactive PR review exploration.
 */

import http from 'node:http';
import { Orchestrator } from '../agents/orchestrator.js';

/**
 * Start the local web dashboard server
 * @param {Object} options
 * @param {number} [options.port=3737]
 * @param {string} [options.host='localhost']
 * @param {Object} [options.initialReport]
 * @param {string} [options.targetDir='.']
 * @returns {http.Server}
 */
export function startDashboardServer({ port = 3737, host = 'localhost', initialReport = null, targetDir = '.' } = {}) {
  let latestReport = initialReport;

  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url, `http://${req.headers.host || `${host}:${port}`}`);

    // API: Get latest report JSON
    if (url.pathname === '/api/report') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(latestReport || { error: 'No report generated yet' }));
      return;
    }

    // API: Trigger re-run
    if (url.pathname === '/api/run' && req.method === 'POST') {
      try {
        const orchestrator = new Orchestrator();
        latestReport = await orchestrator.runReview({ targetDir });
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(latestReport));
      } catch (err) {
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: err.message }));
      }
      return;
    }

    // Serve HTML Dashboard
    if (url.pathname === '/' || url.pathname === '/index.html') {
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end(renderDashboardHtml(latestReport));
      return;
    }

    res.writeHead(404, { 'Content-Type': 'text/plain' });
    res.end('Not Found');
  });

  server.listen(port, host, () => {
    console.log(`\n  🌐 PR Sentinel Web Dashboard is live at: http://${host}:${port}`);
    console.log(`  Hit Ctrl+C to stop the dashboard server.\n`);
  });

  return server;
}

function renderDashboardHtml(report) {
  const safeData = JSON.stringify(report || {}).replace(/</g, '\\u003c');

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>PR Sentinel - Autonomous Multi-Agent PR Review Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #090d16;
      --card-bg: rgba(22, 30, 49, 0.75);
      --card-border: rgba(255, 255, 255, 0.08);
      --primary: #38bdf8;
      --primary-glow: rgba(56, 189, 248, 0.15);
      --success: #34d399;
      --warning: #fbbf24;
      --danger: #f87171;
      --text: #f8fafc;
      --text-muted: #94a3b8;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Inter', -apple-system, sans-serif;
      background-color: var(--bg);
      color: var(--text);
      min-height: 100vh;
      line-height: 1.5;
      background-image: 
        radial-gradient(at 0% 0%, rgba(56, 189, 248, 0.12) 0px, transparent 50%),
        radial-gradient(at 100% 100%, rgba(139, 92, 246, 0.12) 0px, transparent 50%);
    }

    header {
      padding: 1.5rem 2rem;
      border-bottom: 1px solid var(--card-border);
      backdrop-filter: blur(12px);
      display: flex;
      justify-content: space-between;
      align-items: center;
      position: sticky;
      top: 0;
      z-index: 50;
      background: rgba(9, 13, 22, 0.85);
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }

    .logo-badge {
      width: 40px;
      height: 40px;
      border-radius: 10px;
      background: linear-gradient(135deg, #38bdf8, #818cf8);
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 800;
      font-size: 1.25rem;
      color: #090d16;
      box-shadow: 0 0 20px rgba(56, 189, 248, 0.4);
    }

    .brand h1 { font-size: 1.25rem; font-weight: 700; letter-spacing: -0.02em; }
    .brand p { font-size: 0.8rem; color: var(--text-muted); }

    .header-actions { display: flex; gap: 0.75rem; align-items: center; }

    .btn {
      padding: 0.5rem 1rem;
      border-radius: 8px;
      font-size: 0.85rem;
      font-weight: 600;
      cursor: pointer;
      border: 1px solid transparent;
      transition: all 0.2s ease;
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      font-family: inherit;
    }

    .btn-primary {
      background: linear-gradient(135deg, #38bdf8, #6366f1);
      color: #fff;
    }
    .btn-primary:hover { opacity: 0.9; transform: translateY(-1px); box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3); }

    .btn-secondary {
      background: rgba(255, 255, 255, 0.05);
      border-color: var(--card-border);
      color: var(--text);
    }
    .btn-secondary:hover { background: rgba(255, 255, 255, 0.1); }

    .container {
      max-width: 1280px;
      margin: 2rem auto;
      padding: 0 1.5rem;
    }

    .hero-grid {
      display: grid;
      grid-template-columns: 280px 1fr;
      gap: 1.5rem;
      margin-bottom: 2rem;
    }

    .score-card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 1.75rem;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      text-align: center;
      backdrop-filter: blur(8px);
    }

    .score-circle {
      width: 120px;
      height: 120px;
      border-radius: 50%;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      margin: 1rem 0;
      position: relative;
    }

    .score-num { font-size: 2.75rem; font-weight: 800; line-height: 1; }
    .score-label { font-size: 0.75rem; text-transform: uppercase; color: var(--text-muted); font-weight: 600; }

    .verdict-badge {
      padding: 0.35rem 0.85rem;
      border-radius: 9999px;
      font-size: 0.8rem;
      font-weight: 700;
      letter-spacing: 0.05em;
    }

    .badge-approved { background: rgba(52, 211, 153, 0.15); color: var(--success); border: 1px solid rgba(52, 211, 153, 0.3); }
    .badge-warn { background: rgba(251, 191, 36, 0.15); color: var(--warning); border: 1px solid rgba(251, 191, 36, 0.3); }
    .badge-fail { background: rgba(248, 113, 113, 0.15); color: var(--danger); border: 1px solid rgba(248, 113, 113, 0.3); }

    .summary-card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 1.75rem;
      backdrop-filter: blur(8px);
    }

    .agents-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 1rem;
      margin-top: 1.25rem;
    }

    .agent-pill {
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 1rem;
      transition: border-color 0.2s;
    }
    .agent-pill:hover { border-color: rgba(56, 189, 248, 0.4); }

    .agent-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; }
    .agent-name { font-weight: 600; font-size: 0.9rem; }
    .agent-score { font-size: 0.8rem; font-weight: 700; }

    .tabs {
      display: flex;
      gap: 0.5rem;
      border-bottom: 1px solid var(--card-border);
      margin-bottom: 1.5rem;
    }

    .tab {
      padding: 0.75rem 1.25rem;
      background: none;
      border: none;
      color: var(--text-muted);
      font-size: 0.9rem;
      font-weight: 600;
      cursor: pointer;
      position: relative;
      font-family: inherit;
    }
    .tab.active { color: var(--primary); }
    .tab.active::after {
      content: '';
      position: absolute;
      bottom: -1px;
      left: 0;
      right: 0;
      height: 2px;
      background: var(--primary);
    }

    .tab-content { display: none; }
    .tab-content.active { display: block; }

    .finding-card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 1.25rem;
      margin-bottom: 1rem;
    }

    .finding-card.critical { border-left: 4px solid var(--danger); }
    .finding-card.high { border-left: 4px solid #fb923c; }
    .finding-card.medium { border-left: 4px solid var(--warning); }
    .finding-card.info { border-left: 4px solid var(--primary); }

    .finding-title { font-size: 1rem; font-weight: 600; display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.35rem; }
    .finding-desc { color: var(--text-muted); font-size: 0.88rem; margin-bottom: 0.5rem; }
    .finding-rec { background: rgba(52, 211, 153, 0.08); border-radius: 6px; padding: 0.5rem 0.75rem; font-size: 0.85rem; color: #6ee7b7; }

    pre {
      background: #0d121f;
      border: 1px solid rgba(255, 255, 255, 0.06);
      border-radius: 8px;
      padding: 1rem;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.82rem;
      overflow-x: auto;
      color: #e2e8f0;
    }

    .diff-add { color: #86efac; background: rgba(34, 197, 94, 0.1); }
    .diff-del { color: #fca5a5; background: rgba(239, 68, 68, 0.1); }

    .markdown-box {
      background: #0d121f;
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 1.5rem;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.82rem;
      white-space: pre-wrap;
      position: relative;
    }

    .copy-btn {
      position: absolute;
      top: 1rem;
      right: 1rem;
    }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <div class="logo-badge">PS</div>
      <div>
        <h1>PR Sentinel</h1>
        <p>Autonomous Multi-Agent Review & Triage System</p>
      </div>
    </div>
    <div class="header-actions">
      <button class="btn btn-secondary" onclick="runScan()">⚡ Re-Run Audit</button>
      <button class="btn btn-primary" onclick="copyMarkdown()">📋 Copy GitHub PR Review</button>
    </div>
  </header>

  <div class="container">
    <div class="hero-grid">
      <div class="score-card">
        <span class="score-label">Readiness Score</span>
        <div class="score-circle" id="scoreCircle">
          <span class="score-num" id="scoreNum">--</span>
          <span class="score-label">/ 100</span>
        </div>
        <div id="verdictBadge" class="verdict-badge">ANALYZING</div>
      </div>

      <div class="summary-card">
        <h2 style="font-size: 1.1rem; margin-bottom: 0.5rem;">Orchestrated Agent Swarm</h2>
        <p style="color: var(--text-muted); font-size: 0.88rem;" id="execSummary">
          PR Sentinel coordinates 4 specialized autonomous agents to evaluate security, guidelines compliance, code quality, and automated patch remediation.
        </p>

        <div class="agents-grid">
          <div class="agent-pill">
            <div class="agent-header">
              <span class="agent-name">🛡️ SecuritySentinel</span>
              <span class="agent-score" id="secScore">--/100</span>
            </div>
            <p style="font-size: 0.78rem; color: var(--text-muted);" id="secDesc">Scans leaked API keys & dangerous code execution</p>
          </div>

          <div class="agent-pill">
            <div class="agent-header">
              <span class="agent-name">📋 ComplianceAuditor</span>
              <span class="agent-score" id="compScore">--/100</span>
            </div>
            <p style="font-size: 0.78rem; color: var(--text-muted);" id="compDesc">Enforces CONTRIBUTING.md & repo isolation</p>
          </div>

          <div class="agent-pill">
            <div class="agent-header">
              <span class="agent-name">🏗️ QualityCritic</span>
              <span class="agent-score" id="qaScore">--/100</span>
            </div>
            <p style="font-size: 0.78rem; color: var(--text-muted);" id="qaDesc">Evaluates architecture & error resilience</p>
          </div>
        </div>
      </div>
    </div>

    <div class="tabs">
      <button class="tab active" onclick="switchTab('tab-findings')">🔍 All Findings</button>
      <button class="tab" onclick="switchTab('tab-patches')">🛠️ Auto-Patches (<span id="patchCount">0</span>)</button>
      <button class="tab" onclick="switchTab('tab-timeline')">⏱️ Agent Timeline</button>
      <button class="tab" onclick="switchTab('tab-markdown')">📝 GitHub PR Review Markdown</button>
    </div>

    <div id="tab-findings" class="tab-content active">
      <div id="findingsList">Loading findings...</div>
    </div>

    <div id="tab-patches" class="tab-content">
      <div id="patchesList">No patches available.</div>
    </div>

    <div id="tab-timeline" class="tab-content">
      <div id="timelineList" style="background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 12px; padding: 1.5rem;">
        Timeline loading...
      </div>
    </div>

    <div id="tab-markdown" class="tab-content">
      <div class="markdown-box">
        <button class="btn btn-secondary copy-btn" onclick="copyMarkdown()">Copy Markdown</button>
        <div id="markdownContent">Loading markdown review...</div>
      </div>
    </div>
  </div>

  <script>
    let reportData = ${safeData};

    function switchTab(tabId) {
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      event.target.classList.add('active');
      document.getElementById(tabId).classList.add('active');
    }

    function renderReport(data) {
      if (!data || !data.agents) return;
      reportData = data;

      // Score
      const score = data.compositeScore || 0;
      document.getElementById('scoreNum').innerText = score;
      const verdict = data.verdict || 'NEEDS_REVIEW';
      const badge = document.getElementById('verdictBadge');
      badge.innerText = verdict;
      badge.className = 'verdict-badge ' + (verdict === 'APPROVED' ? 'badge-approved' : (verdict === 'NEEDS_REVIEW' ? 'badge-warn' : 'badge-fail'));

      // Agent Scores
      document.getElementById('secScore').innerText = (data.agents.security?.score || 0) + '/100';
      document.getElementById('compScore').innerText = (data.agents.compliance?.score || 0) + '/100';
      document.getElementById('qaScore').innerText = (data.agents.quality?.score || 0) + '/100';

      // Patches count
      const patches = data.agents.patcher?.patches || [];
      document.getElementById('patchCount').innerText = patches.length;

      // Render Findings
      const allFindings = [
        ...(data.agents.security?.findings || []),
        ...(data.agents.compliance?.findings || []),
        ...(data.agents.quality?.findings || []),
      ];

      const findingsContainer = document.getElementById('findingsList');
      if (allFindings.length === 0) {
        findingsContainer.innerHTML = '<div style="padding: 2rem; text-align: center; color: var(--success);">✔ Zero blocking issues detected.</div>';
      } else {
        findingsContainer.innerHTML = allFindings.map(f => {
          const sevClass = (f.severity || 'info').toLowerCase();
          return \`
            <div class="finding-card \${sevClass}">
              <div class="finding-title">
                <span style="font-size: 0.75rem; padding: 2px 6px; border-radius: 4px; background: rgba(255,255,255,0.1);">\${f.severity || 'INFO'}</span>
                \${f.title}
              </div>
              <div class="finding-desc">\${f.description}</div>
              \${f.file && f.file !== 'N/A' ? \`<div style="font-size: 0.78rem; font-family: monospace; color: var(--primary); margin-bottom: 0.5rem;">File: \${f.file}\${f.line ? ':' + f.line : ''}</div>\` : ''}
              \${f.recommendation ? \`<div class="finding-rec">💡 <strong>Remediation:</strong> \${f.recommendation}</div>\` : ''}
            </div>
          \`;
        }).join('');
      }

      // Render Patches
      const patchesContainer = document.getElementById('patchesList');
      if (patches.length === 0) {
        patchesContainer.innerHTML = '<div style="padding: 2rem; text-align: center; color: var(--text-muted);">No automated corrective patches generated.</div>';
      } else {
        patchesContainer.innerHTML = patches.map((p, idx) => \`
          <div class="finding-card info">
            <div class="finding-title">🛠️ Patch #\${idx + 1}: \${p.targetFile}</div>
            <div class="finding-desc">\${p.description || p.title}</div>
            <pre>\${escapeHtml(p.diff)}</pre>
          </div>
        \`).join('');
      }

      // Render Timeline
      const timelineContainer = document.getElementById('timelineList');
      const events = data.events || [];
      timelineContainer.innerHTML = events.map(e => \`
        <div style="display: flex; gap: 1rem; margin-bottom: 0.75rem; font-size: 0.85rem;">
          <span style="color: var(--text-muted); font-family: monospace;">\${e.timestamp.slice(11, 19)}</span>
          <span style="color: var(--primary); font-weight: 600;">[\${e.agent}]</span>
          <span>\${e.message}</span>
        </div>
      \`).join('');

      // Render Markdown
      document.getElementById('markdownContent').innerText = data.markdownReview || 'No markdown review available.';
    }

    function escapeHtml(str) {
      return (str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    async function runScan() {
      document.getElementById('verdictBadge').innerText = 'AUDITING...';
      try {
        const res = await fetch('/api/run', { method: 'POST' });
        const data = await res.json();
        renderReport(data);
      } catch (e) {
        alert('Audit failed: ' + e.message);
      }
    }

    function copyMarkdown() {
      const text = document.getElementById('markdownContent').innerText;
      navigator.clipboard.writeText(text);
      alert('GitHub PR Review markdown copied to clipboard!');
    }

    // Initial render
    renderReport(reportData);
  </script>
</body>
</html>`;
}

export default {
  startDashboardServer,
};
