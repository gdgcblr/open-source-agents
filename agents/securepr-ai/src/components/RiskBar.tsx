import React from 'react';
import { ExposureContext, Severity } from '../types/security';
import { SlidersHorizontal, Lock, Flame, ShieldAlert, CheckCircle2 } from 'lucide-react';

interface RiskBarProps {
  failOn: Severity;
  onChangeFailOn: (val: Severity) => void;
  exposure: ExposureContext;
  onChangeExposure: (val: ExposureContext) => void;
  totalFindings: number;
  criticalCount: number;
  highCount: number;
  redactedCount: number;
  hypothesesCount: number;
  resolvedCount: number;
  onOpenRiskInfo: () => void;
}

export const RiskBar: React.FC<RiskBarProps> = ({
  failOn,
  onChangeFailOn,
  exposure,
  onChangeExposure,
  totalFindings,
  criticalCount,
  highCount,
  redactedCount,
  hypothesesCount,
  resolvedCount,
  onOpenRiskInfo,
}) => {
  return (
    <div className="bg-slate-50/80 border-b border-slate-200 text-slate-700 px-4 sm:px-6 lg:px-8 py-2.5">
      <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-4">
        {/* Left: Policy Settings with segmented controls */}
        <div className="flex flex-wrap items-center gap-5 text-xs">
          {/* Fail-on threshold selector */}
          <div className="flex items-center gap-2">
            <span className="text-slate-500 font-semibold">Gate Threshold:</span>
            <div className="flex items-center bg-slate-200/70 p-0.5 rounded-lg border border-slate-300/60">
              {(['CRITICAL', 'HIGH', 'MEDIUM'] as Severity[]).map((level) => (
                <button
                  key={level}
                  onClick={() => onChangeFailOn(level)}
                  className={`px-2.5 py-1 text-xs font-mono font-medium rounded-md transition-all ${
                    failOn === level
                      ? 'bg-white text-slate-900 shadow-xs font-semibold'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  {level}
                </button>
              ))}
            </div>
          </div>

          {/* Exposure context selector */}
          <div className="flex items-center gap-2">
            <span className="text-slate-500 font-semibold">Asset Exposure:</span>
            <div className="flex items-center bg-slate-200/70 p-0.5 rounded-lg border border-slate-300/60">
              {(['PUBLIC', 'AUTHENTICATED', 'INTERNAL'] as ExposureContext[]).map((exp) => (
                <button
                  key={exp}
                  onClick={() => onChangeExposure(exp)}
                  className={`px-2.5 py-1 text-xs font-mono font-medium rounded-md transition-all ${
                    exposure === exp
                      ? 'bg-white text-emerald-800 shadow-xs font-semibold'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  {exp}
                </button>
              ))}
            </div>
          </div>

          {/* Risk Formula Explanation link */}
          <button
            onClick={onOpenRiskInfo}
            className="text-slate-500 hover:text-emerald-700 flex items-center gap-1 transition-colors text-xs font-medium"
            title="View Contextual Risk Scoring calculation formula"
          >
            <SlidersHorizontal className="w-3.5 h-3.5" />
            <span className="underline decoration-slate-300 underline-offset-2">Risk Model</span>
          </button>
        </div>

        {/* Right: Unboxed Clean Metadata Counters with dot separators */}
        <div className="flex items-center gap-3 text-xs text-slate-600">
          <div className="flex items-center gap-1.5 font-medium">
            <ShieldAlert className="w-3.5 h-3.5 text-rose-600" />
            <span className="font-mono text-slate-900 font-bold">{totalFindings}</span>
            <span>Total Findings</span>
          </div>

          <span aria-hidden="true" className="text-slate-300">·</span>

          <div className="flex items-center gap-1.5 font-medium">
            <span className="text-rose-700 font-mono font-bold">{criticalCount} Critical</span>
            <span className="text-slate-300">/</span>
            <span className="text-amber-700 font-mono font-bold">{highCount} High</span>
          </div>

          <span aria-hidden="true" className="text-slate-300">·</span>

          <div className="flex items-center gap-1.5 font-medium">
            <Lock className="w-3.5 h-3.5 text-emerald-700" />
            <span className="font-mono text-slate-900 font-bold">{redactedCount}</span>
            <span>Redacted Secrets</span>
          </div>

          <span aria-hidden="true" className="text-slate-300">·</span>

          <div className="flex items-center gap-1.5 font-medium">
            <Flame className="w-3.5 h-3.5 text-orange-600" />
            <span className="font-mono text-slate-900 font-bold">{hypothesesCount}</span>
            <span>Attack Paths</span>
          </div>

          {resolvedCount > 0 && (
            <>
              <span aria-hidden="true" className="text-slate-300">·</span>
              <div className="flex items-center gap-1.5 text-emerald-700 font-semibold font-mono">
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>{resolvedCount} Fixed</span>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
