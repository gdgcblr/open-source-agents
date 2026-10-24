import React, { useState, useEffect } from 'react';
import { Header } from './components/Header';
import { RiskBar } from './components/RiskBar';
import { FindingCard } from './components/FindingCard';
import { AttackPathView } from './components/AttackPathView';
import { DiffEditorView } from './components/DiffEditorView';
import { RiskMatrixModal } from './components/RiskMatrixModal';
import { ExportModal } from './components/ExportModal';
import { CliIntegrationModal } from './components/CliIntegrationModal';
import { AgentChatPanel } from './components/AgentChatPanel';
import { GitHubPrIngestModal } from './components/GitHubPrIngestModal';
import { BenchmarkScorecard } from './components/BenchmarkScorecard';
import {
  ExposureContext,
  PullRequestPreset,
  ScanResult,
  Severity,
} from './types/security';
import {
  ShieldAlert,
  Flame,
  FileCode,
  CheckCircle2,
  Search,
  GitPullRequest,
  Bot,
  Award,
} from 'lucide-react';

export default function App() {
  const [presets, setPresets] = useState<PullRequestPreset[]>([]);
  const [currentPr, setCurrentPr] = useState<PullRequestPreset | null>(null);
  const [isCustom, setIsCustom] = useState<boolean>(false);
  const [customFiles, setCustomFiles] = useState<
    Array<{ path: string; content: string; diff?: string }>
  >([]);

  // Policy Settings
  const [failOn, setFailOn] = useState<Severity>('HIGH');
  const [exposure, setExposure] = useState<ExposureContext>('PUBLIC');

  // Scanner state
  const [isScanning, setIsScanning] = useState(false);
  const [scanResult, setScanResult] = useState<ScanResult | null>(null);

  // Active view tab
  const [activeTab, setActiveTab] = useState<'findings' | 'benchmark' | 'attack-paths' | 'agent-chat' | 'diff'>('findings');

  // Finding filters
  const [categoryFilter, setCategoryFilter] = useState<string>('ALL');
  const [severityFilter, setSeverityFilter] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState('');

  // Modals
  const [showRiskModal, setShowRiskModal] = useState(false);
  const [showExportModal, setShowExportModal] = useState(false);
  const [showCliModal, setShowCliModal] = useState(false);
  const [showIngestModal, setShowIngestModal] = useState(false);

  // Load presets on mount
  useEffect(() => {
    fetch('/api/presets')
      .then((res) => res.json())
      .then((data: PullRequestPreset[]) => {
        setPresets(data);
        if (data.length > 0) {
          setCurrentPr(data[0]);
          setExposure(data[0].exposure || 'PUBLIC');
          runScanOnFiles(data[0].files, data[0].exposure || 'PUBLIC', failOn);
        }
      })
      .catch((err) => {
        console.error('Failed to load presets:', err);
      });
  }, []);

  // Run scan helper
  const runScanOnFiles = async (
    files: Array<{ path: string; content: string; diff?: string }>,
    exp: ExposureContext,
    gatePolicy: Severity
  ) => {
    setIsScanning(true);
    try {
      const res = await fetch('/api/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          files,
          exposure: exp,
          failOn: gatePolicy,
        }),
      });
      const data: ScanResult = await res.json();
      setScanResult(data);
    } catch (err) {
      console.error('Scan failed:', err);
    } finally {
      setIsScanning(false);
    }
  };

  const handleSelectPreset = (preset: PullRequestPreset) => {
    setIsCustom(false);
    setCurrentPr(preset);
    setExposure(preset.exposure);
    runScanOnFiles(preset.files, preset.exposure, failOn);
  };

  const handleSelectCustom = () => {
    setIsCustom(true);
    const initial = currentPr?.files || [
      {
        path: 'src/main.py',
        status: 'modified',
        content: `import jwt\n\n# Paste your pull request code here\nclaims = jwt.decode(token, verify=False, algorithms=["none"])\n`,
      },
    ];
    setCustomFiles(initial);
    runScanOnFiles(initial, exposure, failOn);
  };

  const handleReScan = () => {
    const filesToScan = isCustom ? customFiles : currentPr?.files || [];
    runScanOnFiles(filesToScan, exposure, failOn);
  };

  const handleFailOnPolicyChange = (newLevel: Severity) => {
    setFailOn(newLevel);
    const filesToScan = isCustom ? customFiles : currentPr?.files || [];
    runScanOnFiles(filesToScan, exposure, newLevel);
  };

  const handleExposureChange = (newExp: ExposureContext) => {
    setExposure(newExp);
    const filesToScan = isCustom ? customFiles : currentPr?.files || [];
    runScanOnFiles(filesToScan, newExp, failOn);
  };

  // Fix verification handler
  const handleVerifyFix = async (
    findingId: string,
    filePath: string,
    fixedContent: string
  ): Promise<boolean> => {
    try {
      const res = await fetch('/api/verify-fix', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          originalFindingId: findingId,
          filePath,
          fixedContent,
          exposure,
        }),
      });
      const data = await res.json();

      if (data.resolved && scanResult) {
        const updatedFindings = scanResult.prioritizedFindings.map((item) => {
          if (item.finding.id === findingId) {
            return { ...item, resolved: true };
          }
          return item;
        });

        const severityHierarchy: Record<string, number> = {
          INFO: 0,
          LOW: 1,
          MEDIUM: 2,
          HIGH: 3,
          CRITICAL: 4,
        };
        const failThresholdVal = severityHierarchy[failOn] ?? 3;
        const stillFails = updatedFindings.some((item) => {
          if (item.resolved) return false;
          const itemVal = severityHierarchy[item.risk.priorityLevel] ?? 0;
          return itemVal >= failThresholdVal && item.finding.isNewInDiff;
        });

        setScanResult({
          ...scanResult,
          prioritizedFindings: updatedFindings,
          passedGate: !stillFails,
        });

        return true;
      }
      return false;
    } catch {
      return false;
    }
  };

  // Filtered findings
  const findings = scanResult?.prioritizedFindings || [];
  const filteredFindings = findings.filter((item) => {
    if (categoryFilter !== 'ALL' && item.finding.category !== categoryFilter) return false;
    if (severityFilter !== 'ALL' && item.risk.priorityLevel !== severityFilter) return false;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const match =
        item.finding.title.toLowerCase().includes(q) ||
        item.finding.id.toLowerCase().includes(q) ||
        item.finding.description.toLowerCase().includes(q) ||
        item.finding.evidence[0]?.filePath.toLowerCase().includes(q);
      if (!match) return false;
    }
    return true;
  });

  const criticalCount = findings.filter((f) => f.risk.priorityLevel === 'CRITICAL' && !f.resolved)
    .length;
  const highCount = findings.filter((f) => f.risk.priorityLevel === 'HIGH' && !f.resolved).length;
  const resolvedCount = findings.filter((f) => f.resolved).length;

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col font-sans selection:bg-emerald-500/20 selection:text-emerald-950">
      {/* Top Header */}
      <Header
        currentPr={currentPr}
        presets={presets}
        onSelectPr={handleSelectPreset}
        onSelectCustom={handleSelectCustom}
        isCustom={isCustom}
        passedGate={scanResult?.passedGate ?? true}
        totalFindings={findings.filter((f) => !f.resolved).length}
        isScanning={isScanning}
        onRunScan={handleReScan}
        onOpenExport={() => setShowExportModal(true)}
        onOpenCli={() => setShowCliModal(true)}
        onOpenIngest={() => setShowIngestModal(true)}
      />

      {/* Policy & Risk Matrix Subbar */}
      <RiskBar
        failOn={failOn}
        onChangeFailOn={handleFailOnPolicyChange}
        exposure={exposure}
        onChangeExposure={handleExposureChange}
        totalFindings={findings.length}
        criticalCount={criticalCount}
        highCount={highCount}
        redactedCount={scanResult?.redactedItemCount || 0}
        hypothesesCount={scanResult?.attackPathHypotheses?.length || 0}
        resolvedCount={resolvedCount}
        onOpenRiskInfo={() => setShowRiskModal(true)}
      />

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {/* Pull Request Context Card */}
        <div className="bg-white border border-slate-200/90 rounded-xl p-5 shadow-xs flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-start gap-3.5">
            <div className="p-2.5 bg-slate-100 text-emerald-700 rounded-lg shrink-0 mt-0.5">
              <GitPullRequest className="w-5 h-5" />
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="font-mono text-slate-800 font-bold">
                  {isCustom ? 'Custom Diff Review' : `${currentPr?.repo} · PR #${currentPr?.prNumber}`}
                </span>
                <span aria-hidden="true" className="text-slate-300">·</span>
                <span className="text-slate-500 font-medium">
                  Author: <code className="text-slate-800 font-semibold">{isCustom ? 'Developer' : currentPr?.author}</code>
                </span>
                <span aria-hidden="true" className="text-slate-300">·</span>
                <span className="text-slate-500 font-medium">
                  Branch: <code className="text-emerald-800 font-semibold">{isCustom ? 'local-patch' : currentPr?.branch}</code> → <code className="text-slate-600">{isCustom ? 'main' : currentPr?.baseBranch}</code>
                </span>
              </div>
              <h1 className="text-base sm:text-lg font-bold text-slate-900 mt-1 tracking-tight">
                {isCustom ? 'Custom Review Playground' : currentPr?.title}
              </h1>
              <p className="text-xs text-slate-600 mt-1 max-w-3xl leading-relaxed">
                {isCustom
                  ? 'Testing live code changes and deterministic scanners. All raw secrets are scrubbed before analysis.'
                  : currentPr?.description}
              </p>
            </div>
          </div>

          {/* Gate Verdict Box */}
          <div
            className={`px-4 py-3 rounded-xl border flex flex-col justify-center text-right shadow-2xs ${
              scanResult?.passedGate
                ? 'bg-emerald-50/70 border-emerald-300 text-emerald-900'
                : 'bg-rose-50/70 border-rose-300 text-rose-900'
            }`}
          >
            <div className="text-[11px] font-mono uppercase tracking-wider text-slate-500 font-semibold">
              CI Gate Decision
            </div>
            <div className="text-base font-extrabold font-mono tracking-tight">
              {scanResult?.passedGate ? 'PASS / MERGE APPROVED' : 'FAIL / MERGE BLOCKED'}
            </div>
            <div className="text-[11px] text-slate-500 mt-0.5 font-medium">
              Threshold: fail on {failOn}
            </div>
          </div>
        </div>

        {/* View Tabs Bar */}
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 pb-2">
          <div className="flex items-center gap-1.5 bg-slate-200/60 p-1 rounded-xl border border-slate-300/60">
            <button
              onClick={() => setActiveTab('findings')}
              className={`flex items-center gap-2 px-3.5 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                activeTab === 'findings'
                  ? 'bg-white text-slate-900 shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <ShieldAlert className="w-3.5 h-3.5 text-rose-600" />
              <span>Prioritized Findings</span>
              <span className="text-[11px] font-mono text-slate-500 font-normal">
                ({findings.length})
              </span>
            </button>

            <button
              onClick={() => setActiveTab('benchmark')}
              className={`flex items-center gap-2 px-3.5 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                activeTab === 'benchmark'
                  ? 'bg-white text-slate-900 shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <Award className="w-3.5 h-3.5 text-emerald-600" />
              <span>Benchmark & Evaluation</span>
              <span className="text-[10px] font-mono text-emerald-700 bg-emerald-100 px-1.5 py-0.5 rounded font-bold">
                Metrics
              </span>
            </button>

            <button
              onClick={() => setActiveTab('attack-paths')}
              className={`flex items-center gap-2 px-3.5 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                activeTab === 'attack-paths'
                  ? 'bg-white text-slate-900 shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <Flame className="w-3.5 h-3.5 text-orange-600" />
              <span>STRIDE Attack Paths</span>
              <span className="text-[11px] font-mono text-slate-500 font-normal">
                ({scanResult?.attackPathHypotheses?.length || 0})
              </span>
            </button>

            <button
              onClick={() => setActiveTab('agent-chat')}
              className={`flex items-center gap-2 px-3.5 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                activeTab === 'agent-chat'
                  ? 'bg-white text-slate-900 shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <Bot className="w-3.5 h-3.5 text-emerald-600" />
              <span>Review Agent Chat</span>
            </button>

            <button
              onClick={() => setActiveTab('diff')}
              className={`flex items-center gap-2 px-3.5 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                activeTab === 'diff'
                  ? 'bg-white text-slate-900 shadow-xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <FileCode className="w-3.5 h-3.5 text-emerald-600" />
              <span>Code & Diff Workbench</span>
            </button>
          </div>

          {/* Search & Filter Bar (Active in Findings tab) */}
          {activeTab === 'findings' && (
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <div className="relative">
                <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
                <input
                  type="text"
                  placeholder="Filter findings..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-8 pr-3 py-1.5 bg-white border border-slate-200 rounded-lg text-xs text-slate-800 focus:outline-none focus:border-slate-400 w-48 shadow-2xs"
                />
              </div>

              {/* Category Filter */}
              <select
                value={categoryFilter}
                onChange={(e) => setCategoryFilter(e.target.value)}
                className="bg-white border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs text-slate-700 focus:outline-none shadow-2xs font-medium"
              >
                <option value="ALL">All Categories</option>
                <option value="SECRET">Secrets</option>
                <option value="JWT_AUTH">JWT & Auth</option>
                <option value="API_AUTHORIZATION">API Authorization (BOLA)</option>
                <option value="CONFIG">Configuration & CORS</option>
              </select>

              {/* Severity Filter */}
              <select
                value={severityFilter}
                onChange={(e) => setSeverityFilter(e.target.value)}
                className="bg-white border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs text-slate-700 focus:outline-none shadow-2xs font-medium"
              >
                <option value="ALL">All Severities</option>
                <option value="CRITICAL">Critical Only</option>
                <option value="HIGH">High Only</option>
                <option value="MEDIUM">Medium Only</option>
              </select>
            </div>
          )}
        </div>

        {/* Tab 1: Findings & Evidence */}
        {activeTab === 'findings' && (
          <div className="space-y-4">
            {filteredFindings.length === 0 ? (
              <div className="border border-slate-200 bg-white rounded-xl p-10 text-center text-slate-500 shadow-xs">
                <CheckCircle2 className="w-8 h-8 text-emerald-600 mx-auto mb-2" />
                <h4 className="text-sm font-bold text-slate-900">
                  No Matching Findings
                </h4>
                <p className="text-xs text-slate-500 max-w-md mx-auto mt-1">
                  All active filters have zero remaining issues, or no weaknesses matched the query.
                </p>
              </div>
            ) : (
              filteredFindings.map((item) => (
                <FindingCard
                  key={item.finding.id}
                  item={item}
                  onVerifyFix={handleVerifyFix}
                />
              ))
            )}
          </div>
        )}

        {/* Tab 2: Empirical Evaluation Benchmark Suite */}
        {activeTab === 'benchmark' && <BenchmarkScorecard />}

        {/* Tab 3: STRIDE Attack Paths */}
        {activeTab === 'attack-paths' && (
          <AttackPathView hypotheses={scanResult?.attackPathHypotheses || []} />
        )}

        {/* Tab 4: Conversational Review Agent */}
        {activeTab === 'agent-chat' && (
          <AgentChatPanel
            findings={scanResult?.prioritizedFindings || []}
            attackPaths={scanResult?.attackPathHypotheses || []}
            passedGate={scanResult?.passedGate ?? true}
            currentCodeContext={currentPr?.files?.map((f) => f.content).join('\n') || ''}
          />
        )}

        {/* Tab 5: PR Code & Diff Workbench */}
        {activeTab === 'diff' && (
          <DiffEditorView
            files={isCustom ? customFiles : currentPr?.files || []}
            isScanning={isScanning}
            onApplyAndScan={(updated) => {
              if (isCustom) setCustomFiles(updated);
              runScanOnFiles(updated, exposure, failOn);
            }}
          />
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-200 bg-white py-4 text-xs text-slate-500 mt-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="font-mono text-slate-700 font-bold">SecurePR AI</span>
            <span>·</span>
            <span>Evidence-Driven Code Security Gate</span>
            <span>·</span>
            <span className="text-emerald-700 font-semibold">100% Deterministic + Empirical Benchmark</span>
          </div>
          <div className="text-slate-500 font-mono text-[11px]">
            Agent package: <code className="text-slate-700 font-semibold">agents/securepr-agent/</code>
          </div>
        </div>
      </footer>

      {/* Modals */}
      <RiskMatrixModal
        isOpen={showRiskModal}
        onClose={() => setShowRiskModal(false)}
      />

      <ExportModal
        isOpen={showExportModal}
        onClose={() => setShowExportModal(false)}
        scanResult={scanResult}
        prTitle={currentPr?.title}
        prNumber={currentPr?.prNumber}
      />

      <CliIntegrationModal
        isOpen={showCliModal}
        onClose={() => setShowCliModal(false)}
      />

      <GitHubPrIngestModal
        isOpen={showIngestModal}
        onClose={() => setShowIngestModal(false)}
        onPrLoaded={(newPr) => {
          setPresets((prev) => [newPr, ...prev]);
          setCurrentPr(newPr);
          setIsCustom(false);
          runScanOnFiles(newPr.files, exposure, failOn);
        }}
      />
    </div>
  );
}
