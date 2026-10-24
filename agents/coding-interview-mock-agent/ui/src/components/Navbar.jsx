import React from 'react';
import { Play, Award, CheckCircle2, Clock, Code2, Sparkles } from 'lucide-react';

const STAGES = [
  { key: 'intro', label: '1. Intro' },
  { key: 'problem', label: '2. Problem' },
  { key: 'discussion', label: '3. Approach' },
  { key: 'coding', label: '4. Coding' },
  { key: 'review', label: '5. Review' },
  { key: 'followup', label: '6. Follow-up' },
  { key: 'feedback', label: '7. Report' },
];

export default function Navbar({ session, onFinishInterview, onStartNew, onAdvanceStage }) {
  const currentStage = session?.current_stage || 'intro';

  return (
    <header className="h-16 border-b border-slate-800 bg-slate-900/90 backdrop-blur px-6 flex items-center justify-between shrink-0 select-none">
      {/* Brand & Title */}
      <div className="flex items-center space-x-3">
        <div className="flex items-center space-x-1 font-black text-xl tracking-tight">
          <span className="text-blue-500">G</span>
          <span className="text-red-500">o</span>
          <span className="text-yellow-500">o</span>
          <span className="text-blue-500">g</span>
          <span className="text-green-500">l</span>
          <span className="text-red-500">e</span>
          <span className="text-slate-300 font-semibold text-sm ml-2 px-2 py-0.5 rounded bg-slate-800 border border-slate-700">
            SWE Mock Interview
          </span>
        </div>
      </div>

      {/* Stage Stepper */}
      <div className="hidden lg:flex items-center space-x-1">
        {STAGES.map((st, idx) => {
          const isActive = currentStage === st.key;
          const isPassed = STAGES.findIndex(s => s.key === currentStage) > idx;

          return (
            <div
              key={st.key}
              onClick={() => onAdvanceStage && onAdvanceStage(st.key)}
              title={`Switch to ${st.label}`}
              className={`flex items-center space-x-1 px-2.5 py-1 rounded-full text-xs font-medium cursor-pointer transition-all ${
                isActive
                  ? 'bg-blue-600/20 text-blue-400 border border-blue-500/40 shadow-sm'
                  : isPassed
                  ? 'bg-emerald-950/40 text-emerald-400 border border-emerald-800/40'
                  : 'text-slate-500 hover:text-slate-300 hover:bg-slate-800/50'
              }`}
            >
              {isPassed ? (
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
              ) : (
                <span className={`w-1.5 h-1.5 rounded-full ${isActive ? 'bg-blue-400 animate-pulse' : 'bg-slate-600'}`} />
              )}
              <span>{st.label}</span>
            </div>
          );
        })}
      </div>

      {/* Action Controls */}
      <div className="flex items-center space-x-3">
        {session && (
          <button
            onClick={onFinishInterview}
            className="flex items-center space-x-1.5 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-xs font-semibold px-3.5 py-2 rounded-lg shadow-sm transition active:scale-95"
          >
            <Award className="w-4 h-4" />
            <span>Finish & View Report</span>
          </button>
        )}
        <button
          onClick={onStartNew}
          className="text-xs font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 border border-slate-700 px-3 py-2 rounded-lg transition"
        >
          New Session
        </button>
      </div>
    </header>
  );
}

