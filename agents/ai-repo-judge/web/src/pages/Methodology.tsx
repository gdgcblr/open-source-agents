import { Card, Empty, SectionTitle } from "../components/ui";
import { useIndex } from "../data";

const DETAILS: Record<string, string> = {
  compliance: "Folder location and kebab-case name, required files (README, .gitignore, .env.example, manifest), changes confined to the submission's own folders, PR checklist and title, no committed virtualenvs or caches, unique name.",
  security: "Secrets in files and in every commit of the PR (redacted here), committed .env/credential files, dangerous calls (eval/exec, shell=True, unsafe deserialisation, SQL formatting, verify=False), AI-specific risks (model output reaching code execution, unbounded agent loops, API keys in browser code), dependency pinning, known vulnerabilities via OSV.dev, and text aimed at AI judges.",
  quality: "Tests and their size relative to the code, how complexity and function length are spread, type hints, docstrings, swallowed exceptions, logging, modularity, and ruff lint results with a fixed rule set so every submission is held to the same bar.",
  functionality: "Every import declared in the manifest, env vars documented, README run command points at real files, code parses, install steps match the manifest, no machine-specific paths. The LLM checks each README claim against the code.",
  ai_native: "Maturity ladder (prompt → structured output → tool use → agent loop → multi-agent/RAG/MCP) with file:line evidence, robust model calls (retries, timeouts, limits, error handling), portability (model from env, mock mode, local models), AI-behaviour tests, observability and guardrails.",
  docs: "Coverage of the template's sections, leftover template placeholders, a genuine example input and output, architecture, limitations and security notes. The LLM rates clarity and how real the example looks.",
  innovation: "Mostly the LLM's view of novelty and usefulness, plus README similarity to other submissions and shared-code detection.",
};

export default function Methodology() {
  const { data, error } = useIndex();
  if (error) return <Empty title="Couldn't load results">{error}</Empty>;
  if (!data) return <p className="animate-pulse text-sm text-muted">Loading…</p>;
  const llmTotal = Math.round(data.rubric.reduce((a, r) => a + r.weight * r.llm_share, 0) * 100);
  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">How it works</h1>
        <p className="mt-1 text-sm text-ink-2">
          The judge reads each pull request's code without running it. Plain code checks produce most of the score,
          and an LLM review adds judgement on the things code can't measure. Every finding links to its evidence.
        </p>
      </div>

      <Card className="p-5">
        <SectionTitle title="The rubric" hint={`Seven weighted dimensions. The LLM can move at most ${llmTotal}% of the total.`} />
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[13px]">
            <thead className="text-muted"><tr><th className="py-1.5 pr-3 font-medium">Dimension</th><th className="py-1.5 pr-3 font-medium">Weight</th><th className="py-1.5 pr-3 font-medium">LLM share</th><th className="py-1.5 font-medium">What it measures</th></tr></thead>
            <tbody>
              {data.rubric.map((r) => (
                <tr key={r.key} className="border-t border-grid align-top">
                  <td className="py-2 pr-3 font-medium text-ink">{r.label}</td>
                  <td className="tabular py-2 pr-3 text-ink-2">{Math.round(r.weight * 100)}%</td>
                  <td className="tabular py-2 pr-3 text-ink-2">{Math.round(r.llm_share * 100)}%</td>
                  <td className="py-2 text-ink-2"><p className="text-ink">{r.purpose}</p><p className="mt-1 text-[12.5px] text-muted">{DETAILS[r.key]}</p></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card className="p-5 text-[13.5px] leading-relaxed text-ink-2">
        <SectionTitle title="Verdicts" />
        <ul className="list-disc space-y-1.5 pl-5">
          <li><b className="text-ink">Blocked</b>, whatever the score, when a live-looking API key appears in code or config (including in an earlier commit of the PR), or when the PR changes files outside its own new folder(s). These mirror the repository's own rules.</li>
          <li><b className="text-ink">Ready to merge</b> when the overall score is at least {data.thresholds.ready} and no high or critical findings come from static analysis.</li>
          <li><b className="text-ink">Needs changes</b> otherwise. Each project page lists the top three fixes.</li>
        </ul>
      </Card>

      <Card className="p-5 text-[13.5px] leading-relaxed text-ink-2">
        <SectionTitle title="Keeping the AI reviewer honest" />
        <ul className="list-disc space-y-1.5 pl-5">
          <li>Submission content goes to the model as clearly delimited, untrusted data. Text that addresses graders or asks for a score is flagged, ignored, and costs {data.thresholds.manipulation_penalty} points. Quoted examples and test data (common in security tools) don't count.</li>
          <li>The model never sets the score. It returns 1–5 ratings against written anchors at temperature 0; code turns them into points under fixed caps, and it cannot create blocking findings.</li>
          <li>Reviews are blind: the author's name is not sent. "Implemented" claims need a code citation; features outside the excerpts are marked "not visible" and don't count either way.</li>
          <li><b className="text-ink">Confidence</b> shows how much of the rubric was backed by every evidence source it was designed for (for example, it drops when the LLM review didn't run).</li>
        </ul>
      </Card>

      <Card className="p-5 text-[13.5px] leading-relaxed text-ink-2">
        <SectionTitle title="Freshness and cost" />
        <p>Each PR is judged once per commit. Results are stored and reused until the author pushes again or the rules change, so the dashboard never re-evaluates on page load. Comparisons with other submissions (similarity, medians, name clashes) are recomputed on every run, because a new PR can change how unique an older one looks.</p>
      </Card>

      <Card className="p-5 text-[13.5px] leading-relaxed text-ink-2">
        <SectionTitle title="Limits" />
        <ul className="list-disc space-y-1.5 pl-5">
          <li>Code is analysed, never executed, so runtime bugs can slip through. Python gets the deepest analysis; Go, JavaScript and TypeScript get pattern-based checks.</li>
          <li>Secrets in docs or tests can't be told apart from realistic fakes; they are flagged for the author to confirm rather than blocking.</li>
          <li>LLM ratings vary a little between models. The provider and model are shown on every project page.</li>
          <li>This is unofficial feedback, not the event's judging.</li>
        </ul>
      </Card>
    </div>
  );
}
