/**
 * MergeReady Landing Page — Interactive Controller
 * Deterministic offline CLI validation demo
 */

// Single configuration constant for GitHub URL
const GITHUB_REPO_URL = "https://github.com/Rithvik-krishna/open-source-agents/tree/feat/merge-ready/tools/merge-ready";
const GITHUB_DOCS_URL = "https://github.com/Rithvik-krishna/open-source-agents/blob/feat/merge-ready/tools/merge-ready/README.md";

// Terminal demo scenarios
const SCENARIOS = {
  problematic: {
    command: "merge-ready check agents/example-agent",
    statusText: "Exit code: 1 (FAILED)",
    statusClass: "fail",
    output: [
      { type: "divider" },
      { type: "header", text: "  MergeReady Contribution Validator — agents/example-agent" },
      { type: "divider" },
      { type: "space" },
      { type: "pass", rule: "L01", name: "Dedicated Directory Location" },
      { type: "pass", rule: "L02", name: "Naming Conventions" },
      { type: "pass", rule: "F01", name: "Required File Standards" },
      {
        type: "fail",
        rule: "D01",
        name: "Template Residue Detection",
        findings: [
          {
            severity: "ERROR",
            msg: "Template placeholder found: '[Project Name]' in README.md:1",
            req: "CONTRIBUTING.md Project Structure & Documentation",
            fix: "Replace all template placeholders with real project information."
          }
        ]
      },
      { type: "pass", rule: "D02", name: "Required Documentation Sections" },
      {
        type: "fail",
        rule: "S01",
        name: "Zero Secrets Policy",
        findings: [
          {
            severity: "ERROR",
            msg: "Suspected hardcoded credential (Google API Key): 'AIza...7890 [REDACTED]' in agent.py:12",
            req: "CONTRIBUTING.md Security & Configuration",
            fix: "Move secret to an environment variable loaded via .env (never commit raw keys)."
          }
        ]
      },
      {
        type: "fail",
        rule: "S02",
        name: "No Virtual Environments or Local Databases",
        findings: [
          {
            severity: "ERROR",
            msg: "Forbidden database artifact detected: 'local_cache.sqlite'",
            req: "CONTRIBUTING.md Clean Working Tree & Git Hygiene",
            fix: "Remove database files from Git tracking and add them to .gitignore."
          }
        ]
      },
      {
        type: "fail",
        rule: "R01",
        name: "Declared Dependency Manifest",
        findings: [
          {
            severity: "ERROR",
            msg: "Undeclared third-party import 'requests' used in agent.py:3 but missing from requirements.txt",
            req: "CONTRIBUTING.md Dependencies",
            fix: "Add 'requests' to requirements.txt."
          }
        ]
      },
      {
        type: "fail",
        rule: "A02",
        name: "Hidden and Deceptive Unicode",
        findings: [
          {
            severity: "ERROR",
            msg: "Dangerous bidirectional Unicode override character (U+202E) detected in agent.py:35",
            req: "CONTRIBUTING.md Static Safety",
            fix: "Remove invisible or direction-altering Unicode characters."
          }
        ]
      },
      { type: "space" },
      { type: "separator" },
      { type: "summary", text: "Summary: 4 pass · 5 fail · 0 error · 0 warn · 0 skipped · 0 n/a" },
      { type: "result_fail", text: "Result: FAILED — Contribution violates repository requirements." },
      { type: "result_fail", text: "Exit code: 1" },
      { type: "separator" }
    ]
  },
  compliant: {
    command: "merge-ready check tools/compliant-tool",
    statusText: "Exit code: 0 (PASSED)",
    statusClass: "pass",
    output: [
      { type: "divider" },
      { type: "header", text: "  MergeReady Contribution Validator — tools/compliant-tool" },
      { type: "divider" },
      { type: "space" },
      { type: "pass", rule: "L01", name: "Dedicated Directory Location" },
      { type: "pass", rule: "L02", name: "Naming Conventions" },
      { type: "pass", rule: "F01", name: "Required File Standards" },
      { type: "pass", rule: "D01", name: "Template Residue Detection" },
      { type: "pass", rule: "D02", name: "Required Documentation Sections" },
      { type: "pass", rule: "S01", name: "Zero Secrets Policy" },
      { type: "pass", rule: "S02", name: "No Virtual Environments or Local Databases" },
      { type: "pass", rule: "E01", name: "Environment Variable Drift" },
      { type: "pass", rule: "R01", name: "Declared Dependency Manifest" },
      { type: "pass", rule: "R02", name: "README Command References Consistency" },
      { type: "pass", rule: "A01", name: "Unbounded Execution Loops" },
      { type: "pass", rule: "A02", name: "Hidden and Deceptive Unicode" },
      { type: "space" },
      { type: "separator" },
      { type: "summary", text: "Summary: 12 pass · 0 fail · 0 error · 0 warn · 0 skipped · 0 n/a" },
      { type: "result_pass", text: "Result: PASSED — Contribution meets all checked repository standards." },
      { type: "result_pass", text: "Exit code: 0" },
      { type: "separator" }
    ]
  }
};

document.addEventListener("DOMContentLoaded", () => {
  initDynamicYear();
  initGitHubLinks();
  initTerminalDemo();
  initClipboardButtons();
});

/**
 * Update copyright year dynamically
 */
function initDynamicYear() {
  const yearEl = document.getElementById("current-year");
  if (yearEl) {
    yearEl.textContent = new Date().getFullYear();
  }
}

/**
 * Configure GitHub URLs across the page
 */
function initGitHubLinks() {
  const ghButtons = document.querySelectorAll(".github-btn");
  ghButtons.forEach((btn) => {
    btn.setAttribute("href", GITHUB_REPO_URL);
  });
}

/**
 * Interactive Terminal Demo Controller
 */
function initTerminalDemo() {
  const terminalScreen = document.getElementById("terminal-screen");
  const statusDot = document.getElementById("terminal-status-dot");
  const statusText = document.getElementById("terminal-status-text");
  const segmentBtns = document.querySelectorAll(".segment-btn");

  if (!terminalScreen) return;

  function renderScenario(scenarioKey) {
    const data = SCENARIOS[scenarioKey] || SCENARIOS.problematic;

    // Build terminal HTML
    let html = `<div class="t-line"><span class="t-prompt">$ </span><span class="t-cmd">${escapeHtml(data.command)}</span></div>\n`;

    data.output.forEach((item) => {
      if (item.type === "divider") {
        html += `<div class="t-rule">========================================================================</div>`;
      } else if (item.type === "separator") {
        html += `<div class="t-rule">------------------------------------------------------------------------</div>`;
      } else if (item.type === "header") {
        html += `<div>${escapeHtml(item.text)}</div>`;
      } else if (item.type === "space") {
        html += `<div></div>`;
      } else if (item.type === "pass") {
        html += `<div>  <span class="t-pass">[PASS]</span>   ${item.rule}: ${escapeHtml(item.name)}</div>`;
      } else if (item.type === "fail") {
        html += `<div>  <span class="t-fail">[FAIL]</span>   ${item.rule}: ${escapeHtml(item.name)}</div>`;
        if (item.findings) {
          item.findings.forEach((f) => {
            html += `<div class="t-detail">    - [${f.severity}] ${escapeHtml(f.msg)}</div>`;
            html += `<div class="t-fix">        Requirement: ${escapeHtml(f.req)}</div>`;
            html += `<div class="t-fix">        Fix: ${escapeHtml(f.fix)}</div>`;
          });
        }
      } else if (item.type === "summary") {
        html += `<div>${escapeHtml(item.text)}</div>`;
      } else if (item.type === "result_fail") {
        html += `<div class="t-summary-fail">${escapeHtml(item.text)}</div>`;
      } else if (item.type === "result_pass") {
        html += `<div class="t-summary-pass">${escapeHtml(item.text)}</div>`;
      }
    });

    terminalScreen.innerHTML = html;

    // Update status indicators
    if (statusDot) {
      statusDot.className = `status-indicator ${data.statusClass}`;
    }
    if (statusText) {
      statusText.textContent = data.statusText;
    }
  }

  // Segment click events
  segmentBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const scenario = btn.getAttribute("data-scenario");
      segmentBtns.forEach((b) => {
        b.classList.remove("active");
        b.setAttribute("aria-checked", "false");
      });
      btn.classList.add("active");
      btn.setAttribute("aria-checked", "true");
      renderScenario(scenario);
    });
  });

  // Keyboard navigation for segmented control (Arrow keys)
  const segmentGroup = document.querySelector(".segmented-control");
  if (segmentGroup) {
    segmentGroup.addEventListener("keydown", (e) => {
      if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        e.preventDefault();
        const btns = Array.from(segmentBtns);
        const currentIndex = btns.findIndex((b) => b.classList.contains("active"));
        let nextIndex = e.key === "ArrowRight" ? currentIndex + 1 : currentIndex - 1;
        if (nextIndex >= btns.length) nextIndex = 0;
        if (nextIndex < 0) nextIndex = btns.length - 1;
        btns[nextIndex].click();
        btns[nextIndex].focus();
      }
    });
  }

  // Initial render: problematic scenario
  renderScenario("problematic");
}

/**
 * Copy to clipboard for installation and commands
 */
function initClipboardButtons() {
  const copyButtons = document.querySelectorAll(".copy-btn");

  copyButtons.forEach((btn) => {
    btn.addEventListener("click", async () => {
      const textToCopy = btn.getAttribute("data-clipboard");
      if (!textToCopy) return;

      try {
        if (navigator.clipboard && window.isSecureContext) {
          await navigator.clipboard.writeText(textToCopy);
        } else {
          // Fallback for non-https or older browsers
          const textarea = document.createElement("textarea");
          textarea.value = textToCopy;
          textarea.style.position = "fixed";
          textarea.style.left = "-9999px";
          document.body.appendChild(textarea);
          textarea.select();
          document.execCommand("copy");
          document.body.removeChild(textarea);
        }

        // Visual feedback
        const textSpan = btn.querySelector(".copy-text");
        const originalText = textSpan ? textSpan.textContent : "Copy";
        btn.classList.add("copied");
        if (textSpan) textSpan.textContent = "Copied";

        setTimeout(() => {
          btn.classList.remove("copied");
          if (textSpan) textSpan.textContent = originalText;
        }, 2000);
      } catch (err) {
        console.error("Failed to copy command:", err);
      }
    });
  });
}

/**
 * Helper to escape HTML characters safely
 */
function escapeHtml(str) {
  if (!str) return "";
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
