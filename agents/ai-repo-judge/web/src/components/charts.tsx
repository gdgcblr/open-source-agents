// Small hand-built charts that follow the dataviz mark specs: thin marks, 4px rounded data-ends,
// 2px surface gaps, hairline solid grid, text in ink tokens (never the series colour), a hover/focus
// tooltip on every mark, and a table view for every chart.
import { type ReactNode, useId, useState } from "react";
import { DIM_SHORT, scoreTone } from "../lib/format";
import type { DimensionKey } from "../types";

// ---- tooltip ---------------------------------------------------------------------------------------
type Tip = { x: number; y: number; content: ReactNode } | null;

function useTip() {
  const [tip, setTip] = useState<Tip>(null);
  const bind = (content: ReactNode) => ({
    onMouseEnter: (e: React.MouseEvent) => setTip({ x: e.clientX, y: e.clientY, content }),
    onMouseMove: (e: React.MouseEvent) => setTip({ x: e.clientX, y: e.clientY, content }),
    onMouseLeave: () => setTip(null),
    onFocus: (e: React.FocusEvent) => {
      const r = (e.target as Element).getBoundingClientRect();
      setTip({ x: r.left + r.width / 2, y: r.top, content });
    },
    onBlur: () => setTip(null),
    tabIndex: 0,
  });
  const node = tip && (
    <div role="tooltip" className="pointer-events-none fixed z-50 max-w-64 rounded-lg bg-surface px-2.5 py-1.5 text-xs text-ink shadow-lg"
      style={{ left: tip.x + 12, top: tip.y + 12, boxShadow: "0 0 0 1px var(--ring), 0 6px 20px rgb(0 0 0 / .12)" }}>
      {tip.content}
    </div>
  );
  return { bind, node };
}

// ---- table twin ------------------------------------------------------------------------------------
export function ChartFrame({ title, hint, rows, columns, children }: {
  title: string; hint?: string; rows: (string | number)[][]; columns: string[]; children: ReactNode;
}) {
  const [table, setTable] = useState(false);
  const id = useId();
  return (
    <div>
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h3 id={id} className="text-[15px] font-semibold text-ink">{title}</h3>
          {hint && <p className="mt-0.5 text-[13px] text-muted">{hint}</p>}
        </div>
        <button type="button" onClick={() => setTable((t) => !t)}
          className="shrink-0 rounded-md px-2 py-1 text-xs text-ink-2 hover:bg-surface-2">
          {table ? "Show chart" : "Show table"}
        </button>
      </div>
      {table ? (
        <div className="overflow-x-auto">
          <table aria-labelledby={id} className="w-full text-left text-[13px]">
            <thead><tr className="text-muted">{columns.map((c) => <th key={c} className="py-1 pr-4 font-medium">{c}</th>)}</tr></thead>
            <tbody className="tabular">
              {rows.map((r, i) => (
                <tr key={i} className="border-t border-grid">{r.map((c, j) => <td key={j} className="py-1.5 pr-4 text-ink-2">{c}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : children}
    </div>
  );
}

// ---- meter ---------------------------------------------------------------------------------------
/** A ratio against 100. The fill carries severity; the track is a lighter step of the same hue. */
export function Meter({ value, height = 6, label }: { value: number | null; height?: number; label?: string }) {
  const color = scoreTone(value);
  return (
    <div role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={value ?? undefined} aria-label={label}
      className="w-full overflow-hidden rounded-full" style={{ height, background: `color-mix(in oklab, ${color} 16%, var(--surface))` }}>
      <div className="h-full rounded-full transition-[width] duration-500"
        style={{ width: `${Math.max(0, Math.min(100, value ?? 0))}%`, background: color }} />
    </div>
  );
}

/** Seven compact dimension meters for a card. Each carries its number, so colour is never alone. */
export function DimensionMeters({ scores, order }: { scores: Partial<Record<DimensionKey, number | null>>; order: DimensionKey[] }) {
  return (
    <div className="grid grid-cols-[auto_1fr_auto] items-center gap-x-2 gap-y-1">
      {order.map((k) => (
        <div key={k} className="contents">
          <span className="text-[11.5px] text-muted">{DIM_SHORT[k]}</span>
          <Meter value={scores[k] ?? null} height={4} label={DIM_SHORT[k]} />
          <span className="tabular w-6 text-right text-[11.5px] text-ink-2">{scores[k] ?? "–"}</span>
        </div>
      ))}
    </div>
  );
}

// ---- bullet comparison (this project vs cohort median) ---------------------------------------------
export function DimensionCompare({ rows }: { rows: { key: DimensionKey; label: string; score: number | null; median: number | null; weight: number }[] }) {
  const { bind, node } = useTip();
  return (
    <ChartFrame title="Score by dimension" hint="Bar = this submission · tick = median of all submissions"
      columns={["Dimension", "Weight", "Score", "Median"]}
      rows={rows.map((r) => [r.label, `${Math.round(r.weight * 100)}%`, r.score ?? "–", r.median ?? "–"])}>
      <div className="mb-2 flex items-center gap-4 text-xs text-ink-2">
        <span className="inline-flex items-center gap-1.5"><span className="h-2 w-3 rounded-sm bg-accent" />This submission</span>
        <span className="inline-flex items-center gap-1.5"><span className="h-3 w-0.5 bg-ink-2" />All-submission median</span>
      </div>
      <div className="space-y-2.5">
        {rows.map((r) => (
          <div key={r.key} className="grid grid-cols-[minmax(84px,128px)_1fr_auto] items-center gap-3">
            <span className="truncate text-[13px] text-ink-2" title={r.label}>{r.label}</span>
            <div className="relative h-5 rounded-md" style={{ background: "var(--surface-2)" }}
              {...bind(<span><b>{r.label}</b>: {r.score ?? "n/a"} · median {r.median ?? "n/a"} · weight {Math.round(r.weight * 100)}%</span>)}>
              <div className="absolute inset-y-1 left-0 rounded-r-[4px]"
                style={{ width: `${r.score ?? 0}%`, background: scoreTone(r.score) }} />
              {r.median != null && (
                <div className="absolute -top-0.5 -bottom-0.5 w-0.5 rounded-full bg-ink-2"
                  style={{ left: `calc(${r.median}% - 1px)`, boxShadow: "0 0 0 2px var(--surface)" }} />
              )}
            </div>
            <span className="tabular w-8 text-right text-[13px] font-medium text-ink">{r.score ?? "–"}</span>
          </div>
        ))}
      </div>
      {node}
    </ChartFrame>
  );
}

// ---- columns (histogram, ordinal levels) -----------------------------------------------------------
export function ColumnChart({ title, hint, data, colorFor, height = 160, xLabel }: {
  title: string; hint?: string; data: { label: string; value: number; tip?: string }[];
  colorFor?: (i: number) => string; height?: number; xLabel?: string;
}) {
  const { bind, node } = useTip();
  const max = Math.max(1, ...data.map((d) => d.value));
  const peak = data.reduce((best, d, i) => (d.value > data[best].value ? i : best), 0);
  const ticks = [0, Math.ceil(max / 2), max];
  return (
    <ChartFrame title={title} hint={hint} columns={[xLabel ?? "Bucket", "Count"]} rows={data.map((d) => [d.label, d.value])}>
      <div className="grid grid-cols-[auto_1fr] gap-2">
        <div className="tabular flex flex-col justify-between text-right text-[11px] text-muted" style={{ height }}>
          {[...ticks].reverse().map((t) => <span key={t} className="-translate-y-1/2 first:translate-y-0 last:translate-y-0">{t}</span>)}
        </div>
        <div>
          <div className="relative flex items-end gap-0.5 border-b border-axis" style={{ height }}>
            {ticks.slice(1).map((t) => (
              <div key={t} className="pointer-events-none absolute inset-x-0 border-t border-grid" style={{ bottom: `${(t / max) * 100}%` }} />
            ))}
            {data.map((d, i) => (
              <div key={d.label} className="relative flex h-full flex-1 items-end justify-center" {...bind(d.tip ?? `${d.label}: ${d.value}`)}>
                {i === peak && d.value > 0 && (
                  <span className="tabular absolute text-[11px] font-medium text-ink-2" style={{ bottom: `calc(${(d.value / max) * 100}% + 2px)` }}>{d.value}</span>
                )}
                <div className="w-full max-w-6 rounded-t-[4px]"
                  style={{ height: `${(d.value / max) * 100}%`, background: colorFor ? colorFor(i) : "var(--accent)", minHeight: d.value ? 2 : 0 }} />
              </div>
            ))}
          </div>
          <div className="mt-1 flex gap-0.5">
            {data.map((d) => <span key={d.label} className="tabular flex-1 truncate text-center text-[10.5px] text-muted">{d.label}</span>)}
          </div>
        </div>
      </div>
      {node}
    </ChartFrame>
  );
}

// ---- horizontal bar list -----------------------------------------------------------------------------
export function BarList({ title, hint, data, max: maxIn, unit = "" }: {
  title: string; hint?: string; data: { label: string; value: number }[]; max?: number; unit?: string;
}) {
  const { bind, node } = useTip();
  const max = maxIn ?? Math.max(1, ...data.map((d) => d.value));
  return (
    <ChartFrame title={title} hint={hint} columns={["Item", "Value"]} rows={data.map((d) => [d.label, `${d.value}${unit}`])}>
      {data.length === 0 ? <p className="text-sm text-muted">Nothing to show yet.</p> : (
        <div className="space-y-1.5">
          {data.map((d) => (
            <div key={d.label} className="grid grid-cols-[minmax(90px,150px)_1fr] items-center gap-3" {...bind(`${d.label}: ${d.value}${unit}`)}>
              <span className="truncate text-[13px] text-ink-2" title={d.label}>{d.label}</span>
              <div className="flex items-center gap-2">
                <div className="h-3.5 rounded-r-[4px] bg-accent" style={{ width: `${(d.value / max) * 100}%`, minWidth: 2 }} />
                <span className="tabular text-[12px] text-ink-2">{d.value}{unit}</span>
              </div>
            </div>
          ))}
        </div>
      )}
      {node}
    </ChartFrame>
  );
}

// ---- stacked fail/warn bars --------------------------------------------------------------------------
export function IssueBars({ data, total }: { data: { label: string; fail: number; warn: number }[]; total: number }) {
  const { bind, node } = useTip();
  const max = Math.max(1, total);
  return (
    <ChartFrame title="Most common issues" hint={`Checks that failed or warned, across ${total} submissions`}
      columns={["Check", "Failed", "Warned"]} rows={data.map((d) => [d.label, d.fail, d.warn])}>
      <div className="mb-2 flex items-center gap-4 text-xs text-ink-2">
        <span className="inline-flex items-center gap-1.5"><span className="h-2 w-3 rounded-sm bg-critical" />Failed</span>
        <span className="inline-flex items-center gap-1.5"><span className="h-2 w-3 rounded-sm bg-warning" />Warned</span>
      </div>
      <div className="space-y-2">
        {data.map((d) => (
          <div key={d.label} {...bind(<span><b>{d.label}</b><br />{d.fail} failed · {d.warn} warned</span>)}>
            <div className="mb-0.5 flex justify-between gap-3 text-[12.5px]">
              <span className="truncate text-ink-2">{d.label}</span>
              <span className="tabular shrink-0 text-muted">{d.fail + d.warn}/{total}</span>
            </div>
            <div className="flex h-2.5 gap-0.5">
              {d.fail > 0 && <div className="rounded-l-[3px] bg-critical" style={{ width: `${(d.fail / max) * 100}%` }} />}
              {d.warn > 0 && <div className={`bg-warning ${d.fail ? "" : "rounded-l-[3px]"} rounded-r-[4px]`} style={{ width: `${(d.warn / max) * 100}%` }} />}
            </div>
          </div>
        ))}
      </div>
      {node}
    </ChartFrame>
  );
}

// ---- sparkline (score history) -----------------------------------------------------------------------
export function Sparkline({ points, width = 220, height = 48 }: { points: { label: string; value: number }[]; width?: number; height?: number }) {
  const { bind, node } = useTip();
  if (points.length < 2) return null;
  const pad = 6;
  const vals = points.map((p) => p.value);
  const lo = Math.max(0, Math.min(...vals) - 10);
  const hi = Math.min(100, Math.max(...vals) + 10);
  const xs = (i: number) => pad + (i / (points.length - 1)) * (width - pad * 2);
  const ys = (v: number) => height - pad - ((v - lo) / Math.max(1, hi - lo)) * (height - pad * 2);
  const delta = points[points.length - 1].value - points[0].value;
  const d = points.map((p, i) => `${i ? "L" : "M"}${xs(i).toFixed(1)},${ys(p.value).toFixed(1)}`).join(" ");
  const last = points[points.length - 1];
  return (
    <div className="flex items-center gap-3">
      <svg width={width} height={height} role="img" aria-label={`Score history: ${points.map((p) => p.value).join(", ")}`}>
        {lo < 70 && hi > 70 && <line x1={pad} x2={width - pad} y1={ys(70)} y2={ys(70)} stroke="var(--grid)" strokeWidth={1} />}
        <path d={d} fill="none" stroke="var(--accent)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        {points.map((p, i) => (
          <circle key={i} cx={xs(i)} cy={ys(p.value)} r={i === points.length - 1 ? 4 : 3} fill="var(--accent)"
            stroke="var(--surface)" strokeWidth={2} {...bind(`${p.label}: ${p.value}`)} />
        ))}
      </svg>
      <span className="text-sm text-ink-2"><b className="text-ink">{last.value}</b> now
        <span className="block text-xs text-muted">{delta > 0 ? "+" : ""}{delta} since {points[0].label}</span></span>
      {node}
    </div>
  );
}
