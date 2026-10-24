import { useEffect, useRef, useState } from "react";
import {
  Aperture,
  ArrowDownToLine,
  ArrowUpRight,
  Fingerprint,
  Images,
  ShieldCheck,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import { Button, ButtonLink } from "./components/motion/button/base";
import { Input } from "./components/motion/input";
import { TodoList } from "./components/agents/todo-list";
import { PromptInput } from "./components/agents/prompt-input";
import { MessageBubble } from "./components/agents/message-bubble";

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "X-Curator-Request": "local", ...options.headers },
  });
  if (!response.ok) {
    let detail;
    try {
      detail = (await response.json()).detail;
    } catch {
      /* Non-JSON server response. */
    }
    throw Error(
      typeof detail === "string"
        ? detail
        : `Request failed (${response.status}). Check your inputs and try again.`,
    );
  }
  return response.json();
}
const thumb = (photo) => `/api/photos/${photo.id}/thumb?v=2`;
const tabs = [
  ["gallery", Images, "Gallery"],
  ["upload", Upload, "Add photos"],
  ["find", Fingerprint, "Find my photos"],
  ["review", Sparkles, "AI review"],
];
const Field = (props) => (
  <Input
    {...props}
    classNames={{ field: "field-shell", label: "field-label" }}
  />
);

export function FaceBoxes({ faces = [] }) {
  return (
    <div className="face-boxes" aria-hidden="true">
      {faces
        .filter(
          (face) =>
            Array.isArray(face.box) &&
            face.box.length === 4 &&
            face.box.every((v) => Number.isFinite(v) && v >= 0 && v <= 1),
        )
        .map((face, index) => (
          <span
            key={index}
            className={face.ambiguous ? "face-box ambiguous" : "face-box"}
            style={{
              left: `${face.box[0] * 100}%`,
              top: `${face.box[1] * 100}%`,
              width: `${face.box[2] * 100}%`,
              height: `${face.box[3] * 100}%`,
            }}
            title={
              face.ambiguous
                ? "Ambiguous possible match"
                : "Possible face match"
            }
          />
        ))}
    </div>
  );
}

export function PhotoCard({ photo, onSelect }) {
  return (
    <button
      className="photo"
      onClick={() => onSelect(photo)}
      aria-label={`Open ${photo.filename}`}
    >
      <div className="photo-frame">
        <img
          loading="lazy"
          decoding="async"
          src={thumb(photo)}
          alt={photo.filename}
          width={photo.width}
          height={photo.height}
        />
        <FaceBoxes faces={photo.matched_faces || photo.detected_faces || []} />
        {!!photo.picked && (
          <span className="pick-badge">
            <Sparkles size={12} /> AI pick
          </span>
        )}
        <span className="open-photo">
          <ArrowUpRight size={17} />
        </span>
      </div>
      <span className="photo-title">{photo.filename}</span>
      <span className="photo-credit">
        {photo.photographer}
        {photo.similarity != null ? " · possible match" : ""}
      </span>
    </button>
  );
}

export function PhotoDetails({ photo, close, notify, organizer = true }) {
  const dialog = useRef(null);
  const [watermark, setWatermark] = useState("");
  const [metadata, setMetadata] = useState(true);
  const [captionCopied, setCaptionCopied] = useState(false);
  useEffect(() => {
    const element = dialog.current,
      previous = document.activeElement,
      overflow = document.body.style.overflow;
    element.showModal();
    document.body.style.overflow = "hidden";
    return () => {
      element.close();
      document.body.style.overflow = overflow;
      previous?.focus();
    };
  }, []);
  const result = photo.assessment;
  async function share() {
    try {
      const response = await fetch(`/api/photos/${photo.id}/preview?v=2`);
      if (!response.ok) throw Error("Could not load preview.");
      const file = new File([await response.blob()], "event-moment.webp", {
        type: "image/webp",
      });
      if (navigator.canShare?.({ files: [file] }))
        await navigator.share({
          files: [file],
          text: result.caption || "",
          title: "Event moment",
        });
      else
        notify(
          "Photo sharing is unavailable in this browser. Download the original and copy the caption.",
        );
    } catch (error) {
      if (error.name !== "AbortError") notify(error.message, true);
    }
  }
  return (
    <dialog
      ref={dialog}
      onCancel={close}
      onClose={close}
      className="photo-dialog"
      aria-labelledby="photo-title"
    >
      <div className="detail-toolbar">
        <span>PHOTO DETAILS</span>
        <Button
          variant="ghost"
          onClick={close}
          aria-label="Close photo details"
        >
          <X size={18} /> Close
        </Button>
      </div>
      <div className="detail-layout">
        <div className="detail-image">
          <div className="matched-image">
            <img
              src={`/api/photos/${photo.id}/preview?v=2`}
              alt={photo.filename}
            />
            <FaceBoxes
              faces={photo.matched_faces || photo.detected_faces || []}
            />
          </div>
          <span>
            High-quality optimized preview · untouched original available below
          </span>
        </div>
        <div className="detail-copy">
          <span className="eyebrow">
            {photo.picked ? "IN YOUR SHORTLIST" : "EVENT PHOTO"}
          </span>
          <h2 id="photo-title">{photo.filename}</h2>
          <p>
            Photo by {photo.photographer} · {photo.role}
          </p>
          {photo.search_reason && (
            <p className="search-evidence">{photo.search_reason}</p>
          )}
          {photo.matched_faces?.length > 0 && (
            <p className="fine">
              Dotted boxes mark possible matches. Amber means ambiguous; review
              manually.
            </p>
          )}
          <div className="assessment">
            {!photo.picked && result.score != null && (
              <p className="fine">
                Outside the current shortlist. Selection considers AI rank and
                visual diversity; the original stays available.
              </p>
            )}
            <h3>
              {result.score != null
                ? `AI score ${result.score}/10`
                : "Awaiting AI review"}
            </h3>
            <p>
              {result.reason ||
                "This photo stays available. Technical hints never remove it from AI review."}
            </p>
            <div className="criteria">
              {["moment", "composition", "expressions"]
                .filter((key) => result[key] != null)
                .map((key) => (
                  <span key={key}>
                    {key} <strong>{result[key]}/10</strong>
                  </span>
                ))}
            </div>
          </div>
          {photo.flags.length > 0 && (
            <div className="technical">
              <h3>Technical hints</h3>
              {photo.flags.map((flag) => (
                <p key={flag}>{flag}</p>
              ))}
              <small>Advisory only. AI reviews these frames too.</small>
            </div>
          )}
          <label className="native-label">
            Suggested caption
            <textarea
              readOnly
              rows={3}
              value={result.caption || ""}
              placeholder="A caption appears after AI review."
            />
          </label>
          <div className="actions">
            <Button
              variant="outline"
              disabled={!result.caption}
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(result.caption);
                  setCaptionCopied(true);
                } catch {
                  notify("Select the caption and copy it manually.");
                }
              }}
            >
              {captionCopied ? "Copied" : "Copy caption"}
            </Button>
            <Button variant="ghost" onClick={share}>
              Share preview <ArrowUpRight size={14} />
            </Button>
          </div>
          <ButtonLink
            className="download-original"
            href={`/api/photos/${photo.id}/original`}
            download
          >
            <ArrowDownToLine size={16} /> Download original
          </ButtonLink>
          {organizer && (
            <details>
              <summary>Watermark & attribution export</summary>
              <Field
                label="Optional watermark"
                value={watermark}
                onChange={setWatermark}
                maxLength={120}
                placeholder="© Photographer / event"
              />
              <label className="check">
                <input
                  type="checkbox"
                  checked={metadata}
                  onChange={(e) => setMetadata(e.target.checked)}
                />{" "}
                Add photographer credit to JPEG metadata
              </label>
              <a
                className="text-link"
                href={`/api/photos/${photo.id}/export?watermark=${encodeURIComponent(watermark)}&metadata=${metadata}`}
                download
              >
                Download JPEG copy <ArrowUpRight size={14} />
              </a>
              <p className="fine">
                Exports leave originals untouched and strip inherited GPS. RAF
                exports use the embedded JPEG.
              </p>
            </details>
          )}
        </div>
      </div>
    </dialog>
  );
}

export default function App({ initialRole } = {}) {
  const organizer =
    (initialRole ||
      (typeof window !== "undefined"
        ? window.location.pathname
        : "/attendee")) === "/organizer";
  const [state, setState] = useState({
    count: 0,
    picked: 0,
    job: {
      running: false,
      phase: "ready",
      total: 0,
      reviewed: 0,
      tokens: 0,
      cache_hits: 0,
    },
  });
  const [runtime, setRuntime] = useState(null);
  const [photos, setPhotos] = useState([]);
  const [mode, setMode] = useState("all");
  const [result, setResult] = useState(null);
  const [faceResults, setFaceResults] = useState(null);
  const [selected, setSelected] = useState(null);
  const [notice, setNotice] = useState(null);
  const [busy, setBusy] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [showFind, setShowFind] = useState(false);
  const [findMode, setFindMode] = useState("event");
  const [pair, setPair] = useState(null);
  const [prompt, setPrompt] = useState("");
  const [activeRequest, setActiveRequest] = useState("");
  const [next, setNext] = useState(0);
  const [more, setMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [top, setTop] = useState("15");
  const priorJob = useRef(false);
  const sequence = useRef(0);
  const pairUrls = useRef([]);
  const notify = (text, error = false) => setNotice({ text, error });
  async function gallery(reset = true) {
    const seq = ++sequence.current;
    if (mode === "results") {
      setPhotos(result?.photos || []);
      setMore(false);
      setLoading(false);
      return;
    }
    if (mode === "faces") {
      setPhotos(faceResults || []);
      setMore(false);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const data = await api(
        `/api/photos?offset=${reset ? 0 : next}&limit=48&best=${mode === "best"}`,
      );
      if (seq !== sequence.current) return;
      setPhotos((old) => (reset ? data.photos : [...old, ...data.photos]));
      setNext(data.next_offset);
      setMore(data.photos.length === 48);
    } catch (error) {
      notify(error.message, true);
    } finally {
      if (seq === sequence.current) setLoading(false);
    }
  }
  useEffect(() => {
    gallery();
  }, [mode, result, faceResults]);
  useEffect(() => {
    let active = true;
    async function refresh() {
      try {
        const data = await api("/api/state");
        if (!active) return;
        setState(data);
        if (priorJob.current && !data.job.running) {
          if (data.job.error) notify(data.job.error, true);
          if (data.job.kind === "agent") {
            const response = await api("/api/agent");
            if (!active) return;
            if (!data.job.error) {
              setResult(response.result);
              setMode("results");
            }
          } else await gallery();
        }
        priorJob.current = data.job.running;
      } catch (error) {
        if (active) notify(error.message, true);
      }
    }
    refresh();
    const timer = setInterval(refresh, 1200);
    api("/api/runtime")
      .then((data) => {
        if (active) setRuntime(data);
      })
      .catch((error) => {
        if (active) notify(error.message, true);
      });
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [mode]);
  useEffect(
    () => () => pairUrls.current.forEach((url) => URL.revokeObjectURL(url)),
    [],
  );

  async function work(action) {
    setBusy(true);
    setNotice(null);
    try {
      await action();
    } catch (error) {
      notify(error.message, true);
    } finally {
      setBusy(false);
    }
  }
  async function ask(query) {
    if (!query.trim()) return;
    await work(async () => {
      await api("/api/agent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      });
      priorJob.current = true;
      setActiveRequest(query.trim());
      setResult(null);
      setMode("all");
      setPrompt("");
      setState((s) => ({
        ...s,
        job: {
          ...s.job,
          running: true,
          kind: "agent",
          phase: "Planning",
          total: 0,
          reviewed: 0,
          error: "",
          trace: [],
          agent_step: 0,
          current_tool: "",
        },
      }));
    });
  }
  async function importDirectory(event) {
    event.preventDefault();
    const form = event.currentTarget;
    await work(async () => {
      const data = Object.fromEntries(new FormData(form));
      data.permission = form.elements.permission.checked;
      const response = await api("/api/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      priorJob.current = true;
      setShowImport(false);
      setMode("all");
      setState((s) => ({
        ...s,
        job: {
          ...s.job,
          running: true,
          kind: "import",
          phase: "Reading directory",
          total: response.total,
          reviewed: 0,
          error: "",
        },
      }));
    });
  }
  async function find(event) {
    event.preventDefault();
    const form = event.currentTarget;
    await work(async () => {
      const data = new FormData(form);
      const files = data.getAll("files").filter((f) => f.size);
      if (files.length > 10 || files.some((f) => f.size > 10 * 1024 * 1024))
        throw Error("Use up to 10 reference photos, under 10 MB each.");
      const response = await api("/api/match", { method: "POST", body: data });
      if (response.mode === "pair") {
        pairUrls.current.forEach((url) => URL.revokeObjectURL(url));
        pairUrls.current = files.map((file) => URL.createObjectURL(file));
        setPair({ ...response, urls: [...pairUrls.current] });
      } else {
        setFaceResults(response.photos);
        setMode("faces");
        setShowFind(false);
        setPair(null);
      }
      form.reset();
      notify(response.note);
    });
  }
  const job = state.job;
  const agentBusy = job.running && job.kind === "agent";
  const tasks =
    job.kind === "agent"
      ? [
          {
            id: "plan",
            title: "Choose the right tool",
            status:
              job.agent_step > 1 || job.current_tool
                ? "completed"
                : job.running
                  ? "in-progress"
                  : "completed",
          },
          {
            id: "look",
            title: job.current_tool
              ? job.current_tool.replaceAll("_", " ")
              : "Inspect event photos",
            status:
              job.trace?.length || !job.running
                ? "completed"
                : job.current_tool
                  ? "in-progress"
                  : "pending",
            detail: job.total ? `${job.reviewed}/${job.total}` : undefined,
          },
          {
            id: "reply",
            title: "Return matching photos",
            status: job.running
              ? "pending"
              : job.error
                ? "cancelled"
                : "completed",
          },
        ]
      : [
          {
            id: "read",
            title:
              job.kind === "import"
                ? "Read photo directory"
                : "Read event photos",
            status: job.total ? "completed" : "pending",
          },
          {
            id: "process",
            title:
              job.kind === "import"
                ? "Import originals & prepare previews"
                : "Review photos with local AI",
            status: job.running
              ? "in-progress"
              : job.error
                ? "cancelled"
                : "completed",
            detail: job.total ? `${job.reviewed}/${job.total}` : undefined,
          },
          {
            id: "ready",
            title: "Ready to browse",
            status: job.running
              ? "pending"
              : job.error
                ? "cancelled"
                : "completed",
          },
        ];
  return (
    <div className="app-shell photo-first">
      <header className="app-header">
        <a className="wordmark" href={organizer ? "/organizer" : "/attendee"}>
          <Aperture size={24} />
          <span>
            AfterClick
            <small>{organizer ? "ORGANIZER STUDIO" : "EVENT GALLERY"}</small>
          </span>
        </a>
        <div className="header-actions">
          <span className="local-status">
            <span /> Local
          </span>
          <a
            className="switch-view"
            href={organizer ? "/attendee" : "/organizer"}
          >
            {organizer ? "Attendee view" : "Organizer view"}{" "}
            <ArrowUpRight size={13} />
          </a>
        </div>
      </header>
      <main>
        <div className="studio-heading">
          <div>
            <h1>{organizer ? "Your event, in focus." : "You were there."}</h1>
            <p>
              {state.count} photos{organizer ? ` · ${state.picked} picks` : ""}
            </p>
          </div>
          <div className="actions">
            {organizer ? (
              <>
                <Button
                  variant="outline"
                  onClick={() => setShowImport((v) => !v)}
                  disabled={job.running}
                >
                  <Upload size={15} /> Import folder
                </Button>
                <Button variant="ghost" onClick={() => setShowFind((v) => !v)}>
                  <Fingerprint size={15} /> Face search
                </Button>
              </>
            ) : (
              <Button onClick={() => setShowFind((v) => !v)}>
                <Fingerprint size={15} /> Find my photos
              </Button>
            )}
          </div>
        </div>
        {notice && (
          <div
            className={`notice ${notice.error ? "error" : ""}`}
            role={notice.error ? "alert" : "status"}
          >
            <span>{notice.text}</span>
            <button
              aria-label="Dismiss message"
              onClick={() => setNotice(null)}
            >
              <X size={16} />
            </button>
          </div>
        )}
        {organizer && (showImport || state.count === 0) && (
          <section className="import-strip">
            <form onSubmit={importDirectory}>
              <Field
                label="Photo directory on this laptop"
                name="directory"
                placeholder="/Users/you/Pictures/Event"
                required
              />
              <Field
                label="Photo credit"
                name="photographer"
                placeholder="Photographer / team"
                maxLength={100}
                required
              />
              <label className="check">
                <input name="permission" type="checkbox" required />I have
                permission to import these photos.
              </label>
              <Button type="submit" disabled={busy || job.running}>
                Import photos <ArrowUpRight size={15} />
              </Button>
            </form>
          </section>
        )}
        {showFind && (
          <section className="find-strip">
            <form onSubmit={find}>
              <div className="fields">
                <label className="native-label">
                  Mode
                  <select
                    name="mode"
                    value={findMode}
                    onChange={(e) => {
                      setFindMode(e.target.value);
                      setPair(null);
                    }}
                  >
                    <option value="event">Find in event</option>
                    <option value="pair">
                      Compare two photos · one to one
                    </option>
                  </select>
                </label>
                {findMode === "event" ? (
                  <label className="native-label">
                    Search for
                    <select name="team">
                      <option value="false">Me</option>
                      {organizer && (
                        <option value="true">Anyone in my team</option>
                      )}
                    </select>
                  </label>
                ) : (
                  <input name="team" type="hidden" value="false" />
                )}
              </div>
              <label className="native-label">
                {findMode === "pair"
                  ? "Reference · one clear face"
                  : "Reference selfie"}
                <input
                  type="file"
                  name="files"
                  accept="image/jpeg,image/png,image/webp"
                  multiple={findMode === "event" && organizer}
                  required
                />
              </label>
              {findMode === "pair" && (
                <label className="native-label">
                  Comparison photo · one clear face
                  <input
                    type="file"
                    name="files"
                    accept="image/jpeg,image/png,image/webp"
                    required
                  />
                </label>
              )}
              <label className="check">
                <input name="consent" type="checkbox" value="true" required />I
                consent and have permission from everyone in these references.
              </label>
              <details>
                <summary>Matching sensitivity</summary>
                <Field
                  label="Cosine threshold · higher is stricter"
                  name="threshold"
                  type="number"
                  min="0.3"
                  max="0.9"
                  step="0.01"
                  defaultValue="0.45"
                />
              </details>
              <div className="actions">
                <Button
                  type="submit"
                  disabled={busy || !runtime?.face_models_ready}
                >
                  {busy
                    ? "Matching locally…"
                    : findMode === "pair"
                      ? "Compare faces"
                      : "Find possible matches"}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  disabled={busy}
                  onClick={() =>
                    work(async () => {
                      await api("/api/face-index", { method: "DELETE" });
                      setFaceResults(null);
                      setMode("all");
                      pairUrls.current.forEach((url) =>
                        URL.revokeObjectURL(url),
                      );
                      pairUrls.current = [];
                      setPair(null);
                      notify("Face index and comparison previews cleared.");
                    })
                  }
                >
                  Clear face data
                </Button>
              </div>
            </form>
            {pair && (
              <div className="pair-result">
                <h3>
                  {pair.matched
                    ? "Possible match"
                    : "No match at this threshold"}
                </h3>
                <p>
                  Cosine similarity {pair.similarity} · not an identity
                  probability
                </p>
                <div className="pair-photos">
                  {pair.urls.map((url, index) => (
                    <div key={url} className="matched-image">
                      <img
                        src={url}
                        alt={index ? "Comparison photo" : "Reference photo"}
                      />
                      {index === 1 && pair.matched && (
                        <FaceBoxes faces={[{ box: pair.target_box }]} />
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>
        )}
        <div className={organizer ? "studio-layout" : "attendee-layout"}>
          <section className="photo-workspace">
            <div className="workspace-tools">
              <div className="filter-row">
                <button
                  className={mode === "all" ? "filter active" : "filter"}
                  onClick={() => setMode("all")}
                >
                  All photos
                </button>
                {organizer && (
                  <button
                    className={mode === "best" ? "filter active" : "filter"}
                    onClick={() => setMode("best")}
                  >
                    Highlights
                  </button>
                )}
                {result && organizer && (
                  <button
                    className={mode === "results" ? "filter active" : "filter"}
                    onClick={() => setMode("results")}
                  >
                    Search results · {result.photos.length}
                  </button>
                )}
                {faceResults && (
                  <button
                    className={mode === "faces" ? "filter active" : "filter"}
                    onClick={() => setMode("faces")}
                  >
                    Face matches · {faceResults.length}
                  </button>
                )}
              </div>
              {organizer && state.picked > 0 && (
                <a className="text-link" href="/api/picks.zip" download>
                  <ArrowDownToLine size={14} /> Picks
                </a>
              )}
            </div>
            {mode === "results" && result && (
              <p className="result-caption">{result.answer}</p>
            )}
            <div className="masonry" aria-busy={loading}>
              {photos.map((photo) => (
                <PhotoCard
                  key={photo.id}
                  photo={photo}
                  onSelect={setSelected}
                />
              ))}
            </div>
            {loading && !photos.length && (
              <div className="loading-grid">
                {[0, 1, 2, 3].map((n) => (
                  <div key={n} />
                ))}
              </div>
            )}
            {!loading && !photos.length && (
              <div className="empty">
                <Images size={30} />
                <h3>
                  {state.count
                    ? "No matching photos."
                    : organizer
                      ? "Import your event folder."
                      : "Photos are on their way."}
                </h3>
              </div>
            )}
            {more && (
              <div className="load-more">
                <Button
                  variant="outline"
                  onClick={() => gallery(false)}
                  disabled={loading}
                >
                  Load more
                </Button>
              </div>
            )}
          </section>
          {organizer && (
            <aside className="agent-sidebar">
              <div className="agent-title">
                <Sparkles size={16} />
                <strong>Event agent</strong>
                <span>Local Gemma</span>
              </div>
              {activeRequest && (
                <div className="active-request" aria-label="Current request">
                  <span>Your request</span>
                  <p>{activeRequest}</p>
                </div>
              )}
              {job.running && (
                <TodoList
                  items={tasks}
                  title={
                    job.kind === "agent" ? "Finding your photos" : "Processing"
                  }
                  defaultOpen
                  collapseOnComplete
                />
              )}

              <div className="conversation">
                {result && (
                  <div className="single-response">
                    <MessageBubble variant="soft" align="left">
                      <p>{result.answer}</p>
                      <small>
                        {result.photos.length} results · {result.tokens} local
                        tokens
                      </small>
                    </MessageBubble>
                    <button
                      className="dismiss-response"
                      aria-label="Dismiss response"
                      onClick={() => {
                        setResult(null);
                        setActiveRequest("");
                        setMode("all");
                      }}
                    >
                      <X size={14} />
                    </button>
                  </div>
                )}
                {!result && !agentBusy && (
                  <div className="agent-suggestions">
                    <p>What are you looking for?</p>
                    {[
                      "Photos with the Google logo",
                      "Photos with multiple faces",
                      "Show the current highlights",
                    ].map((query) => (
                      <button
                        key={query}
                        disabled={
                          job.running || busy || !runtime?.default_model_ready
                        }
                        onClick={() => ask(query)}
                      >
                        {query} <ArrowUpRight size={13} />
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <PromptInput
                value={prompt}
                onValueChange={setPrompt}
                onSubmit={ask}
                placeholder="Ask about these photos…"
                aria-label="Ask the event agent"
                maxLength={500}
                minRows={1}
                maxRows={4}
                loading={agentBusy}
                disabled={
                  busy ||
                  !state.count ||
                  (!agentBusy && job.running) ||
                  !runtime?.default_model_ready
                }
                onStop={() =>
                  work(async () =>
                    notify((await api("/api/cancel", { method: "POST" })).note),
                  )
                }
              />
              <details className="highlight-settings">
                <summary>Build highlights</summary>
                <Field
                  label="Number of picks"
                  type="number"
                  min="1"
                  max="1000"
                  value={top}
                  onChange={setTop}
                />
                <Button
                  size="sm"
                  disabled={
                    busy ||
                    job.running ||
                    !state.count ||
                    !runtime?.default_model_ready
                  }
                  onClick={() =>
                    work(async () => {
                      await api("/api/curate", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                          top: Number(top),
                          provider: "ollama",
                        }),
                      });
                      priorJob.current = true;
                    })
                  }
                >
                  Review every photo
                </Button>
              </details>
              {!runtime?.default_model_ready && (
                <p className="fine">
                  Start Ollama and install gemma4:e2b-it-q4_K_M.
                </p>
              )}
            </aside>
          )}
        </div>
        <footer>
          <span>
            <ShieldCheck size={14} /> Originals untouched. Everything stays on
            this laptop.
          </span>
        </footer>
      </main>
      {selected && (
        <PhotoDetails
          photo={selected}
          organizer={organizer}
          close={() => setSelected(null)}
          notify={notify}
        />
      )}
    </div>
  );
}
