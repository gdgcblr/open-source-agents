"""OSS Pulse Agent — Interactive Web UI & API.

Runs a local web dashboard powered by FastAPI + Tailwind CSS.
Launch with:
    python app.py
Open:
    http://localhost:8000
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

# Fix Windows cp1252 encoding
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).parent))

from agent import OSSPulseAgent, run_analysis
from models.report import HealthReport

app = FastAPI(
    title="OSS Pulse Agent",
    description="Evidence-Driven Repository Intelligence Agent powered by Google Gemini",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/analyze")
def api_analyze(repo: str = Query(..., description="owner/repository")) -> dict:
    """Analyze a single repository and return JSON report."""
    try:
        parts = repo.strip().split("/")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise HTTPException(status_code=400, detail="Repository must be in 'owner/repo' format (e.g. 'pallets/flask')")
        
        agent = OSSPulseAgent()
        report = agent.analyze(parts[0].strip(), parts[1].strip())
        return report.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/compare")
def api_compare(repo1: str = Query(...), repo2: str = Query(...)) -> dict:
    """Compare two repositories side-by-side."""
    try:
        agent = OSSPulseAgent()
        r1 = agent.analyze(*repo1.strip().split("/"))
        r2 = agent.analyze(*repo2.strip().split("/"))
        return {
            "repo1": r1.model_dump(),
            "repo2": r2.model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>OSS Pulse Agent — Repository Intelligence</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <style>
    @keyframes pulse-subtle { 0%, 100% { opacity: 1; } 50% { opacity: 0.85; } }
    .pulse-glow { animation: pulse-subtle 3s infinite; }
  </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen font-sans antialiased selection:bg-indigo-500 selection:text-white">

  <!-- Header -->
  <header class="border-b border-slate-800 bg-slate-900/60 backdrop-blur sticky top-0 z-50">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 py-4 flex flex-col sm:flex-row items-center justify-between gap-4">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-500 to-cyan-400 flex items-center justify-center text-white shadow-lg shadow-indigo-500/20">
          <i class="fa-solid fa-heart-pulse text-xl"></i>
        </div>
        <div>
          <h1 class="text-xl font-bold bg-gradient-to-r from-white via-slate-200 to-indigo-300 bg-clip-text text-transparent">OSS Pulse Agent</h1>
          <p class="text-xs text-slate-400">Evidence-Driven Repository Intelligence • Powered by <span class="text-cyan-400 font-semibold">Gemini 3.8 Flash</span></p>
        </div>
      </div>
      <div class="flex items-center gap-2 text-xs">
        <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
          <span class="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
          Gemini Agent Live
        </span>
        <span class="inline-flex items-center gap-1 px-3 py-1 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
          <i class="fa-brands fa-github"></i> 5,000 req/hr
        </span>
      </div>
    </div>
  </header>

  <!-- Main Container -->
  <main class="max-w-7xl mx-auto px-4 sm:px-6 py-8">
    
    <!-- Search / Analyze Bar -->
    <section class="max-w-3xl mx-auto mb-10 text-center">
      <h2 class="text-3xl sm:text-4xl font-extrabold tracking-tight mb-3">
        Is that open-source project <span class="bg-gradient-to-r from-indigo-400 to-cyan-400 bg-clip-text text-transparent">actually healthy?</span>
      </h2>
      <p class="text-slate-400 text-sm sm:text-base mb-6">
        Beyond star counts & checkboxes: real maintenance telemetry, security posture, and actionable newcomer issues.
      </p>

      <form id="searchForm" onsubmit="handleAnalyze(event)" class="flex flex-col sm:flex-row gap-2 max-w-xl mx-auto">
        <div class="relative flex-1">
          <i class="fa-brands fa-github absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 text-lg"></i>
          <input 
            type="text" 
            id="repoInput"
            value="gdgcblr/meetup"
            placeholder="owner/repository (e.g. pallets/flask)"
            class="w-full pl-12 pr-4 py-3.5 rounded-xl bg-slate-900 border border-slate-700 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 outline-none text-white text-sm transition"
            required
          />
        </div>
        <button 
          type="submit" 
          id="submitBtn"
          class="px-6 py-3.5 rounded-xl bg-gradient-to-r from-indigo-600 to-cyan-600 hover:from-indigo-500 hover:to-cyan-500 text-white font-semibold text-sm shadow-lg shadow-indigo-600/30 transition flex items-center justify-center gap-2"
        >
          <i class="fa-solid fa-wand-magic-sparkles"></i>
          Analyze Repo
        </button>
      </form>

      <!-- Quick suggestions -->
      <div class="flex flex-wrap items-center justify-center gap-2 mt-4 text-xs text-slate-400">
        <span>Try:</span>
        <button onclick="setAndAnalyze('gdgcblr/meetup')" class="px-2.5 py-1 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 transition text-slate-300">gdgcblr/meetup</button>
        <button onclick="setAndAnalyze('pallets/flask')" class="px-2.5 py-1 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 transition text-slate-300">pallets/flask</button>
        <button onclick="setAndAnalyze('tiangolo/fastapi')" class="px-2.5 py-1 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 transition text-slate-300">tiangolo/fastapi</button>
        <button onclick="setAndAnalyze('google/gemma_pytorch')" class="px-2.5 py-1 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 transition text-slate-300">google/gemma_pytorch</button>
      </div>
    </section>

    <!-- Loading State -->
    <div id="loading" class="hidden text-center py-16">
      <div class="inline-block relative w-16 h-16 mb-4">
        <div class="w-16 h-16 rounded-full border-4 border-indigo-500/20 border-t-indigo-500 animate-spin"></div>
        <i class="fa-solid fa-robot absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 text-indigo-400"></i>
      </div>
      <h3 class="text-lg font-semibold text-white mb-1">Gemini Agent is Analyzing Repository Telemetry...</h3>
      <p class="text-xs text-slate-400" id="loadingStep">Querying GitHub commit velocity, security configurations & bus factor...</p>
    </div>

    <!-- Error State -->
    <div id="errorState" class="hidden max-w-xl mx-auto p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-sm flex items-start gap-3 my-6">
      <i class="fa-solid fa-circle-exclamation text-lg mt-0.5"></i>
      <div id="errorMsg">Failed to analyze repository.</div>
    </div>

    <!-- Results Section -->
    <div id="results" class="hidden space-y-8">
      
      <!-- Top Overview Card -->
      <div class="p-6 sm:p-8 rounded-2xl bg-slate-900/80 border border-slate-800 shadow-xl relative overflow-hidden">
        <div class="absolute -right-16 -top-16 w-64 h-64 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none"></div>

        <div class="flex flex-col md:flex-row items-start md:items-center justify-between gap-6 pb-6 border-b border-slate-800">
          <div>
            <div class="flex items-center gap-3 mb-1">
              <h2 id="repoFullName" class="text-2xl font-bold text-white hover:text-indigo-400 transition">owner/repo</h2>
              <a id="repoLink" href="#" target="_blank" class="text-slate-400 hover:text-white text-sm"><i class="fa-solid fa-arrow-up-right-from-square"></i></a>
            </div>
            <p id="repoDesc" class="text-sm text-slate-400 max-w-2xl mb-3">Repository description...</p>
            <div class="flex flex-wrap gap-4 text-xs text-slate-300">
              <span id="repoLang"><i class="fa-solid fa-code text-indigo-400 mr-1"></i> Python</span>
              <span id="repoStars"><i class="fa-solid fa-star text-amber-400 mr-1"></i> 0</span>
              <span id="repoForks"><i class="fa-solid fa-code-fork text-cyan-400 mr-1"></i> 0</span>
              <span id="repoLicense"><i class="fa-solid fa-scale-balanced text-emerald-400 mr-1"></i> MIT</span>
            </div>
          </div>

          <!-- Overall Score Badge -->
          <div class="flex items-center gap-4 bg-slate-950/70 p-4 rounded-xl border border-slate-800 shrink-0">
            <div class="text-center">
              <div class="text-xs uppercase tracking-wider text-slate-400 font-semibold mb-1">Overall Health</div>
              <div class="flex items-baseline gap-1 justify-center">
                <span id="overallScoreNum" class="text-4xl font-extrabold text-white">0</span>
                <span class="text-sm text-slate-500">/100</span>
              </div>
              <div id="overallGrade" class="text-xs font-bold px-2 py-0.5 rounded-full inline-block mt-1 bg-indigo-500/20 text-indigo-300">Grade -</div>
            </div>
            <div class="border-l border-slate-800 pl-4 text-left text-xs space-y-1">
              <div><span class="text-slate-400">Data Coverage:</span> <span id="dataCovPct" class="font-bold text-white">0%</span></div>
              <div><span class="text-slate-400">Evidence Quality:</span> <span id="evQuality" class="font-bold text-emerald-400">High</span></div>
              <div><span class="text-slate-400">Duration:</span> <span id="analysisDuration" class="text-slate-300">0s</span></div>
            </div>
          </div>
        </div>

        <!-- 4 Dimension Progress Bars -->
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 pt-6">
          <div class="p-4 rounded-xl bg-slate-950/40 border border-slate-800/80">
            <div class="flex justify-between text-xs mb-1.5 font-medium">
              <span class="text-slate-300"><i class="fa-solid fa-chart-line text-indigo-400 mr-1.5"></i>Activity & Maintenance (30%)</span>
              <span id="scoreActivity" class="font-bold text-white">0/100</span>
            </div>
            <div class="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
              <div id="barActivity" class="bg-indigo-500 h-2 rounded-full transition-all duration-1000" style="width: 0%"></div>
            </div>
            <p id="sumActivity" class="text-[11px] text-slate-400 mt-2 truncate">Commits, SLA, stale backlog</p>
          </div>

          <div class="p-4 rounded-xl bg-slate-950/40 border border-slate-800/80">
            <div class="flex justify-between text-xs mb-1.5 font-medium">
              <span class="text-slate-300"><i class="fa-solid fa-shield-halved text-emerald-400 mr-1.5"></i>Security Config (25%)</span>
              <span id="scoreSecurity" class="font-bold text-white">0/100</span>
            </div>
            <div class="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
              <div id="barSecurity" class="bg-emerald-500 h-2 rounded-full transition-all duration-1000" style="width: 0%"></div>
            </div>
            <p id="sumSecurity" class="text-[11px] text-slate-400 mt-2 truncate">Dependabot, SAST, policy</p>
          </div>

          <div class="p-4 rounded-xl bg-slate-950/40 border border-slate-800/80">
            <div class="flex justify-between text-xs mb-1.5 font-medium">
              <span class="text-slate-300"><i class="fa-solid fa-book-open text-cyan-400 mr-1.5"></i>Documentation (20%)</span>
              <span id="scoreDocs" class="font-bold text-white">0/100</span>
            </div>
            <div class="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
              <div id="barDocs" class="bg-cyan-500 h-2 rounded-full transition-all duration-1000" style="width: 0%"></div>
            </div>
            <p id="sumDocs" class="text-[11px] text-slate-400 mt-2 truncate">README depth, guide, license</p>
          </div>

          <div class="p-4 rounded-xl bg-slate-950/40 border border-slate-800/80">
            <div class="flex justify-between text-xs mb-1.5 font-medium">
              <span class="text-slate-300"><i class="fa-solid fa-users text-amber-400 mr-1.5"></i>Community Health (25%)</span>
              <span id="scoreCommunity" class="font-bold text-white">0/100</span>
            </div>
            <div class="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
              <div id="barCommunity" class="bg-amber-500 h-2 rounded-full transition-all duration-1000" style="width: 0%"></div>
            </div>
            <p id="sumCommunity" class="text-[11px] text-slate-400 mt-2 truncate">Bus factor, good first issues</p>
          </div>
        </div>
      </div>

      <!-- Gemini AI Executive Synthesis -->
      <div class="p-6 sm:p-8 rounded-2xl bg-gradient-to-br from-indigo-950/40 via-slate-900/60 to-cyan-950/30 border border-indigo-500/20 shadow-xl">
        <div class="flex items-center gap-2 mb-4 text-indigo-300 font-semibold text-sm">
          <i class="fa-solid fa-robot text-indigo-400 text-lg"></i>
          <span>Gemini 3.8 Flash Contextual Reasoning</span>
        </div>
        <div id="aiSummary" class="text-sm text-slate-300 leading-relaxed whitespace-pre-line space-y-3">
          AI insights will appear here...
        </div>
      </div>

      <!-- Actionable Findings & Recommendations -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
        
        <!-- Findings Cards -->
        <div>
          <h3 class="text-lg font-bold text-white mb-4 flex items-center justify-between">
            <span><i class="fa-solid fa-triangle-exclamation text-amber-400 mr-2"></i>Prioritized Findings</span>
            <span id="findingsCount" class="text-xs px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-300 font-normal">0 items</span>
          </h3>
          <div id="findingsList" class="space-y-3">
            <!-- Cards injected by JS -->
          </div>
        </div>

        <!-- Good First Issues (Contribution Readiness) -->
        <div>
          <h3 class="text-lg font-bold text-white mb-4 flex items-center justify-between">
            <span><i class="fa-solid fa-seedling text-emerald-400 mr-2"></i>Contribution Opportunities</span>
            <span id="oppsCount" class="text-xs px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-300 font-normal">0 items</span>
          </h3>
          <div id="oppsList" class="space-y-3">
            <!-- Opportunities injected by JS -->
          </div>
        </div>

      </div>

    </div>

  </main>

  <footer class="border-t border-slate-800/80 py-6 text-center text-xs text-slate-500 mt-16">
    <p>OSS Pulse Agent • Built for GDG Cloud Bengaluru (Road to DevFest: Fork, Build, Merge)</p>
    <p class="mt-1">Security Notice: Evaluates observable configuration files only. Not a vulnerability audit.</p>
  </footer>

  <script>
    function setAndAnalyze(repo) {
      document.getElementById('repoInput').value = repo;
      handleAnalyze(new Event('submit'));
    }

    async function handleAnalyze(e) {
      if (e) e.preventDefault();
      const repo = document.getElementById('repoInput').value.trim();
      if (!repo) return;

      const loading = document.getElementById('loading');
      const results = document.getElementById('results');
      const errorState = document.getElementById('errorState');
      const submitBtn = document.getElementById('submitBtn');

      loading.classList.remove('hidden');
      results.classList.add('hidden');
      errorState.classList.add('hidden');
      submitBtn.disabled = true;

      try {
        const response = await fetch(`/api/analyze?repo=${encodeURIComponent(repo)}`);
        if (!response.ok) {
          const errData = await response.json().catch(() => ({}));
          throw new Error(errData.detail || `HTTP Error ${response.status}`);
        }
        const data = await response.json();
        renderResults(data);
      } catch (err) {
        document.getElementById('errorMsg').innerText = err.message || 'Analysis failed.';
        errorState.classList.remove('hidden');
      } finally {
        loading.classList.add('hidden');
        submitBtn.disabled = false;
      }
    }

    function renderResults(data) {
      const results = document.getElementById('results');
      results.classList.remove('hidden');

      // Top info
      document.getElementById('repoFullName').innerText = data.repository.full_name;
      document.getElementById('repoLink').href = data.repository.url;
      document.getElementById('repoDesc').innerText = data.repository.description || 'No description provided.';
      document.getElementById('repoLang').innerHTML = `<i class="fa-solid fa-code text-indigo-400 mr-1"></i> ${data.repository.language || 'Unknown'}`;
      document.getElementById('repoStars').innerHTML = `<i class="fa-solid fa-star text-amber-400 mr-1"></i> ${data.repository.stars.toLocaleString()}`;
      document.getElementById('repoForks').innerHTML = `<i class="fa-solid fa-code-fork text-cyan-400 mr-1"></i> ${data.repository.forks.toLocaleString()}`;
      document.getElementById('repoLicense').innerHTML = `<i class="fa-solid fa-scale-balanced text-emerald-400 mr-1"></i> ${data.repository.license_name || 'No License'}`;

      // Overall Score
      document.getElementById('overallScoreNum').innerText = Math.round(data.overall_score);
      document.getElementById('overallGrade').innerText = `Grade ${data.overall_grade}`;
      document.getElementById('dataCovPct').innerText = `${Math.round(data.data_coverage_percentage || 0)}%`;
      document.getElementById('evQuality').innerText = data.evidence_quality || 'High';
      document.getElementById('analysisDuration').innerText = `${data.analysis_duration_seconds}s`;

      // Color grade badge
      const gradeEl = document.getElementById('overallGrade');
      if (data.overall_score >= 80) {
        gradeEl.className = 'text-xs font-bold px-2 py-0.5 rounded-full inline-block mt-1 bg-emerald-500/20 text-emerald-400';
      } else if (data.overall_score >= 60) {
        gradeEl.className = 'text-xs font-bold px-2 py-0.5 rounded-full inline-block mt-1 bg-amber-500/20 text-amber-400';
      } else {
        gradeEl.className = 'text-xs font-bold px-2 py-0.5 rounded-full inline-block mt-1 bg-rose-500/20 text-rose-400';
      }

      // 4 Categories
      const catMap = {};
      data.category_scores.forEach(cs => { catMap[cs.category] = cs; });

      if (catMap.activity) {
        document.getElementById('scoreActivity').innerText = `${Math.round(catMap.activity.score)}/100`;
        document.getElementById('barActivity').style.width = `${catMap.activity.score}%`;
        document.getElementById('sumActivity').innerText = catMap.activity.evidence_summary;
      }
      if (catMap.security) {
        document.getElementById('scoreSecurity').innerText = `${Math.round(catMap.security.score)}/100`;
        document.getElementById('barSecurity').style.width = `${catMap.security.score}%`;
        document.getElementById('sumSecurity').innerText = catMap.security.evidence_summary;
      }
      if (catMap.documentation) {
        document.getElementById('scoreDocs').innerText = `${Math.round(catMap.documentation.score)}/100`;
        document.getElementById('barDocs').style.width = `${catMap.documentation.score}%`;
        document.getElementById('sumDocs').innerText = catMap.documentation.evidence_summary;
      }
      if (catMap.community) {
        document.getElementById('scoreCommunity').innerText = `${Math.round(catMap.community.score)}/100`;
        document.getElementById('barCommunity').style.width = `${catMap.community.score}%`;
        document.getElementById('sumCommunity').innerText = catMap.community.evidence_summary;
      }

      // AI Summary
      document.getElementById('aiSummary').innerText = data.ai_summary || 'Deterministic insights generated.';

      // Findings
      const findingsList = document.getElementById('findingsList');
      findingsList.innerHTML = '';
      document.getElementById('findingsCount').innerText = `${data.all_findings.length} findings`;

      if (data.all_findings.length === 0) {
        findingsList.innerHTML = '<div class="p-4 rounded-xl bg-slate-900 border border-slate-800 text-xs text-slate-400">No major issues identified.</div>';
      } else {
        data.all_findings.slice(0, 6).forEach(f => {
          let sevColor = 'bg-slate-800 text-slate-400 border-slate-700';
          if (f.severity === 'critical') sevColor = 'bg-rose-500/20 text-rose-300 border-rose-500/30';
          else if (f.severity === 'high') sevColor = 'bg-orange-500/20 text-orange-300 border-orange-500/30';
          else if (f.severity === 'medium') sevColor = 'bg-amber-500/20 text-amber-300 border-amber-500/30';
          else if (f.severity === 'low') sevColor = 'bg-cyan-500/20 text-cyan-300 border-cyan-500/30';

          findingsList.innerHTML += `
            <div class="p-4 rounded-xl bg-slate-900 border border-slate-800 space-y-1.5">
              <div class="flex items-center justify-between gap-2">
                <span class="text-xs font-bold uppercase tracking-wider px-2 py-0.5 rounded border ${sevColor}">${f.severity}</span>
                <span class="text-[11px] text-slate-500 font-mono">${f.id}</span>
              </div>
              <h4 class="text-sm font-semibold text-white">${f.title}</h4>
              <p class="text-xs text-slate-400">${f.impact}</p>
              <div class="pt-2 text-xs text-emerald-400 font-medium">
                <i class="fa-solid fa-wrench mr-1"></i> Fix: ${f.recommended_fix}
              </div>
            </div>
          `;
        });
      }

      // Contribution Opportunities
      const oppsList = document.getElementById('oppsList');
      oppsList.innerHTML = '';
      const opps = data.contribution_opportunities || [];
      document.getElementById('oppsCount').innerText = `${opps.length} issues`;

      if (opps.length === 0) {
        oppsList.innerHTML = '<div class="p-4 rounded-xl bg-slate-900 border border-slate-800 text-xs text-slate-400">No open beginner issues found in this repository.</div>';
      } else {
        opps.forEach(opp => {
          oppsList.innerHTML += `
            <div class="p-4 rounded-xl bg-slate-900 border border-slate-800 flex items-start justify-between gap-4">
              <div>
                <div class="flex items-center gap-2 mb-1">
                  <span class="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">${opp.difficulty}</span>
                  <span class="text-xs text-slate-400">${opp.why_good_fit}</span>
                </div>
                <h4 class="text-sm font-semibold text-white">${opp.title}</h4>
              </div>
              <a href="${opp.url}" target="_blank" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs text-white shrink-0 transition flex items-center gap-1.5">
                <span>View</span>
                <i class="fa-solid fa-arrow-up-right-from-square text-[10px]"></i>
              </a>
            </div>
          `;
        });
      }
    }
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    """Serve the interactive web UI."""
    return HTML_TEMPLATE


if __name__ == "__main__":
    import os
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 8000))
    print(f"\n>> Starting OSS Pulse Web UI on http://localhost:{port} ...")
    uvicorn.run("app:app", host=host, port=port, reload=False)
