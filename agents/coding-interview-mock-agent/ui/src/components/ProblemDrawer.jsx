import React from 'react';
import { BookOpen, AlertCircle, CheckCircle, Lightbulb, ListChecks } from 'lucide-react';

export default function ProblemDrawer({ question, revealedConstraints = [] }) {
  if (!question) {
    return (
      <div className="p-6 text-center text-slate-500">
        <BookOpen className="w-8 h-8 mx-auto mb-2 opacity-40" />
        <p className="text-sm">Problem statement will appear once the interview starts.</p>
      </div>
    );
  }

  const diffBadgeColor = {
    easy: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
    medium: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
    hard: 'bg-rose-500/10 text-rose-400 border-rose-500/30',
  }[question.difficulty] || 'bg-slate-800 text-slate-300 border-slate-700';

  return (
    <div className="h-full overflow-y-auto p-5 space-y-5 text-slate-200 text-sm">
      {/* Title & Metadata */}
      <div>
        <div className="flex items-center space-x-2 mb-2">
          <span className={`text-xs uppercase font-bold tracking-wider px-2 py-0.5 rounded border ${diffBadgeColor}`}>
            {question.difficulty}
          </span>
          <span className="text-xs bg-slate-800 text-slate-400 px-2 py-0.5 rounded border border-slate-700 font-medium">
            {question.topic}
          </span>
        </div>
        <h2 className="text-lg font-bold text-white tracking-tight">{question.title}</h2>
      </div>

      {/* Description */}
      <div className="space-y-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
          <BookOpen className="w-3.5 h-3.5 text-blue-400" />
          Problem Description
        </h3>
        <p className="text-slate-300 leading-relaxed whitespace-pre-line text-xs bg-slate-900/60 p-3.5 rounded-lg border border-slate-800/80">
          {question.description}
        </p>
      </div>

      {/* Examples */}
      {question.examples && question.examples.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
            <Lightbulb className="w-3.5 h-3.5 text-yellow-400" />
            Examples
          </h3>
          <div className="space-y-2">
            {question.examples.map((ex, i) => (
              <div key={i} className="bg-slate-900/80 border border-slate-800 p-3 rounded-lg text-xs space-y-1.5">
                <div>
                  <span className="text-slate-400 font-medium">Input: </span>
                  <code className="text-blue-300 bg-slate-950 px-1.5 py-0.5 rounded">{ex.input}</code>
                </div>
                <div>
                  <span className="text-slate-400 font-medium">Output: </span>
                  <code className="text-emerald-300 bg-slate-950 px-1.5 py-0.5 rounded">{ex.output}</code>
                </div>
                {ex.explanation && (
                  <div className="text-slate-400 text-[11px] pt-1 italic">
                    {ex.explanation}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Constraints & Inquiries */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
            <ListChecks className="w-3.5 h-3.5 text-purple-400" />
            Discovered Constraints ({revealedConstraints.length}/{question.constraints?.length || 0})
          </h3>
        </div>

        {revealedConstraints.length === 0 ? (
          <div className="p-3 rounded-lg border border-dashed border-slate-800 bg-slate-900/30 text-xs text-slate-500 italic">
            💡 Google interview tip: Inquire about input bounds, nulls, negative numbers, and duplicates in chat to uncover hidden constraints!
          </div>
        ) : (
          <ul className="space-y-1.5">
            {revealedConstraints.map((c, i) => (
              <li key={i} className="flex items-start space-x-2 text-xs bg-purple-950/20 border border-purple-900/40 p-2.5 rounded-lg text-purple-200">
                <CheckCircle className="w-3.5 h-3.5 text-purple-400 shrink-0 mt-0.5" />
                <span>{c}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

