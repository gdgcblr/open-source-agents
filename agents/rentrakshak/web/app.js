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
  setTimeout(() => el.classList.add("hidden"), 3500);
}

async function api(path, opts = {}) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText);
  return data;
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById("panel-" + tab.dataset.panel).classList.add("active");
    if (tab.dataset.panel === "checklist") loadChecklist();
  });
});

document.getElementById("load-scam").onclick = () => {
  document.getElementById("listing").value = SAMPLES.scam;
};
document.getElementById("load-clean").onclick = () => {
  document.getElementById("listing").value = SAMPLES.clean;
};

document.getElementById("btn-seed").onclick = async () => {
  try {
    const r = await api("/api/demo/seed", { method: "POST" });
    toast(r.message || "Demo data loaded");
  } catch (e) {
    toast("Seed failed: " + e.message);
  }
};

document.getElementById("run-check").onclick = async () => {
  const listing = document.getElementById("listing").value;
  const chat = document.getElementById("chat").value;
  const locality = document.getElementById("locality").value;
  const out = document.getElementById("report-out");
  out.classList.remove("hidden");
  out.innerHTML = "<p class='muted'>Analyzing…</p>";
  try {
    const rep = await api("/api/safety-report", {
      method: "POST",
      body: JSON.stringify({
        listing_text: listing,
        chat_text: chat || null,
        locality_hint: locality || null,
      }),
    });
    renderReport(rep, out);
  } catch (e) {
    out.innerHTML = `<p class="muted" style="color:var(--danger)">${e.message}</p>`;
  }
};

function riskClass(cat) {
  if (cat === "critical_warning") return "critical";
  if (cat === "high_concern") return "high";
  if (cat === "low_concern") return "low";
  return "needs_verification";
}

function renderReport(rep, el) {
  const rc = riskClass(rep.risk_category);
  const labels = {
    critical: "Critical warning",
    high: "High concern",
    low: "Low concern",
    needs_verification: "Needs verification",
  };
  let html = `<div class="risk-banner ${rc}"><strong>${labels[rc] || rep.risk_category}</strong><p class="muted">${rep.risk_reasoning}</p></div>`;
  const prop = rep.property || {};
  html += `<div class="metrics">
    <div class="metric"><div class="val">${(rep.findings || []).length}</div><div class="lbl">Red flags</div></div>
    <div class="metric"><div class="val">${prop.locality || "—"}</div><div class="lbl">Locality</div></div>
    <div class="metric"><div class="val">${prop.monthly_rent_inr ? "₹" + prop.monthly_rent_inr : "—"}</div><div class="lbl">Rent in text</div></div>
  </div>`;
  (rep.findings || []).forEach((f) => {
    html += `<div class="finding"><span class="rid">${f.rule_id}</span> · ${f.severity}<br>${f.explanation}<div class="evidence">"${f.evidence_excerpt}"</div><div class="muted" style="margin-top:0.35rem">Next: ${f.recommended_next_step}</div></div>`;
  });
  const re = rep.rent_estimate;
  if (re) {
    if (re.sufficient_data) {
      html += `<p class="muted" style="margin-top:1rem">Rent benchmark (demo): ₹${re.rent_min_inr?.toLocaleString()} – ₹${re.rent_max_inr?.toLocaleString()}/mo</p>`;
    } else {
      html += `<p class="muted" style="margin-top:1rem">Not enough rent comparables — no market guess.</p>`;
    }
  }
  el.innerHTML = html;
}

document.getElementById("comm-search").onclick = async () => {
  const loc = document.getElementById("comm-loc").value;
  const list = document.getElementById("comm-list");
  list.innerHTML = "<p class='muted'>Loading…</p>";
  try {
    const res = await api("/api/experiences?locality=" + encodeURIComponent(loc));
    if (!res.items?.length) {
      list.innerHTML = "<p class='muted'>No posts. Click <strong>Load demo data</strong> in the header.</p>";
      return;
    }
    list.innerHTML = res.items
      .map(
        (i) =>
          `<div class="item"><strong>${i.locality}</strong> · ${i.category} · ${i.sentiment}<p style="margin-top:0.5rem">${escapeHtml(i.experience_text)}</p></div>`
      )
      .join("");
  } catch (e) {
    list.innerHTML = `<p class="muted">${e.message}</p>`;
  }
};

document.getElementById("vac-search").onclick = async () => {
  const loc = document.getElementById("vac-loc").value;
  const list = document.getElementById("vac-list");
  list.innerHTML = "<p class='muted'>Loading…</p>";
  try {
    const res = await api("/api/vacating?locality=" + encodeURIComponent(loc));
    if (!res.items?.length) {
      list.innerHTML = "<p class='muted'>No rooms. Load demo data first.</p>";
      return;
    }
    list.innerHTML = res.items
      .map(
        (r) =>
          `<div class="item"><strong>${r.locality}</strong> · ${r.room_type} · ₹${r.monthly_rent_inr.toLocaleString()}/mo<p style="margin-top:0.5rem">${escapeHtml(r.description)}</p><p class="muted">From ${r.availability_date}</p></div>`
      )
      .join("");
  } catch (e) {
    list.innerHTML = `<p class="muted">${e.message}</p>`;
  }
};

async function loadChecklist() {
  const list = document.getElementById("checklist-list");
  if (list.dataset.loaded) return;
  list.innerHTML = "<p class='muted'>Loading…</p>";
  try {
    const res = await api("/api/checklist");
    list.innerHTML = res.items
      .map((i) => `<div class="item"><strong>${escapeHtml(i.title)}</strong><p class="muted">${escapeHtml(i.description)}</p></div>`)
      .join("");
    list.dataset.loaded = "1";
  } catch (e) {
    list.innerHTML = `<p class="muted">${e.message}</p>`;
  }
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}
