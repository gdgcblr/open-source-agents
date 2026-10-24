import { AlertOctagon, AlertTriangle, CheckCircle2, CircleDashed, CircleSlash, Info, ShieldAlert, XCircle } from "lucide-react";
import type { ReactNode } from "react";
import { SEVERITY, VERDICT } from "../lib/format";
import type { Severity, Status, Verdict } from "../types";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`card ${className}`}>{children}</section>;
}

export function SectionTitle({ title, hint, right }: { title: string; hint?: string; right?: ReactNode }) {
  return (
    <div className="mb-3 flex items-end justify-between gap-3">
      <div>
        <h2 className="text-[15px] font-semibold text-ink">{title}</h2>
        {hint && <p className="mt-0.5 text-[13px] text-muted">{hint}</p>}
      </div>
      {right}
    </div>
  );
}

const VERDICT_ICON: Record<Verdict, typeof CheckCircle2> = {
  ready: CheckCircle2,
  needs_changes: AlertTriangle,
  blocked: AlertOctagon,
};

/** Status is never colour alone: icon + label, on a light tint of the status hue. */
export function VerdictBadge({ verdict, size = "sm" }: { verdict: Verdict; size?: "sm" | "lg" }) {
  const v = VERDICT[verdict];
  const Icon = VERDICT_ICON[verdict];
  const lg = size === "lg";
  return (
    <span
      title={v.hint}
      className={`inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full font-medium text-ink ${lg ? "px-3 py-1 text-sm" : "px-2 py-0.5 text-xs"}`}
      style={{ background: `color-mix(in oklab, ${v.color} 16%, var(--surface))` }}
    >
      <Icon aria-hidden size={lg ? 16 : 13} style={{ color: v.color }} strokeWidth={2.4} />
      {v.label}
    </span>
  );
}

const SEV_ICON: Record<Severity, typeof Info> = {
  critical: ShieldAlert,
  high: AlertOctagon,
  medium: AlertTriangle,
  low: Info,
  info: Info,
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  const s = SEVERITY[severity];
  const Icon = SEV_ICON[severity];
  return (
    <span
      className="inline-flex shrink-0 items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-ink"
      style={{ background: `color-mix(in oklab, ${s.color} 18%, var(--surface))` }}
    >
      <Icon aria-hidden size={12} style={{ color: severity === "low" || severity === "info" ? "var(--ink-2)" : s.color }} />
      {s.label}
    </span>
  );
}

const STATUS: Record<Status, { Icon: typeof Info; color: string; label: string }> = {
  pass: { Icon: CheckCircle2, color: "var(--good)", label: "Pass" },
  warn: { Icon: AlertTriangle, color: "var(--warning)", label: "Warning" },
  fail: { Icon: XCircle, color: "var(--critical)", label: "Fail" },
  skip: { Icon: CircleSlash, color: "var(--muted)", label: "Not applicable" },
};

export function StatusIcon({ status }: { status: Status }) {
  const s = STATUS[status];
  return <s.Icon aria-label={s.label} size={16} style={{ color: s.color }} className="shrink-0" strokeWidth={2.2} />;
}

export function Chip({ children, title }: { children: ReactNode; title?: string }) {
  return (
    <span title={title} className="inline-flex items-center rounded-md bg-surface-2 px-1.5 py-0.5 text-[11.5px] text-ink-2">
      {children}
    </span>
  );
}

export function StatTile({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <Card className="px-4 py-3">
      <div className="text-[12.5px] text-muted">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-ink">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-ink-2">{sub}</div>}
    </Card>
  );
}

export function Avatar({ src, name, size = 20 }: { src: string | null; name: string | null; size?: number }) {
  if (!src) return <CircleDashed aria-hidden size={size} className="text-muted" />;
  return <img src={`${src}${src.includes("?") ? "&" : "?"}s=${size * 2}`} alt="" width={size} height={size}
    loading="lazy" className="rounded-full" style={{ boxShadow: "0 0 0 1px var(--ring)" }} title={name ?? ""} />;
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <Card className="px-6 py-12 text-center">
      <p className="font-medium text-ink">{title}</p>
      {children && <div className="mt-2 text-sm text-ink-2">{children}</div>}
    </Card>
  );
}
