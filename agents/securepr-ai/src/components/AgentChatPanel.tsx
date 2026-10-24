import React, { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, Terminal, RefreshCw } from 'lucide-react';
import { PrioritizedFinding, AttackPathHypothesis } from '../types/security';

export interface ChatMessage {
  id: string;
  sender: 'user' | 'agent';
  text: string;
  timestamp: string;
  toolCall?: {
    name: string;
    detail: string;
    status: 'done' | 'running';
  };
}

interface AgentChatPanelProps {
  findings: PrioritizedFinding[];
  attackPaths: AttackPathHypothesis[];
  passedGate: boolean;
  activeFilePath?: string;
  currentCodeContext?: string;
  onApplySuggestedFix?: (findingId: string, fixCode: string) => void;
}

export const AgentChatPanel: React.FC<AgentChatPanelProps> = ({
  findings,
  attackPaths,
  passedGate,
  currentCodeContext,
}) => {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'init-1',
      sender: 'agent',
      text: `Hello! I am your SecurePR AI Review Agent. I've automatically evaluated the changed files in this pull request against deterministic AST rules, scrubbed all credentials, and mapped STRIDE threat models.\n\nAsk me anything about these findings, request unified diff patches, or test fix verifications!`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      toolCall: {
        name: 'scan_codebase()',
        detail: `Found ${findings.length} issues · Gate: ${passedGate ? 'PASSED' : 'BLOCKED'}`,
        status: 'done',
      },
    },
  ]);
  const [input, setInput] = useState('');
  const [isSending, setIsSending] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isSending]);

  const handleSend = async (customPrompt?: string) => {
    const textToSend = customPrompt || input.trim();
    if (!textToSend || isSending) return;

    const userMsg: ChatMessage = {
      id: `usr-${Date.now()}`,
      sender: 'user',
      text: textToSend,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMsg]);
    if (!customPrompt) setInput('');
    setIsSending(true);

    try {
      const historyPayload = [...messages, userMsg].map((m) => ({
        role: m.sender === 'agent' ? 'assistant' : 'user',
        content: m.text,
      }));

      const res = await fetch('/api/agent/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: historyPayload,
          findings,
          attackPaths,
          passedGate,
          currentCodeContext,
        }),
      });

      const data = await res.json();
      const agentMsg: ChatMessage = {
        id: `agt-${Date.now()}`,
        sender: 'agent',
        text: data.reply || 'Analysis completed.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };

      setMessages((prev) => [...prev, agentMsg]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: `agt-err-${Date.now()}`,
          sender: 'agent',
          text: 'Unable to reach conversational agent backend. Please ensure the server is active.',
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    } finally {
      setIsSending(false);
    }
  };

  const samplePrompts = [
    'How does the JWT bypass link to BOLA?',
    'Could the CORS finding be a false positive?',
    'Provide an RS256 token verification patch',
    'Summarize remediation priorities for CI gate clearance',
  ];

  return (
    <div className="border border-slate-200 bg-white rounded-xl overflow-hidden shadow-xs flex flex-col h-[650px]">
      {/* Header */}
      <div className="p-3.5 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-emerald-600 text-white flex items-center justify-center shadow-2xs">
            <Bot className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2 text-xs font-bold text-slate-900">
              <span>SecurePR Conversational Agent</span>
              <span className="font-mono text-[10px] text-emerald-700 bg-emerald-100/70 px-1.5 py-0.5 rounded">
                Gemini 3.8 Flash
              </span>
            </div>
            <div className="text-[11px] text-slate-500">
              Multi-Turn Review · STRIDE Reasoning · Fix Verification
            </div>
          </div>
        </div>

        <button
          onClick={() =>
            setMessages([
              {
                id: `reset-${Date.now()}`,
                sender: 'agent',
                text: 'Chat history reset. How can I assist you with this pull request review?',
                timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
              },
            ])
          }
          className="text-slate-400 hover:text-slate-600 p-1.5 rounded-lg hover:bg-slate-100 transition-colors"
          title="Reset conversation"
        >
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Messages Thread */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-slate-50/40">
        {messages.map((m) => {
          const isAgent = m.sender === 'agent';
          return (
            <div
              key={m.id}
              className={`flex gap-3 text-xs ${isAgent ? 'items-start' : 'items-start flex-row-reverse'}`}
            >
              <div
                className={`w-6 h-6 rounded-lg flex items-center justify-center shrink-0 mt-0.5 ${
                  isAgent
                    ? 'bg-emerald-100 text-emerald-800 border border-emerald-200'
                    : 'bg-slate-900 text-white'
                }`}
              >
                {isAgent ? <Bot className="w-3.5 h-3.5" /> : <User className="w-3.5 h-3.5" />}
              </div>

              <div
                className={`max-w-[85%] rounded-xl p-3.5 space-y-1.5 shadow-2xs ${
                  isAgent
                    ? 'bg-white border border-slate-200 text-slate-800'
                    : 'bg-slate-900 text-white'
                }`}
              >
                {/* Tool Call Badge */}
                {m.toolCall && (
                  <div className="px-2.5 py-1 bg-slate-50 border border-slate-200 rounded-lg font-mono text-[11px] text-emerald-800 font-semibold flex items-center gap-1.5 mb-2">
                    <Terminal className="w-3 h-3 text-emerald-700" />
                    <span>Tool executed: {m.toolCall.name}</span>
                    <span className="text-slate-300">·</span>
                    <span className="text-slate-600 font-normal">{m.toolCall.detail}</span>
                  </div>
                )}

                <div className="whitespace-pre-wrap leading-relaxed font-sans text-xs">
                  {m.text}
                </div>

                <div className={`text-[10px] font-mono text-right pt-0.5 ${isAgent ? 'text-slate-400' : 'text-slate-300'}`}>
                  {m.timestamp}
                </div>
              </div>
            </div>
          );
        })}

        {isSending && (
          <div className="flex gap-3 items-start text-xs">
            <div className="w-6 h-6 rounded-lg bg-emerald-100 text-emerald-800 border border-emerald-200 flex items-center justify-center shrink-0 mt-0.5">
              <Bot className="w-3.5 h-3.5" />
            </div>
            <div className="bg-white border border-slate-200 rounded-xl p-3 text-slate-600 flex items-center gap-2 shadow-2xs">
              <div className="w-3.5 h-3.5 border-2 border-emerald-600 border-t-transparent rounded-full animate-spin" />
              <span>Analyzing PR context and reasoning with AppSec tools...</span>
            </div>
          </div>
        )}
        <div ref={scrollRef} />
      </div>

      {/* Suggested Quick Prompts */}
      <div className="p-2.5 bg-slate-50 border-t border-slate-200 flex items-center gap-2 overflow-x-auto text-[11px]">
        <span className="text-slate-500 shrink-0 font-medium">Prompts:</span>
        {samplePrompts.map((p, idx) => (
          <button
            key={idx}
            onClick={() => handleSend(p)}
            className="px-2.5 py-1 bg-white hover:bg-slate-100 text-slate-700 border border-slate-200 rounded-lg whitespace-nowrap shadow-2xs transition-colors font-medium"
          >
            {p}
          </button>
        ))}
      </div>

      {/* Input Box */}
      <div className="p-3 bg-white border-t border-slate-200 flex items-center gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          placeholder="Ask SecurePR Agent about attack chains, false positives, or code fixes..."
          className="flex-1 bg-slate-50 border border-slate-200 rounded-lg px-3.5 py-2 text-xs text-slate-800 focus:outline-none focus:border-slate-400 focus:bg-white transition-colors"
        />
        <button
          onClick={() => handleSend()}
          disabled={!input.trim() || isSending}
          className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold disabled:opacity-50 transition-colors flex items-center gap-1 shadow-xs"
        >
          <Send className="w-3.5 h-3.5" />
          <span>Send</span>
        </button>
      </div>
    </div>
  );
};
