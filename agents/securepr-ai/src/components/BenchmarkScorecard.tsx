import React, { useState, useEffect } from 'react';
import {
  Award,
  Play,
  CheckCircle2,
  AlertTriangle,
  ShieldCheck,
  Lock,
  Target,
  BarChart3,
  RefreshCw,
  Sparkles,
} from 'lucide-react';

interface BenchmarkMetrics {
  precision: number;
  recall: number;
  falsePositiveRate: number;
  f1Score: number;
  fixVerificationAccuracy: number;
  evidenceCorrectness: number;
  secretLeakageRate: number;
  totalCasesEvaluated: number;
  fixCasesEvaluated: number;
}

interface ConfusionMatrix {
  truePositives: number;
  falsePositives: number;
  trueNegatives: number;
  falseNegatives: number;
}

interface BenchmarkData {
  metrics: BenchmarkMetrics;
  confusionMatrix: ConfusionMatrix;
  categoryBreakdown: Record<string, { tp: number; fp: number; tn: number; fn: number }>;
  caseResults: Array<{
    id: string;
    name: string;
    category: string;
    expected: string;
    outcome: string;
    passed: boolean;
    findingId: string | null;
  }>;
  fixResults: Array<{
    id: string;
    findingId: string;
    expectedVerdict: string;
    actualVerdict: string;
    passed: boolean;
  }>;
}

export const BenchmarkScorecard: React.FC = () => {
  const [data, setData] = useState<BenchmarkData | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [activeTab, setActiveTab] = useState<'overview' | 'test-cases' | 'fixes'>('overview');

  const fetchBenchmark = async () => {
    setIsRunning(true);
    try {
      const res = await fetch('/api/evaluation/run', { method: 'POST' });
      const json = await res.json();
      setData(json);
    } catch (err) {
      console.error('Failed to run benchmark:', err);
    } finally {
      setIsRunning(false);
    }
  };

  useEffect(() => {
    fetchBenchmark();
  }, []);

  if (!data) {
    return (
      <div className="bg-white border border-slate-200 rounded-xl p-12 text-center text-slate-500 shadow-sm">
        <div className="w-6 h-6 border-2 border-emerald-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
        <p className="text-sm font-medium text-slate-700">Executing Empirical Evaluation Suite...</p>
        <p className="text-xs text-slate-400 mt-1">Evaluating Precision, Recall, FPR, and Secret Leakage</p>
      </div>
    );
  }

  const { metrics, confusionMatrix, caseResults, fixResults, categoryBreakdown } = data;

  return (
    <div className="space-y-6">
      {/* Top Banner: Original Engineering Contribution */}
      <div className="bg-gradient-to-r from-emerald-50 via-teal-50 to-sky-50 border border-emerald-200/80 rounded-xl p-5 shadow-xs">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-start gap-3.5">
            <div className="w-10 h-10 rounded-lg bg-emerald-600 text-white flex items-center justify-center shadow-xs shrink-0 mt-0.5">
              <Award className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-slate-900 tracking-tight">
                  Empirical Security Evaluation Scorecard
                </h2>
                <span className="text-[11px] font-mono text-emerald-800 font-semibold px-2 py-0.5 bg-emerald-100 rounded">
                  Validated Benchmark
                </span>
              </div>
              <p className="text-xs text-slate-600 mt-1 max-w-2xl leading-relaxed">
                Rather than relying on unverified claims of "multi-agent reasoning", SecurePR AI measures real-world efficacy across ground-truth vulnerability datasets, false-positive lures, and fix verification regressions.
              </p>
            </div>
          </div>

          <button
            onClick={fetchBenchmark}
            disabled={isRunning}
            className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold rounded-lg shadow-xs transition-colors disabled:opacity-50 shrink-0"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRunning ? 'animate-spin' : ''}`} />
            <span>{isRunning ? 'Running Benchmark...' : 'Re-Run Evaluation'}</span>
          </button>
        </div>
      </div>

      {/* 6 Key Evaluated Metrics Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {/* Precision */}
        <div className="bg-white border border-slate-200/90 rounded-xl p-4 shadow-2xs hover:border-slate-300 transition-colors">
          <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
            Precision
          </div>
          <div className="text-2xl font-bold font-mono text-emerald-600 mt-1">
            {metrics.precision}%
          </div>
          <div className="text-[10px] text-slate-500 mt-1">
            TP / (TP + FP) · No false alarms
          </div>
        </div>

        {/* Recall */}
        <div className="bg-white border border-slate-200/90 rounded-xl p-4 shadow-2xs hover:border-slate-300 transition-colors">
          <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
            Recall (Sensitivity)
          </div>
          <div className="text-2xl font-bold font-mono text-emerald-600 mt-1">
            {metrics.recall}%
          </div>
          <div className="text-[10px] text-slate-500 mt-1">
            TP / (TP + FN) · Flaws caught
          </div>
        </div>

        {/* False Positive Rate */}
        <div className="bg-white border border-slate-200/90 rounded-xl p-4 shadow-2xs hover:border-slate-300 transition-colors">
          <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
            False Positive Rate
          </div>
          <div className="text-2xl font-bold font-mono text-slate-800 mt-1">
            {metrics.falsePositiveRate}%
          </div>
          <div className="text-[10px] text-slate-500 mt-1">
            FP / (FP + TN) · Clean code passes
          </div>
        </div>

        {/* Fix-Verification Accuracy */}
        <div className="bg-white border border-slate-200/90 rounded-xl p-4 shadow-2xs hover:border-slate-300 transition-colors">
          <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
            Fix Accuracy
          </div>
          <div className="text-2xl font-bold font-mono text-blue-600 mt-1">
            {metrics.fixVerificationAccuracy}%
          </div>
          <div className="text-[10px] text-slate-500 mt-1">
            Catches flawed & incomplete fixes
          </div>
        </div>

        {/* Evidence Correctness */}
        <div className="bg-white border border-slate-200/90 rounded-xl p-4 shadow-2xs hover:border-slate-300 transition-colors">
          <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
            Evidence Correctness
          </div>
          <div className="text-2xl font-bold font-mono text-indigo-600 mt-1">
            {metrics.evidenceCorrectness}%
          </div>
          <div className="text-[10px] text-slate-500 mt-1">
            Accurate file & line attribution
          </div>
        </div>

        {/* Secret Leakage */}
        <div className="bg-emerald-50/60 border border-emerald-300/80 rounded-xl p-4 shadow-2xs">
          <div className="text-[11px] font-semibold text-emerald-800 uppercase tracking-wider flex items-center gap-1">
            <Lock className="w-3 h-3 text-emerald-700" />
            <span>Secret Leakage</span>
          </div>
          <div className="text-2xl font-bold font-mono text-emerald-700 mt-1">
            {metrics.secretLeakageRate}%
          </div>
          <div className="text-[10px] text-emerald-700 font-medium mt-1">
            Synthetic cases only; not a guarantee
          </div>
        </div>
      </div>

      {/* Main Analysis: Confusion Matrix & Category Breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Confusion Matrix (2 Columns) */}
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <span className="text-xs font-bold text-slate-900 flex items-center gap-2">
                <Target className="w-4 h-4 text-emerald-600" />
                <span>Detection Confusion Matrix</span>
              </span>
              <span className="text-[11px] font-mono text-slate-500">
                Total Samples: {metrics.totalCasesEvaluated}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-3 mt-4">
              <div className="bg-emerald-50 border border-emerald-200/70 rounded-lg p-3 text-center">
                <div className="text-[11px] text-emerald-800 font-semibold">True Positives (TP)</div>
                <div className="text-2xl font-bold font-mono text-emerald-700 mt-0.5">
                  {confusionMatrix.truePositives}
                </div>
                <div className="text-[10px] text-emerald-600">Correctly detected flaws</div>
              </div>

              <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 text-center">
                <div className="text-[11px] text-slate-600 font-semibold">False Positives (FP)</div>
                <div className="text-2xl font-bold font-mono text-slate-800 mt-0.5">
                  {confusionMatrix.falsePositives}
                </div>
                <div className="text-[10px] text-slate-500">Safe code falsely flagged</div>
              </div>

              <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 text-center">
                <div className="text-[11px] text-slate-600 font-semibold">False Negatives (FN)</div>
                <div className="text-2xl font-bold font-mono text-slate-800 mt-0.5">
                  {confusionMatrix.falseNegatives}
                </div>
                <div className="text-[10px] text-slate-500">Missed vulnerabilities</div>
              </div>

              <div className="bg-emerald-50 border border-emerald-200/70 rounded-lg p-3 text-center">
                <div className="text-[11px] text-emerald-800 font-semibold">True Negatives (TN)</div>
                <div className="text-2xl font-bold font-mono text-emerald-700 mt-0.5">
                  {confusionMatrix.trueNegatives}
                </div>
                <div className="text-[10px] text-emerald-600">Correctly passed clean code</div>
              </div>
            </div>
          </div>

          <div className="mt-4 pt-3 border-t border-slate-100 text-[11px] text-slate-500 leading-snug">
            <strong>Evaluation Ground Truth:</strong> All positive and negative test cases are independently verified against OWASP API Top 10, Semgrep AST standards, and safe credential handling benchmarks.
          </div>
        </div>

        {/* Category Breakdown (1 Column) */}
        <div className="lg:col-span-2 bg-white border border-slate-200 rounded-xl p-5 shadow-xs">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <span className="text-xs font-bold text-slate-900 flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-emerald-600" />
              <span>Performance by Vulnerability Class</span>
            </span>
            <span className="text-[11px] font-mono text-slate-500">100% Deterministic AST Rules</span>
          </div>

          <div className="mt-4 space-y-3">
            {Object.entries(categoryBreakdown).map(([cat, stats]) => {
              const total = stats.tp + stats.fp + stats.tn + stats.fn;
              const catAccuracy = total > 0 ? (((stats.tp + stats.tn) / total) * 100).toFixed(0) : 100;
              return (
                <div key={cat} className="border border-slate-100 rounded-lg p-3 bg-slate-50/50">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-slate-800 font-mono">{cat}</span>
                    <span className="font-mono font-bold text-emerald-700">{catAccuracy}% Accuracy</span>
                  </div>
                  <div className="flex items-center gap-3 text-[11px] text-slate-500 mt-1">
                    <span>TP: {stats.tp}</span>
                    <span>·</span>
                    <span>TN: {stats.tn}</span>
                    <span>·</span>
                    <span>FP: {stats.fp}</span>
                    <span>·</span>
                    <span>FN: {stats.fn}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Tabs for Case Inspection */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-xs">
        <div className="px-5 py-3 border-b border-slate-200 bg-slate-50/70 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setActiveTab('overview')}
              className={`px-3 py-1 text-xs font-semibold rounded-md transition-colors ${
                activeTab === 'overview'
                  ? 'bg-white text-slate-900 shadow-2xs border border-slate-200'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Benchmark Ground-Truth Dataset ({caseResults.length})
            </button>
            <button
              onClick={() => setActiveTab('fixes')}
              className={`px-3 py-1 text-xs font-semibold rounded-md transition-colors ${
                activeTab === 'fixes'
                  ? 'bg-white text-slate-900 shadow-2xs border border-slate-200'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Fix-Verification Regression Tests ({fixResults.length})
            </button>
          </div>
          <span className="text-[11px] font-mono text-slate-400">Validated against live scanner engine</span>
        </div>

        {activeTab === 'overview' ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/40 text-slate-500 font-semibold">
                  <th className="py-2.5 px-4 font-mono">Case ID</th>
                  <th className="py-2.5 px-4">Test Scenario</th>
                  <th className="py-2.5 px-4">Category</th>
                  <th className="py-2.5 px-4">Expected Ground Truth</th>
                  <th className="py-2.5 px-4">Scanner Outcome</th>
                  <th className="py-2.5 px-4 text-right">Result</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {caseResults.map((tc) => (
                  <tr key={tc.id} className="hover:bg-slate-50/80 transition-colors">
                    <td className="py-2.5 px-4 font-mono font-medium text-slate-700">{tc.id}</td>
                    <td className="py-2.5 px-4 font-medium text-slate-900">{tc.name}</td>
                    <td className="py-2.5 px-4 font-mono text-slate-500">{tc.category}</td>
                    <td className="py-2.5 px-4 text-slate-600">{tc.expected}</td>
                    <td className="py-2.5 px-4 text-slate-700 font-mono text-[11px]">
                      {tc.outcome} {tc.findingId ? `(${tc.findingId})` : ''}
                    </td>
                    <td className="py-2.5 px-4 text-right">
                      {tc.passed ? (
                        <span className="inline-flex items-center gap-1 text-emerald-700 font-semibold font-mono text-[11px]">
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          <span>PASS</span>
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-rose-600 font-semibold font-mono text-[11px]">
                          <AlertTriangle className="w-3.5 h-3.5" />
                          <span>FAIL</span>
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/40 text-slate-500 font-semibold">
                  <th className="py-2.5 px-4 font-mono">Test ID</th>
                  <th className="py-2.5 px-4">Target Finding</th>
                  <th className="py-2.5 px-4">Expected Verification Verdict</th>
                  <th className="py-2.5 px-4">Scanner Verification Verdict</th>
                  <th className="py-2.5 px-4 text-right">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {fixResults.map((fc) => (
                  <tr key={fc.id} className="hover:bg-slate-50/80 transition-colors">
                    <td className="py-2.5 px-4 font-mono font-medium text-slate-700">{fc.id}</td>
                    <td className="py-2.5 px-4 font-mono font-semibold text-slate-900">{fc.findingId}</td>
                    <td className="py-2.5 px-4 text-slate-600">{fc.expectedVerdict}</td>
                    <td className="py-2.5 px-4 font-mono text-[11px] text-slate-700">{fc.actualVerdict}</td>
                    <td className="py-2.5 px-4 text-right">
                      {fc.passed ? (
                        <span className="inline-flex items-center gap-1 text-emerald-700 font-semibold font-mono text-[11px]">
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          <span>PASS</span>
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-rose-600 font-semibold font-mono text-[11px]">
                          <AlertTriangle className="w-3.5 h-3.5" />
                          <span>FAIL</span>
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
