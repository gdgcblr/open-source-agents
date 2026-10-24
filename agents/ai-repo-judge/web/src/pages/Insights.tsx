import { Link } from "react-router-dom";
import { BarList, ColumnChart, IssueBars } from "../components/charts";
import { Card, Empty, StatTile, VerdictBadge } from "../components/ui";
import { useIndex } from "../data";
import { DIM_ORDER, LEVELS } from "../lib/format";
import type { Verdict } from "../types";

export default function Insights() {
  const { data, error } = useIndex();
  if (error) return <Empty title="Couldn't load results">{error}</Empty>;
  if (!data) return <p className="animate-pulse text-sm text-muted">Loading…</p>;
  const ins = data.insights;
  const label = Object.fromEntries(data.rubric.map((r) => [r.key, r.label]));
  const idToSlug = Object.fromEntries(data.submissions.map((s) => [s.id, s.slug]));
  const verdicts: Verdict[] = ["ready", "needs_changes", "blocked"];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Insights</h1>
        <p className="mt-1 max-w-2xl text-sm text-ink-2">
          What the whole set of submissions looks like: where people do well, and the gaps most of them share.
          Useful for organisers planning workshops and for contributors checking their work against common pitfalls.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatTile label="Submissions judged" value={ins.count} sub={`${data.errors.length} PR(s) skipped`} />
        <StatTile label="Median overall" value={ins.median_overall} sub={`average ${ins.avg_overall}`} />
        <StatTile label="Attempts to sway AI judges" value={ins.manipulation_attempts} sub="flagged and penalised" />
        <StatTile label="LLM tokens used" value={ins.llm_tokens >= 1000 ? `${(ins.llm_tokens / 1000).toFixed(1)}K` : ins.llm_tokens}
          sub="reviews are cached per commit" />
      </div>

      <Card className="p-5">
        <h3 className="mb-3 text-[15px] font-semibold text-ink">Verdicts</h3>
        <div className="flex flex-wrap gap-6">
          {verdicts.map((v) => (
            <Link key={v} to={`/?verdict=${v}`} className="flex items-center gap-3 rounded-lg hover:opacity-80">
              <span className="text-3xl font-semibold text-ink">{ins.by_verdict[v] ?? 0}</span>
              <VerdictBadge verdict={v} />
            </Link>
          ))}
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-5">
          <ColumnChart title="Score distribution" hint="Number of submissions per 10-point band" xLabel="Score band"
            data={ins.histogram.map((h) => ({ label: h.bucket.split("-")[0], value: h.count, tip: `${h.bucket}: ${h.count} submission(s)` }))} />
        </Card>
        <Card className="p-5">
          <BarList title="Median score by dimension" hint="Where the median submission is strong or weak" max={100}
            data={DIM_ORDER.map((k) => ({ label: label[k] ?? k, value: ins.dimension_median[k] ?? 0 }))} />
        </Card>
        <Card className="p-5">
          <ColumnChart title="AI maturity" hint="L0 no AI · L1 prompt wrapper · L2 structured · L3 tool use · L4 agent loop · L5 multi-agent/RAG/MCP"
            xLabel="Level" colorFor={(i) => `var(--lvl-${i})`}
            data={ins.ai_levels.map((l) => ({ label: `L${l.level}`, value: l.count, tip: `L${l.level} ${LEVELS[l.level]}: ${l.count}` }))} />
        </Card>
        <Card className="p-5">
          <IssueBars total={ins.count} data={ins.common_issues.slice(0, 8).map((i) => ({ label: i.label, fail: i.fail, warn: i.warn }))} />
        </Card>
        <Card className="p-5">
          <BarList title="Model providers" hint="Submissions using each provider" data={ins.providers.slice(0, 8).map((p) => ({ label: p.name, value: p.count }))} />
        </Card>
        <Card className="p-5">
          <BarList title="Frameworks" hint="Agent frameworks and app stacks detected" data={ins.frameworks.slice(0, 8).map((p) => ({ label: p.name, value: p.count }))} />
        </Card>
      </div>

      <Card className="p-5">
        <h3 className="text-[15px] font-semibold text-ink">Similar ideas</h3>
        <p className="mb-3 mt-0.5 text-[13px] text-muted">Submissions whose READMEs describe closely related projects. Worth a look for collaboration, or for differentiating.</p>
        {ins.clusters.length ? (
          <ul className="space-y-2">
            {ins.clusters.map((c, i) => (
              <li key={i} className="flex flex-wrap gap-1.5">
                {c.members.map((id) => (
                  <Link key={id} to={`/pr/${id}`} className="rounded-md bg-surface-2 px-2 py-0.5 text-[12.5px] text-ink-2 hover:text-accent-ink">
                    {idToSlug[id] ?? id} <span className="text-muted">#{id}</span>
                  </Link>
                ))}
              </li>
            ))}
          </ul>
        ) : <p className="text-sm text-ink-2">No clusters of near-identical ideas.</p>}
      </Card>
    </div>
  );
}
