const byId = (id) => document.getElementById(id);
const state = { casefile: null, imageName: "", imageData: "", imageMime: "", currentStep: 1, channelStats: {}, selectedChannel: null, coordinates: {} };
const sample = {
  description: "A deep pothole is breaking up the road near the metro entrance. Motorbikes are swerving around it.",
  location: "12th Main Road, Indiranagar",
  landmark: "Near the metro entrance",
  observed_at: "today at 8:30 AM",
};

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" })[char]);
}
function base64FromBuffer(buffer) {
  const bytes = new Uint8Array(buffer); let binary = ""; const chunk = 0x8000;
  for (let index = 0; index < bytes.length; index += chunk) binary += String.fromCharCode(...bytes.subarray(index, Math.min(index + chunk, bytes.length)));
  return btoa(binary);
}
async function readExifGps(file) {
  if (!file || !file.type.includes("jpeg")) return null;
  const bytes = new DataView(await file.arrayBuffer());
  if (bytes.getUint16(0, false) !== 0xffd8) return null;
  let offset = 2;
  while (offset + 4 < bytes.byteLength) {
    if (bytes.getUint8(offset) !== 0xff) { offset += 1; continue; }
    const marker = bytes.getUint8(offset + 1); const length = bytes.getUint16(offset + 2, false);
    if (marker === 0xe1 && offset + 10 < bytes.byteLength && new TextDecoder().decode(new Uint8Array(bytes.buffer, bytes.byteOffset + offset + 4, 6)) === "Exif\0\0") {
      const tiff = offset + 10; const little = bytes.getUint16(tiff, false) === 0x4949;
      const u16 = (at) => bytes.getUint16(at, little); const u32 = (at) => bytes.getUint32(at, little);
      if (u16(tiff + 2) !== 42) return null;
      const ifd = tiff + u32(tiff + 4); const count = u16(ifd); let gpsOffset = 0;
      for (let index = 0; index < count; index += 1) { const entry = ifd + 2 + index * 12; if (u16(entry) === 0x8825) gpsOffset = tiff + u32(entry + 8); }
      if (!gpsOffset) return null;
      const gpsCount = u16(gpsOffset); let latRef = "N"; let lonRef = "E"; let lat = null; let lon = null;
      const rational = (at) => { const numerator = u32(at); const denominator = u32(at + 4); return denominator ? numerator / denominator : 0; };
      for (let index = 0; index < gpsCount; index += 1) {
        const entry = gpsOffset + 2 + index * 12; const tag = u16(entry); const type = u16(entry + 2); const items = u32(entry + 4);
        if ((tag === 1 || tag === 3) && type === 2) { const ref = bytes.getUint8(entry + 8); if (tag === 1) latRef = String.fromCharCode(ref); else lonRef = String.fromCharCode(ref); }
        if ((tag === 2 || tag === 4) && type === 5 && items >= 3) { const values = tiff + u32(entry + 8); const degrees = rational(values); const minutes = rational(values + 8); const seconds = rational(values + 16); const decimal = degrees + minutes / 60 + seconds / 3600; if (tag === 2) lat = latRef === "S" ? -decimal : decimal; else lon = lonRef === "W" ? -decimal : decimal; }
      }
      return lat !== null && lon !== null ? { latitude: lat.toFixed(6), longitude: lon.toFixed(6), source: "photo GPS metadata" } : null;
    }
    offset += 2 + length;
  }
  return null;
}
function list(items) { return `<ul>${(items || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`; }
function showError(message = "") {
  const box = byId("error"); box.hidden = !message; box.textContent = message;
  if (message) box.scrollIntoView({ behavior:"smooth", block:"center" });
}
function goTo(step) {
  state.currentStep = step;
  document.querySelectorAll(".stage").forEach((stage) => stage.classList.toggle("active", Number(stage.dataset.stage) === step));
  document.querySelectorAll(".step").forEach((button) => {
    const number = Number(button.dataset.step);
    button.classList.toggle("active", number === step);
    if (number <= step) button.disabled = false;
  });
  showError(); window.scrollTo({ top:0, behavior:"smooth" });
}
function payload() {
  return {
    description:byId("description").value.trim(), image_name:state.imageName,
    location:byId("location").value.trim(), landmark:byId("landmark").value.trim(),
    observed_at:byId("observed_at").value.trim(), duration:byId("duration").value.trim(),
    pole_number:byId("pole_number").value.trim(), coordinates:state.coordinates, image_data:state.imageData, image_mime:state.imageMime,
  };
}
async function post(path, body) {
  const response = await fetch(path, { method:"POST", headers:{ "Content-Type":"application/json" }, body:JSON.stringify(body) });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}
function optionMarkup(option, action = false, routeIndex = 0, routeCategory = "") {
  const channelId = option.id || `${routeIndex}-${option.mode}`;
  const stat = state.channelStats[`${routeCategory}::${channelId}`];
  const percentage = stat && stat.reports >= 5 ? ` (${Math.round((stat.accepted / stat.reports) * 100)}%, local sample)` : "";
  const outcome = stat ? `${stat.accepted} of ${stat.reports} local user report${stat.reports === 1 ? "" : "s"} said it was accepted${percentage}${stat.resolved ? `; ${stat.resolved} later resolved` : ""}.` : "No local outcome reports yet.";
  const labels = { portal_handoff:"Open official service", guided_handoff:"Open official guidance", whatsapp_handoff:"Open WhatsApp", phone_handoff:"Call helpline", copy_text:"Copy complaint" };
  const community = option.track_feedback === false ? "" : `<small class="community-stat">Community-reported for ${escapeHtml(routeCategory)}: ${escapeHtml(outcome)}</small>`;
  const metadata = `${option.recommended ? `<small class="recommended">Recommended for this report</small><small>${escapeHtml(option.recommendation_reason)}</small>` : ""}${option.contact ? `<small><strong>Contact:</strong> ${escapeHtml(option.contact)}</small>` : ""}${community}`;
  const details = `<details class="channel-details"><summary>Details</summary><small>Prepare: ${escapeHtml((option.needs || []).join(", "))}</small>${option.not_for ? `<small><strong>Not for:</strong> ${escapeHtml(option.not_for)}</small>` : ""}${option.last_verified ? `<small>Verified: ${escapeHtml(option.last_verified)}</small>` : ""}${option.source ? `<small><a href="${escapeHtml(option.source)}" target="_blank" rel="noopener">View official source</a></small>` : ""}</details>`;
  return `<div class="option ${option.recommended ? "recommended-option" : ""}"><div><strong>${escapeHtml(option.name)}</strong><small>${escapeHtml(option.best_for || "")}</small><div class="channel-meta">${metadata}${details}</div></div>${action ? `<button class="route-action" data-route="${routeIndex}" data-category="${escapeHtml(routeCategory)}" data-channel-id="${escapeHtml(channelId)}" data-channel-name="${escapeHtml(option.name)}" data-track-feedback="${option.track_feedback !== false}" data-mode="${escapeHtml(option.mode)}" data-destination="${escapeHtml(option.destination || option.source || "")}">${labels[option.mode] || "Use this option"}</button>` : ""}</div>`;
}
function renderRoute(casefile) {
  byId("issue-summary").innerHTML = `<p>${escapeHtml(casefile.safety_note)}</p>`;
  byId("trace-list").innerHTML = (casefile.decision_trace || []).map((item) => `<div class="trace-row"><span>${escapeHtml(item.stage.replaceAll("_", " "))}</span><p>${escapeHtml(item.summary)}</p></div>`).join("");
  byId("route-summary").innerHTML = casefile.routing_plan.map((route, index) => `<article class="route-card ${index === 0 ? "primary-route" : ""}"><div class="stage-number">${index === 0 ? "Primary issue" : "Related issue"}</div><h3>${escapeHtml(route.category)}</h3><p><strong>Likely responsible authority:</strong> ${escapeHtml(route.authority)}</p><p class="why"><strong>Why:</strong> ${escapeHtml(route.reason)}</p><h3>Available options</h3>${route.options.map((option) => optionMarkup(option, false, index, route.category)).join("") || "<p>No verified option is stored yet. Copy the prepared complaint and verify a current channel.</p>"}</article>`).join("");
}
function configureQuestions(casefile) {
  const fields = new Set(casefile.questions.map((question) => question.field));
  byId("duration-wrap").hidden = !fields.has("duration") && casefile.category !== "Garbage / waste";
  byId("pole-wrap").hidden = !fields.has("pole_number") && casefile.category !== "Streetlight / visibility";
  const required = casefile.questions.filter((question) => question.required);
  byId("missing-box").innerHTML = required.length ? `<strong>Still needed</strong>${list(required.map((question) => question.label))}` : "<strong>Ready:</strong> the required case details are present.";
}
function renderReview(casefile) {
  byId("case-id").textContent = casefile.case_id;
  byId("review-badges").innerHTML = "";
  byId("evidence-list").innerHTML = list(casefile.evidence_checklist);
  byId("safety-note").textContent = casefile.safety_note;
  const privacyFindings = casefile.privacy_findings || [];
  byId("privacy-note").textContent = privacyFindings.length ? `Potential ${privacyFindings.join(" and ")} detected — remove or redact it before sharing.` : casefile.privacy_note;
  byId("english-draft").value = casefile.english_draft; byId("kannada-draft").value = casefile.kannada_draft;
  byId("guardrail-box").innerHTML = `<div class="guardrail-title">${escapeHtml(casefile.guardrails?.summary || "Review checks")}</div>${(casefile.guardrails?.checks || []).map((check) => `<div class="guardrail-row"><span class="guardrail-mark ${check.passed ? "pass" : "attention"}">${check.passed ? "✓" : "!"}</span><span>${escapeHtml(check.label)}${check.note ? `<small>${escapeHtml(check.note)}</small>` : ""}</span></div>`).join("")}`;
  byId("duplicate-box").innerHTML = "";
}
function renderHandoffs(casefile) {
  byId("handoff-routes").innerHTML = casefile.routing_plan.map((route, index) => `<article class="route-card ${index === 0 ? "primary-route" : ""}"><h3>${escapeHtml(route.category)} → ${escapeHtml(route.authority)}</h3>${route.options.map((option) => optionMarkup(option, true, index, route.category)).join("")}</article>`).join("");
  document.querySelectorAll("[data-mode]").forEach((button) => button.addEventListener("click", () => handoff(button)));
}
async function handoff(button) {
  button.disabled = true;
  try {
    const saved = await post(`/api/cases/${encodeURIComponent(state.casefile.case_id)}/approve`, { mode:button.dataset.mode, channel_id:button.dataset.channelId, channel_name:button.dataset.channelName, english_draft:byId("english-draft").value, kannada_draft:byId("kannada-draft").value });
    state.casefile = saved;
    state.selectedChannel = { id:button.dataset.channelId, name:button.dataset.channelName, category:button.dataset.category };
    if (button.dataset.mode === "copy_text") await navigator.clipboard.writeText(saved.english_draft);
    if (button.dataset.destination) window.open(button.dataset.destination, "_blank", "noopener");
    const action = button.dataset.mode === "copy_text" ? "Complaint copied" : "Official destination opened";
    byId("handoff-result").hidden = false; byId("handoff-result").textContent = `${action}. Case ${saved.case_id} is marked approved locally; review once more before final submission.`;
    byId("feedback-panel").hidden = button.dataset.trackFeedback !== "true";
    await loadCases();
  } catch (error) { showError(error.message); } finally { button.disabled = false; }
}

byId("identify").addEventListener("click", async () => {
  if (!byId("description").value.trim()) return showError("Please describe the civic problem first.");
  const button = byId("identify"); button.disabled = true; button.textContent = "Identifying…";
  try { state.casefile = await post("/api/analyze", payload()); renderRoute(state.casefile); configureQuestions(state.casefile); goTo(2); }
  catch (error) { showError(error.message); }
  finally { button.disabled = false; button.textContent = "Analyze report"; }
});
byId("collect-details").addEventListener("click", () => goTo(3));
byId("prepare").addEventListener("click", async () => {
  const button = byId("prepare"); button.disabled = true; button.textContent = "Checking details…";
  try {
    const checked = await post("/api/analyze", payload()); configureQuestions(checked);
    if (checked.status === "needs_information") {
      const required = checked.questions.filter((question) => question.required).map((question) => question.label).join(", ");
      return showError(`Please complete: ${required}.`);
    }
    state.casefile = await post("/api/cases", payload()); renderReview(state.casefile); goTo(4); await loadCases();
  } catch (error) { showError(error.message); }
  finally { button.disabled = false; button.textContent = "Prepare complaint"; }
});
byId("approval-check").addEventListener("change", (event) => { byId("approve-review").disabled = !event.target.checked; });
byId("approve-review").addEventListener("click", () => { state.casefile.english_draft = byId("english-draft").value; state.casefile.kannada_draft = byId("kannada-draft").value; renderHandoffs(state.casefile); goTo(5); });
document.querySelectorAll(".back").forEach((button) => button.addEventListener("click", () => goTo(Number(button.dataset.back))));
document.querySelectorAll(".step").forEach((button) => button.addEventListener("click", () => { if (!button.disabled) goTo(Number(button.dataset.step)); }));
byId("sample").addEventListener("click", () => Object.entries(sample).forEach(([key, value]) => { byId(key).value = value; }));
byId("image").addEventListener("change", async (event) => {
  const file = event.target.files[0]; state.imageName = file?.name || ""; const preview = byId("image-preview");
  state.imageData = ""; state.imageMime = file?.type || "";
  if (!file) { preview.hidden = true; preview.innerHTML = ""; return; }
  if (file.size <= 8_000_000) state.imageData = base64FromBuffer(await file.arrayBuffer());
  if (!byId("description").value.trim() || byId("description").value.startsWith("Photo attached")) {
    byId("description").value = `Photo attached: ${file.name}. Please confirm what the image shows and add anything important.`;
  }
  const url = URL.createObjectURL(file); preview.innerHTML = `<img src="${url}" alt="Selected evidence preview"><p class="fineprint">${file.size <= 8_000_000 ? "Ready for Gemini vision when configured." : "Image is larger than 8 MB; only the filename is retained locally."}</p><p id="photo-location" class="fineprint">Checking photo metadata…</p>`; preview.hidden = false;
  const photoCoordinates = await readExifGps(file);
  if (photoCoordinates) { state.coordinates = photoCoordinates; byId("photo-location").textContent = `Coordinates found in photo metadata: ${photoCoordinates.latitude}, ${photoCoordinates.longitude}`; }
  else byId("photo-location").textContent = "No GPS metadata found in this photo. You can use device location later.";
});
byId("locate").addEventListener("click", () => {
  const status = byId("location-status");
  if (!navigator.geolocation) { status.textContent = "Location is not available in this browser."; return; }
  status.textContent = "Finding your location…";
  navigator.geolocation.getCurrentPosition((position) => {
    const latitude = position.coords.latitude.toFixed(6); const longitude = position.coords.longitude.toFixed(6);
    state.coordinates = { latitude, longitude };
    status.textContent = `Coordinates captured: ${latitude}, ${longitude}`;
    if (!byId("location").value.trim()) byId("location").value = `GPS location (${latitude}, ${longitude})`;
  }, () => { status.textContent = "Could not access location. Enter a street or landmark instead."; }, { enableHighAccuracy:true, timeout:8000 });
});
async function loadCases() {
  const response = await fetch("/api/cases"); const cases = await response.json();
  byId("cases").innerHTML = cases.length ? cases.slice().reverse().map((item) => `<div class="history-item"><strong>${escapeHtml(item.case_id)} · ${escapeHtml(item.category)}</strong><br>${escapeHtml(item.location)} · ${escapeHtml(item.status.replaceAll("_", " "))}</div>`).join("") : "No cases yet.";
}
async function loadChannelStats() {
  const response = await fetch("/api/channel-stats"); state.channelStats = await response.json();
}
document.querySelectorAll(".feedback").forEach((button) => button.addEventListener("click", async () => {
  if (!state.selectedChannel) return;
  try {
    await post(`/api/cases/${encodeURIComponent(state.casefile.case_id)}/feedback`, { channel_id:state.selectedChannel.id, category:state.selectedChannel.category, accepted:button.dataset.accepted === "true", resolved:button.dataset.resolved === "true" });
    await loadChannelStats();
    byId("feedback-panel").innerHTML = `<div class="success">Thanks. The recommendation will show this as one local user report, not as an official efficiency claim.</div>`;
  } catch (error) { showError(error.message); }
}));
byId("start-over").addEventListener("click", () => window.location.reload());
Promise.all([loadCases(), loadChannelStats()]).catch(() => { byId("cases").textContent = "Local demo data could not be loaded."; });
