import React, { useState } from 'react';
import { Play, CheckCircle, Terminal, Clock, RefreshCw, AlertTriangle } from 'lucide-react';

const LANGUAGES = [
  { key: 'python', label: 'Python 3' },
  { key: 'javascript', label: 'JavaScript (Node)' },
  { key: 'cpp', label: 'C++ 17' },
  { key: 'java', label: 'Java 17' },
];

export default function CodeEditor({
  code,
  onChange,
  language,
  onLanguageChange,
  onRunCode,
  onSubmitCode,
  runResult,
  isRunning,
  isSubmitting
}) {
  const [consoleOpen, setConsoleOpen] = useState(true);

  // Tab key indent handler
  const handleKeyDown = (e) => {
    if (e.key === 'Tab') {
      e.preventDefault();
      const start = e.target.selectionStart;
      const end = e.target.selectionEnd;
      const newCode = code.substring(0, start) + '    ' + code.substring(end);
      onChange(newCode);
      setTimeout(() => {
        e.target.selectionStart = e.target.selectionEnd = start + 4;
      }, 0);
    }
  };

  const lineCount = (code || '').split('\n').length;
  const lineNumbers = Array.from({ length: Math.max(lineCount, 15) }, (_, i) => i + 1);

  return (
    <div className="flex flex-col h-full bg-slate-950 overflow-hidden">
      {/* Editor Header Toolbar */}
      <div className="h-12 border-b border-slate-800 bg-slate-900/80 px-4 flex items-center justify-between shrink-0">
        <div className="flex items-center space-x-3">
          <select
            value={language}
            onChange={(e) => onLanguageChange(e.target.value)}
            className="bg-slate-800 text-slate-200 text-xs rounded-lg px-2.5 py-1.5 border border-slate-700 focus:outline-none focus:border-blue-500 font-medium"
          >
            {LANGUAGES.map((l) => (
              <option key={l.key} value={l.key}>
                {l.label}
              </option>
            ))}
          </select>
          <span className="text-xs text-slate-500 hidden sm:inline">Monospace Editor • Tab = 4 Spaces</span>
        </div>

        <div className="flex items-center space-x-2">
          <button
            onClick={onRunCode}
            disabled={isRunning}
            className="flex items-center space-x-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-semibold px-3 py-1.5 rounded-lg transition disabled:opacity-50 active:scale-95"
          >
            {isRunning ? (
              <RefreshCw className="w-3.5 h-3.5 animate-spin text-blue-400" />
            ) : (
              <Play className="w-3.5 h-3.5 text-blue-400 fill-blue-400" />
            )}
            <span>{isRunning ? 'Running...' : 'Run Code'}</span>
          </button>

          <button
            onClick={onSubmitCode}
            disabled={isSubmitting}
            className="flex items-center space-x-1.5 bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold px-3.5 py-1.5 rounded-lg shadow-sm transition disabled:opacity-50 active:scale-95"
          >
            {isSubmitting ? (
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <CheckCircle className="w-3.5 h-3.5" />
            )}
            <span>Submit Solution</span>
          </button>
        </div>
      </div>

      {/* Editor Body with Line Numbers */}
      <div className="flex-1 flex overflow-hidden relative font-mono text-xs">
        {/* Line Numbers */}
        <div className="w-11 bg-slate-900/50 text-slate-600 text-right pr-2 pt-3 select-none border-r border-slate-800/80 leading-5">
          {lineNumbers.map((num) => (
            <div key={num}>{num}</div>
          ))}
        </div>

        {/* Text Area */}
        <textarea
          value={code}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          spellCheck={false}
          className="flex-1 bg-transparent text-slate-200 p-3 outline-none resize-none leading-5 font-mono selection:bg-blue-600/30 overflow-auto whitespace-pre tab-size-4"
          placeholder="// Write your solution here..."
        />
      </div>

      {/* Execution Output Console Drawer */}
      <div className="border-t border-slate-800 bg-slate-900/90 flex flex-col shrink-0 transition-all max-h-56">
        <div
          onClick={() => setConsoleOpen(!consoleOpen)}
          className="px-4 py-2 bg-slate-900 flex items-center justify-between cursor-pointer border-b border-slate-800/80 select-none"
        >
          <div className="flex items-center space-x-2 text-xs font-semibold text-slate-400">
            <Terminal className="w-3.5 h-3.5 text-slate-400" />
            <span>Execution Console</span>
            {runResult && (
              <span
                className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${
                  runResult.success
                    ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                    : 'bg-rose-950 text-rose-400 border border-rose-800'
                }`}
              >
                {runResult.success ? 'Success' : `Exit ${runResult.exit_code}`}
              </span>
            )}
          </div>

          {runResult && (
            <div className="flex items-center space-x-1.5 text-[11px] text-slate-500 font-mono">
              <Clock className="w-3 h-3" />
              <span>{runResult.execution_time_ms} ms</span>
            </div>
          )}
        </div>

        {consoleOpen && (
          <div className="p-3 bg-slate-950 font-mono text-xs overflow-y-auto max-h-40 space-y-1.5">
            {!runResult ? (
              <div className="text-slate-600 italic">Click "Run Code" to test execution output here.</div>
            ) : (
              <>
                {runResult.stdout && (
                  <pre className="text-emerald-300 whitespace-pre-wrap">{runResult.stdout}</pre>
                )}
                {runResult.stderr && (
                  <pre className="text-rose-400 whitespace-pre-wrap">{runResult.stderr}</pre>
                )}
                {runResult.details && !runResult.stdout && !runResult.stderr && (
                  <div className="text-slate-400">{runResult.details}</div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

