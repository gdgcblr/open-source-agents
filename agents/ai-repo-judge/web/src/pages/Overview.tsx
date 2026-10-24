import { GitPullRequest, Lightbulb, Search, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { DimensionMeters, Meter } from "../components/charts";
import { Avatar, Chip, Empty, StatTile, VerdictBadge } from "../components/ui";
import { useIndex } from "../data";
import { DIM_ORDER, DIM_SHORT, timeAgo } from "../lib/format";
import type { DimensionKey, SubmissionSummary, Verdict } from "../types";

const PAGE = 24;

type SortKey = "updated" | "overall" | "ai_level" | "number" | DimensionKey;

const SORTS: { key: SortKey; label: string }[] = [
  { key: "updated", label: "Recently updated" },
  { key: "overall", label: "Overall score" },
  ...DIM_ORDER.map((k) => ({ key: k as SortKey, label: `${DIM_SHORT[k]} score` })),
  { key: "ai_level", label: "AI maturity level" },
  { key: "number", label: "PR number" },
];

function sortValue(s: SubmissionSummary, key: SortKey): number {
  if (key === "updated") return Date.parse(s.updated_at ?? s.judged_at) || 0;
  if (key === "overall") return s.overall;
  if (key === "ai_level") return s.ai_level * 1000 + s.overall;
  if (key === "number") return s.number ?? 0;
  return s.scores[key] ?? -1;
}

function Select({ label, value, onChange, options }: {
  label: string; value: string; onChange: (v: string) => void; options: { value: string; label: string }[];
}) {
  return (
    <label className="flex items-center gap-1.5 text-[13px] text-muted">
      <span className="sr-only sm:not-sr-only">{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}
        className="rounded-lg bg-surface px-2 py-1.5 text-[13px] text-ink" style={{ boxShadow: "0 0 0 1px var(--ring)" }}>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </label>
  );
}

function SubmissionCard({ s }: { s: SubmissionSummary }) {
  const stack = [...s.providers, ...s.frameworks.filter((f) => !["CLI"].includes(f))];
  return (
    <Link to={`/pr/${s.id}`} className="card rise group flex min-w-0 flex-col gap-3 p-4 transition-shadow hover:shadow-md">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-1.5">
            <span className="min-w-0 truncate font-semibold text-ink group-hover:text-accent-ink">{s.slug}</span>
            {s.number && <span className="shrink-0 text-xs text-muted">#{s.number}</span>}
          </div>
          <p className="mt-0.5 line-clamp-1 text-[12.5px] text-ink-2" title={s.title}>{s.title}</p>
        </div>
        <VerdictBadge verdict={s.verdict} />
      </div>

      <div className="flex items-center gap-2 text-xs text-muted">
        <Avatar src={s.author_avatar} name={s.author} size={18} />
        <span className="min-w-0 truncate">{s.author ?? "local"}</span>
        <span aria-hidden>·</span>
        <span className="capitalize">{s.category === "unknown" ? "other" : s.category.replace(/s$/, "")}</span>
        <span aria-hidden>·</span>
        <span className="shrink-0">{s.state}</span>
        <span className="ml-auto shrink-0">{timeAgo(s.updated_at ?? s.judged_at)}</span>
      </div>

      <div className="flex items-end gap-3">
        <div className="shrink-0">
          <span className="text-3xl font-semibold leading-none text-ink">{s.overall}</span>
          <span className="text-sm text-muted">/100</span>
        </div>
        <div className="mb-1 flex-1">
          <Meter value={s.overall} label="Overall score" />
          <div className="mt-1 flex justify-between text-[11px] text-muted">
            <span>{s.llm_used ? "Static + LLM" : "Static only"}</span>
            <span title="Share of the rubric backed by all of its evidence sources">confidence {s.confidence}%</span>
          </div>
        </div>
      </div>

      <DimensionMeters scores={s.scores} order={DIM_ORDER} />

      <div className="flex flex-wrap gap-1">
        <Chip title={s.ai_level_label}><Sparkles aria-hidden size={11} className="mr-1" />L{s.ai_level} · {s.ai_level_label}</Chip>
        {stack.slice(0, 3).map((t) => <Chip key={t}>{t}</Chip>)}
        {stack.length > 3 && <Chip title={stack.slice(3).join(", ")}>+{stack.length - 3}</Chip>}
      </div>

      {s.top_fix && (
        <p className="mt-auto flex gap-1.5 border-t border-grid pt-2.5 text-[12.5px] leading-snug text-ink-2">
          <Lightbulb aria-hidden size={14} className="mt-0.5 shrink-0 text-muted" />
          <span className="line-clamp-2">{s.top_fix}</span>
        </p>
      )}
    </Link>
  );
}

export default function Overview() {
  const { data, error, loading } = useIndex();
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const cat = params.get("cat") ?? "all";
  const verdict = params.get("verdict") ?? "all";
  const stack = params.get("stack") ?? "all";
  const sort = (params.get("sort") ?? "updated") as SortKey;
  const [limit, setLimit] = useState(PAGE);
  useEffect(() => setLimit(PAGE), [q, cat, verdict, stack, sort]);
  const set = (key: string, value: string, fallback: string) => {
    const next = new URLSearchParams(params);
    if (value === fallback || !value) next.delete(key);
    else next.set(key, value);
    setParams(next, { replace: true });
  };

  const stacks = useMemo(() => {
    const c = new Map<string, number>();
    data?.submissions.forEach((s) => [...s.providers, ...s.frameworks].forEach((t) => c.set(t, (c.get(t) ?? 0) + 1)));
    return [...c.entries()].sort((a, b) => b[1] - a[1]).map(([t]) => t);
  }, [data]);

  const rows = useMemo(() => {
    if (!data) return [];
    const needle = q.trim().toLowerCase();
    return data.submissions
      .filter((s) => cat === "all" || s.category === cat)
      .filter((s) => verdict === "all" || s.verdict === verdict)
      .filter((s) => stack === "all" || s.providers.includes(stack) || s.frameworks.includes(stack))
      .filter((s) => !needle || [s.slug, s.title, s.author ?? "", ...s.frameworks, ...s.providers, `#${s.number}`]
        .some((v) => v.toLowerCase().includes(needle)))
      .sort((a, b) => sortValue(b, sort) - sortValue(a, sort));
  }, [data, q, cat, verdict, stack, sort]);

  if (error) return <Empty title="Couldn't load results">{error}. Run <code>judge run</code>, then reload.</Empty>;
  if (!data) return <p className={`text-sm text-muted ${loading ? "animate-pulse" : ""}`}>Loading submissions…</p>;

  const ins = data.insights;
  const ready = ins.by_verdict.ready ?? 0;
  const verdicts: Verdict[] = ["ready", "needs_changes", "blocked"];
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Submissions</h1>
        <p className="mt-1 max-w-2xl text-sm text-ink-2">
          Evidence-based feedback on every agent and tool submitted{data.repo ? <> to <b className="font-medium">{data.repo}</b></> : null}.
          Each project is scored on seven dimensions; open one to see the evidence and what to fix first.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatTile label="Submissions" value={ins.count}
          sub={`${ins.by_category.agents ?? 0} agents · ${ins.by_category.tools ?? 0} tools`} />
        <StatTile label="Median score" value={ins.median_overall} sub={`average ${ins.avg_overall}`} />
        <StatTile label="Ready to merge" value={ready} sub={`${ins.count ? Math.round((ready / ins.count) * 100) : 0}% of submissions`} />
        <StatTile label="Blocked" value={ins.by_verdict.blocked ?? 0}
          sub={`${ins.secrets_found} with live-looking keys`} />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <label className="relative min-w-[200px] flex-1">
          <Search aria-hidden size={15} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted" />
          <input value={q} onChange={(e) => set("q", e.target.value, "")} placeholder="Search name, author, framework…"
            aria-label="Search submissions"
            className="w-full rounded-lg bg-surface py-1.5 pl-8 pr-3 text-sm text-ink placeholder:text-muted"
            style={{ boxShadow: "0 0 0 1px var(--ring)" }} />
        </label>
        <div className="flex rounded-lg bg-surface p-0.5" style={{ boxShadow: "0 0 0 1px var(--ring)" }} role="group" aria-label="Category">
          {["all", "agents", "tools"].map((c) => (
            <button key={c} type="button" onClick={() => set("cat", c, "all")} aria-pressed={cat === c}
              className={`rounded-md px-2.5 py-1 text-[13px] capitalize ${cat === c ? "bg-surface-2 font-medium text-ink" : "text-ink-2"}`}>
              {c}
            </button>
          ))}
        </div>
        <Select label="Verdict" value={verdict} onChange={(v) => set("verdict", v, "all")}
          options={[{ value: "all", label: "All verdicts" }, ...verdicts.map((v) => ({
            value: v, label: `${v === "ready" ? "Ready" : v === "blocked" ? "Blocked" : "Needs changes"} (${ins.by_verdict[v] ?? 0})`,
          }))]} />
        <Select label="Stack" value={stack} onChange={(v) => set("stack", v, "all")}
          options={[{ value: "all", label: "Any stack" }, ...stacks.map((t) => ({ value: t, label: t }))]} />
        <Select label="Sort" value={sort} onChange={(v) => set("sort", v, "updated")}
          options={SORTS.map((s) => ({ value: s.key, label: s.label }))} />
      </div>

      {rows.length === 0 ? (
        <Empty title="No submissions match these filters" />
      ) : (
        <>
          <div className={`grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 ${loading ? "opacity-60" : ""}`}>
            {rows.slice(0, limit).map((s) => <SubmissionCard key={s.id} s={s} />)}
          </div>
          {rows.length > limit && (
            <div className="flex justify-center">
              <button type="button" onClick={() => setLimit((l) => l + PAGE)}
                className="card px-4 py-2 text-sm font-medium text-ink hover:bg-surface-2">
                Show {Math.min(PAGE, rows.length - limit)} more of {rows.length - limit}
              </button>
            </div>
          )}
        </>
      )}

      {data.errors.length > 0 && (
        <details className="text-sm text-ink-2">
          <summary className="cursor-pointer text-muted">{data.errors.length} pull request(s) skipped</summary>
          <ul className="mt-2 space-y-1">
            {data.errors.map((e) => (
              <li key={e.id} className="flex items-center gap-2">
                <GitPullRequest aria-hidden size={14} className="text-muted" />
                {e.url ? <a className="text-accent-ink hover:underline" href={e.url} target="_blank" rel="noreferrer">#{e.id}</a> : `#${e.id}`}
                <span>{e.title}</span><span className="text-muted">({e.error})</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
