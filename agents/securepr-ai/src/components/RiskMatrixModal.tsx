import React from 'react';
import { X, SlidersHorizontal } from 'lucide-react';

interface RiskMatrixModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const RiskMatrixModal: React.FC<RiskMatrixModalProps> = ({ isOpen, onClose }) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-xs">
      <div className="bg-white border border-slate-200 rounded-xl max-w-2xl w-full p-6 text-slate-800 shadow-2xl space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
          <div className="flex items-center gap-2">
            <SlidersHorizontal className="w-5 h-5 text-emerald-600" />
            <h3 className="text-base font-bold text-slate-900">
              SecurePR Contextual Risk Prioritization Model
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
        <div className="space-y-3 text-xs sm:text-sm text-slate-600 leading-relaxed">
          <p>
            Unlike traditional scanners that assign static severity levels (e.g., treating every JWT reference or authorization header equally), SecurePR AI calculates a <strong>contextual risk score</strong> (0.0 to 10.0) reflecting real-world exploitability:
          </p>

          <div className="p-3 bg-slate-900 border border-slate-800 rounded-lg font-mono text-xs text-emerald-400">
            Composite Score = ((Impact × 0.55) + (Likelihood × 0.45)) × 10 × Exposure Multiplier
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs pt-1">
            <div className="border border-slate-200 p-3 rounded-lg bg-slate-50">
              <span className="font-bold text-slate-800 block mb-1">Impact & Likelihood Baseline</span>
              <ul className="space-y-1 text-slate-600">
                <li>• <strong>SECRET:</strong> Impact 0.95, Likelihood 0.85</li>
                <li>• <strong>JWT_AUTH:</strong> Impact 0.90, Likelihood 0.80</li>
                <li>• <strong>API_AUTH (BOLA):</strong> Impact 0.85, Likelihood 0.75</li>
                <li>• <strong>CONFIG / CORS:</strong> Impact 0.65, Likelihood 0.60</li>
              </ul>
            </div>

            <div className="border border-slate-200 p-3 rounded-lg bg-slate-50">
              <span className="font-bold text-slate-800 block mb-1">Exposure Context Multiplier</span>
              <ul className="space-y-1 text-slate-600">
                <li>• <strong>PUBLIC (Internet facing):</strong> 1.00× factor</li>
                <li>• <strong>AUTHENTICATED:</strong> 0.85× factor</li>
                <li>• <strong>INTERNAL / VPN:</strong> 0.65× factor</li>
                <li>• <strong>LOCAL_ONLY (Unit test):</strong> 0.30× factor</li>
              </ul>
            </div>
          </div>

          <div className="pt-2 text-xs text-slate-500">
            <span className="font-semibold text-slate-700">Confidence Weighting:</span> Issues identified in newly modified diff lines carry high baseline confidence (90%+), isolating actionable PR findings from repository technical debt.
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
