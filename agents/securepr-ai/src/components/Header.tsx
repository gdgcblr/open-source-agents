import React from 'react';
import { Shield, ShieldAlert, ShieldCheck, Play, FileText, Terminal, ChevronDown, Award } from 'lucide-react';
import { PullRequestPreset } from '../types/security';

interface HeaderProps {
  currentPr: PullRequestPreset | null;
  presets: PullRequestPreset[];
  onSelectPr: (preset: PullRequestPreset) => void;
  onSelectCustom: () => void;
  isCustom: boolean;
  passedGate: boolean;
  totalFindings: number;
  isScanning: boolean;
  onRunScan: () => void;
  onOpenExport: () => void;
  onOpenCli: () => void;
  onOpenIngest: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  currentPr,
  presets,
  onSelectPr,
  onSelectCustom,
  isCustom,
  passedGate,
  totalFindings,
  isScanning,
  onRunScan,
  onOpenExport,
  onOpenCli,
  onOpenIngest,
}) => {
  return (
    <header className="border-b border-slate-200 bg-white/95 backdrop-blur-xs text-slate-800 sticky top-0 z-40 shadow-2xs">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3 flex flex-wrap items-center justify-between gap-4">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-emerald-600 text-white flex items-center justify-center shadow-xs">
            <Shield className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-base tracking-tight text-slate-900">SecurePR AI</span>
              <span className="text-xs text-slate-500 font-mono">v0.1.0</span>
            </div>
            <div className="text-xs text-slate-500">
              Deterministic Security & Benchmark-Verified PR Review
            </div>
          </div>
        </div>

        {/* PR Selector Dropdown & Presets */}
        <div className="flex items-center gap-2">
          <div className="relative group">
            <button className="flex items-center gap-2 px-3 py-1.5 bg-slate-50 border border-slate-200 hover:border-slate-300 rounded-lg text-xs font-medium text-slate-700 shadow-2xs transition-colors">
              <span className="text-slate-500">Target PR:</span>
              <span className="font-mono text-emerald-700 font-semibold">
                {isCustom ? 'Custom Diff Input' : `PR #${currentPr?.prNumber}: ${currentPr?.title.slice(0, 24)}...`}
              </span>
              <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
            </button>
            <div className="hidden group-hover:block absolute left-0 mt-1 w-80 bg-white border border-slate-200 rounded-lg shadow-lg py-1 z-50">
              <div className="px-3 py-1.5 text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                Select Benchmark PR
              </div>
              {presets.map((preset) => (
                <button
                  key={preset.id}
                  onClick={() => onSelectPr(preset)}
                  className={`w-full text-left px-3 py-2 text-xs hover:bg-slate-50 flex flex-col gap-0.5 ${
                    !isCustom && currentPr?.id === preset.id ? 'bg-emerald-50/60 text-emerald-900 font-semibold' : 'text-slate-700'
                  }`}
                >
                  <div className="font-medium font-mono">
                    PR #{preset.prNumber} · {preset.branch}
                  </div>
                  <div className="text-[11px] text-slate-500 truncate">{preset.title}</div>
                </button>
              ))}
              <div className="border-t border-slate-100 my-1"></div>
              <button
                onClick={onSelectCustom}
                className={`w-full text-left px-3 py-2 text-xs hover:bg-slate-50 flex items-center justify-between ${
                  isCustom ? 'bg-emerald-50 text-emerald-900 font-semibold' : 'text-slate-700'
                }`}
              >
                <span>Paste Custom Diff / Edit Code</span>
                <span className="text-[10px] text-slate-400 font-mono">User Diff</span>
              </button>
            </div>
          </div>

          <button
            onClick={onOpenIngest}
            className="flex items-center gap-1 px-3 py-1.5 bg-slate-50 border border-slate-200 hover:bg-slate-100 text-slate-700 rounded-lg text-xs font-semibold shadow-2xs transition-colors"
            title="Import from GitHub PR URL or upload code files"
          >
            <span>+ Load PR / Upload</span>
          </button>

          {/* PR Gate Status Banner */}
          <div
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-bold border shadow-2xs ${
              passedGate
                ? 'bg-emerald-50 text-emerald-800 border-emerald-300'
                : 'bg-rose-50 text-rose-800 border-rose-300'
            }`}
          >
            {passedGate ? (
              <>
                <ShieldCheck className="w-4 h-4 text-emerald-600" />
                <span>GATE: PASSED</span>
              </>
            ) : (
              <>
                <ShieldAlert className="w-4 h-4 text-rose-600" />
                <span>GATE: BLOCKED ({totalFindings})</span>
              </>
            )}
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-2">
          <button
            onClick={onRunScan}
            disabled={isScanning}
            className="flex items-center gap-1.5 px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold shadow-xs transition-colors disabled:opacity-50"
          >
            <Play className={`w-3.5 h-3.5 ${isScanning ? 'animate-spin' : ''}`} />
            <span>{isScanning ? 'Scanning...' : 'Re-scan PR'}</span>
          </button>

          <button
            onClick={onOpenExport}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 rounded-lg text-xs font-medium shadow-2xs transition-colors"
          >
            <FileText className="w-3.5 h-3.5 text-slate-500" />
            <span>PR Report</span>
          </button>

          <button
            onClick={onOpenCli}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 rounded-lg text-xs font-medium shadow-2xs transition-colors"
          >
            <Terminal className="w-3.5 h-3.5 text-slate-500" />
            <span>CLI / CI</span>
          </button>
        </div>
      </div>
    </header>
  );
};
