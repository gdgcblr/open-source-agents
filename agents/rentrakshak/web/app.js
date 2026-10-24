const API = "";
const SAMPLES = {
  scam: `2 BHK in Koramangala near forum mall. Rent Rs 15000 only!!!
URGENT pay token today before viewing — transfer to my friend account.
Send OTP for booking confirmation.`,
  clean: `2 BHK semi-furnished apartment in HSR Layout. Rent Rs 38000, deposit 3 months.
Maintenance Rs 3000. Owner prefers in-person viewing on weekends.
Written agreement with clear refund terms for deposit.`,
};

function toast(msg) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  setTimeout(() => el.classList.add("hidden"), 4000);
}

async function api(path, opts = {}) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  let data = {};
  try { data = await res.json(); } catch (_) {}
  if (!res.ok) throw new Error(data.detail || data.message || res.statusText);
  return data;
}

function esc(s) {
  const d = document.createElement("div");
  d.textContent = s ?? "";
  return d.innerHTML;
}

function showView(name) {
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
  document.querySelectorAll(".nav-item").forEach((n) => n.classList.remove("active"));
  const v = document.getElementById("view-" + name);
  if (v) v.classList.add("active");
  document.querySelector(`.nav-item[data-view="${name}"]`)?.classList.add("active");
  if (name === "checklist") loadChecklist();
  if (name === "rent") loadLocalitySelects();
}

document.querySelectorAll(".nav-item").forEach((btn) => {
  btn.onclick = () => showView(btn.dataset.view);
});
document.querySelectorAll("[data-goto]").forEach((el) => {
  el.onclick = () => showView(el.dataset.goto);
});
document.querySelectorAll(".feature-card").forEach((c) => {
  c.onclick = () => showView(c.dataset.goto);
});

document.querySelectorAll(".subtab").forEach((t) => {
  t.onclick = () => {
    document.querySelectorAll(".subtab").forEach((x) => x.classList.remove("active"));
    document.querySelectorAll(".tab-pane").forEach((x) => x.classList.remove("active"));
    t.classList.add("active");
    document.getElementById(t.dataset.tab).classList.add("active");
  };
});

function fillSelect(id, localities) {
  const el = document.getElementById(id);
  if (!el || el.dataset.filled) return;
  el.innerHTML = localities.map((l) => `<option value="${esc(l)}">${esc(l)}</option>`).join("");
  el.dataset.filled = "1";
}

async function loadLocalitySelects() {
  const data = await api("/api/localities");
  const locs = data.all_supported || [];
  ["prop-locality", "rent-locality", "comm-locality", "vac-locality", "sub-locality"].forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    const cur = el.dataset.filled;
    el.innerHTML = locs.map((l) => `<option>${esc(l)}</option>`).join("");
    el.dataset.filled = "1";
  });
  renderLocalityCards(data.popular || []);
}

function renderLocalityCards(cards) {
  const root = document.getElementById("locality-cards");
  if (!root) return;
  root.innerHTML = cards
    .map((c) => {
      const avg = c.rent_median_inr
        ? `₹${(c.rent_min_inr / 1000).toFixed(0)}k – ₹${(c.rent_max_inr / 1000).toFixed(0)}k`
        : "No data";
      return `<div class="loc-card" data-loc="${esc(c.locality)}"><h4>${esc(c.locality)}</h4><div class="avg">${avg}</div><small>${c.comparable_count} comps · demo</small></div>`;
    })
    .join("");
  root.querySelectorAll(".loc-card").forEach((card) => {
    card.onclick = () => {
      showView("rent");
      const sel = document.getElementById("rent-locality");
      if (sel) sel.value = card.dataset.loc;
      runRentEstimate();
    };
  });
}

async function runRentEstimate() {
  const loc = document.getElementById("rent-locality").value;
  const bhk = document.getElementById("rent-bhk").value;
  const furn = document.getElementById("rent-furnishing").value;
  const out = document.getElementById("rent-out");
  out.innerHTML = "<p class='muted'>Loading…</p>";
  const q = new URLSearchParams({ locality: loc });
  if (bhk) q.set("bhk", bhk);
  if (furn) q.set("furnishing", furn);
  const r = await api("/api/rent-estimate?" + q);
  if (!r.sufficient_data) {
    out.innerHTML = `<p><strong>Insufficient data</strong> for this filter (${r.comparable_count} comps).</p><p class="muted">${(r.limitations || []).join(" ")}</p>`;
    return;
  }
  out.innerHTML = `<h3>${esc(r.locality)}</h3>
    <p><strong>₹${r.rent_min_inr?.toLocaleString()} – ₹${r.rent_max_inr?.toLocaleString()}</strong> / month (median ₹${r.rent_median_inr?.toLocaleString()})</p>
    <p class="muted">${r.comparable_count} comparables · ${esc(r.data_classification)}</p>
    <ul class="muted small">${(r.limitations || []).map((l) => `<li>${esc(l)}</li>`).join("")}</ul>`;
}

document.getElementById("run-rent").onclick = () => runRentEstimate().catch((e) => toast(e.message));

document.getElementById("btn-seed").onclick = async () => {
  try {
    const r = await api("/api/demo/seed", { method: "POST" });
    toast(r.message);
    refreshRail();
    loadLocalitySelects();
  } catch (e) { toast(e.message); }
};

document.getElementById("load-scam").onclick = () => { document.getElementById("listing").value = SAMPLES.scam; };
document.getElementById("load-clean").onclick = () => { document.getElementById("listing").value = SAMPLES.clean; };

document.getElementById("file-upload").onchange = async (ev) => {
  const file = ev.target.files?.[0];
  if (!file) return;
  const status = document.getElementById("upload-status");
  const fd = new FormData();
  fd.append("file", file);
  status.textContent = "Uploading…";
  try {
    const res = await fetch("/api/upload-listing", { method: "POST", body: fd });
    const data = await res.json();
    if (data.extracted_text) {
      document.getElementById("listing").value = data.extracted_text;
      status.textContent = "Loaded " + file.name;
    } else {
      status.textContent = data.message || "Upload noted — paste text manually.";
      toast(data.message || "OCR not enabled");
    }
  } catch (e) {
    status.textContent = "Upload failed";
  }
};

document.getElementById("run-check").onclick = async () => {
  const out = document.getElementById("report-out");
  out.classList.remove("hidden");
  out.innerHTML = "<p class='muted'>Analysing…</p>";
  const rent = document.getElementById("prop-rent").value;
  const dep = document.getElementById("prop-deposit").value;
  try {
    const rep = await api("/api/safety-report", {
      method: "POST",
      body: JSON.stringify({
        listing_text: document.getElementById("listing").value,
        chat_text: document.getElementById("chat").value || null,
        locality_hint: document.getElementById("prop-locality").value || null,
        monthly_rent_inr: rent ? +rent : null,
        deposit_inr: dep ? +dep : null,
        bhk: document.getElementById("prop-bhk").value || null,
        furnishing: document.getElementById("prop-furnishing").value || null,
        property_type: document.getElementById("prop-type").value || null,
      }),
    });
    renderReport(rep, out);
  } catch (e) {
    out.innerHTML = `<p style="color:var(--danger)">${esc(e.message)}</p>`;
  }
};

function renderReport(rep, el) {
  const rc = rep.risk_category === "critical_warning" ? "critical" : rep.risk_category === "low_concern" ? "low" : "";
  let html = `<div class="risk ${rc}"><strong>${esc(rep.risk_category)}</strong><p class="muted">${esc(rep.risk_reasoning)}</p></div>`;
  (rep.findings || []).forEach((f) => {
    html += `<div class="item"><strong>${esc(f.rule_id)}</strong> · ${esc(f.severity)}<br>${esc(f.explanation)}<br><small class="muted">"${esc(f.evidence_excerpt)}"</small></div>`;
  });
  const re = rep.rent_estimate;
  if (re?.sufficient_data) {
    html += `<p class="muted">Rent benchmark: ₹${re.rent_min_inr?.toLocaleString()} – ₹${re.rent_max_inr?.toLocaleString()}</p>`;
  }
  if (rep.deposit_assessment?.notes) {
    html += `<h4>Deposit notes</h4><ul>${rep.deposit_assessment.notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>`;
  }
  if (rep.community_summary?.submission_count) {
    html += `<p class="muted">Community: ${rep.community_summary.submission_count} posts in ${esc(rep.property?.locality)} — patterns only, not proof.</p>`;
  }
  el.innerHTML = html;
}

async function searchCommunity() {
  const q = new URLSearchParams();
  const loc = document.getElementById("comm-locality").value;
  if (loc) q.set("locality", loc);
  const cat = document.getElementById("comm-category").value;
  if (cat) q.set("category", cat);
  const sent = document.getElementById("comm-sentiment").value;
  if (sent) q.set("sentiment", sent);
  const pt = document.getElementById("comm-ptype").value;
  if (pt) q.set("property_type", pt);
  const res = await api("/api/experiences?" + q);
  document.getElementById("comm-stats").textContent = `${res.count} posts · self-reported, not verified`;
  const list = document.getElementById("comm-list");
  if (!res.items?.length) {
    list.innerHTML = "<p class='muted'>No posts — click <strong>Load demo data</strong> in sidebar.</p>";
    return;
  }
  list.innerHTML = res.items.map(renderExpItem).join("");
}

function renderExpItem(i) {
  const b = i.sentiment === "positive" ? "pos" : i.sentiment === "negative" ? "neg" : "neu";
  return `<article class="item">
    <span class="badge ${b}">${esc(i.sentiment)}</span>
    <strong>${esc(i.locality)}</strong> · ${esc(i.category)} · ${esc(i.property_type)}
    ${i.rent_band ? `<span class="muted"> · rent ${esc(i.rent_band)}</span>` : ""}
    <p style="margin-top:0.5rem">${esc(i.experience_text)}</p>
    <small class="muted">${esc(i.created_at?.slice(0, 10) || "")}</small>
  </article>`;
}

document.getElementById("comm-search").onclick = () => searchCommunity().catch((e) => toast(e.message));

document.getElementById("vac-search").onclick = async () => {
  const q = new URLSearchParams();
  const loc = document.getElementById("vac-locality").value;
  if (loc) q.set("locality", loc);
  const max = document.getElementById("vac-max-rent").value;
  if (max) q.set("max_rent_inr", max);
  const res = await api("/api/vacating?" + q);
  const list = document.getElementById("vac-list");
  if (!res.items?.length) {
    list.innerHTML = "<p class='muted'>No active rooms. Load demo data.</p>";
    return;
  }
  list.innerHTML = res.items.map((r) => `<article class="item"><strong>${esc(r.locality)}</strong> · ${esc(r.room_type)} · <strong>₹${r.monthly_rent_inr.toLocaleString()}</strong>/mo
    <p>${esc(r.description)}</p><small class="muted">From ${esc(r.availability_date)} · deposit ${r.deposit_inr ? "₹" + r.deposit_inr : "—"}</small></article>`).join("");
};

async function loadChecklist() {
  const data = await api("/api/checklist");
  document.getElementById("checklist-list").innerHTML = data.items.map((i) =>
    `<div class="item"><strong>${esc(i.title)}</strong><p class="muted">${esc(i.description)}</p></div>`).join("");
  document.getElementById("legal-list").innerHTML = data.legal_sources.map((r) =>
    `<div class="item"><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title)}</a><p class="muted small">${esc(r.explanation)}</p></div>`).join("");
}

document.getElementById("sub-submit").onclick = async () => {
  const out = document.getElementById("sub-result");
  out.classList.remove("hidden");
  try {
    const body = {
      locality: document.getElementById("sub-locality").value,
      property_type: document.getElementById("sub-ptype").value,
      category: document.getElementById("sub-cat").value,
      sentiment: document.getElementById("sub-sent").value,
      experience_text: document.getElementById("sub-text").value,
      rent_band: document.getElementById("sub-rent").value || null,
    };
    const rm = document.getElementById("sub-r-maint").value;
    const rc = document.getElementById("sub-r-comm").value;
    if (rm) body.rating_maintenance = +rm;
    if (rc) body.rating_communication = +rc;
    const r = await api("/api/experiences", { method: "POST", body: JSON.stringify(body) });
    out.innerHTML = `<p>Status: <strong>${esc(r.moderation_status)}</strong></p><p class="muted">Save edit token privately:</p><code>${esc(r.edit_token)}</code>`;
    refreshRail();
  } catch (e) {
    out.innerHTML = `<p style="color:var(--danger)">${esc(e.message)}</p>`;
  }
};

document.getElementById("ask-btn").onclick = async () => {
  const q = document.getElementById("ask-q").value;
  const r = await api("/api/ask", { method: "POST", body: JSON.stringify({ question: q }) });
  document.getElementById("ask-ans").textContent = r.answer;
};

document.getElementById("global-search").onkeydown = (e) => {
  if (e.key === "Enter") {
    showView("community");
    const v = e.target.value.trim();
    if (v) document.getElementById("comm-locality").value = v;
    searchCommunity().catch(() => {});
  }
};

async function refreshRail() {
  try {
    const res = await api("/api/experiences?limit=5");
    const el = document.getElementById("rail-feed");
    if (!res.items?.length) { el.textContent = "No posts yet."; return; }
    el.innerHTML = res.items.map((i) => `<div class="rail-item"><span class="badge neu">${esc(i.sentiment)}</span> ${esc(i.locality)}<br>${esc(i.experience_text.slice(0, 80))}…</div>`).join("");
  } catch (_) {}
}

loadLocalitySelects().catch(() => {});
refreshRail();
