import React, { useState, useEffect } from 'react';
import Navbar from './components/Navbar';
import ProblemDrawer from './components/ProblemDrawer';
import ChatFeed from './components/ChatFeed';
import CodeEditor from './components/CodeEditor';
import ReportModal from './components/ReportModal';
import { MessageSquare, BookOpen, Sparkles, Terminal, ShieldAlert } from 'lucide-react';

const API_BASE = '/api';

export default function App() {
  const [session, setSession] = useState(null);
  const [candidateName, setCandidateName] = useState('Google Candidate');
  const [difficulty, setDifficulty] = useState('medium');
  const [topic, setTopic] = useState('');
  const [language, setLanguage] = useState('python');
  const [code, setCode] = useState('');
  const [messages, setMessages] = useState([]);
  const [runResult, setRunResult] = useState(null);
  const [report, setReport] = useState(null);

  const [isTyping, setIsTyping] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showStartModal, setShowStartModal] = useState(true);
  const [showReportModal, setShowReportModal] = useState(false);
  const [leftTab, setLeftTab] = useState('chat'); // 'chat' or 'problem'

  // Initialize session
  const handleStartInterview = async (e) => {
    if (e) e.preventDefault();
    try {
      const res = await fetch(`${API_BASE}/interview/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          candidate_name: candidateName,
          difficulty: difficulty,
          topic: topic || null,
          language: language,
        }),
      });

      if (!res.ok) throw new Error('Failed to start interview');
      const data = await res.json();

      // Fetch full session details
      const sessionRes = await fetch(`${API_BASE}/interview/${data.session_id}`);
      const fullSession = await sessionRes.json();

      setSession(fullSession);
      setMessages(fullSession.messages || []);
      setCode(fullSession.latest_code || data.starter_code || '');
      setShowStartModal(false);
      setRunResult(null);
      setReport(null);
    } catch (err) {
      console.error('Error starting interview:', err);
      alert('Could not start interview. Ensure backend server is running on port 8000.');
    }
  };

  // Send message
  const handleSendMessage = async (text) => {
    if (!session) return;
    setIsTyping(true);

    // Optimistically update message feed
    const tempMsg = {
      id: Date.now().toString(),
      role: 'candidate',
      content: text,
      timestamp: new Date().toISOString(),
      stage: session.current_stage,
    };
    setMessages((prev) => [...prev, tempMsg]);

    try {
      const res = await fetch(`${API_BASE}/interview/${session.session_id}/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
      });

      if (!res.ok) throw new Error('Message sending failed');
      const data = await res.json();

      const aiMsg = {
        id: (Date.now() + 1).toString(),
        role: 'interviewer',
        content: data.response,
        timestamp: new Date().toISOString(),
        stage: data.stage,
      };
      setMessages((prev) => [...prev, aiMsg]);

      // Update session stage and revealed constraints
      setSession((prev) => ({
        ...prev,
        current_stage: data.stage,
        revealed_constraints: data.revealed_constraints,
      }));
    } catch (err) {
      console.error('Chat error:', err);
    } finally {
      setIsTyping(false);
    }
  };

  // Run code
  const handleRunCode = async () => {
    if (!session) return;
    setIsRunning(true);
    setRunResult(null);

    try {
      const res = await fetch(`${API_BASE}/interview/${session.session_id}/code/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: code,
          language: language,
        }),
      });

      const data = await res.json();
      setRunResult(data);
    } catch (err) {
      console.error('Run code error:', err);
      setRunResult({
        stdout: '',
        stderr: 'Network error calling code execution service.',
        exit_code: 1,
        execution_time_ms: 0,
        success: false,
      });
    } finally {
      setIsRunning(false);
    }
  };

  // Submit code
  const handleSubmitCode = async () => {
    if (!session) return;
    setIsSubmitting(true);

    try {
      const res = await fetch(`${API_BASE}/interview/${session.session_id}/code/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: code,
          language: language,
        }),
      });

      const data = await res.json();
      const aiMsg = {
        id: Date.now().toString(),
        role: 'interviewer',
        content: data.response,
        timestamp: new Date().toISOString(),
        stage: data.stage,
      };
      setMessages((prev) => [...prev, aiMsg]);
      setSession((prev) => ({ ...prev, current_stage: data.stage }));
      setLeftTab('chat');
    } catch (err) {
      console.error('Submit code error:', err);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Advance stage manually
  const handleAdvanceStage = async (targetStage) => {
    if (!session) return;
    try {
      const res = await fetch(`${API_BASE}/interview/${session.session_id}/advance`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ next_stage: targetStage }),
      });
      const updated = await res.json();
      setSession(updated);
      setMessages(updated.messages || []);
    } catch (err) {
      console.error('Advance stage error:', err);
    }
  };

  // Finish interview and view report
  const handleFinishInterview = async () => {
    if (!session) return;
    try {
      const res = await fetch(`${API_BASE}/interview/${session.session_id}/finish`, {
        method: 'POST',
      });
      const reportData = await res.json();
      setReport(reportData);
      setShowReportModal(true);
    } catch (err) {
      console.error('Finish interview error:', err);
      alert('Could not generate report.');
    }
  };

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-slate-950 text-slate-100">
      {/* Navbar */}
      <Navbar
        session={session}
        onFinishInterview={handleFinishInterview}
        onStartNew={() => setShowStartModal(true)}
        onAdvanceStage={handleAdvanceStage}
      />

      {/* Main Workspace Grid */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Column: Chat and Problem Drawer */}
        <div className="w-full lg:w-[45%] flex flex-col border-r border-slate-800 bg-slate-900/40">
          {/* Tab Bar */}
          <div className="flex items-center border-b border-slate-800 bg-slate-900 px-4 py-2 shrink-0">
            <button
              onClick={() => setLeftTab('chat')}
              className={`flex items-center space-x-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                leftTab === 'chat'
                  ? 'bg-blue-600/20 text-blue-400 border border-blue-500/40'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <MessageSquare className="w-3.5 h-3.5" />
              <span>Interviewer Dialogue</span>
            </button>

            <button
              onClick={() => setLeftTab('problem')}
              className={`flex items-center space-x-2 px-3 py-1.5 rounded-lg text-xs font-semibold ml-2 transition ${
                leftTab === 'problem'
                  ? 'bg-blue-600/20 text-blue-400 border border-blue-500/40'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <BookOpen className="w-3.5 h-3.5" />
              <span>Problem Statement & Bounds</span>
              {session?.revealed_constraints?.length > 0 && (
                <span className="bg-purple-900/60 text-purple-300 text-[10px] px-1.5 py-0.2 rounded-full border border-purple-700">
                  {session.revealed_constraints.length}
                </span>
              )}
            </button>
          </div>

          {/* Tab Content */}
          <div className="flex-1 overflow-hidden">
            {leftTab === 'chat' ? (
              <ChatFeed
                messages={messages}
                onSendMessage={handleSendMessage}
                isTyping={isTyping}
                currentStage={session?.current_stage}
              />
            ) : (
              <ProblemDrawer
                question={session?.question}
                revealedConstraints={session?.revealed_constraints}
              />
            )}
          </div>
        </div>

        {/* Right Column: Code Editor & Execution Console */}
        <div className="hidden lg:flex lg:w-[55%] flex-col overflow-hidden">
          <CodeEditor
            code={code}
            onChange={setCode}
            language={language}
            onLanguageChange={setLanguage}
            onRunCode={handleRunCode}
            onSubmitCode={handleSubmitCode}
            runResult={runResult}
            isRunning={isRunning}
            isSubmitting={isSubmitting}
          />
        </div>
      </div>

      {/* Start Interview Modal */}
      {showStartModal && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 w-full max-w-md rounded-2xl p-6 shadow-2xl space-y-5">
            <div className="flex items-center space-x-3">
              <div className="w-10 h-10 rounded-xl bg-blue-600/20 border border-blue-500/30 flex items-center justify-center text-blue-400">
                <Sparkles className="w-5 h-5" />
              </div>
              <div>
                <h2 className="text-base font-bold text-white tracking-tight">Configure Interview</h2>
                <p className="text-xs text-slate-400">Simulate a Google SWE Technical Interview</p>
              </div>
            </div>

            <form onSubmit={handleStartInterview} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Candidate Name</label>
                <input
                  type="text"
                  value={candidateName}
                  onChange={(e) => setCandidateName(e.target.value)}
                  className="w-full bg-slate-950 text-slate-200 text-xs rounded-xl px-3.5 py-2.5 border border-slate-800 focus:outline-none focus:border-blue-500"
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Select Difficulty</label>
                <div className="grid grid-cols-3 gap-2">
                  {['easy', 'medium', 'hard'].map((d) => (
                    <button
                      key={d}
                      type="button"
                      onClick={() => setDifficulty(d)}
                      className={`text-xs font-semibold py-2 rounded-xl capitalize border transition ${
                        difficulty === d
                          ? d === 'easy'
                            ? 'bg-emerald-600/20 border-emerald-500 text-emerald-400'
                            : d === 'medium'
                            ? 'bg-amber-600/20 border-amber-500 text-amber-400'
                            : 'bg-rose-600/20 border-rose-500 text-rose-400'
                          : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-white'
                      }`}
                    >
                      {d}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">DSA Topic Preference (Optional)</label>
                <input
                  type="text"
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                  placeholder="e.g. Arrays, Graphs, Dynamic Programming..."
                  className="w-full bg-slate-950 text-slate-200 text-xs rounded-xl px-3.5 py-2.5 border border-slate-800 focus:outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Coding Language</label>
                <select
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                  className="w-full bg-slate-950 text-slate-200 text-xs rounded-xl px-3.5 py-2.5 border border-slate-800 focus:outline-none focus:border-blue-500"
                >
                  <option value="python">Python 3</option>
                  <option value="javascript">JavaScript (Node)</option>
                  <option value="cpp">C++ 17</option>
                  <option value="java">Java 17</option>
                </select>
              </div>

              <div className="pt-2 flex items-center justify-end space-x-2">
                {session && (
                  <button
                    type="button"
                    onClick={() => setShowStartModal(false)}
                    className="px-4 py-2 text-xs font-semibold text-slate-400 hover:text-white transition"
                  >
                    Cancel
                  </button>
                )}
                <button
                  type="submit"
                  className="w-full bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold py-2.5 rounded-xl shadow-lg transition active:scale-95"
                >
                  Begin Interview
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Report Modal */}
      {showReportModal && (
        <ReportModal
          report={report}
          onClose={() => setShowReportModal(false)}
        />
      )}
    </div>
  );
}

