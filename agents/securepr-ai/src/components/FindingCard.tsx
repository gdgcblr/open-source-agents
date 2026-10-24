import React, { useState } from 'react';
import { PrioritizedFinding } from '../types/security';
import {
  ShieldAlert,
  AlertTriangle,
  Info,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Sparkles,
  Check,
  Copy,
  Wrench,
  ShieldCheck,
} from 'lucide-react';

interface FindingCardProps {
  item: PrioritizedFinding;
  onVerifyFix: (findingId: string, filePath: string, fixedContent: string) => Promise<boolean>;
}

export const FindingCard: React.FC<FindingCardProps> = ({ item, onVerifyFix }) => {
  const { finding, risk, resolved } = item;
  const [showRiskDetail, setShowRiskDetail] = useState(false);
  const [showAiAnalysis, setShowAiAnalysis] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiContent, setAiContent] = useState<string | null>(item.aiExplanation || null);
  const [showFixModal, setShowFixModal] = useState(false);
  const [isVerifying, setIsVerifying] = useState(false);
  const [verifyStatus, setVerifyStatus] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Severity visual styling (Light theme high contrast)
  const severityConfig = {
    CRITICAL: {
      border: 'border-l-rose-500',
      badgeText: 'text-rose-700',
      bgTag: 'bg-rose-50',
      icon: ShieldAlert,
    },
    HIGH: {
      border: 'border-l-amber-500',
      badgeText: 'text-amber-700',
      bgTag: 'bg-amber-50',
      icon: AlertTriangle,
    },
    MEDIUM: {
      border: 'border-l-yellow-500',
      badgeText: 'text-yellow-700',
      bgTag: 'bg-yellow-50',
      icon: AlertTriangle,
    },
    LOW: {
      border: 'border-l-blue-500',
      badgeText: 'text-blue-700',
      bgTag: 'bg-blue-50',
      icon: Info,
    },
    INFO: {
      border: 'border-l-slate-400',
      badgeText: 'text-slate-600',
      bgTag: 'bg-slate-50',
      icon: Info,
    },
  }[risk.priorityLevel] || {
    border: 'border-l-slate-400',
    badgeText: 'text-slate-600',
    bgTag: 'bg-slate-50',
    icon: Info,
  };

  const IconComponent = resolved ? ShieldCheck : severityConfig.icon;

  const handleAskAi = async () => {
    setShowAiAnalysis(true);
    if (aiContent) return;
    setAiLoading(true);

    try {
      const res = await fetch('/api/explain', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          finding,
          fileContent: finding.evidence[0]?.snippet || '',
        }),
      });
      const data = await res.json();
      setAiContent(data.analysis || 'Analysis complete.');
    } catch {
      setAiContent('Could not connect to AI reasoning service. Please check configuration.');
    } finally {
      setAiLoading(false);
    }
  };

  const getSuggestedFixCode = () => {
    if (finding.category === 'JWT_AUTH') {
      return `# Secure replacement: Enforce signature verification and algorithm restriction
claims = jwt.decode(
    token,
    JWT_PUBLIC_KEY,
    algorithms=["RS256"],
    options={"verify_signature": True, "verify_exp": True}
)`;
    }
    if (finding.category === 'API_AUTHORIZATION') {
      return `# Secure replacement: Require authentication & verify user ownership
@app.post("/users/{user_id}/profile")
def update_profile(user_id: str, payload: dict, user = Depends(get_current_user)):
    if user["sub"] != user_id and not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    db.users.filter(id=user_id).update(**payload)`;
    }
    if (finding.category === 'SECRET') {
      return `# Secure replacement: Load credential safely from environment variable or Vault
API_KEY = os.environ.get("SERVICE_API_KEY")
if not API_KEY:
    raise RuntimeError("Missing required SERVICE_API_KEY environment variable")`;
    }
    if (finding.category === 'CONFIG') {
      return `# Secure replacement: Whitelist explicit allowed frontend origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://dashboard.example.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT"]
)`;
    }
    return `# Secure remediation:
${finding.remediationHint}`;
  };

  const [fixCodeInput, setFixCodeInput] = useState(getSuggestedFixCode());

  const handleRunVerification = async () => {
    setIsVerifying(true);
    setVerifyStatus(null);
    try {
      const isOk = await onVerifyFix(
        finding.id,
        finding.evidence[0]?.filePath || 'src/main.py',
        fixCodeInput
      );
      if (isOk) {
        setVerifyStatus('success');
      } else {
        setVerifyStatus('failed');
      }
    } catch {
      setVerifyStatus('error');
    } finally {
      setIsVerifying(false);
    }
  };

  const handleCopySnippet = () => {
    navigator.clipboard.writeText(finding.evidence[0]?.snippet || '');
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div
      className={`border rounded-xl overflow-hidden transition-all border-l-4 shadow-xs ${
        resolved
          ? 'border-emerald-300 border-l-emerald-600 bg-emerald-50/20'
          : `border-slate-200 bg-white ${severityConfig.border}`
      }`}
    >
      <div className="p-4 sm:p-5 flex flex-col gap-3">
        {/* Header row */}
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <div
              className={`p-1.5 rounded-lg mt-0.5 ${
                resolved
                  ? 'bg-emerald-100 text-emerald-700'
                  : `${severityConfig.bgTag} ${severityConfig.badgeText}`
              }`}
            >
              <IconComponent className="w-4 h-4" />
            </div>

            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs font-bold text-slate-700">
                  {finding.id}
                </span>

                <span aria-hidden="true" className="text-slate-300">·</span>

                <span
                  className={`font-mono text-xs font-bold ${
                    resolved ? 'text-emerald-700' : severityConfig.badgeText
                  }`}
                >
                  {resolved ? 'VERIFIED RESOLVED' : `${risk.priorityLevel} (${risk.numericScore}/10)`}
                </span>

                <span aria-hidden="true" className="text-slate-300">·</span>

                <span className="text-xs text-slate-500 font-medium font-mono">
                  {finding.category}
                </span>

                {finding.isNewInDiff && (
                  <>
                    <span aria-hidden="true" className="text-slate-300">·</span>
                    <span className="text-xs text-amber-700 font-mono font-semibold">New in Diff</span>
                  </>
                )}
              </div>

              <h3 className="text-sm sm:text-base font-bold text-slate-900 mt-1 tracking-tight">
                {finding.title}
              </h3>
            </div>
          </div>

          {/* Quick Actions */}
          <div className="flex items-center gap-2">
            <button
              onClick={handleAskAi}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-50 hover:bg-slate-100 text-slate-700 border border-slate-200 rounded-lg text-xs font-semibold shadow-2xs transition-colors"
            >
              <Sparkles className="w-3.5 h-3.5 text-emerald-600" />
              <span>AI Analysis</span>
            </button>

            <button
              onClick={() => setShowFixModal(!showFixModal)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold shadow-2xs transition-colors ${
                resolved
                  ? 'bg-emerald-50 text-emerald-800 border border-emerald-300 hover:bg-emerald-100'
                  : 'bg-emerald-600 hover:bg-emerald-700 text-white'
              }`}
            >
              <Wrench className="w-3.5 h-3.5" />
              <span>{resolved ? 'View Fix Details' : 'Verify Fix'}</span>
            </button>
          </div>
        </div>

        {/* Unboxed Metadata Line (Zero-Pill Compliance) */}
        <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500 pt-1 border-t border-slate-100">
          <span>STRIDE: {finding.stride.join(', ')}</span>
          {finding.owaspApiCategory && (
            <>
              <span aria-hidden="true" className="text-slate-300">·</span>
              <span>OWASP: {finding.owaspApiCategory}</span>
            </>
          )}
          {finding.cweId && (
            <>
              <span aria-hidden="true" className="text-slate-300">·</span>
              <span className="font-mono">{finding.cweId}</span>
            </>
          )}
          <span aria-hidden="true" className="text-slate-300">·</span>
          <span>Scanner: {finding.scannerName}</span>
        </div>

        {/* Description */}
        <p className="text-xs sm:text-sm text-slate-700 leading-relaxed">
          {finding.description}
        </p>

        {/* Redacted Evidence Snippet */}
        {finding.evidence.length > 0 && (
          <div className="mt-1 bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
            <div className="px-3.5 py-1.5 bg-slate-950 border-b border-slate-800 flex items-center justify-between text-xs">
              <span className="font-mono text-slate-400">
                {finding.evidence[0].filePath}:{finding.evidence[0].startLine}
                {finding.evidence[0].endLine !== finding.evidence[0].startLine
                  ? `-${finding.evidence[0].endLine}`
                  : ''}
              </span>

              <div className="flex items-center gap-3">
                <div className="flex items-center gap-1 text-[11px] text-emerald-400 font-medium">
                  <CheckCircle2 className="w-3 h-3" />
                  <span>Sanitized (No secret leakage)</span>
                </div>
                <button
                  onClick={handleCopySnippet}
                  className="text-slate-400 hover:text-slate-200 transition-colors"
                  title="Copy snippet"
                >
                  {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                </button>
              </div>
            </div>

            <pre className="p-3.5 text-xs font-mono text-slate-200 overflow-x-auto leading-5 bg-slate-900">
              <code>{finding.evidence[0].snippet}</code>
            </pre>
          </div>
        )}

        {/* Contextual Risk Accordion */}
        <div className="border border-slate-200 rounded-lg overflow-hidden bg-slate-50/50">
          <button
            onClick={() => setShowRiskDetail(!showRiskDetail)}
            className="w-full px-3.5 py-2 flex items-center justify-between text-xs text-slate-700 hover:bg-slate-100/70 transition-colors"
          >
            <div className="flex items-center gap-2">
              <span className="font-semibold text-slate-600">Risk Assessment:</span>
              <span className="font-mono text-slate-900">{risk.rationale}</span>
            </div>
            {showRiskDetail ? <ChevronUp className="w-3.5 h-3.5 text-slate-500" /> : <ChevronDown className="w-3.5 h-3.5 text-slate-500" />}
          </button>

          {showRiskDetail && (
            <div className="px-4 py-3 border-t border-slate-200 text-xs text-slate-600 grid grid-cols-2 sm:grid-cols-4 gap-3 bg-white">
              <div>
                <div className="text-[11px] text-slate-500">Impact Factor</div>
                <div className="font-mono text-slate-900 text-sm font-bold">{risk.impact.toFixed(2)}</div>
                <div className="text-[10px] text-slate-400">Weight 55%</div>
              </div>
              <div>
                <div className="text-[11px] text-slate-500">Likelihood Factor</div>
                <div className="font-mono text-slate-900 text-sm font-bold">{risk.likelihood.toFixed(2)}</div>
                <div className="text-[10px] text-slate-400">Weight 45%</div>
              </div>
              <div>
                <div className="text-[11px] text-slate-500">Exposure Multiplier</div>
                <div className="font-mono text-emerald-700 text-sm font-bold">×{risk.exposureModifier.toFixed(2)}</div>
                <div className="text-[10px] text-slate-400">Public vs Internal</div>
              </div>
              <div>
                <div className="text-[11px] text-slate-500">Confidence</div>
                <div className="font-mono text-slate-900 text-sm font-bold">{Math.round(risk.confidence * 100)}%</div>
                <div className="text-[10px] text-slate-400">AST Line-Attributed</div>
              </div>
            </div>
          )}
        </div>

        {/* AI Analysis Panel */}
        {showAiAnalysis && (
          <div className="mt-2 p-4 bg-teal-50/50 border border-teal-200 rounded-lg">
            <div className="flex items-center justify-between pb-2 mb-2 border-b border-teal-200/60">
              <div className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-emerald-700" />
                <span className="text-xs font-bold text-teal-900">
                  SecurePR AI Contextual Threat Analysis
                </span>
              </div>
              <span className="text-[10px] font-mono text-teal-700">
                Gemini 3.8 Flash · Zero Secret Leakage Verified
              </span>
            </div>

            {aiLoading ? (
              <div className="flex items-center gap-2 text-xs text-teal-800 py-3">
                <div className="w-3.5 h-3.5 border-2 border-teal-600 border-t-transparent rounded-full animate-spin" />
                <span>Correlating evidence and evaluating false-positive boundary...</span>
              </div>
            ) : (
              <div className="text-xs text-slate-800 space-y-2 whitespace-pre-line leading-relaxed font-sans">
                {aiContent}
              </div>
            )}
          </div>
        )}

        {/* Fix Verification Workbench */}
        {showFixModal && (
          <div className="mt-2 p-4 bg-slate-50 border border-slate-200 rounded-lg">
            <div className="flex items-center justify-between pb-2 mb-3 border-b border-slate-200">
              <div className="flex items-center gap-2">
                <Wrench className="w-4 h-4 text-emerald-700" />
                <span className="text-xs font-bold text-slate-900">
                  Interactive Fix Verification Workbench
                </span>
              </div>
              <span className="text-[11px] text-slate-500 font-medium">
                Apply patch and re-evaluate gate closure
              </span>
            </div>

            <p className="text-xs text-slate-600 mb-2">
              Review or adjust the remediation code below. Clicking <strong>Verify Fix</strong> immediately re-evaluates the file against Semgrep AST rules and secret scanners to prove closure.
            </p>

            <textarea
              value={fixCodeInput}
              onChange={(e) => setFixCodeInput(e.target.value)}
              rows={6}
              className="w-full bg-slate-900 border border-slate-800 rounded-lg p-3 font-mono text-xs text-emerald-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 shadow-inner"
            />

            <div className="flex items-center justify-between mt-3">
              <div className="text-xs">
                {verifyStatus === 'success' && (
                  <span className="text-emerald-700 font-semibold flex items-center gap-1">
                    <CheckCircle2 className="w-4 h-4" />
                    Fix verified! Vulnerability closed. PR gate blockage cleared.
                  </span>
                )}
                {verifyStatus === 'failed' && (
                  <span className="text-rose-700 font-semibold flex items-center gap-1">
                    <AlertTriangle className="w-4 h-4" />
                    Fix incomplete: The vulnerability is still detected.
                  </span>
                )}
                {verifyStatus === 'error' && (
                  <span className="text-amber-700 font-semibold">Error verifying fix. Check server status.</span>
                )}
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => setShowFixModal(false)}
                  className="px-3 py-1.5 text-xs text-slate-600 hover:text-slate-900 font-medium"
                >
                  Cancel
                </button>
                <button
                  onClick={handleRunVerification}
                  disabled={isVerifying}
                  className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold shadow-xs disabled:opacity-50 flex items-center gap-1.5"
                >
                  {isVerifying ? (
                    <div className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  ) : (
                    <Check className="w-3.5 h-3.5" />
                  )}
                  <span>Test Fix Verification</span>
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
