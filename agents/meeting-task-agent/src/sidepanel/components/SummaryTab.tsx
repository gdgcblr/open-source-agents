import React, { useState } from 'react';
import { MeetingSession } from '../../shared/types.ts';
import { Sparkles, CheckSquare, MessageSquare, ChevronDown, ChevronUp } from 'lucide-react';

interface SummaryTabProps {
  session: MeetingSession | null;
  onGenerateSummary: () => void;
  isGenerating: boolean;
}

export const SummaryTab: React.FC<SummaryTabProps> = ({
  session,
  onGenerateSummary,
  isGenerating,
}) => {
  const [showTranscript, setShowTranscript] = useState(false);
  const summary = session?.summary;
  const transcript = session?.transcript || [];

  return (
    <div className="space-y-4">
      {/* Action Banner / Generate button */}
      <div className="bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-100 rounded-xl p-3.5 flex items-center justify-between">
        <div>
          <h3 className="text-xs font-bold text-slate-800 flex items-center gap-1.5">
            <Sparkles size={14} className="text-blue-600" />
            Gemma Meeting Summarizer
          </h3>
          <p className="text-[11px] text-slate-600">
            {transcript.length > 0
              ? `${transcript.length} transcript lines captured`
              : 'Waiting for meeting speech / captions...'}
          </p>
        </div>
        <button
          onClick={onGenerateSummary}
          disabled={isGenerating || transcript.length === 0}
          className="bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300 text-white text-xs font-semibold px-3 py-1.5 rounded-lg shadow-sm transition-all flex items-center gap-1.5"
        >
          <Sparkles size={13} className={isGenerating ? 'animate-spin' : ''} />
          {isGenerating ? 'Analyzing...' : 'Summarise'}
        </button>
      </div>

      {/* Summary Content */}
      {summary ? (
        <div className="space-y-3.5">
          {/* Executive Overview */}
          <div className="bg-white rounded-xl p-3.5 border border-slate-200/80 shadow-xs">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">
              Executive Overview
            </h4>
            <p className="text-xs text-slate-700 leading-relaxed">{summary.overview}</p>
          </div>

          {/* Key Discussion Points */}
          {summary.keyPoints && summary.keyPoints.length > 0 && (
            <div className="bg-white rounded-xl p-3.5 border border-slate-200/80 shadow-xs">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2 flex items-center gap-1.5">
                <MessageSquare size={13} className="text-indigo-500" />
                Key Discussion Points
              </h4>
              <ul className="space-y-1.5">
                {summary.keyPoints.map((point, idx) => (
                  <li key={idx} className="text-xs text-slate-700 flex items-start gap-2">
                    <span className="text-blue-500 font-bold">•</span>
                    <span>{point}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Key Decisions */}
          {summary.decisions && summary.decisions.length > 0 && (
            <div className="bg-emerald-50/60 rounded-xl p-3.5 border border-emerald-200/80 shadow-xs">
              <h4 className="text-xs font-bold uppercase tracking-wider text-emerald-800 mb-2 flex items-center gap-1.5">
                <CheckSquare size={13} className="text-emerald-600" />
                Decisions Made
              </h4>
              <ul className="space-y-1.5">
                {summary.decisions.map((decision, idx) => (
                  <li key={idx} className="text-xs text-emerald-950 flex items-start gap-2 font-medium">
                    <span className="text-emerald-600">✓</span>
                    <span>{decision}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      ) : (
        <div className="bg-white rounded-xl p-6 border border-dashed border-slate-300 text-center">
          <Sparkles size={24} className="mx-auto text-slate-400 mb-2" />
          <h4 className="text-xs font-semibold text-slate-700">No summary generated yet</h4>
          <p className="text-[11px] text-slate-500 mt-1 max-w-xs mx-auto">
            Click "Summarise" above to run the Gemma Agent over the current meeting captions.
          </p>
        </div>
      )}

      {/* Collapsible Transcript Viewer */}
      <div className="bg-white rounded-xl border border-slate-200/80 overflow-hidden shadow-xs">
        <button
          onClick={() => setShowTranscript(!showTranscript)}
          className="w-full px-3.5 py-2.5 bg-slate-50 hover:bg-slate-100 flex items-center justify-between text-xs font-semibold text-slate-700 transition-colors"
        >
          <span className="flex items-center gap-1.5">
            <MessageSquare size={13} className="text-slate-500" />
            Live Transcript ({transcript.length} lines)
          </span>
          {showTranscript ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>

        {showTranscript && (
          <div className="p-3 max-h-60 overflow-y-auto space-y-2 bg-slate-50/30 text-xs">
            {transcript.length === 0 ? (
              <p className="text-slate-400 italic text-[11px] text-center py-4">
                No captions captured yet. Ensure closed captions are turned ON in Google Meet or Teams.
              </p>
            ) : (
              transcript.map((chunk) => (
                <div key={chunk.id} className="bg-white p-2 rounded-lg border border-slate-100 shadow-2xs">
                  <div className="flex items-center justify-between text-[10px] text-slate-400 mb-0.5">
                    <span className="font-semibold text-slate-800">{chunk.speaker}</span>
                    <span>{new Date(chunk.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
                  </div>
                  <p className="text-slate-700">{chunk.text}</p>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
};

