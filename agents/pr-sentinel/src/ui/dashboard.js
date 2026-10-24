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

    // API: Trigger audit (supports custom target path)
    if (url.pathname === '/api/run' && req.method === 'POST') {
      let body = '';
      req.on('data', chunk => { body += chunk; });
      req.on('end', async () => {
        try {
          let customTarget = targetDir;
          if (body) {
            try {
              const parsed = JSON.parse(body);
              if (parsed.path) customTarget = parsed.path;
            } catch (e) {}
          }
          const orchestrator = new Orchestrator();
          latestReport = await orchestrator.runReview({ targetDir: customTarget });
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify(latestReport));
        } catch (err) {
          res.writeHead(500, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: err.message }));
        }
      });
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

  server.updateReport = (rep) => {
    latestReport = rep;
  };

  server.on('error', (err) => {
    if (err.code === 'EADDRINUSE') {
      const fallbackPort = port + 1;
      console.warn(`  ⚠️ Port ${port} is in use, trying http://${host}:${fallbackPort}...`);
      server.listen(fallbackPort, host);
    } else {
      console.error('  ❌ Dashboard server error:', err.message);
    }
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

    @media print {
      @page {
        size: A4;
        margin: 1.5cm;
      }
      body {
        background: #ffffff !important;
        color: #1e293b !important;
        font-size: 10pt;
        -webkit-print-color-adjust: exact !important;
        print-color-adjust: exact !important;
      }
      header {
        border-bottom: 2px solid #0284c7 !important;
        background: #ffffff !important;
        position: static !important;
        padding: 0 0 1rem 0 !important;
        margin-bottom: 1.5rem !important;
      }
      .logo-badge {
        background: #0284c7 !important;
        color: #ffffff !important;
        box-shadow: none !important;
      }
      .header-actions, .tabs, .copy-btn, #tab-markdown {
        display: none !important;
      }
      .container {
        max-width: 100% !important;
        margin: 0 !important;
        padding: 0 !important;
      }
      .hero-grid {
        display: grid !important;
        grid-template-columns: 220px 1fr !important;
        gap: 1.25rem !important;
        margin-bottom: 1.5rem !important;
        page-break-inside: avoid !important;
      }
      .score-card, .summary-card {
        background: #f8fafc !important;
        border: 1px solid #cbd5e1 !important;
        border-radius: 8px !important;
        box-shadow: none !important;
        padding: 1.25rem !important;
      }
      .score-num {
        color: #0f172a !important;
        font-size: 2.25rem !important;
      }
      .badge-approved { background: #dcfce7 !important; color: #15803d !important; border: 1px solid #86efac !important; }
      .badge-warn { background: #fef9c3 !important; color: #a16207 !important; border: 1px solid #fde047 !important; }
      .badge-fail { background: #fee2e2 !important; color: #b91c1c !important; border: 1px solid #fca5a5 !important; }

      .agent-pill {
        background: #ffffff !important;
        border: 1px solid #cbd5e1 !important;
        color: #0f172a !important;
      }
      .agent-name { color: #0f172a !important; font-weight: 700 !important; }
      .agent-score { color: #0369a1 !important; font-weight: 800 !important; }

      .tab-content {
        display: block !important;
        margin-bottom: 2rem !important;
      }
      .tab-content::before {
        display: block;
        font-size: 1.15rem;
        font-weight: 700;
        color: #0f172a;
        margin: 1.5rem 0 0.75rem 0;
        padding-bottom: 0.35rem;
        border-bottom: 1px solid #cbd5e1;
      }
      #tab-findings::before { content: "1. Detailed Findings & Audit Observations"; }
      #tab-patches::before { content: "2. Automated Remediation Patches (Unified Diffs)"; }
      #tab-timeline::before { content: "3. Multi-Agent Audit Trail & Execution Timeline"; }

      .finding-card {
        background: #ffffff !important;
        border: 1px solid #cbd5e1 !important;
        box-shadow: none !important;
        page-break-inside: avoid !important;
        margin-bottom: 0.85rem !important;
        padding: 1rem !important;
      }
      .finding-card.critical { border-left: 5px solid #dc2626 !important; background: #fff5f5 !important; }
      .finding-card.high { border-left: 5px solid #ea580c !important; background: #fffaf0 !important; }
      .finding-card.medium { border-left: 5px solid #ca8a04 !important; background: #fefce8 !important; }
      .finding-card.info { border-left: 5px solid #0284c7 !important; background: #f0f9ff !important; }

      .finding-title {
        color: #0f172a !important;
        font-size: 0.95rem !important;
        font-weight: 700 !important;
      }
      .finding-desc {
        color: #334155 !important;
        font-size: 0.88rem !important;
      }
      .finding-rec {
        background: #f0fdf4 !important;
        border: 1px solid #86efac !important;
        color: #166534 !important;
        font-size: 0.85rem !important;
        margin-top: 0.5rem !important;
      }

      pre {
        background: #f8fafc !important;
        border: 1px solid #cbd5e1 !important;
        color: #0f172a !important;
        font-size: 8pt !important;
        white-space: pre-wrap !important;
        page-break-inside: avoid !important;
      }
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
      <input id="auditTarget" type="text" placeholder="Target path (e.g. . or agents/other-slug)" style="background: rgba(255,255,255,0.06); border: 1px solid var(--card-border); color: #fff; padding: 0.45rem 0.75rem; border-radius: 8px; font-size: 0.82rem; width: 220px;" />
      <button class="btn btn-secondary" onclick="runScan()">🔍 Audit</button>
      <button class="btn btn-secondary" onclick="exportPdf()">📄 Export PDF</button>
      <button class="btn btn-primary" onclick="downloadMarkdown()">📥 Download .md</button>
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

          <div class="agent-pill">
            <div class="agent-header">
              <span class="agent-name">💥 BlastPredictor</span>
              <span class="agent-score" id="blastScore">--%</span>
            </div>
            <p style="font-size: 0.78rem; color: var(--text-muted);" id="blastDesc">Simulates downstream caller breakages</p>
          </div>
        </div>
      </div>
    </div>

    <div class="tabs">
      <button class="tab active" onclick="switchTab('tab-findings')">🔍 All Findings</button>
      <button class="tab" onclick="switchTab('tab-blast')">💥 Blast Radius Radar (<span id="blastCallersCount">0</span>)</button>
      <button class="tab" onclick="switchTab('tab-patches')">🛠️ Auto-Patches (<span id="patchCount">0</span>)</button>
      <button class="tab" onclick="switchTab('tab-timeline')">⏱️ Agent Timeline</button>
      <button class="tab" onclick="switchTab('tab-markdown')">📝 GitHub PR Review Markdown</button>
    </div>

    <div id="tab-findings" class="tab-content active">
      <div id="findingsList">Loading findings...</div>
    </div>

    <div id="tab-blast" class="tab-content">
      <div id="blastDetails">Loading blast radius simulation...</div>
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
        <div style="position: absolute; top: 1rem; right: 1rem; display: flex; gap: 0.5rem;">
          <button class="btn btn-secondary" onclick="copyMarkdown()">📋 Copy</button>
          <button class="btn btn-primary" onclick="downloadMarkdown()">📥 Download .md</button>
        </div>
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

      // Blast Predictor score
      const blastData = data.agents.blast || {};
      const blastScoreEl = document.getElementById('blastScore');
      if (blastScoreEl) blastScoreEl.innerText = (blastData.blastScore || 0) + '%';
      const blastCallersCountEl = document.getElementById('blastCallersCount');
      if (blastCallersCountEl) blastCallersCountEl.innerText = (blastData.downstreamCallers?.length || 0);

      // Render Blast Radius Tab
      const blastContainer = document.getElementById('blastDetails');
      if (blastContainer) {
        const impacts = blastData.downstreamImpacts || [];
        const callers = blastData.downstreamCallers || [];
        let blastHtml = `
          <div style="background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
              <div>
                <h3 style="font-size: 1.15rem; font-weight: 700; color: var(--text);">Downstream Semantic Ripple Forecast</h3>
                <p style="font-size: 0.85rem; color: var(--text-muted); margin-top: 0.25rem;">${escapeHtml(blastData.summary || '')}</p>
              </div>
              <div style="text-align: right;">
                <span style="display: inline-block; padding: 4px 10px; border-radius: 9999px; font-size: 0.75rem; font-weight: 700; background: ${blastData.metrics?.badgeColor ? blastData.metrics.badgeColor + '22' : 'rgba(56,189,248,0.2)'}; color: ${blastData.metrics?.badgeColor || '#38bdf8'}; border: 1px solid ${blastData.metrics?.badgeColor || '#38bdf8'};">
                  ${blastData.containmentVerdict || 'ISOLATED'}
                </span>
                <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 0.35rem;">Contract: ${blastData.contractIntegrity || 'STABLE'}</div>
              </div>
            </div>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-top: 1rem; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 1rem;">
              <div><span style="font-size: 0.75rem; color: var(--text-muted);">Impacted Untouched Callers</span><div style="font-size: 1.4rem; font-weight: 700;">${callers.length}</div></div>
              <div><span style="font-size: 0.75rem; color: var(--text-muted);">Modified Interface Symbols</span><div style="font-size: 1.4rem; font-weight: 700;">${blastData.metrics?.modifiedSymbolsCount || 0}</div></div>
              <div><span style="font-size: 0.75rem; color: var(--text-muted);">Untested Caller Risk</span><div style="font-size: 1.4rem; font-weight: 700; color: ${blastData.metrics?.untestedDownstreamCallers ? 'var(--warning)' : 'var(--success)'};">${blastData.metrics?.untestedDownstreamCallers ? 'YES (UNTESTED)' : 'COVERED'}</div></div>
            </div>
          </div>
        `;

        if (impacts.length === 0) {
          blastHtml += `
            <div style="background: rgba(52, 211, 153, 0.1); border: 1px solid rgba(52, 211, 153, 0.3); border-radius: 12px; padding: 1.5rem; text-align: center;">
              <div style="font-weight: 700; color: var(--success); font-size: 1.1rem;">Hermetically Isolated Change</div>
              <div style="color: var(--text-muted); font-size: 0.85rem; margin-top: 0.25rem;">This PR does not alter public contracts relied upon by other repository modules. Zero downstream breakages predicted.</div>
            </div>
          `;
        } else {
          blastHtml += `<h4 style="font-size: 0.95rem; margin-bottom: 0.75rem; color: var(--text-muted); text-transform: uppercase;">Downstream Consumers Requiring Contract Verification</h4>`;
          blastHtml += impacts.map(imp => `
            <div class="finding-card ${imp.severity === 'CRITICAL' ? 'critical' : imp.severity === 'HIGH' ? 'high' : 'medium'}">
              <div class="finding-title">
                <span style="font-size: 0.75rem; padding: 2px 6px; border-radius: 4px; background: rgba(255,255,255,0.1);">${imp.severity}</span>
                ${escapeHtml(imp.impactedFile)} (Symbol: ${escapeHtml(imp.brokenSymbol)})
              </div>
              <div class="finding-desc">${escapeHtml(imp.predictedFailure)}</div>
              <div class="finding-rec">🛡️ <strong>Safety Requirement:</strong> ${escapeHtml(imp.preventionFix)}</div>
            </div>
          `).join('');
        }
        blastContainer.innerHTML = blastHtml;
      }

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
      const actionIssues = allFindings.filter(f => f.severity && f.severity !== 'INFO');
      const infoChecks = allFindings.filter(f => !f.severity || f.severity === 'INFO');

      let html = '';
      if (actionIssues.length === 0) {
        html += \`
          <div style="background: rgba(52, 211, 153, 0.1); border: 1px solid rgba(52, 211, 153, 0.3); border-radius: 12px; padding: 1.5rem; text-align: center; margin-bottom: 1.5rem;">
            <div style="font-size: 1.5rem; margin-bottom: 0.25rem;">🎉</div>
            <div style="font-weight: 700; color: var(--success); font-size: 1.1rem;">Zero Blocking Vulnerabilities Detected</div>
            <div style="color: var(--text-muted); font-size: 0.85rem; margin-top: 0.25rem;">All security, guidelines compliance, and architectural safety checks passed successfully.</div>
          </div>
        \`;
      } else {
        html += actionIssues.map(f => {
          const sevClass = (f.severity || 'info').toLowerCase();
          return \`
            <div class="finding-card \${sevClass}">
              <div class="finding-title">
                <span style="font-size: 0.75rem; padding: 2px 6px; border-radius: 4px; background: rgba(255,255,255,0.1);">\${f.severity}</span>
                \${f.title}
              </div>
              <div class="finding-desc">\${f.description}</div>
              \${f.file && f.file !== 'N/A' ? \`<div style="font-size: 0.78rem; font-family: monospace; color: var(--primary); margin-bottom: 0.5rem;">File: \${f.file}\${f.line ? ':' + f.line : ''}</div>\` : ''}
              \${f.recommendation ? \`<div class="finding-rec">💡 <strong>Remediation:</strong> \${f.recommendation}</div>\` : ''}
            </div>
          \`;
        }).join('');
      }

      if (infoChecks.length > 0) {
        html += '<div style="margin-top: 1.5rem; font-size: 0.85rem; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.75rem;">Verified Audit Checks</div>';
        html += infoChecks.map(f => \`
          <div class="finding-card info" style="opacity: 0.85;">
            <div class="finding-title">
              <span style="font-size: 0.75rem; padding: 2px 6px; border-radius: 4px; background: rgba(56,189,248,0.15); color: var(--primary);">VERIFIED</span>
              \${f.title}
            </div>
            <div class="finding-desc" style="margin-bottom: 0;">\${f.description}</div>
          </div>
        \`).join('');
      }

      findingsContainer.innerHTML = html;

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
      const targetInput = document.getElementById('auditTarget');
      const customPath = targetInput ? targetInput.value.trim() : '';
      document.getElementById('verdictBadge').innerText = 'AUDITING...';
      try {
        const res = await fetch('/api/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: customPath || '.' }),
        });
        const data = await res.json();
        renderReport(data);
      } catch (e) {
        alert('Audit failed: ' + e.message);
      }
    }

    function exportPdf() {
      window.print();
    }

    function downloadMarkdown() {
      const text = document.getElementById('markdownContent').innerText;
      if (!text || text === 'Loading markdown review...') {
        alert('No markdown review available to download.');
        return;
      }
      const timestamp = new Date().toISOString().slice(0, 10);
      const verdict = (reportData && reportData.verdict) ? reportData.verdict.toLowerCase() : 'report';
      const filename = 'pr-review-' + verdict + '-' + timestamp + '.md';
      const blob = new Blob([text], { type: 'text/markdown;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.setAttribute('href', url);
      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    }

    function copyMarkdown() {
      const text = document.getElementById('markdownContent').innerText;
      navigator.clipboard.writeText(text);
      alert('GitHub PR Review markdown copied to clipboard!');
    }

    // Check if report is already available or poll for it
    async function loadLatestReport() {
      try {
        const res = await fetch('/api/report');
        if (!res.ok) return false;
        const data = await res.json();
        if (data && data.agents) {
          renderReport(data);
          return true;
        }
      } catch (e) {
        return false;
      }
      return false;
    }

    // Initial render or auto-load
    if (reportData && reportData.agents) {
      renderReport(reportData);
    } else {
      document.getElementById('verdictBadge').innerText = 'AUDITING...';
      const pollTimer = setInterval(async () => {
        const done = await loadLatestReport();
        if (done) clearInterval(pollTimer);
      }, 1000);

      // Trigger initial audit if none running
      loadLatestReport().then(found => {
        if (!found) {
          runScan();
        }
      });
    }
  </script>
</body>
</html>`;
}

export default {
  startDashboardServer,
};
