import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from "react";
import { Model } from "survey-core";
import { Survey } from "survey-react-ui";

type JsonObject = Record<string, unknown>;
type InputTab = "pdf" | "json";
type AppView = "library" | "create" | "editor";
type LibraryTab = "active" | "drafts";
type PreviewMode = "form" | "pdf";

type ConversionResult = {
  survey: JsonObject;
  warnings: string[];
  model: string;
  attempts: number;
};

const STORAGE_KEY = "pdf-to-surveyjs-draft-v1";

function isObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function toConversionResult(value: unknown): ConversionResult {
  if (!isObject(value)) throw new Error("JSON must contain an object.");
  const survey = isObject(value.survey) ? value.survey : value;
  if (!Array.isArray(survey.elements) && !Array.isArray(survey.pages)) {
    throw new Error("Survey JSON needs an elements or pages array.");
  }
  return {
    survey,
    warnings: Array.isArray(value.warnings)
      ? value.warnings.filter((item): item is string => typeof item === "string")
      : [],
    model: typeof value.model === "string" ? value.model : "Imported JSON",
    attempts: typeof value.attempts === "number" ? value.attempts : 0,
  };
}

function downloadJson(filename: string, value: unknown) {
  const blob = new Blob([JSON.stringify(value, null, 2) + "\n"], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export default function App() {
  const [view, setView] = useState<AppView>("library");
  const [libraryTab, setLibraryTab] = useState<LibraryTab>("drafts");
  const [activeTab, setActiveTab] = useState<InputTab>("pdf");
  const [file, setFile] = useState<File | null>(null);
  const [pdfPreviewUrl, setPdfPreviewUrl] = useState<string | null>(null);
  const [previewMode, setPreviewMode] = useState<PreviewMode>("form");
  const [result, setResult] = useState<ConversionResult | null>(null);
  const [jsonText, setJsonText] = useState("");
  const [jsonError, setJsonError] = useState("");
  const [answers, setAnswers] = useState<JsonObject | null>(null);
  const [error, setError] = useState("");
  const [savedMessage, setSavedMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [retryInvalid, setRetryInvalid] = useState(true);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (!saved) return;
    try {
      const restored = toConversionResult(JSON.parse(saved));
      setResult(restored);
      setJsonText(JSON.stringify(restored.survey, null, 2));
      setSavedMessage("Restored from this browser");
    } catch {
      window.localStorage.removeItem(STORAGE_KEY);
    }
  }, []);

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "auto" });
  }, [view]);

  useEffect(
    () => () => {
      if (pdfPreviewUrl) URL.revokeObjectURL(pdfPreviewUrl);
    },
    [pdfPreviewUrl],
  );

  useEffect(() => {
    if (!loading) return;
    setElapsedSeconds(0);
    const timer = window.setInterval(
      () => setElapsedSeconds((seconds) => seconds + 1),
      1000,
    );
    return () => window.clearInterval(timer);
  }, [loading]);

  const progressMessage =
    elapsedSeconds < 5
      ? "Extracting text and preparing the request…"
      : elapsedSeconds < 30
        ? "Gemma is identifying questions and choices…"
        : elapsedSeconds < 60
          ? "Still working—detailed PDFs can take a little longer."
          : "Gemma is still processing the form. Keep this tab open.";

  const surveyModel = useMemo(() => {
    if (!result) return null;
    const model = new Model(result.survey);
    model.showCompletedPage = false;
    model.onComplete.add((sender) => setAnswers({ ...sender.data }));
    return model;
  }, [result]);

  function openResult(nextResult: ConversionResult) {
    setResult(nextResult);
    setJsonText(JSON.stringify(nextResult.survey, null, 2));
    setJsonError("");
    setAnswers(null);
    setSavedMessage("");
    setView("editor");
  }

  function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0] ?? null;
    setFile(selected);
    setPdfPreviewUrl(selected ? URL.createObjectURL(selected) : null);
    setPreviewMode("form");
    setError("");
  }

  async function importJson(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0];
    if (!selected) return;
    setError("");
    setPdfPreviewUrl(null);
    setPreviewMode("form");
    try {
      openResult(toConversionResult(JSON.parse(await selected.text())));
    } catch (importError) {
      setError(importError instanceof Error ? importError.message : "Invalid JSON file.");
    } finally {
      event.target.value = "";
    }
  }

  function editJson(value: string) {
    setJsonText(value);
    setSavedMessage("");
    try {
      const next = toConversionResult(JSON.parse(value));
      setResult((current) => ({
        ...next,
        warnings: current?.warnings ?? next.warnings,
        model: current?.model ?? next.model,
        attempts: current?.attempts ?? next.attempts,
      }));
      setJsonError("");
    } catch (editError) {
      setJsonError(editError instanceof Error ? editError.message : "Invalid JSON.");
    }
  }

  function saveLocally() {
    if (!result || jsonError) return;
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(result));
    setSavedMessage("Saved in this browser");
  }

  const surveyTitle =
    result && typeof result.survey.title === "string" && result.survey.title.trim()
      ? result.survey.title
      : "Untitled survey";

  async function convert(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    setLoading(true);
    setError("");
    setAnswers(null);

    const body = new FormData();
    body.append("pdf", file);
    body.append("maxRetries", retryInvalid ? "1" : "0");
    try {
      const response = await fetch("/api/convert", { method: "POST", body });
      const payload = (await response.json()) as ConversionResult | { error: string };
      if (!response.ok || "error" in payload) {
        throw new Error("error" in payload ? payload.error : "Conversion failed.");
      }
      openResult(payload);
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Conversion failed.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app-frame">
      <div className="tricolor-ribbon" aria-hidden="true" />
      <aside className="gov-utility-bar" aria-label="Official government portal notice">
        <div className="emblem-text">
          <span className="emblem-flag" aria-hidden="true">🇮🇳</span>
          <span>भारत सरकार | Government of India</span>
        </div>
        <div className="gov-utility-links" aria-label="Portal assistance">
          <span>Screen Reader Access</span>
          <span>Skip to Main Content</span>
          <span>Helpdesk</span>
        </div>
      </aside>

      <header className="topbar">
        <button className="brand" onClick={() => setView("library")} aria-label="National Form Digitization Portal home">
          <div className="brand-crest" aria-hidden="true">🏛️</div>
          <div className="brand-text">
            <strong>National Form Digitization Portal</strong>
            <span>राष्ट्रीय प्रपत्र डिजिटलीकरण | Digital India Initiative <span className="brand-tag">GovForms AI</span></span>
          </div>
        </button>
        <nav aria-label="Primary navigation">
          <button className={view === "library" ? "nav-link current" : "nav-link"} onClick={() => setView("library")}>Forms Directory</button>
          <button className="primary small" onClick={() => setView("create")}>+ Digitize Form</button>
        </nav>
      </header>

      {view === "library" && (
        <main className="page library-page">
          <section className="page-heading">
            <div>
              <p className="eyebrow">Public Services & Scheme Digitization</p>
              <h1>National Scheme & Service Forms</h1>
              <p>Automated conversion of official government PDF forms into accessible, valid SurveyJS digital services.</p>
            </div>
            <button className="primary" onClick={() => setView("create")}>+ Digitize New Form</button>
          </section>

          <section className="summary-grid" aria-label="Form summary">
            <article><span>Published Forms</span><strong>0</strong><small>Active citizen services</small></article>
            <article><span>Draft Forms</span><strong>{result ? 1 : 0}</strong><small>Saved in official workbench</small></article>
            <article><span>Citizen Submissions</span><strong>{answers ? 1 : 0}</strong><small>Captured during testing</small></article>
          </section>

          <section className="forms-card">
            <div className="forms-toolbar">
              <div className="library-tabs" role="tablist" aria-label="Form status">
                <button role="tab" aria-selected={libraryTab === "active"} className={libraryTab === "active" ? "active" : ""} onClick={() => setLibraryTab("active")}>Published Schemes</button>
                <button role="tab" aria-selected={libraryTab === "drafts"} className={libraryTab === "drafts" ? "active" : ""} onClick={() => setLibraryTab("drafts")}>Drafts & Revisions {result ? <span>1</span> : null}</button>
              </div>
              <span className="local-note">Secured locally in administrative console</span>
            </div>

            {libraryTab === "drafts" && result ? (
              <div className="forms-table" role="table" aria-label="Draft forms">
                <div className="table-head" role="row"><span>Scheme / Form Title</span><span>Engine & Model</span><span>Status</span><span aria-hidden="true" /></div>
                <div className="form-row" role="row">
                  <div className="form-name"><span className="form-icon">{surveyTitle.charAt(0).toUpperCase()}</span><div><strong>{surveyTitle}</strong><small>Converted via Google ADK + Gemma</small></div></div>
                  <span>{result.model}</span>
                  <span><i className="status-dot" />Verified Draft</span>
                  <button className="text-button" onClick={() => setView("editor")}>Open Workbench <span aria-hidden="true">›</span></button>
                </div>
              </div>
            ) : (
              <div className="empty-state">
                <span className="empty-symbol">{libraryTab === "active" ? "✓" : "+"}</span>
                <h2>{libraryTab === "active" ? "No published services yet" : "Start form digitization"}</h2>
                <p>{libraryTab === "active" ? "Forms published to national citizen schemes will appear here." : "Upload an official departmental PDF form or import a SurveyJS schema."}</p>
                {libraryTab === "drafts" && <button className="primary" onClick={() => setView("create")}>Digitize Form</button>}
              </div>
            )}
          </section>
        </main>
      )}

      {view === "create" && (
        <main className="page create-page">
          <button className="back-button" onClick={() => setView("library")}>‹ Back to Directory</button>
          <header className="create-heading">
            <p className="eyebrow">Form Intake & Processing</p>
            <h1>Digitize Departmental Form</h1>
            <p>Upload a departmental PDF to generate a standardized SurveyJS schema using Gemma and Google ADK.</p>
          </header>

          <div className="source-tabs" role="tablist" aria-label="Survey source">
            <button role="tab" aria-selected={activeTab === "pdf"} className={activeTab === "pdf" ? "active" : ""} onClick={() => { setActiveTab("pdf"); setError(""); }}>Official PDF Document</button>
            <button role="tab" aria-selected={activeTab === "json"} className={activeTab === "json" ? "active" : ""} onClick={() => { setActiveTab("json"); setError(""); }}>Existing SurveyJS Schema</button>
          </div>

          {activeTab === "pdf" ? (
            <section className="source-card" aria-labelledby="upload-heading">
              <div className="source-copy"><span className="source-icon">PDF</span><div><h2 id="upload-heading">Extract & Digitize from PDF</h2><p>Gemma analyzes sections, labels, inputs, and validation rules with automated self-healing.</p></div></div>
              <form onSubmit={convert} className="upload-form">
                <label className="file-picker"><span>{file ? file.name : "Select departmental PDF file"}</span><input type="file" accept="application/pdf,.pdf" onChange={chooseFile} /></label>
                <button className="primary" type="submit" disabled={!file || loading}>{loading ? `Digitizing… ${elapsedSeconds}s` : "Start Digitization"}</button>
                <label className="retry-option"><input type="checkbox" checked={retryInvalid} disabled={loading} onChange={(event) => setRetryInvalid(event.target.checked)} />Bounded self-healing retry on validation failure</label>
              </form>
              {loading && <div className="generation-status" role="status" aria-live="polite"><span className="spinner" aria-hidden="true" /><div><strong>Processing Government Document</strong><p>{progressMessage}</p></div></div>}
              {error && <p className="error" role="alert">{error}</p>}
            </section>
          ) : (
            <section className="source-card" aria-labelledby="json-heading">
              <div className="source-copy"><span className="source-icon braces">{'{ }'}</span><div><h2 id="json-heading">Import Standardized Schema</h2><p>Load a verified SurveyJS JSON definition to preview, edit, or test interactively.</p></div></div>
              <label className="primary file-action">Upload Schema JSON<input type="file" accept="application/json,.json" onChange={importJson} /></label>
              {error && <p className="error" role="alert">{error}</p>}
            </section>
          )}
        </main>
      )}

      {view === "editor" && result && surveyModel && (
        <main className="editor-page">
          <header className="editor-topbar">
            <div><button className="back-button" onClick={() => setView("library")}>‹ Forms Directory</button><div><strong>{surveyTitle}</strong><span>{savedMessage || "Administrative Draft · Not yet published"}</span></div></div>
            <div className="editor-actions"><button className="secondary" onClick={() => downloadJson("survey.json", result.survey)}>Export Schema (JSON)</button><button className="primary" disabled={Boolean(jsonError)} onClick={saveLocally}>Save Official Draft</button></div>
          </header>

          {result.warnings.length > 0 && <details className="warnings"><summary>{result.warnings.length} verification notice{result.warnings.length === 1 ? "" : "s"}</summary><ul>{result.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></details>}

          <section className="workspace" aria-label="Survey editor">
            <div className="preview surface">
              <div className="section-heading">
                <div><p className="step">Citizen Experience</p><h2>{previewMode === "form" ? "Interactive Form Preview" : "Source Document"}</h2></div>
                {pdfPreviewUrl ? (
                  <div className="preview-switch" role="tablist" aria-label="Preview type">
                    <button role="tab" aria-selected={previewMode === "form"} className={previewMode === "form" ? "active" : ""} onClick={() => setPreviewMode("form")}>Interactive Form</button>
                    <button role="tab" aria-selected={previewMode === "pdf"} className={previewMode === "pdf" ? "active" : ""} onClick={() => setPreviewMode("pdf")}>Original Document</button>
                  </div>
                ) : <span className="preview-badge">Live Verification</span>}
              </div>
              {previewMode === "pdf" && pdfPreviewUrl ? (
                <iframe className="pdf-preview" src={pdfPreviewUrl} title="Uploaded source PDF" />
              ) : (
                <Survey model={surveyModel} />
              )}
            </div>
            <div className="json-editor surface"><div className="section-heading"><div><p className="step">Specification</p><h2>SurveyJS Schema JSON</h2></div><span className={jsonError ? "code-state invalid" : "code-state"}>{jsonError ? "Schema Error" : "Schema Valid"}</span></div><textarea aria-label="Survey JSON editor" spellCheck={false} value={jsonText} onChange={(event) => editJson(event.target.value)} /><p className={jsonError ? "editor-status invalid" : "editor-status"}>{jsonError || "Interactive form synchronizes in real-time"}</p></div>
          </section>

          {answers && <section className="answers"><div><strong>Sample Citizen Response Captured</strong><span>Validated against SurveyJS runtime schema. Not stored on remote servers.</span></div><button className="secondary" onClick={() => downloadJson("response.json", answers)}>Download Response JSON</button></section>}
        </main>
      )}

      <footer className="gov-footer">
        <div className="gov-footer-content">
          <div>
            <strong>National Form Digitization Portal</strong>
            <p>Designed and developed for Digital India initiatives using Google Agent Development Kit (ADK) & Gemma.</p>
          </div>
          <div>
            <p>© {new Date().getFullYear()} Government of India. All rights reserved.</p>
            <p>Built for automated public service delivery & accessible e-governance.</p>
          </div>
        </div>
      </footer>
    </div>
  );
}
