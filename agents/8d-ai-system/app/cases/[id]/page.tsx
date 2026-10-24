"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft, Layers, CheckCircle2, Circle, Sparkles, Clock,
  ChevronRight, AlertCircle, History
} from "lucide-react";
import FishboneDiagram from "@/components/FishboneDiagram";

interface DStepData {
  stepNumber: number;
  content: string;
  aiSuggested: string | null;
  approved: boolean;
  approvedBy: string | null;
  approvedAt: string | null;
}

interface AuditEntry {
  id: string;
  stepNum: number;
  action: string;
  before: string | null;
  after: string | null;
  userId: string;
  createdAt: string;
}

interface CaseData {
  id: string;
  title: string;
  plant: string;
  product: string;
  reportedBy: string;
  priority: string;
  status: string;
  createdAt: string;
  steps: DStepData[];
  auditLogs: AuditEntry[];
}

const STEP_META = [
  { num: 1, label: "Team Formation", short: "D1" },
  { num: 2, label: "Problem Description", short: "D2" },
  { num: 3, label: "Containment Actions", short: "D3" },
  { num: 4, label: "Root Cause Analysis", short: "D4" },
  { num: 5, label: "Root Cause Verification", short: "D5" },
  { num: 6, label: "Corrective Actions", short: "D6" },
  { num: 7, label: "Preventive Actions", short: "D7" },
  { num: 8, label: "Recognition & Closure", short: "D8" },
];

const PRIORITY_COLOR: Record<string, string> = {
  Critical: "text-red-400 bg-red-500/10 border-red-500/30",
  High: "text-orange-400 bg-orange-500/10 border-orange-500/30",
  Medium: "text-yellow-400 bg-yellow-500/10 border-yellow-500/30",
  Low: "text-green-400 bg-green-500/10 border-green-500/30",
};

function parseJson(s: string | null | undefined) {
  if (!s) return {};
  try { return JSON.parse(s); } catch { return {}; }
}

// ─────────────────── Step renderers ───────────────────

function D1View({ data, aiData, onEdit }: { data: Record<string, unknown>; aiData: Record<string, unknown>; onEdit: (d: Record<string, unknown>) => void }) {
  const members: { name: string; role: string; department: string }[] = (data.members as []) || (aiData.members as []) || [];
  const leader = (data.teamLeader as string) || (aiData.teamLeader as string) || "";
  const rationale = (data.rationale as string) || (aiData.rationale as string) || "";

  return (
    <div className="space-y-4">
      <div className="bg-indigo-500/10 border border-indigo-500/20 rounded-lg p-4">
        <div className="text-xs text-indigo-400 mb-1 font-medium uppercase tracking-wide">Team Leader</div>
        <input
          className="bg-transparent text-gray-100 w-full text-sm focus:outline-none"
          value={leader}
          onChange={(e) => onEdit({ ...data, ...aiData, teamLeader: e.target.value })}
        />
      </div>
      <div>
        <div className="text-xs text-gray-500 mb-2 font-medium uppercase tracking-wide">Team Members</div>
        <div className="space-y-2">
          {members.map((m, i) => (
            <div key={i} className="flex items-center gap-3 bg-gray-800/50 rounded-lg px-4 py-3">
              <div className="w-8 h-8 rounded-full bg-indigo-600/30 flex items-center justify-center text-xs font-bold text-indigo-300">
                {m.name?.charAt(0) || "?"}
              </div>
              <div className="flex-1">
                <div className="text-sm font-medium text-gray-200">{m.name}</div>
                <div className="text-xs text-gray-500">{m.role} · {m.department}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
      {rationale && (
        <div className="text-sm text-gray-400 bg-gray-800/30 rounded-lg p-3 italic">
          {rationale}
        </div>
      )}
    </div>
  );
}

function D2View({ data, aiData, onEdit }: { data: Record<string, unknown>; aiData: Record<string, unknown>; onEdit: (d: Record<string, unknown>) => void }) {
  const merged = { ...aiData, ...data };
  const fields = [
    { key: "problemStatement", label: "Problem Statement", multiline: true },
    { key: "what", label: "What is wrong?" },
    { key: "when", label: "When first detected?" },
    { key: "where", label: "Where in the process?" },
    { key: "who", label: "Who is affected?" },
    { key: "howMany", label: "How many / Quantity?" },
    { key: "isNot", label: "What it is NOT" },
    { key: "customerImpact", label: "Customer Impact" },
  ];

  return (
    <div className="space-y-4">
      {fields.map(({ key, label, multiline }) => (
        <div key={key}>
          <label className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-1 block">{label}</label>
          {multiline ? (
            <textarea
              rows={3}
              value={(merged[key] as string) || ""}
              onChange={(e) => onEdit({ ...merged, [key]: e.target.value })}
              className="w-full bg-gray-800/50 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-indigo-500 resize-none"
            />
          ) : (
            <input
              value={(merged[key] as string) || ""}
              onChange={(e) => onEdit({ ...merged, [key]: e.target.value })}
              className="w-full bg-gray-800/50 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-indigo-500"
            />
          )}
        </div>
      ))}
      <div className="flex gap-3">
        <div className="flex-1">
          <label className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-1 block">Severity</label>
          <select
            value={(merged.severity as string) || "Medium"}
            onChange={(e) => onEdit({ ...merged, severity: e.target.value })}
            className="w-full bg-gray-800/50 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-indigo-500"
          >
            <option>Critical</option><option>High</option><option>Medium</option><option>Low</option>
          </select>
        </div>
      </div>
    </div>
  );
}

function D3View({ data, aiData }: { data: Record<string, unknown>; aiData: Record<string, unknown> }) {
  const merged = { ...aiData, ...data };
  const actions: { action: string; owner: string; dueDate: string; status: string }[] = (merged.immediateActions as []) || [];

  return (
    <div className="space-y-4">
      <div>
        <div className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">Immediate Containment Actions</div>
        <div className="space-y-2">
          {actions.map((a, i) => (
            <div key={i} className="bg-gray-800/50 rounded-lg p-3 flex items-start justify-between gap-4">
              <div className="flex-1">
                <div className="text-sm text-gray-200">{a.action}</div>
                <div className="text-xs text-gray-500 mt-1">Owner: {a.owner} · Due: {a.dueDate}</div>
              </div>
              <span className="text-xs px-2 py-1 rounded-full bg-yellow-500/20 text-yellow-400 border border-yellow-500/30 flex-shrink-0">
                {a.status}
              </span>
            </div>
          ))}
        </div>
      </div>
      {merged.stockHold ? (
        <InfoBlock label="Stock / Product Hold" value={merged.stockHold as string} />
      ) : null}
      {merged.customerNotification ? (
        <InfoBlock label="Customer Notification" value={merged.customerNotification as string} />
      ) : null}
      {merged.effectivenessCheck ? (
        <InfoBlock label="Effectiveness Check" value={merged.effectivenessCheck as string} />
      ) : null}
    </div>
  );
}

function D4View({ data, aiData }: { data: Record<string, unknown>; aiData: Record<string, unknown> }) {
  const merged = { ...aiData, ...data };
  const fishbone = merged.fishbone as { effect: string; categories: Record<string, string[]> } | undefined;
  const fiveWhy: { why: string; answer: string }[] = (merged.fiveWhy as []) || [];

  return (
    <div className="space-y-6">
      {fishbone && (
        <div>
          <div className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-3">Ishikawa Fishbone Diagram</div>
          <FishboneDiagram data={fishbone} />
        </div>
      )}
      {fiveWhy.length > 0 && (
        <div>
          <div className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-3">5-Why Analysis</div>
          <div className="space-y-2">
            {fiveWhy.map((item, i) => (
              <div key={i} className="flex gap-3">
                <div className="w-6 h-6 rounded-full bg-indigo-600/30 text-indigo-300 text-xs flex items-center justify-center flex-shrink-0 mt-0.5 font-bold">
                  {i + 1}
                </div>
                <div className="flex-1 bg-gray-800/50 rounded-lg p-3">
                  <div className="text-xs text-gray-500 mb-1">{item.why}</div>
                  <div className="text-sm text-gray-200">{item.answer}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
      {merged.rootCause ? (
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4">
          <div className="text-xs font-medium text-red-400 uppercase tracking-wide mb-1">Identified Root Cause</div>
          <div className="text-sm text-gray-200">{merged.rootCause as string}</div>
        </div>
      ) : null}
      {merged.escapeCause ? (
        <InfoBlock label="Escape Cause (Why Not Caught Earlier)" value={merged.escapeCause as string} />
      ) : null}
    </div>
  );
}

function D5View({ data, aiData }: { data: Record<string, unknown>; aiData: Record<string, unknown> }) {
  const merged = { ...aiData, ...data };
  const methods: { method: string; result: string; responsible: string }[] = (merged.verificationMethods as []) || [];
  const evidence: string[] = (merged.evidenceRequired as []) || [];

  return (
    <div className="space-y-4">
      <div>
        <div className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">Verification Methods</div>
        {methods.map((m, i) => (
          <div key={i} className="bg-gray-800/50 rounded-lg p-3 mb-2">
            <div className="text-sm text-gray-200">{m.method}</div>
            <div className="text-xs text-gray-500 mt-1">Expected: {m.result} · Responsible: {m.responsible}</div>
          </div>
        ))}
      </div>
      {evidence.length > 0 && (
        <div>
          <div className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">Evidence Required</div>
          <ul className="space-y-1">
            {evidence.map((e, i) => (
              <li key={i} className="flex items-center gap-2 text-sm text-gray-300">
                <div className="w-1.5 h-1.5 rounded-full bg-indigo-500" />
                {e}
              </li>
            ))}
          </ul>
        </div>
      )}
      {merged.conclusion ? <InfoBlock label="Conclusion" value={merged.conclusion as string} /> : null}
    </div>
  );
}

function D6View({ data, aiData }: { data: Record<string, unknown>; aiData: Record<string, unknown> }) {
  const merged = { ...aiData, ...data };
  const actions: { action: string; owner: string; targetDate: string; priority: string; status: string }[] = (merged.actions as []) || [];

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        {actions.map((a, i) => (
          <div key={i} className="bg-gray-800/50 rounded-lg p-3">
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1">
                <div className="text-sm text-gray-200">{a.action}</div>
                <div className="text-xs text-gray-500 mt-1">Owner: {a.owner} · Target: {a.targetDate}</div>
              </div>
              <span className={`text-xs px-2 py-1 rounded-full border flex-shrink-0 ${
                a.priority === "High" ? "bg-red-500/20 text-red-400 border-red-500/30" :
                a.priority === "Critical" ? "bg-orange-500/20 text-orange-400 border-orange-500/30" :
                "bg-yellow-500/20 text-yellow-400 border-yellow-500/30"
              }`}>{a.priority}</span>
            </div>
          </div>
        ))}
      </div>
      {merged.successCriteria ? <InfoBlock label="Success Criteria" value={merged.successCriteria as string} /> : null}
      {merged.implementationPlan ? <InfoBlock label="Implementation Plan" value={merged.implementationPlan as string} /> : null}
    </div>
  );
}

function D7View({ data, aiData }: { data: Record<string, unknown>; aiData: Record<string, unknown> }) {
  const merged = { ...aiData, ...data };
  const changes: { change: string; area: string; owner: string; dueDate: string }[] = (merged.systemChanges as []) || [];
  const similar: string[] = (merged.similarProcesses as []) || [];
  const docs: string[] = (merged.documentUpdates as []) || [];

  return (
    <div className="space-y-4">
      {changes.length > 0 && (
        <div>
          <div className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">System / Process Changes</div>
          {changes.map((c, i) => (
            <div key={i} className="bg-gray-800/50 rounded-lg p-3 mb-2">
              <div className="text-sm text-gray-200">{c.change}</div>
              <div className="text-xs text-gray-500 mt-1">Area: {c.area} · Owner: {c.owner} · Due: {c.dueDate}</div>
            </div>
          ))}
        </div>
      )}
      {similar.length > 0 && (
        <div>
          <div className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">Similar Processes to Review</div>
          {similar.map((s, i) => (
            <div key={i} className="flex items-center gap-2 text-sm text-gray-300 py-1">
              <ChevronRight size={14} className="text-indigo-400" />
              {s}
            </div>
          ))}
        </div>
      )}
      {docs.length > 0 && (
        <div>
          <div className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">Documents to Update</div>
          {docs.map((d, i) => (
            <div key={i} className="flex items-center gap-2 text-sm text-gray-300 py-1">
              <ChevronRight size={14} className="text-teal-400" />
              {d}
            </div>
          ))}
        </div>
      )}
      {merged.controlPlan ? <InfoBlock label="Control Plan" value={merged.controlPlan as string} /> : null}
      {merged.trainingRequired ? <InfoBlock label="Training Required" value={merged.trainingRequired as string} /> : null}
    </div>
  );
}

function D8View({ data, aiData }: { data: Record<string, unknown>; aiData: Record<string, unknown> }) {
  const merged = { ...aiData, ...data };
  const learnings: string[] = (merged.keyLearnings as []) || [];

  return (
    <div className="space-y-4">
      {merged.summary ? (
        <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-lg p-4">
          <div className="text-xs font-medium text-emerald-400 uppercase tracking-wide mb-2">8D Summary</div>
          <div className="text-sm text-gray-200">{merged.summary as string}</div>
        </div>
      ) : null}
      {learnings.length > 0 && (
        <div>
          <div className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">Key Learnings</div>
          {learnings.map((l, i) => (
            <div key={i} className="flex items-start gap-2 text-sm text-gray-300 py-1.5 border-b border-gray-800">
              <CheckCircle2 size={14} className="text-emerald-400 mt-0.5 flex-shrink-0" />
              {l}
            </div>
          ))}
        </div>
      )}
      {merged.teamAcknowledgment ? <InfoBlock label="Team Acknowledgment" value={merged.teamAcknowledgment as string} /> : null}
      {merged.lessonsLearned ? <InfoBlock label="Lessons Learned" value={merged.lessonsLearned as string} /> : null}
      {merged.effectiveness ? <InfoBlock label="Effectiveness Measurement" value={merged.effectiveness as string} /> : null}
    </div>
  );
}

function InfoBlock({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-gray-800/30 rounded-lg p-3">
      <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">{label}</div>
      <div className="text-sm text-gray-300">{value}</div>
    </div>
  );
}

const STEP_VIEWS: Record<number, React.ComponentType<{
  data: Record<string, unknown>;
  aiData: Record<string, unknown>;
  onEdit: (d: Record<string, unknown>) => void;
}>> = {
  1: D1View, 2: D2View, 3: D3View, 4: D4View,
  5: D5View, 6: D6View, 7: D7View, 8: D8View,
};

// ─────────────────── Main Page ───────────────────

export default function CasePage() {
  const { id } = useParams<{ id: string }>();
  const [caseData, setCaseData] = useState<CaseData | null>(null);
  const [activeStep, setActiveStep] = useState(1);
  const [generating, setGenerating] = useState(false);
  const [approving, setApproving] = useState(false);
  const [editedContent, setEditedContent] = useState<Record<string, unknown>>({});
  const [showAudit, setShowAudit] = useState(false);

  const loadCase = useCallback(async () => {
    const res = await fetch(`/api/cases/${id}`);
    const data = await res.json();
    setCaseData(data);
    const currentStep = parseInt(data.status.replace("D", "")) || 1;
    if (data.status !== "CLOSED") setActiveStep(currentStep);
  }, [id]);

  useEffect(() => { loadCase(); }, [loadCase]);

  const getStep = (num: number) => caseData?.steps.find((s) => s.stepNumber === num);

  const getContext = () => {
    if (!caseData) return {};
    const ctx: Record<string, unknown> = {
      title: caseData.title,
      plant: caseData.plant,
      product: caseData.product,
    };
    for (let i = 1; i <= 8; i++) {
      const step = getStep(i);
      if (step) {
        const key = `d${i}`;
        ctx[key] = parseJson(step.content);
        if (!Object.keys(ctx[key] as object).length) {
          ctx[key] = parseJson(step.aiSuggested);
        }
      }
    }
    const d2 = ctx["d2"] as Record<string, unknown>;
    if (d2) ctx["description"] = d2.problemStatement as string || "";
    return ctx;
  };

  const handleGenerate = async (stepNum: number) => {
    setGenerating(true);
    try {
      const res = await fetch("/api/ai/suggest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ stepNumber: stepNum, context: getContext() }),
      });
      const { suggestion, error } = await res.json();
      if (error) { alert("AI error: " + error); return; }

      await fetch(`/api/cases/${id}/steps`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          stepNumber: stepNum,
          content: suggestion,
          aiSuggested: suggestion,
          action: "AI_SUGGESTED",
        }),
      });
      setEditedContent({});
      await loadCase();
    } finally {
      setGenerating(false);
    }
  };

  const handleSaveEdit = async () => {
    const step = getStep(activeStep);
    const base = parseJson(step?.aiSuggested);
    const merged = { ...base, ...editedContent };

    await fetch(`/api/cases/${id}/steps`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ stepNumber: activeStep, content: merged, action: "HUMAN_EDITED" }),
    });
    setEditedContent({});
    await loadCase();
  };

  const handleApprove = async () => {
    setApproving(true);
    try {
      await fetch(`/api/cases/${id}/steps`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ stepNumber: activeStep, approvedBy: "Quality Engineer" }),
      });
      await loadCase();
      if (activeStep < 8) setActiveStep(activeStep + 1);
    } finally {
      setApproving(false);
    }
  };

  if (!caseData) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <div className="text-gray-500">Loading case...</div>
      </div>
    );
  }

  const currentStepData = getStep(activeStep);
  const currentContent = Object.keys(editedContent).length > 0
    ? editedContent
    : parseJson(currentStepData?.content);
  const currentAiData = parseJson(currentStepData?.aiSuggested);
  const isApproved = currentStepData?.approved || false;
  const hasContent = currentStepData !== undefined;
  const StepView = STEP_VIEWS[activeStep];

  const completedSteps = caseData.steps.filter((s) => s.approved).length;

  return (
    <div className="min-h-screen bg-gray-950">
      {/* Header */}
      <header className="border-b border-gray-800 bg-gray-900/80 backdrop-blur sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center">
              <Layers size={18} />
            </div>
            <Link href="/" className="flex items-center gap-2 text-gray-400 hover:text-gray-200 transition-colors">
              <ArrowLeft size={14} />
              <span className="text-sm">Dashboard</span>
            </Link>
            <span className="text-gray-700">/</span>
            <span className="text-sm text-gray-300 max-w-xs truncate">{caseData.title}</span>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setShowAudit(!showAudit)}
              className="flex items-center gap-2 text-sm text-gray-400 hover:text-gray-200 transition-colors px-3 py-1.5 rounded-lg hover:bg-gray-800"
            >
              <History size={14} />
              Audit Trail
            </button>
            <div className={`text-xs px-3 py-1.5 rounded-full border font-medium ${PRIORITY_COLOR[caseData.priority]}`}>
              {caseData.priority}
            </div>
            <div className="text-xs text-gray-500 bg-gray-800 px-3 py-1.5 rounded-full">
              {completedSteps}/8 steps approved
            </div>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-6 py-6 flex gap-6">
        {/* Left sidebar — step navigation */}
        <div className="w-52 flex-shrink-0">
          <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-3 px-1">8D Steps</div>
          <div className="space-y-1">
            {STEP_META.map((s) => {
              const stepData = getStep(s.num);
              const isActive = activeStep === s.num;
              const isDone = stepData?.approved;
              const hasAI = !!stepData;

              return (
                <button
                  key={s.num}
                  onClick={() => setActiveStep(s.num)}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors text-left ${
                    isActive
                      ? "bg-indigo-600/20 border border-indigo-500/30 text-indigo-300"
                      : "hover:bg-gray-800/50 text-gray-400 hover:text-gray-200 border border-transparent"
                  }`}
                >
                  <div className="flex-shrink-0">
                    {isDone ? (
                      <CheckCircle2 size={16} className="text-green-400" />
                    ) : hasAI ? (
                      <Clock size={16} className="text-yellow-400" />
                    ) : (
                      <Circle size={16} className="text-gray-600" />
                    )}
                  </div>
                  <div className="min-w-0">
                    <div className="font-medium text-xs">{s.short}</div>
                    <div className="text-xs truncate opacity-75">{s.label}</div>
                  </div>
                </button>
              );
            })}
          </div>

          {/* Progress */}
          <div className="mt-6 px-1">
            <div className="flex justify-between text-xs text-gray-500 mb-1">
              <span>Progress</span>
              <span>{Math.round((completedSteps / 8) * 100)}%</span>
            </div>
            <div className="h-1.5 bg-gray-800 rounded-full">
              <div
                className="h-full bg-gradient-to-r from-indigo-600 to-green-500 rounded-full transition-all duration-500"
                style={{ width: `${(completedSteps / 8) * 100}%` }}
              />
            </div>
          </div>
        </div>

        {/* Main content */}
        <div className="flex-1 min-w-0">
          {/* Step header */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 mb-4">
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-bold text-indigo-400 bg-indigo-500/10 px-2 py-0.5 rounded">
                    D{activeStep}
                  </span>
                  <h2 className="font-semibold text-lg">
                    {STEP_META[activeStep - 1].label}
                  </h2>
                  {isApproved && (
                    <span className="flex items-center gap-1 text-xs text-green-400 bg-green-500/10 px-2 py-0.5 rounded-full border border-green-500/20">
                      <CheckCircle2 size={11} />
                      Approved
                    </span>
                  )}
                </div>
                <div className="text-sm text-gray-500">
                  {caseData.title} · {caseData.plant}
                </div>
              </div>
              <div className="flex items-center gap-2">
                {!hasContent && (
                  <button
                    onClick={() => handleGenerate(activeStep)}
                    disabled={generating}
                    className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
                  >
                    <Sparkles size={14} className={generating ? "animate-spin" : ""} />
                    {generating ? "Generating..." : "Generate with AI"}
                  </button>
                )}
                {hasContent && !isApproved && (
                  <>
                    {Object.keys(editedContent).length > 0 && (
                      <button
                        onClick={handleSaveEdit}
                        className="text-sm px-4 py-2 rounded-lg border border-gray-700 hover:border-gray-600 text-gray-300 transition-colors"
                      >
                        Save Edits
                      </button>
                    )}
                    <button
                      onClick={() => handleGenerate(activeStep)}
                      disabled={generating}
                      className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-gray-200 px-3 py-2 rounded-lg hover:bg-gray-800 transition-colors"
                    >
                      <Sparkles size={13} />
                      Regenerate
                    </button>
                    <button
                      onClick={handleApprove}
                      disabled={approving}
                      className="flex items-center gap-2 bg-green-600 hover:bg-green-500 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
                    >
                      <CheckCircle2 size={14} />
                      {approving ? "Approving..." : "Approve & Continue"}
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>

          {/* AI badge */}
          {hasContent && (
            <div className="flex items-center gap-2 mb-3 px-1">
              <div className="flex items-center gap-1.5 text-xs text-indigo-400 bg-indigo-500/10 px-2.5 py-1 rounded-full border border-indigo-500/20">
                <Sparkles size={11} />
                AI Generated
              </div>
              <div className="text-xs text-gray-600">·</div>
              <div className="text-xs text-gray-500">Review and edit before approving</div>
            </div>
          )}

          {/* Step content */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
            {!hasContent ? (
              <div className="py-12 text-center">
                <div className="w-12 h-12 rounded-full bg-indigo-600/20 flex items-center justify-center mx-auto mb-4">
                  <Sparkles size={24} className="text-indigo-400" />
                </div>
                <h3 className="text-lg font-semibold mb-2">Ready for AI Analysis</h3>
                <p className="text-gray-400 text-sm mb-6 max-w-sm mx-auto">
                  Click &quot;Generate with AI&quot; to get intelligent suggestions for D{activeStep}: {STEP_META[activeStep - 1].label}.
                  You can review and edit before approving.
                </p>
                <button
                  onClick={() => handleGenerate(activeStep)}
                  disabled={generating}
                  className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white px-6 py-3 rounded-lg font-medium transition-colors mx-auto"
                >
                  <Sparkles size={16} className={generating ? "animate-spin" : ""} />
                  {generating ? "AI is analyzing..." : `Generate D${activeStep} Suggestions`}
                </button>
              </div>
            ) : (
              <StepView
                data={currentContent}
                aiData={currentAiData}
                onEdit={(d) => setEditedContent(d)}
              />
            )}
          </div>

          {/* Audit diff */}
          {hasContent && currentStepData?.aiSuggested && !isApproved && (
            <div className="mt-4 bg-gray-900/50 border border-gray-800 rounded-xl p-4">
              <div className="flex items-center gap-2 mb-3">
                <AlertCircle size={14} className="text-yellow-400" />
                <span className="text-sm font-medium text-gray-300">Pending Human Review</span>
                <span className="text-xs text-gray-500">— edit any field above, then approve</span>
              </div>
            </div>
          )}
        </div>

        {/* Audit trail panel */}
        {showAudit && (
          <div className="w-72 flex-shrink-0">
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 sticky top-24">
              <div className="flex items-center gap-2 mb-4">
                <History size={14} className="text-indigo-400" />
                <h3 className="text-sm font-semibold">Audit Trail</h3>
              </div>
              <div className="space-y-2 max-h-96 overflow-y-auto scrollbar-thin">
                {caseData.auditLogs.map((log) => (
                  <div key={log.id} className="text-xs border-l-2 border-gray-700 pl-3 py-1">
                    <div className={`font-medium ${
                      log.action === "AI_SUGGESTED" ? "text-indigo-400" :
                      log.action === "APPROVED" ? "text-green-400" :
                      log.action === "HUMAN_EDITED" ? "text-yellow-400" : "text-gray-400"
                    }`}>
                      {log.action === "AI_SUGGESTED" ? "🤖 AI Suggested" :
                       log.action === "APPROVED" ? "✅ Approved" :
                       log.action === "HUMAN_EDITED" ? "✏️ Edited" :
                       log.action}
                      {log.stepNum > 0 && ` · D${log.stepNum}`}
                    </div>
                    <div className="text-gray-600 mt-0.5">{log.userId}</div>
                    <div className="text-gray-700">{new Date(log.createdAt).toLocaleString()}</div>
                  </div>
                ))}
                {caseData.auditLogs.length === 0 && (
                  <div className="text-gray-600 text-center py-4">No activity yet</div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
