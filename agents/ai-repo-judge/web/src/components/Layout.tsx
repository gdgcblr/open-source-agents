import { GitPullRequest, Monitor, Moon, Sun } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { useIndex } from "../data";
import { timeAgo } from "../lib/format";

type Theme = "system" | "light" | "dark";

function readTheme(): Theme {
  try {
    const t = localStorage.getItem("theme");
    return t === "light" || t === "dark" ? t : "system";
  } catch {
    return "system";
  }
}

function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(readTheme);
  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") delete root.dataset.theme;
    else root.dataset.theme = theme;
    try {
      if (theme === "system") localStorage.removeItem("theme");
      else localStorage.setItem("theme", theme);
    } catch {
      /* storage unavailable (private mode): the choice lasts for this page view */
    }
  }, [theme]);
  const next: Record<Theme, Theme> = { system: "light", light: "dark", dark: "system" };
  const Icon = theme === "light" ? Sun : theme === "dark" ? Moon : Monitor;
  return (
    <button type="button" onClick={() => setTheme(next[theme])} title={`Theme: ${theme} (click to change)`}
      aria-label={`Theme: ${theme}`} className="rounded-lg p-2 text-ink-2 hover:bg-surface-2">
      <Icon size={18} />
    </button>
  );
}

const link = ({ isActive }: { isActive: boolean }) =>
  `rounded-lg px-3 py-1.5 text-sm whitespace-nowrap ${isActive ? "bg-surface-2 font-medium text-ink" : "text-ink-2 hover:text-ink"}`;

export default function Layout({ children }: { children: ReactNode }) {
  const { data } = useIndex();
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 border-b border-grid backdrop-blur" style={{ background: "color-mix(in oklab, var(--page) 85%, transparent)" }}>
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-2.5">
          <NavLink to="/" className="flex shrink-0 items-center gap-2">
            <span className="grid h-7 w-7 place-items-center rounded-lg bg-accent text-white">
              <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden><path d="M5 13l4 4 10-11" stroke="currentColor" strokeWidth="3" fill="none" strokeLinecap="round" strokeLinejoin="round" /></svg>
            </span>
            <span className="hidden font-semibold text-ink sm:inline">AI Repo Judge</span>
          </NavLink>
          <nav className="-mx-1 flex min-w-0 flex-1 gap-1 overflow-x-auto px-1">
            <NavLink to="/" end className={link}>Submissions</NavLink>
            <NavLink to="/insights" className={link}>Insights</NavLink>
            <NavLink to="/methodology" className={link}><span className="sm:hidden">Method</span><span className="hidden sm:inline">How it works</span></NavLink>
          </nav>
          {data?.repo && (
            <a href={`https://github.com/${data.repo}/pulls`} target="_blank" rel="noreferrer" title={data.repo}
              className="hidden items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm text-ink-2 hover:bg-surface-2 md:inline-flex">
              <GitPullRequest size={16} /> {data.repo}
            </a>
          )}
          <ThemeToggle />
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
      <footer className="mx-auto max-w-6xl px-4 pb-10 text-xs leading-relaxed text-muted">
        <p>
          Unofficial, automated feedback for contributors and maintainers. It is not the event's official judging.
          Scores combine static analysis with an LLM review (capped at{" "}
          {data ? Math.round(data.rubric.reduce((a, r) => a + r.weight * r.llm_share, 0) * 100) : 31}% of the total); every finding
          links to its evidence. {data && <>Last judged {timeAgo(data.generated_at)} · rules {data.judge_version} · prompt {data.prompt_version}.</>}
        </p>
      </footer>
    </div>
  );
}
