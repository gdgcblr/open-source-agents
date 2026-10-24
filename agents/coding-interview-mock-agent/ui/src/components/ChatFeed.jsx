import React, { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, Sparkles, MessageSquarePlus, ChevronRight } from 'lucide-react';

const SUGGESTED_QUESTIONS = [
  "Can the input array be empty or have only 1 element?",
  "Are duplicates allowed in the input?",
  "Can numbers be negative or exceed standard integer limits?",
  "I'd like to propose a brute force approach first.",
  "I can optimize this to O(N) using a Hash Map.",
  "I'm ready to start coding the implementation now."
];

export default function ChatFeed({ messages = [], onSendMessage, isTyping, currentStage }) {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isTyping]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!input.trim() || isTyping) return;
    onSendMessage(input);
    setInput('');
  };

  const handleQuickPrompt = (prompt) => {
    if (isTyping) return;
    onSendMessage(prompt);
  };

  return (
    <div className="flex flex-col h-full bg-slate-900/60 border-r border-slate-800">
      {/* Header bar */}
      <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between bg-slate-900/80">
        <div className="flex items-center space-x-2">
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">Google SWE Interviewer</span>
        </div>
        <span className="text-[11px] text-slate-500 font-mono">Stage: {currentStage?.toUpperCase()}</span>
      </div>

      {/* Message history */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((msg, index) => {
          const isInterviewer = msg.role === 'interviewer';

          return (
            <div
              key={msg.id || index}
              className={`flex items-start space-x-3 ${isInterviewer ? '' : 'flex-row-reverse space-x-reverse'}`}
            >
              {/* Avatar */}
              <div
                className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 text-xs shadow-sm ${
                  isInterviewer
                    ? 'bg-gradient-to-tr from-blue-600 to-indigo-600 text-white'
                    : 'bg-gradient-to-tr from-emerald-600 to-teal-600 text-white'
                }`}
              >
                {isInterviewer ? <Bot className="w-4 h-4" /> : <User className="w-4 h-4" />}
              </div>

              {/* Message Bubble */}
              <div
                className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-xs leading-relaxed ${
                  isInterviewer
                    ? 'bg-slate-800/90 text-slate-200 border border-slate-700/60 shadow-sm'
                    : 'bg-blue-600 text-white shadow-md'
                }`}
              >
                <div className="whitespace-pre-wrap">{msg.content}</div>
                <div
                  className={`text-[10px] mt-1 text-right ${
                    isInterviewer ? 'text-slate-500' : 'text-blue-200'
                  }`}
                >
                  {msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}
                </div>
              </div>
            </div>
          );
        })}

        {isTyping && (
          <div className="flex items-start space-x-3">
            <div className="w-7 h-7 rounded-lg bg-blue-600/30 text-blue-400 border border-blue-500/40 flex items-center justify-center shrink-0">
              <Sparkles className="w-4 h-4 animate-spin" />
            </div>
            <div className="bg-slate-800/90 border border-slate-700/60 rounded-2xl px-4 py-3 flex items-center space-x-1.5">
              <span className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce [animation-delay:-0.3s]"></span>
              <span className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce [animation-delay:-0.15s]"></span>
              <span className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce"></span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Quick clarification chips */}
      <div className="px-4 py-2 border-t border-slate-800/60 bg-slate-900/40 overflow-x-auto flex items-center space-x-2 no-scrollbar">
        <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider shrink-0">Suggest:</span>
        {SUGGESTED_QUESTIONS.map((q, i) => (
          <button
            key={i}
            onClick={() => handleQuickPrompt(q)}
            className="text-[11px] whitespace-nowrap bg-slate-800/80 hover:bg-slate-700 text-slate-300 hover:text-white px-2.5 py-1 rounded-full border border-slate-700/80 transition active:scale-95"
          >
            {q}
          </button>
        ))}
      </div>

      {/* Input bar */}
      <form onSubmit={handleSubmit} className="p-3 border-t border-slate-800 bg-slate-900 flex items-center space-x-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a clarifying question or discuss your approach..."
          className="flex-1 bg-slate-950 text-slate-200 text-xs rounded-xl px-3.5 py-2.5 border border-slate-800 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition"
          disabled={isTyping}
        />
        <button
          type="submit"
          disabled={!input.trim() || isTyping}
          className="bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:hover:bg-blue-600 text-white p-2.5 rounded-xl transition shadow-sm active:scale-95"
        >
          <Send className="w-4 h-4" />
        </button>
      </form>
    </div>
  );
}

