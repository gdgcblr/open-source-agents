// Thin client for the FirstRun HTTP API (firstrun/web.py).

async function request(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    ...options,
  });
  let body = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }
  if (!res.ok) {
    const err = new Error((body && (body.error || body.message)) || `${res.status} ${res.statusText}`);
    err.status = res.status;
    err.body = body;
    throw err;
  }
  return body;
}

export const getStatus = () => request("/api/status");
export const listRuns = () => request("/api/runs");
export const getRun = (id) => request(`/api/runs/${encodeURIComponent(id)}`);
export const startRun = (payload) => request("/api/runs", { method: "POST", body: JSON.stringify(payload) });
export const fileUrl = (id, name) => `/api/runs/${encodeURIComponent(id)}/files/${name}`;

export async function getText(id, name) {
  const res = await fetch(fileUrl(id, name));
  if (!res.ok) throw new Error(`${name} is not available for this run`);
  return res.text();
}

// Streams a run's events. Finished runs replay their saved events, live runs keep streaming.
// Returns a stop function.
export function streamEvents(id, { onEvent, onEnd, onError }) {
  const source = new EventSource(`/api/runs/${encodeURIComponent(id)}/events`);
  let ended = false;
  const finish = () => {
    if (ended) return;
    ended = true;
    source.close();
    onEnd && onEnd();
  };
  source.onmessage = (msg) => {
    let ev;
    try {
      ev = JSON.parse(msg.data);
    } catch {
      return;
    }
    onEvent(ev);
    if (ev.kind === "done") finish();
  };
  source.onerror = () => {
    // EventSource reconnects on its own and resumes from Last-Event-ID.
    // A closed stream after "done" is normal, anything else is reported once.
    if (ended) return;
    if (source.readyState === EventSource.CLOSED) {
      onError && onError(new Error("Lost the connection to FirstRun."));
      finish();
    }
  };
  return () => {
    ended = true;
    source.close();
  };
}
