import React, { useState } from 'react';
import { AttackPathHypothesis } from '../types/security';
import { Flame, ShieldCheck, CheckSquare, Square, AlertCircle, Database, Key, Server } from 'lucide-react';

interface AttackPathViewProps {
  hypotheses: AttackPathHypothesis[];
}

export const AttackPathView: React.FC<AttackPathViewProps> = ({ hypotheses }) => {
  const [checkedSteps, setCheckedSteps] = useState<Record<string, boolean>>({});

  const toggleCheck = (id: string) => {
    setCheckedSteps((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  if (hypotheses.length === 0) {
    return (
      <div className="border border-slate-200 bg-white rounded-xl p-10 text-center text-slate-500 shadow-xs">
        <ShieldCheck className="w-9 h-9 text-emerald-600 mx-auto mb-2" />
        <h4 className="text-sm font-bold text-slate-900">No Multi-File Attack Paths Inferred</h4>
        <p className="text-xs text-slate-500 max-w-md mx-auto mt-1">
          Findings do not combine to form an interconnected exploitation chain across authentication, API endpoints, or data tiers.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="border-b border-slate-200 pb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
            <Flame className="w-5 h-5 text-orange-600" />
            <span>Cross-File Threat Modeling & Attack-Path Hypotheses</span>
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Correlates individual static findings into end-to-end STRIDE attack vectors across trust boundaries.
          </p>
        </div>
        <div className="text-xs text-slate-500 font-mono">
          STRIDE Taxonomy · Verified Inferred Chains
        </div>
      </div>

      <div className="space-y-6">
        {hypotheses.map((hyp) => (
          <div
            key={hyp.id}
            className="border border-slate-200 bg-white rounded-xl p-5 shadow-xs overflow-hidden"
          >
            {/* Header */}
            <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 pb-3">
              <div>
                <div className="flex items-center gap-2 text-xs">
                  <span className="font-mono text-orange-700 font-bold">{hyp.id}</span>
                  <span aria-hidden="true" className="text-slate-300">·</span>
                  <span className="text-slate-700 font-semibold">STRIDE: {hyp.stride}</span>
                  <span aria-hidden="true" className="text-slate-300">·</span>
                  <span className="text-amber-700 font-mono text-[11px] font-semibold bg-amber-50 px-2 py-0.5 rounded">
                    Requires Validation
                  </span>
                </div>
                <h3 className="text-base font-bold text-slate-900 mt-1">{hyp.title}</h3>
                <p className="text-xs text-slate-600 mt-1 leading-relaxed">{hyp.summary}</p>
              </div>
            </div>

            {/* Visual Node Chain Flow */}
            <div className="my-5">
              <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-3">
                Attack Path Progression Diagram
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 relative">
                {hyp.steps.map((step) => {
                  const isKey = step.actionOrState.toLowerCase().includes('credential') || step.actionOrState.toLowerCase().includes('token');
                  const isApi = step.actionOrState.toLowerCase().includes('route') || step.actionOrState.toLowerCase().includes('endpoint');
                  const Icon = isKey ? Key : isApi ? Server : Database;

                  return (
                    <div
                      key={step.stepNumber}
                      className="border border-slate-200 bg-slate-50/70 p-4 rounded-xl relative flex flex-col justify-between shadow-2xs hover:border-slate-300 transition-colors"
                    >
                      <div>
                        <div className="flex items-center justify-between text-xs mb-2">
                          <span className="font-mono text-emerald-800 font-bold">
                            Step {step.stepNumber}
                          </span>
                          <span className="p-1.5 rounded-lg bg-white border border-slate-200 text-slate-700 shadow-2xs">
                            <Icon className="w-4 h-4 text-emerald-700" />
                          </span>
                        </div>

                        <div className="font-mono text-[11px] text-slate-500 truncate mb-1">
                          {step.filePath}
                        </div>

                        <p className="text-xs text-slate-800 font-medium leading-relaxed">
                          {step.actionOrState}
                        </p>
                      </div>

                      {step.associatedFindingId && (
                        <div className="mt-3 pt-2.5 border-t border-slate-200/80 flex items-center justify-between text-[11px] font-mono text-slate-500">
                          <span>Ref Finding:</span>
                          <span className="text-amber-700 font-bold">{step.associatedFindingId}</span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Auditor Verification Checklist */}
            <div className="bg-slate-50 border border-slate-200 rounded-xl p-4">
              <div className="text-xs font-bold text-slate-800 mb-2.5 flex items-center gap-1.5">
                <AlertCircle className="w-4 h-4 text-amber-600" />
                <span>Auditor & Developer Verification Checklist</span>
              </div>
              <div className="space-y-2.5 text-xs">
                <label
                  onClick={() => toggleCheck(`${hyp.id}-1`)}
                  className="flex items-start gap-2.5 text-slate-700 cursor-pointer hover:text-slate-900"
                >
                  {checkedSteps[`${hyp.id}-1`] ? (
                    <CheckSquare className="w-4 h-4 text-emerald-600 mt-0.5 shrink-0" />
                  ) : (
                    <Square className="w-4 h-4 text-slate-400 mt-0.5 shrink-0" />
                  )}
                  <span>
                    Verify if the entry point ({hyp.steps[0]?.filePath}) is reachable by unauthenticated external traffic via public ingress routes.
                  </span>
                </label>

                <label
                  onClick={() => toggleCheck(`${hyp.id}-2`)}
                  className="flex items-start gap-2.5 text-slate-700 cursor-pointer hover:text-slate-900"
                >
                  {checkedSteps[`${hyp.id}-2`] ? (
                    <CheckSquare className="w-4 h-4 text-emerald-600 mt-0.5 shrink-0" />
                  ) : (
                    <Square className="w-4 h-4 text-slate-400 mt-0.5 shrink-0" />
                  )}
                  <span>
                    Test automated integration test simulating token forgery with algorithm <code className="font-mono text-emerald-800 font-semibold bg-emerald-50 px-1 rounded">"none"</code> against the target endpoint.
                  </span>
                </label>

                <label
                  onClick={() => toggleCheck(`${hyp.id}-3`)}
                  className="flex items-start gap-2.5 text-slate-700 cursor-pointer hover:text-slate-900"
                >
                  {checkedSteps[`${hyp.id}-3`] ? (
                    <CheckSquare className="w-4 h-4 text-emerald-600 mt-0.5 shrink-0" />
                  ) : (
                    <Square className="w-4 h-4 text-slate-400 mt-0.5 shrink-0" />
                  )}
                  <span>
                    Confirm that database tenant filtering prevents User A from mutating User B's record even when supplied in the request payload.
                  </span>
                </label>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
