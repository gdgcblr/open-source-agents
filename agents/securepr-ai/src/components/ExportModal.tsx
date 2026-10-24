import React, { useState } from 'react';
import { X, Copy, Download, Check, FileText } from 'lucide-react';
import { ScanResult } from '../types/security';

interface ExportModalProps {
  isOpen: boolean;
  onClose: () => void;
  scanResult: ScanResult | null;
  prTitle?: string;
  prNumber?: number;
}

export const ExportModal: React.FC<ExportModalProps> = ({
  isOpen,
  onClose,
  scanResult,
  prTitle = 'Pull Request',
  prNumber = 1,
}) => {
  const [tab, setTab] = useState<'markdown' | 'json'>('markdown');
  const [copied, setCopied] = useState(false);

  if (!isOpen || !scanResult) return null;

  const gateIcon = scanResult.passedGate ? '✅' : '❌';
  const gateStatus = scanResult.passedGate ? 'PASSED' : 'BLOCKED';

  let markdown = `## SecurePR AI Security Review - ${gateIcon} \`${gateStatus}\`\n\n`;
  markdown += `**PR:** #${prNumber} · **Findings:** ${scanResult.totalFindings} · **Redacted Secrets:** ${scanResult.redactedItemCount} · **Gate Policy:** \`${scanResult.failOnPolicy}\`\n\n`;

  if (scanResult.attackPathHypotheses.length > 0) {
    markdown += `### ⛓️ Inferred Multi-File Attack Hypotheses (STRIDE)\n`;
    for (const hyp of scanResult.attackPathHypotheses) {
      markdown += `#### [${hyp.id}] ${hyp.title} (\`${hyp.stride}\`)\n${hyp.summary}\n\n`;
      markdown += `**Attack Flow:**\n`;
      for (const step of hyp.steps) {
        markdown += `${step.stepNumber}. \`${step.filePath}\`: ${step.actionOrState}\n`;
      }
      markdown += `\n`;
    }
  }

  markdown += `### 🛡️ Prioritized Findings\n\n`;
  if (scanResult.prioritizedFindings.length === 0) {
    markdown += `No security weaknesses identified in this pull request diff.\n`;
  } else {
    for (const item of scanResult.prioritizedFindings) {
      const f = item.finding;
      const r = item.risk;
      const statusBadge = item.resolved ? '`[RESOLVED]`' : `\`[${r.priorityLevel} - ${r.numericScore}/10]\``;

      markdown += `#### ${statusBadge} ${f.id}: ${f.title}\n`;
      markdown += `- **Category:** \`${f.category}\` | **STRIDE:** ${f.stride.join(', ')}\n`;
      if (f.owaspApiCategory) markdown += `- **OWASP:** \`${f.owaspApiCategory}\`\n`;
      markdown += `- **Risk Rationale:** ${r.rationale}\n\n`;
      markdown += `**Evidence (${f.evidence[0]?.filePath}:${f.evidence[0]?.startLine}):**\n\`\`\`python\n${f.evidence[0]?.snippet}\n\`\`\`\n\n`;
      markdown += `**Recommended Fix:**\n${f.remediationHint}\n\n---\n\n`;
    }
  }

  const jsonString = JSON.stringify(scanResult, null, 2);

  const handleCopy = () => {
    navigator.clipboard.writeText(tab === 'markdown' ? markdown : jsonString);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    const content = tab === 'markdown' ? markdown : jsonString;
    const blob = new Blob([content], {
      type: tab === 'markdown' ? 'text/markdown' : 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download =
      tab === 'markdown'
        ? `securepr-report-pr-${prNumber}.md`
        : `securepr-report-pr-${prNumber}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-xs">
      <div className="bg-white border border-slate-200 rounded-xl max-w-3xl w-full p-6 text-slate-800 shadow-2xl space-y-4 flex flex-col max-h-[85vh]">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
          <div className="flex items-center gap-2">
            <FileText className="w-5 h-5 text-emerald-600" />
            <h3 className="text-base font-bold text-slate-900">
              Export Security Review Report
            </h3>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700 p-1 rounded-lg"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Tab switcher */}
        <div className="flex items-center justify-between">
          <div className="flex items-center bg-slate-100 p-0.5 rounded-lg border border-slate-200 text-xs">
            <button
              onClick={() => setTab('markdown')}
              className={`px-3 py-1 font-mono rounded-md transition-colors ${
                tab === 'markdown'
                  ? 'bg-white text-slate-900 font-bold shadow-2xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              GitHub PR Markdown Comment
            </button>
            <button
              onClick={() => setTab('json')}
              className={`px-3 py-1 font-mono rounded-md transition-colors ${
                tab === 'json'
                  ? 'bg-white text-slate-900 font-bold shadow-2xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Machine-Readable JSON Report
            </button>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleCopy}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
              <span>{copied ? 'Copied!' : 'Copy'}</span>
            </button>

            <button
              onClick={handleDownload}
              className="flex items-center gap-1.5 px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold shadow-xs"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Download File</span>
            </button>
          </div>
        </div>

        {/* Preview content */}
        <div className="flex-1 overflow-auto bg-slate-900 border border-slate-800 rounded-lg p-4">
          <pre className="text-xs font-mono text-slate-200 whitespace-pre-wrap leading-relaxed">
            {tab === 'markdown' ? markdown : jsonString}
          </pre>
        </div>
      </div>
    </div>
  );
};
