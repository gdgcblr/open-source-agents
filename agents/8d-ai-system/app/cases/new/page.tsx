"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Layers, Sparkles } from "lucide-react";

export default function NewCase() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    title: "",
    plant: "",
    product: "",
    reportedBy: "",
    priority: "Medium",
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    const res = await fetch("/api/cases", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(form),
    });
    const data = await res.json();
    router.push(`/cases/${data.id}`);
  };

  return (
    <div className="min-h-screen bg-gray-950">
      <header className="border-b border-gray-800 bg-gray-900/80 backdrop-blur sticky top-0 z-10">
        <div className="max-w-3xl mx-auto px-6 py-4 flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center">
            <Layers size={18} />
          </div>
          <h1 className="font-bold text-lg">8D AI System</h1>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-6 py-10">
        <Link href="/" className="flex items-center gap-2 text-gray-400 hover:text-gray-200 text-sm mb-8 transition-colors">
          <ArrowLeft size={16} />
          Back to Dashboard
        </Link>

        <div className="mb-8">
          <div className="flex items-center gap-2 mb-2">
            <Sparkles size={18} className="text-indigo-400" />
            <h2 className="text-2xl font-bold">New 8D Problem Report</h2>
          </div>
          <p className="text-gray-400 text-sm">
            Provide the basic problem information. AI will guide you through each D-step with intelligent suggestions.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="bg-gray-900 border border-gray-800 rounded-xl p-8 space-y-6">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Problem Title <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              required
              placeholder="e.g., Dimensional non-conformance on Shaft Assembly Part #4521"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-indigo-500 transition-colors"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Plant / Location <span className="text-red-400">*</span>
              </label>
              <input
                type="text"
                required
                placeholder="e.g., Plant A - Dharuhera"
                value={form.plant}
                onChange={(e) => setForm({ ...form, plant: e.target.value })}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-indigo-500 transition-colors"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Product / Part <span className="text-red-400">*</span>
              </label>
              <input
                type="text"
                required
                placeholder="e.g., Engine Head Gasket"
                value={form.product}
                onChange={(e) => setForm({ ...form, product: e.target.value })}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-indigo-500 transition-colors"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Reported By <span className="text-red-400">*</span>
              </label>
              <input
                type="text"
                required
                placeholder="e.g., Rajesh Kumar"
                value={form.reportedBy}
                onChange={(e) => setForm({ ...form, reportedBy: e.target.value })}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-indigo-500 transition-colors"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Priority</label>
              <select
                value={form.priority}
                onChange={(e) => setForm({ ...form, priority: e.target.value })}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-sm text-gray-100 focus:outline-none focus:border-indigo-500 transition-colors"
              >
                <option>Critical</option>
                <option>High</option>
                <option>Medium</option>
                <option>Low</option>
              </select>
            </div>
          </div>

          <div className="bg-indigo-500/10 border border-indigo-500/20 rounded-lg p-4">
            <div className="flex items-start gap-3">
              <Sparkles size={16} className="text-indigo-400 mt-0.5 flex-shrink-0" />
              <div className="text-sm text-indigo-300">
                <strong>AI-Guided Process:</strong> After creating the case, our AI will automatically suggest team members (D1),
                generate a structured problem description (D2), propose containment actions (D3), perform root cause analysis
                with a Fishbone diagram (D4), and guide you through D5–D8. You approve every step.
              </div>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-white py-3 rounded-lg font-medium text-sm transition-colors"
          >
            {loading ? "Creating Case..." : "Create 8D Case & Start AI Analysis →"}
          </button>
        </form>
      </main>
    </div>
  );
}
