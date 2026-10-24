import React, { useState } from 'react';
import { X, Award, CheckCircle, AlertTriangle, BookOpen, Copy, Check, TrendingUp } from 'lucide-react';

export default function ReportModal({ report, onClose }) {
  const [copied, setCopied] = useState(false);

  if (!report) return null;

  const handleCopy = () => {
    navigator.clipboard.writeText(report.markdown_report || JSON.stringify(report, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const recColor = {
    'Strong Hire': 'bg-emerald-500/20 text-emerald-400 border-emerald-500/50',
    'Hire': 'bg-teal-500/20 text-teal-400 border-teal-500/50',
    'Leaning Hire': 'bg-amber-500/20 text-amber-400 border-amber-500/50',
    'Leaning No Hire': 'bg-orange-500/20 text-orange-400 border-orange-500/50',
    'No Hire': 'bg-rose-500/20 text-rose-400 border-rose-500/50',
  }[report.hiring_recommendation] || 'bg-slate-800 text-slate-300 border-slate-700';

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-800 w-full max-w-3xl rounded-2xl shadow-2xl flex flex-col max-h-[90vh] overflow-hidden">
        {/* Modal Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/90">
          <div className="flex items-center space-x-2">
            <Award className="w-5 h-5 text-yellow-500" />
            <h2 className="text-base font-bold text-white tracking-tight">
              Google SWE Interview Evaluation Report
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6 text-slate-200 text-xs">
          {/* Top Score Banner */}
          <div className="bg-gradient-to-r from-slate-950 to-slate-900 border border-slate-800 p-5 rounded-2xl flex flex-col sm:flex-row items-center justify-between gap-4">
            <div>
              <div className="text-slate-400 text-xs mb-1">Candidate: <span className="text-white font-semibold">{report.candidate_name}</span></div>
              <div className="text-slate-400 text-xs">Problem: <span className="text-white font-medium">{report.question_title} ({report.difficulty})</span></div>
            </div>

            <div className="flex items-center space-x-4">
              <div className="text-right">
                <div className="text-[10px] text-slate-400 uppercase tracking-wider font-semibold">Overall Score</div>
                <div className="text-3xl font-extrabold text-white tracking-tight">
                  {report.interview_score} <span className="text-sm font-normal text-slate-400">/ 10</span>
                </div>
              </div>
              <div className={`px-3.5 py-2 rounded-xl border text-xs font-bold uppercase tracking-wider ${recColor}`}>
                {report.hiring_recommendation}
              </div>
            </div>
          </div>

          {/* Rubric Breakdown Grid */}
          <div>
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3 flex items-center gap-1.5">
              <TrendingUp className="w-4 h-4 text-blue-400" />
              Competency Breakdown
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {Object.entries(report.rubric_breakdown || {}).map(([dim, score]) => (
                <div key={dim} className="bg-slate-950 border border-slate-800 p-3 rounded-xl space-y-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-slate-300 font-medium">{dim}</span>
                    <span className="font-bold text-white">{score} / 10</span>
                  </div>
                  <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full ${
                        score >= 8 ? 'bg-emerald-500' : score >= 6 ? 'bg-blue-500' : 'bg-amber-500'
                      }`}
                      style={{ width: `${score * 10}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Technical Complexity Notes */}
          {report.code_review_notes && (
            <div className="bg-slate-950/80 border border-slate-800 p-3.5 rounded-xl space-y-1 text-slate-300">
              <div className="font-semibold text-white">Complexity Assessment</div>
              <div className="font-mono text-[11px] text-blue-300">{report.code_review_notes}</div>
            </div>
          )}

          {/* Strengths & Weaknesses Columns */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Strengths */}
            <div className="bg-emerald-950/10 border border-emerald-900/30 p-4 rounded-xl space-y-2">
              <h4 className="text-xs font-bold uppercase tracking-wider text-emerald-400 flex items-center gap-1.5">
                <CheckCircle className="w-4 h-4" />
                Key Strengths
              </h4>
              <ul className="space-y-1.5 text-slate-300">
                {report.strengths?.map((s, i) => (
                  <li key={i} className="flex items-start space-x-2">
                    <span className="text-emerald-400 font-bold">•</span>
                    <span>{s}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Areas for Growth */}
            <div className="bg-amber-950/10 border border-amber-900/30 p-4 rounded-xl space-y-2">
              <h4 className="text-xs font-bold uppercase tracking-wider text-amber-400 flex items-center gap-1.5">
                <AlertTriangle className="w-4 h-4" />
                Areas for Growth
              </h4>
              <ul className="space-y-1.5 text-slate-300">
                {report.weaknesses?.map((w, i) => (
                  <li key={i} className="flex items-start space-x-2">
                    <span className="text-amber-400 font-bold">•</span>
                    <span>{w}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          {/* Recommended Practice Topics */}
          {report.recommended_topics?.length > 0 && (
            <div className="bg-slate-950 border border-slate-800 p-4 rounded-xl space-y-2">
              <h4 className="text-xs font-bold uppercase tracking-wider text-purple-400 flex items-center gap-1.5">
                <BookOpen className="w-4 h-4" />
                Recommended Study Topics
              </h4>
              <div className="flex flex-wrap gap-2 pt-1">
                {report.recommended_topics.map((t, i) => (
                  <span
                    key={i}
                    className="bg-purple-950/40 text-purple-300 border border-purple-800/50 px-2.5 py-1 rounded-lg text-[11px] font-medium"
                  >
                    {t}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-3.5 border-t border-slate-800 bg-slate-900 flex items-center justify-between">
          <button
            onClick={handleCopy}
            className="flex items-center space-x-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium px-3.5 py-2 rounded-lg border border-slate-700 transition"
          >
            {copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
            <span>{copied ? 'Copied to Clipboard!' : 'Copy Markdown Report'}</span>
          </button>

          <button
            onClick={onClose}
            className="bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold px-4 py-2 rounded-lg transition"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}

