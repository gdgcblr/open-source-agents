import React, { useState } from 'react';
import { X, Terminal, Copy, Check, GitPullRequest, Code2 } from 'lucide-react';

interface CliIntegrationModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const CliIntegrationModal: React.FC<CliIntegrationModalProps> = ({ isOpen, onClose }) => {
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleCopy = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  const localCliSnippet = `# 1. Navigate to agent directory & install dependencies
cd agents/securepr-agent
pip install -r requirements.txt

# 2. Automated PR Gate Scan (blocks on HIGH/CRITICAL)
python -m securepr_agent.cli scan \\
  --path . \\
  --base origin/main \\
  --fail-on HIGH \\
  --md-out pr-security-report.md

# 3. Run Benchmark Suite (Evaluate Precision, Recall & FPR)
python -m securepr_agent.cli benchmark

# 4. Scan remote GitHub PR directly by URL
python -m securepr_agent.cli scan-pr \\
  --pr-url https://github.com/acme-corp/repo/pull/142 \\
  --fail-on HIGH \\
  --post-comment

# 5. Interactive Conversational Agent (Multi-turn review & fix verification)
python -m securepr_agent.cli chat --pr-url https://github.com/acme-corp/repo/pull/142`;

  const githubActionsYaml = `name: SecurePR AI Gate
on:
  pull_request:
    branches: [main, master]

jobs:
  security-gate:
    name: Threat & Vulnerability Gate
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install SecurePR Agent
        run: pip install -r agents/securepr-agent/requirements.txt

      - name: Run SecurePR Security Gate
        env:
          GEMINI_API_KEY: \${{ secrets.GEMINI_API_KEY }}
          GITHUB_TOKEN: \${{ secrets.GITHUB_TOKEN }}
        run: |
          python -m securepr_agent.cli scan \\
            --path . \\
            --base origin/\${{ github.base_ref }} \\
            --fail-on HIGH \\
            --md-out pr-review-comment.md

      - name: Publish PR Comment
        if: always()
        uses: thollander/actions-comment-pull-request@v2
        with:
          filePath: pr-review-comment.md`;

  const preCommitSnippet = `#!/usr/bin/env bash
# .git/hooks/pre-push or pre-commit
echo "[SecurePR AI] Evaluating staged diff for high-risk vulnerabilities..."

python -m securepr_agent.cli scan \\
  --path . \\
  --fail-on HIGH

if [ $? -ne 0 ]; then
  echo "[SecurePR AI] Push blocked: resolve security findings or apply fixes."
  exit 1
fi`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-xs">
      <div className="bg-white border border-slate-200 rounded-xl max-w-3xl w-full p-6 text-slate-800 shadow-2xl space-y-4 flex flex-col max-h-[85vh]">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
          <div className="flex items-center gap-2">
            <Terminal className="w-5 h-5 text-emerald-600" />
            <h3 className="text-base font-bold text-slate-900">
              CLI & CI/CD Pipeline Integration
            </h3>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700 p-1 rounded-lg"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto space-y-5 text-xs text-slate-600 pr-1">
          {/* Section 1: Local CLI */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-bold text-slate-900 flex items-center gap-1.5">
                <Terminal className="w-4 h-4 text-emerald-600" />
                Local Terminal CLI & Benchmark (<code className="font-mono text-emerald-800 font-semibold bg-emerald-50 px-1 rounded">agents/securepr-agent/</code>)
              </span>
              <button
                onClick={() => handleCopy(localCliSnippet, 'cli')}
                className="flex items-center gap-1 text-[11px] text-slate-500 hover:text-slate-900 font-medium"
              >
                {copiedKey === 'cli' ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copiedKey === 'cli' ? 'Copied' : 'Copy Commands'}</span>
              </button>
            </div>
            <pre className="p-3.5 bg-slate-900 border border-slate-800 rounded-lg font-mono text-slate-200 overflow-x-auto leading-5">
              {localCliSnippet}
            </pre>
          </div>

          {/* Section 2: GitHub Actions */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-bold text-slate-900 flex items-center gap-1.5">
                <GitPullRequest className="w-4 h-4 text-emerald-600" />
                GitHub Actions CI Workflow (<code className="font-mono text-emerald-800 font-semibold bg-emerald-50 px-1 rounded">.github/workflows/securepr.yml</code>)
              </span>
              <button
                onClick={() => handleCopy(githubActionsYaml, 'gha')}
                className="flex items-center gap-1 text-[11px] text-slate-500 hover:text-slate-900 font-medium"
              >
                {copiedKey === 'gha' ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copiedKey === 'gha' ? 'Copied' : 'Copy YAML'}</span>
              </button>
            </div>
            <pre className="p-3.5 bg-slate-900 border border-slate-800 rounded-lg font-mono text-slate-200 overflow-x-auto leading-5">
              {githubActionsYaml}
            </pre>
          </div>

          {/* Section 3: Pre-commit Hook */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-bold text-slate-900 flex items-center gap-1.5">
                <Code2 className="w-4 h-4 text-emerald-600" />
                Git Pre-Push Hook (<code className="font-mono text-emerald-800 font-semibold bg-emerald-50 px-1 rounded">.git/hooks/pre-push</code>)
              </span>
              <button
                onClick={() => handleCopy(preCommitSnippet, 'hook')}
                className="flex items-center gap-1 text-[11px] text-slate-500 hover:text-slate-900 font-medium"
              >
                {copiedKey === 'hook' ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copiedKey === 'hook' ? 'Copied' : 'Copy Script'}</span>
              </button>
            </div>
            <pre className="p-3.5 bg-slate-900 border border-slate-800 rounded-lg font-mono text-slate-200 overflow-x-auto leading-5">
              {preCommitSnippet}
            </pre>
          </div>
        </div>

        {/* Footer */}
        <div className="pt-3 border-t border-slate-100 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-lg text-xs font-semibold"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
