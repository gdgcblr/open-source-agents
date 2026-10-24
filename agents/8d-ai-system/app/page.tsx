"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertCircle, CheckCircle2, Clock, Plus, TrendingUp, Layers } from "lucide-react";

interface Case {
  id: string;
  title: string;
  plant: string;
  product: string;
  reportedBy: string;
  status: string;
  priority: string;
  createdAt: string;
  steps: { stepNumber: number; approved: boolean }[];
}

const STATUS_COLOR: Record<string, string> = {
  D1: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  D2: "bg-indigo-500/20 text-indigo-400 border-indigo-500/30",
  D3: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  D4: "bg-orange-500/20 text-orange-400 border-orange-500/30",
  D5: "bg-pink-500/20 text-pink-400 border-pink-500/30",
  D6: "bg-purple-500/20 text-purple-400 border-purple-500/30",
  D7: "bg-teal-500/20 text-teal-400 border-teal-500/30",
  D8: "bg-green-500/20 text-green-400 border-green-500/30",
  CLOSED: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
};

const PRIORITY_COLOR: Record<string, string> = {
  Critical: "text-red-400",
  High: "text-orange-400",
  Medium: "text-yellow-400",
  Low: "text-green-400",
};

export default function Dashboard() {
  const [cases, setCases] = useState<Case[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/cases")
      .then((r) => r.json())
      .then((data) => { setCases(data); setLoading(false); });
  }, []);

  const open = cases.filter((c) => c.status !== "CLOSED").length;
  const closed = cases.filter((c) => c.status === "CLOSED").length;
  const critical = cases.filter((c) => c.priority === "Critical").length;

  return (
    <div className="min-h-screen bg-gray-950">
      {/* Header */}
      <header className="border-b border-gray-800 bg-gray-900/80 backdrop-blur sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center">
              <Layers size={18} />
            </div>
            <div>
              <h1 className="font-bold text-lg leading-none">8D AI System</h1>
              <p className="text-xs text-gray-500 mt-0.5">Root Cause Analysis & Corrective Action</p>
            </div>
          </div>
          <Link
            href="/cases/new"
            className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
          >
            <Plus size={16} />
            New 8D Case
          </Link>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8">
        {/* Stats */}
        <div className="grid grid-cols-4 gap-4 mb-8">
          {[
            { label: "Total Cases", value: cases.length, icon: Layers, color: "text-indigo-400", bg: "bg-indigo-500/10" },
            { label: "Open Cases", value: open, icon: Clock, color: "text-yellow-400", bg: "bg-yellow-500/10" },
            { label: "Closed", value: closed, icon: CheckCircle2, color: "text-green-400", bg: "bg-green-500/10" },
            { label: "Critical", value: critical, icon: AlertCircle, color: "text-red-400", bg: "bg-red-500/10" },
          ].map((s) => (
            <div key={s.label} className="bg-gray-900 border border-gray-800 rounded-xl p-5">
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm text-gray-400">{s.label}</span>
                <div className={`w-8 h-8 rounded-lg ${s.bg} flex items-center justify-center`}>
                  <s.icon size={16} className={s.color} />
                </div>
              </div>
              <div className={`text-3xl font-bold ${s.color}`}>{s.value}</div>
            </div>
          ))}
        </div>

        {/* D-step progress bar */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 mb-8">
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp size={16} className="text-indigo-400" />
            <h2 className="font-semibold text-sm">Pipeline Overview</h2>
          </div>
          <div className="flex gap-2">
            {["D1","D2","D3","D4","D5","D6","D7","D8","CLOSED"].map((s) => {
              const count = cases.filter((c) => c.status === s).length;
              return (
                <div key={s} className="flex-1 text-center">
                  <div className="text-xs text-gray-500 mb-1">{s}</div>
                  <div className={`rounded-md py-1.5 text-sm font-semibold border ${STATUS_COLOR[s] || "bg-gray-700 text-gray-400 border-gray-600"}`}>
                    {count}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Cases table */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl">
          <div className="px-6 py-4 border-b border-gray-800 flex items-center justify-between">
            <h2 className="font-semibold">All Cases</h2>
            <span className="text-sm text-gray-500">{cases.length} total</span>
          </div>
          {loading ? (
            <div className="py-16 text-center text-gray-500">Loading cases...</div>
          ) : cases.length === 0 ? (
            <div className="py-16 text-center">
              <AlertCircle size={40} className="text-gray-700 mx-auto mb-3" />
              <p className="text-gray-500 mb-4">No cases yet. Start by creating your first 8D case.</p>
              <Link href="/cases/new" className="text-indigo-400 hover:text-indigo-300 text-sm font-medium">
                + Create first case
              </Link>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-gray-500">
                  <th className="text-left px-6 py-3 font-medium">Problem</th>
                  <th className="text-left px-6 py-3 font-medium">Plant / Product</th>
                  <th className="text-left px-6 py-3 font-medium">Priority</th>
                  <th className="text-left px-6 py-3 font-medium">Stage</th>
                  <th className="text-left px-6 py-3 font-medium">Progress</th>
                  <th className="text-left px-6 py-3 font-medium">Created</th>
                </tr>
              </thead>
              <tbody>
                {cases.map((c) => {
                  const approved = c.steps.filter((s) => s.approved).length;
                  return (
                    <tr key={c.id} className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors">
                      <td className="px-6 py-4">
                        <Link href={`/cases/${c.id}`} className="font-medium text-gray-100 hover:text-indigo-400 transition-colors">
                          {c.title}
                        </Link>
                        <div className="text-xs text-gray-500 mt-0.5">Reported by {c.reportedBy}</div>
                      </td>
                      <td className="px-6 py-4 text-gray-400">
                        {c.plant}<br/>
                        <span className="text-gray-500 text-xs">{c.product}</span>
                      </td>
                      <td className="px-6 py-4">
                        <span className={`font-medium ${PRIORITY_COLOR[c.priority] || "text-gray-400"}`}>
                          {c.priority}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <span className={`px-2 py-1 rounded-md text-xs font-medium border ${STATUS_COLOR[c.status] || "bg-gray-700 text-gray-400 border-gray-600"}`}>
                          {c.status}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2">
                          <div className="flex-1 h-1.5 bg-gray-800 rounded-full w-24">
                            <div
                              className="h-full bg-indigo-500 rounded-full transition-all"
                              style={{ width: `${(approved / 8) * 100}%` }}
                            />
                          </div>
                          <span className="text-xs text-gray-500">{approved}/8</span>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-gray-500 text-xs">
                        {new Date(c.createdAt).toLocaleDateString()}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </main>
    </div>
  );
}
