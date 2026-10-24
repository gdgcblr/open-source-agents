import { ArrowLeft, Bot, ChevronDown, ExternalLink, FileCode2, GitCommit, GitPullRequest, Lightbulb, ShieldAlert, Wrench } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { DimensionCompare, Meter, Sparkline } from "../components/charts";
import { Avatar, Card, Chip, Empty, SectionTitle, SeverityBadge, StatusIcon, VerdictBadge } from "../components/ui";
import { useIndex, useSubmission } from "../data";
import { LEVELS, SEVERITY, fileUrl, timeAgo } from "../lib/format";
import type { Claim, DimensionResult, Finding, Submission } from "../types";

function Hero({ s, repo }: { s: Submission; repo: string | null }) {
  const commit = s.head_sha && !s.id.startsWith("local") && repo ? `https://github.com/${repo}/commit/${s.head_sha}` : null;
  return (
    <Card className="p-5">
      <div className="flex flex-col gap-5 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0">
          <h1 className="break-words text-2xl font-semibold tracking-tight text-ink">{s.slug}</h1>
          <p className="mt-1 text-sm text-ink-2">{s.title}</p>
          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[13px] text-ink-2">
            <span className="inline-flex items-center gap-1.5"><Avatar src={s.author_avatar} name={s.author} size={18} />{s.author ?? "local folder"}</span>
            <span className="font-mono text-xs">{s.project_path}{s.extra_projects.length ? ` + ${s.extra_projects.join(", ")}` : ""}</span>
            <Chip>{s.state}</Chip>
            {s.url && <a href={s.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-accent-ink hover:underline"><GitPullRequest size={14} />PR #{s.number}</a>}
            {commit && <a href={commit} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-mono text-xs text-accent-ink hover:underline"><GitCommit size={14} />{s.head_sha.slice(0, 7)}</a>}
            <span className="text-muted">judged {timeAgo(s.judged_at)}</span>
          </div>
          <div className="mt-3 flex flex-wrap gap-1">
            {[...s.providers, ...s.frameworks].map((t) => <Chip key={t}>{t}</Chip>)}
            {Object.keys(s.languages).slice(0, 4).map((l) => <Chip key={l} title={`${s.languages[l]} lines`}>{l}</Chip>)}
          </div>
        </div>
        <div className="w-full shrink-0 md:w-60">
          <div className="flex items-baseline gap-1">
            <span className="text-5xl font-semibold leading-none text-ink">{s.overall}</span>
            <span className="text-muted">/100</span>
          </div>
          <div className="mt-3"><Meter value={s.overall} height={8} label="Overall score" /></div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <VerdictBadge verdict={s.verdict} size="lg" />
          </div>
          <p className="mt-2 text-xs text-muted">
            Confidence {s.confidence}% · {s.llm.used ? <>LLM: {s.llm.provider} ({s.llm.model})</> : s.llm.error ? "LLM review failed; static only" : "static analysis only"}
          </p>
        </div>
      </div>
      {s.gates.length > 0 && (
        <div className="mt-4 rounded-xl p-3 text-sm text-ink" style={{ background: "color-mix(in oklab, var(--critical) 12%, var(--surface))" }}>
          <p className="flex items-center gap-1.5 font-medium"><ShieldAlert size={16} style={{ color: "var(--critical)" }} />Blocked regardless of score</p>
          <ul className="mt-1 list-disc pl-6 text-ink-2">{s.gates.map((g) => <li key={g}>{g}</li>)}</ul>
        </div>
      )}
      {s.manipulation_suspected && (
        <div className="mt-3 rounded-xl p-3 text-sm text-ink" style={{ background: "color-mix(in oklab, var(--serious) 14%, var(--surface))" }}>
          <p className="flex items-center gap-1.5 font-medium"><Bot size={16} style={{ color: "var(--serious)" }} />Text aimed at AI judges was found and ignored</p>
          <p className="mt-0.5 text-ink-2">A fixed penalty applies. See the Security section for the exact lines.</p>
        </div>
      )}
    </Card>
  );
}

function Ladder({ s }: { s: Submission }) {
  return (
    <Card className="p-5">
      <SectionTitle title="AI maturity" hint="Where the project sits on the ladder, with the evidence that placed it there" />
      <ol className="space-y-1.5">
        {LEVELS.map((label, i) => {
          const reached = i <= s.ai_level;
          const here = i === s.ai_level;
          return (
            <li key={label} className={`flex items-center gap-3 rounded-lg px-2 py-1.5 ${here ? "bg-surface-2" : ""}`}>
              <span className="grid h-6 w-6 shrink-0 place-items-center rounded-md text-[11px] font-semibold"
                style={{ background: reached ? `var(--lvl-${i})` : "transparent", color: reached ? `var(--lvl-on-${i})` : "var(--ink)",
                  boxShadow: reached ? "none" : "inset 0 0 0 1px var(--axis)" }}>L{i}</span>
              <span className={`text-[13px] ${here ? "font-medium text-ink" : reached ? "text-ink-2" : "text-muted"}`}>
                {here ? s.ai_level_label : label}
              </span>
              {here && <span className="ml-auto text-[11px] text-muted">this project</span>}
            </li>
          );
        })}
      </ol>
      {s.ai_level_evidence.length > 0 && (
        <ul className="mt-3 space-y-1 border-t border-grid pt-3 text-[12.5px] text-ink-2">
          {s.ai_level_evidence.map((e) => <li key={e} className="font-mono text-[11.5px]">{e}</li>)}
        </ul>
      )}
    </Card>
  );
}

const CLAIM: Record<Claim["status"], { label: string; status: "pass" | "warn" | "fail" | "skip" }> = {
  implemented: { label: "Implemented", status: "pass" },
  partial: { label: "Partial", status: "warn" },
  missing: { label: "Missing", status: "fail" },
  unverified: { label: "Not visible in excerpts", status: "skip" },
};

function Claims({ claims }: { claims: Claim[] }) {
  if (!claims.length) return null;
  return (
    <Card className="p-5">
      <SectionTitle title="README claims vs. code" hint="Each advertised feature, checked against the code the reviewer saw" />
      <ul className="divide-y divide-grid">
        {claims.map((c) => (
          <li key={c.feature} className="flex gap-3 py-2">
            <StatusIcon status={CLAIM[c.status].status} />
            <div className="min-w-0">
              <p className="text-[13.5px] text-ink">{c.feature} <span className="text-xs text-muted">· {CLAIM[c.status].label}</span></p>
              {c.evidence && <p className="mt-0.5 break-words font-mono text-[11.5px] text-ink-2">{c.evidence}</p>}
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function FindingItem({ f, s, repo }: { f: Finding; s: Submission; repo: string | null }) {
  const href = fileUrl(repo, s.head_sha, s.project_path, f.file, f.line);
  const where = f.file ? `${f.file}${f.line ? `:${f.line}` : ""}` : null;
  return (
    <li className="py-3">
      <div className="flex flex-wrap items-center gap-2">
        <SeverityBadge severity={f.severity} />
        <span className="text-[13.5px] font-medium text-ink">{f.title}</span>
        {f.source === "llm" && <Chip title="Raised by the LLM reviewer; does not gate the merge">LLM</Chip>}
        {f.commit && <Chip title="Only present in an earlier commit">commit {f.commit}</Chip>}
      </div>
      {where && (href
        ? <a href={href} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1 break-all font-mono text-[11.5px] text-accent-ink hover:underline"><FileCode2 size={12} />{where}</a>
        : <p className="mt-1 break-all font-mono text-[11.5px] text-ink-2">{where}</p>)}
      {f.detail && <p className="mt-1 text-[13px] text-ink-2">{f.detail}</p>}
      {f.snippet && <pre className="mt-1.5 overflow-x-auto rounded-lg bg-surface-2 px-3 py-2 font-mono text-[11.5px] leading-relaxed text-ink-2">{f.snippet}</pre>}
      {f.fix && <p className="mt-1.5 flex gap-1.5 text-[13px] text-ink"><Wrench size={14} className="mt-0.5 shrink-0 text-muted" />{f.fix}</p>}
    </li>
  );
}

function DimensionSection({ d, s, repo, open }: { d: DimensionResult; s: Submission; repo: string | null; open: boolean }) {
  const findings = [...d.findings].sort((a, b) => SEVERITY[b.severity].rank - SEVERITY[a.severity].rank);
  const counts = { fail: d.checks.filter((c) => c.status === "fail").length, warn: d.checks.filter((c) => c.status === "warn").length };
  return (
    <details className="card group" open={open}>
      <summary className="flex cursor-pointer list-none items-center gap-3 p-4 [&::-webkit-details-marker]:hidden">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2">
            <span className="font-semibold text-ink">{d.label}</span>
            <span className="text-xs text-muted">weight {Math.round(d.weight * 100)}%</span>
          </div>
          <p className="mt-0.5 text-xs text-muted">
            {counts.fail} failed · {counts.warn} warning{counts.warn === 1 ? "" : "s"} · {findings.length} finding{findings.length === 1 ? "" : "s"}
            {d.llm_score != null && d.static_score != null && <> · static {d.static_score}, LLM {d.llm_score} (LLM weight {Math.round(d.llm_share * 100)}%)</>}
          </p>
        </div>
        <div className="hidden w-32 sm:block"><Meter value={d.score} label={d.label} /></div>
        <span className="tabular w-8 text-right text-lg font-semibold text-ink">{d.score ?? "–"}</span>
        <ChevronDown aria-hidden size={18} className="text-muted transition-transform group-open:rotate-180" />
      </summary>
      <div className="border-t border-grid px-4 pb-4 pt-3">
        <p className="text-[13px] text-ink-2">{d.purpose}</p>
        {d.llm_rationale && (
          <blockquote className="mt-2 border-l-2 border-axis pl-3 text-[13px] italic text-ink-2">{d.llm_rationale}</blockquote>
        )}
        <ul className="mt-3 space-y-1.5">
          {d.checks.map((c) => (
            <li key={c.id} className="flex gap-2.5">
              <StatusIcon status={c.status} />
              <div className="min-w-0">
                <p className="text-[13.5px] text-ink">{c.label}</p>
                {c.detail && <p className="break-words text-[12.5px] text-muted">{c.detail}</p>}
                {c.fix && c.status !== "pass" && <p className="text-[12.5px] text-ink-2">→ {c.fix}</p>}
              </div>
            </li>
          ))}
        </ul>
        {findings.length > 0 && (
          <ul className="mt-2 divide-y divide-grid border-t border-grid">
            {findings.slice(0, 25).map((f, i) => <FindingItem key={i} f={f} s={s} repo={repo} />)}
            {findings.length > 25 && <li className="py-2 text-xs text-muted">…and {findings.length - 25} more</li>}
          </ul>
        )}
      </div>
    </details>
  );
}

function Files({ s, repo }: { s: Submission; repo: string | null }) {
  const files = [...s.files].filter((f) => f.language !== "Other").sort((a, b) => b.findings - a.findings || b.lines - a.lines).slice(0, 14);
  const max = Math.max(1, ...files.map((f) => f.lines));
  return (
    <Card className="p-5">
      <SectionTitle title="Files" hint={`${s.files.length} files · ${s.loc.toLocaleString()} lines of code · sorted by findings`} />
      <ul className="space-y-1.5">
        {files.map((f) => {
          const href = fileUrl(repo, s.head_sha, s.project_path, f.path);
          return (
            <li key={f.path} className="grid grid-cols-[1fr_auto] items-center gap-3 text-[12.5px]">
              <div className="min-w-0">
                {href ? <a href={href} target="_blank" rel="noreferrer" className="block truncate font-mono text-[11.5px] text-ink-2 hover:text-accent-ink">{f.path}</a>
                  : <span className="block truncate font-mono text-[11.5px] text-ink-2">{f.path}</span>}
                <div className="mt-0.5 h-1 rounded-full bg-surface-2"><div className="h-1 rounded-full bg-axis" style={{ width: `${(f.lines / max) * 100}%` }} /></div>
              </div>
              <span className="tabular text-right text-muted">{f.lines} ln{f.findings ? <> · <b className="text-ink">{f.findings}</b> finding{f.findings === 1 ? "" : "s"}</> : ""}</span>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

export default function Detail() {
  const { id = "" } = useParams();
  const { data: s, error } = useSubmission(id);
  const { data: index } = useIndex();
  const repo = index?.repo ?? null;

  if (error) return <Empty title="Submission not found">{error}</Empty>;
  if (!s) return <p className="animate-pulse text-sm text-muted">Loading…</p>;

  const median = index?.insights.dimension_median ?? {};
  const weakest = [...s.dimensions].filter((d) => d.score != null).sort((a, b) => (a.score ?? 0) - (b.score ?? 0))[0];
  return (
    <div className="space-y-4">
      <Link to="/" className="inline-flex items-center gap-1 text-sm text-ink-2 hover:text-ink"><ArrowLeft size={15} />All submissions</Link>
      <Hero s={s} repo={repo} />

      <div className="grid gap-4 lg:grid-cols-5">
        <Card className="p-5 lg:col-span-3">
          <SectionTitle title="What to fix first" hint="Highest-impact changes, gating issues first" />
          {s.top_fixes.length ? (
            <ol className="space-y-2.5">
              {s.top_fixes.map((f, i) => (
                <li key={f} className="flex gap-3 text-[13.5px] text-ink">
                  <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-accent-wash text-[11px] font-semibold text-accent-ink">{i + 1}</span>
                  <span>{f}</span>
                </li>
              ))}
            </ol>
          ) : <p className="text-sm text-ink-2">Nothing pressing. Nice work.</p>}
          {s.summary && (
            <div className="mt-4 border-t border-grid pt-4">
              <p className="text-[13.5px] text-ink-2">{s.summary}</p>
              {s.strengths.length > 0 && (
                <ul className="mt-2 space-y-1">
                  {s.strengths.map((x) => <li key={x} className="flex gap-1.5 text-[13px] text-ink-2"><Lightbulb size={14} className="mt-0.5 shrink-0 text-muted" />{x}</li>)}
                </ul>
              )}
            </div>
          )}
          {s.history.length > 0 && (
            <div className="mt-4 border-t border-grid pt-4">
              <p className="mb-1 text-xs text-muted">Score across commits</p>
              <Sparkline points={[...s.history.map((h) => ({ label: h.sha.slice(0, 7), value: h.overall })),
                { label: s.head_sha.slice(0, 7), value: s.overall }]} />
            </div>
          )}
        </Card>
        <Card className="p-5 lg:col-span-2">
          <DimensionCompare rows={s.dimensions.map((d) => ({ key: d.key, label: d.label, score: d.score, median: median[d.key] ?? null, weight: d.weight }))} />
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-5">
        <div className="lg:col-span-3"><Claims claims={s.claims} /></div>
        <div className="lg:col-span-2"><Ladder s={s} /></div>
      </div>

      <div className="space-y-2">
        <h2 className="pt-2 text-[15px] font-semibold text-ink">All checks and findings</h2>
        {s.dimensions.map((d) => <DimensionSection key={d.key} d={d} s={s} repo={repo} open={d.key === weakest?.key || d.findings.some((f) => f.gate)} />)}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Files s={s} repo={repo} />
        <Card className="p-5">
          <SectionTitle title="Similar submissions" hint="README topic similarity and shared code blocks" />
          {s.similar.length ? (
            <ul className="space-y-2">
              {s.similar.map((x) => (
                <li key={x.id + x.kind} className="flex items-center justify-between gap-3 text-[13px]">
                  <Link to={`/pr/${x.id}`} className="min-w-0 truncate text-accent-ink hover:underline">{x.slug} <span className="text-muted">#{x.id}</span></Link>
                  <span className="tabular shrink-0 text-muted">{x.kind === "code" ? "shared code" : "similar idea"} {Math.round(x.score * 100)}%</span>
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-ink-2">Nothing similar yet.</p>}
          {s.url && (
            <a href={s.url} target="_blank" rel="noreferrer" className="mt-5 inline-flex items-center gap-1 text-sm text-accent-ink hover:underline">
              Open the pull request <ExternalLink size={13} />
            </a>
          )}
        </Card>
      </div>
    </div>
  );
}
