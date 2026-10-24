/**
 * TShoot: Autonomous Multi-Agent Technical Troubleshooter Frontend.
 * Features:
 * - Multi-Agent Collaborative Triage (Auth, Network, Web Search, Deep Investigator)
 * - Drag & Drop, File Browse, and Clipboard (Ctrl+V) Screenshot Analysis
 * - Autonomous Web Solution Fetching for "Others" category
 * - Interactive Solved / Feedback Loop with Consent-Based Deep Autonomous Investigation
 * - Shell Command Generation & Live Event Stream
 */

document.addEventListener("DOMContentLoaded", () => {
  // -------------------------------------------------------------------------
  // DOM Elements
  // -------------------------------------------------------------------------
  const diagnoseForm = document.getElementById("diagnoseForm");
  const serviceSelect = document.getElementById("serviceSelect");
  const clientEnvSelect = document.getElementById("clientEnvSelect");
  const errorMessageInput = document.getElementById("errorMessageInput");
  const btnDiagnose = document.getElementById("btnDiagnose");
  const btnCheckNetwork = document.getElementById("btnCheckNetwork");
  const quickPills = document.querySelectorAll(".pill-btn");

  const diagnosisCard = document.getElementById("diagnosisCard");
  const diagnosisTitle = document.getElementById("diagnosisTitle");
  const urgencyTag = document.getElementById("urgencyTag");
  const rootCauseText = document.getElementById("rootCauseText");
  const remediationStepsList = document.getElementById("remediationStepsList");
  const sourcesBox = document.getElementById("sourcesBox");
  const sourcesList = document.getElementById("sourcesList");
  const codeSnippetBox = document.getElementById("codeSnippetBox");
  const snippetContent = document.getElementById("snippetContent");
  const btnCopySnippet = document.getElementById("btnCopySnippet");

  // Feedback & Deep Investigation Elements
  const solutionFeedbackSection = document.getElementById("solutionFeedbackSection");
  const btnSolutionSolved = document.getElementById("btnSolutionSolved");
  const btnSolutionNotSolved = document.getElementById("btnSolutionNotSolved");
  const solvedConfirmation = document.getElementById("solvedConfirmation");
  const deepInvestigationConsent = document.getElementById("deepInvestigationConsent");
  const btnGrantDeepPermission = document.getElementById("btnGrantDeepPermission");
  const deepInvestigationResults = document.getElementById("deepInvestigationResults");
  const deepInvId = document.getElementById("deepInvId");
  const deepAnalysisText = document.getElementById("deepAnalysisText");
  const deepLayersContainer = document.getElementById("deepLayersContainer");
  const deepScriptContent = document.getElementById("deepScriptContent");
  const btnCopyDeepScript = document.getElementById("btnCopyDeepScript");
  const btnDeepSolved = document.getElementById("btnDeepSolved");
  const btnOpenEscalateModal2 = document.getElementById("btnOpenEscalateModal2");

  // Screenshot Upload Elements
  const screenshotDropZone = document.getElementById("screenshotDropZone");
  const screenshotFileInput = document.getElementById("screenshotFileInput");
  const dropZonePrompt = document.getElementById("dropZonePrompt");
  const imagePreviewContainer = document.getElementById("imagePreviewContainer");
  const imagePreview = document.getElementById("imagePreview");
  const previewFileName = document.getElementById("previewFileName");
  const previewFileSize = document.getElementById("previewFileSize");
  const btnRemovePreview = document.getElementById("btnRemovePreview");
  const screenshotNotesInput = document.getElementById("screenshotNotesInput");
  const btnAnalyzeScreenshot = document.getElementById("btnAnalyzeScreenshot");
  const screenshotResultCard = document.getElementById("screenshotResultCard");
  const ssDetectedService = document.getElementById("ssDetectedService");
  const ssExtractedText = document.getElementById("ssExtractedText");
  const ssStatusText = document.getElementById("ssStatusText");

  // Network & Terminal Stream
  const connectivityCard = document.getElementById("connectivityCard");
  const connectivityRows = document.getElementById("connectivityRows");
  const connectivitySummaryBadge = document.getElementById("connectivitySummaryBadge");
  const agentStreamLogs = document.getElementById("agentStreamLogs");

  // Escalation Modal
  const btnOpenEscalateModal = document.getElementById("btnOpenEscalateModal");
  const escalateModal = document.getElementById("escalateModal");
  const btnCloseEscalateModal = document.getElementById("btnCloseEscalateModal");
  const escalateForm = document.getElementById("escalateForm");
  const escalatedResultBox = document.getElementById("escalatedResultBox");
  const chatSnippetDisplay = document.getElementById("chatSnippetDisplay");
  const btnCopyChatSnippet = document.getElementById("btnCopyChatSnippet");

  // State
  let currentScreenshotBase64 = null;
  let currentScreenshotName = "";
  let lastDiagnosedError = "";
  let lastDiagnosedService = "Others";

  // -------------------------------------------------------------------------
  // Terminal Stream Logger
  // -------------------------------------------------------------------------
  function logToTerminal(message, type = "info") {
    if (!agentStreamLogs) return;
    const line = document.createElement("div");
    line.className = `log-line ${type}`;
    const time = new Date().toLocaleTimeString();
    line.textContent = `[${time}] ${message}`;
    agentStreamLogs.appendChild(line);
    agentStreamLogs.scrollTop = agentStreamLogs.scrollHeight;
  }

  // -------------------------------------------------------------------------
  // Pre-configured Symptom Presets
  // -------------------------------------------------------------------------
  const PRESETS = {
    google_login_403: {
      service: "Google Account & Cloud",
      error: "Error 403: org_internal. Access blocked: This app is restricted by administrator policy. You cannot sign in with this account.",
    },
    port_8000_conflict: {
      service: "Google ADK Web Server",
      error: "ERROR: [Errno 10048] error while attempting to bind on address ('127.0.0.1', 8000): only one usage of each socket address is permitted",
    },
    oauth_mismatch: {
      service: "Google Account & Cloud",
      error: "Error 400: redirect_uri_mismatch. The redirect URI in the request: http://127.0.0.1:8000 does not match the ones authorized for the OAuth client.",
    },
    invalid_api_key: {
      service: "Gemini API & Credentials",
      error: "Error: 400 INVALID_ARGUMENT. API key not valid. Please pass a valid API key.",
    },
    python_mapping: {
      service: "Others",
      error: "ImportError: cannot import name Mapping from collections (Python 3.10+ deprecation)",
    },
    docker_daemon: {
      service: "Others",
      error: "Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?",
    },
  };

  quickPills.forEach((pill) => {
    pill.addEventListener("click", () => {
      const symptomKey = pill.getAttribute("data-symptom");
      if (PRESETS[symptomKey]) {
        serviceSelect.value = PRESETS[symptomKey].service;
        errorMessageInput.value = PRESETS[symptomKey].error;
        logToTerminal(`Loaded template: ${symptomKey}`, "info");
        diagnoseForm.dispatchEvent(new Event("submit"));
      }
    });
  });

  // -------------------------------------------------------------------------
  // Diagnosis Form Submission
  // -------------------------------------------------------------------------
  diagnoseForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const service = serviceSelect.value;
    const clientEnv = clientEnvSelect.value;
    const errorMsg = errorMessageInput.value.trim();

    if (!errorMsg) return;

    lastDiagnosedError = errorMsg;
    lastDiagnosedService = service;

    // Reset feedback & deep investigation states
    resetFeedbackAndDeepCards();

    btnDiagnose.disabled = true;
    btnDiagnose.innerHTML = `<span class="pulse-dot"></span> Diagnosing...`;

    if (service === "Others") {
      logToTerminal(`[DISPATCH] Coordinator -> Web Search Specialist for ${errorMsg.slice(0, 40)}...`, "info");
    } else {
      logToTerminal(`[DIAGNOSE] Triaging error for ${service}...`, "info");
    }

    try {
      const response = await fetch("/api/diagnose", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          service: service,
          error_message: errorMsg,
          client_env: clientEnv,
        }),
      });

      const data = await response.json();
      btnDiagnose.disabled = false;
      btnDiagnose.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
        </svg>
        Run TShoot Diagnosis
      `;

      if (response.ok) {
        renderDiagnosisResult(data, clientEnv, errorMsg);
      } else {
        logToTerminal(`Diagnosis error: ${data.error || "Unknown"}`, "warn");
      }
    } catch (err) {
      btnDiagnose.disabled = false;
      btnDiagnose.innerHTML = `Run TShoot Diagnosis`;
      logToTerminal(`Network error contacting TShoot agent API`, "warn");
    }
  });

  function renderDiagnosisResult(data, clientEnv, errorMsg) {
    diagnosisTitle.textContent = data.diagnosis_title;
    rootCauseText.textContent = data.root_cause;

    if (data.is_web_search) {
      urgencyTag.textContent = "Internet Search Specialist";
      urgencyTag.className = "tag-badge tag-cyan";
    } else if (data.needs_escalation) {
      urgencyTag.textContent = "Requires Instructor";
      urgencyTag.className = "tag-badge tag-yellow";
    } else {
      urgencyTag.textContent = "Autonomous Resolution";
      urgencyTag.className = "tag-badge tag-green";
    }

    // Remediation steps
    remediationStepsList.innerHTML = "";
    if (data.recommended_steps && Array.isArray(data.recommended_steps)) {
      data.recommended_steps.forEach((step) => {
        const li = document.createElement("li");
        li.textContent = step;
        remediationStepsList.appendChild(li);
      });
    }

    // Sources list
    if (data.sources && Array.isArray(data.sources) && data.sources.length > 0) {
      sourcesList.innerHTML = "";
      data.sources.forEach((s) => {
        const a = document.createElement("a");
        a.className = "source-pill";
        a.href = s.url;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.innerHTML = `
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
            <polyline points="15 3 21 3 21 9"/>
            <line x1="10" y1="14" x2="21" y2="3"/>
          </svg>
          ${s.title}
        `;
        sourcesList.appendChild(a);
      });
      sourcesBox.classList.remove("hidden");
    } else {
      sourcesBox.classList.add("hidden");
    }

    // Code snippet
    if (data.code_snippet) {
      snippetContent.textContent = data.code_snippet;
      codeSnippetBox.classList.remove("hidden");
    } else {
      // Generate OS command
      fetchRemediationCommands(clientEnv, errorMsg);
    }

    // Show diagnosis and feedback sections
    diagnosisCard.classList.remove("hidden");
    solutionFeedbackSection.classList.remove("hidden");
    diagnosisCard.scrollIntoView({ behavior: "smooth" });

    logToTerminal(`[SUCCESS] Resolution ready: ${data.diagnosis_title}`, "success");
  }

  async function fetchRemediationCommands(clientEnv, errorMsg) {
    let osType = "windows";
    if (clientEnv.includes("macOS")) osType = "macos";
    if (clientEnv.includes("Linux")) osType = "linux";

    let category = "port_conflict";
    if (errorMsg.includes("10048") || errorMsg.includes("8000")) category = "port_conflict";
    else if (errorMsg.includes("auth") || errorMsg.includes("403")) category = "gcloud_auth";
    else category = "clean_venv";

    try {
      const cmdRes = await fetch("/api/remediation-commands", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ platform_os: osType, issue_category: category }),
      });
      const cmdData = await cmdRes.json();
      snippetContent.textContent = cmdData.commands;
      codeSnippetBox.classList.remove("hidden");
    } catch (e) {
      codeSnippetBox.classList.add("hidden");
    }
  }

  function resetFeedbackAndDeepCards() {
    solvedConfirmation.classList.add("hidden");
    deepInvestigationConsent.classList.add("hidden");
    deepInvestigationResults.classList.add("hidden");
    btnSolutionSolved.disabled = false;
    btnSolutionNotSolved.disabled = false;
  }

  // -------------------------------------------------------------------------
  // Interactive Feedback & Deep Investigation Loop
  // -------------------------------------------------------------------------
  btnSolutionSolved.addEventListener("click", () => {
    solvedConfirmation.classList.remove("hidden");
    deepInvestigationConsent.classList.add("hidden");
    deepInvestigationResults.classList.add("hidden");
    btnSolutionSolved.disabled = true;
    btnSolutionNotSolved.disabled = true;
    logToTerminal("🎉 Attendee confirmed issue is resolved! TShoot logged success.", "success");
  });

  btnSolutionNotSolved.addEventListener("click", () => {
    solvedConfirmation.classList.add("hidden");
    deepInvestigationConsent.classList.remove("hidden");
    deepInvestigationConsent.scrollIntoView({ behavior: "smooth" });
    logToTerminal("⚠️ Attendee reports issue still stuck. Requesting Deep Investigation consent.", "warn");
  });

  btnGrantDeepPermission.addEventListener("click", async () => {
    btnGrantDeepPermission.disabled = true;
    btnGrantDeepPermission.innerHTML = `<span class="pulse-dot"></span> Running Deep Autonomous Investigation...`;
    logToTerminal("[DEEP_INVESTIGATOR] Consent granted. Running 3-tier deep diagnostics...", "info");

    try {
      const res = await fetch("/api/deep-investigate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          error_message: lastDiagnosedError || errorMessageInput.value,
          service: lastDiagnosedService || serviceSelect.value,
          client_env: clientEnvSelect.value,
          previous_attempts: "Standard remediation steps were executed but attendee remains blocked.",
        }),
      });

      const data = await res.json();
      btnGrantDeepPermission.disabled = false;
      btnGrantDeepPermission.innerHTML = `Grant Permission & Run Deep Diagnostics`;

      if (res.ok) {
        deepInvId.textContent = data.investigation_id;
        deepAnalysisText.textContent = data.deep_analysis;

        // Render layers
        deepLayersContainer.innerHTML = "";
        data.layers.forEach((layer) => {
          const div = document.createElement("div");
          div.className = "deep-layer-item";
          div.innerHTML = `
            <div class="layer-title">${layer.layer_name}</div>
            <div class="layer-findings">${layer.findings}</div>
            <div class="layer-remediation">${layer.remediation}</div>
          `;
          deepLayersContainer.appendChild(div);
        });

        deepScriptContent.textContent = data.actionable_script;
        deepInvestigationConsent.classList.add("hidden");
        deepInvestigationResults.classList.remove("hidden");
        deepInvestigationResults.scrollIntoView({ behavior: "smooth" });

        logToTerminal(`[DEEP_INVESTIGATOR] Complete (${data.investigation_id}). Isolation scripts generated.`, "success");
      } else {
        logToTerminal(`Deep investigation failed: ${data.error || "Unknown"}`, "warn");
      }
    } catch (e) {
      btnGrantDeepPermission.disabled = false;
      btnGrantDeepPermission.innerHTML = `Grant Permission & Run Deep Diagnostics`;
      logToTerminal("Network error contacting deep investigator endpoint", "warn");
    }
  });

  btnDeepSolved.addEventListener("click", () => {
    deepInvestigationResults.innerHTML = `
      <div class="solved-success-msg">
        🎉 Deep Investigation Solved the Block! TShoot has confirmed your environment is healthy. Keep building!
      </div>
    `;
    logToTerminal("🎉 Deep Investigation successfully unblocked attendee!", "success");
  });

  if (btnOpenEscalateModal2) {
    btnOpenEscalateModal2.addEventListener("click", () => {
      escalateModal.classList.remove("hidden");
      document.getElementById("escalateSummary").value = lastDiagnosedError || errorMessageInput.value;
      document.getElementById("escalateCategory").value = lastDiagnosedService || serviceSelect.value;
      document.getElementById("escalateSteps").value = "Attempted standard fixes and Tier 1-3 Deep Autonomous isolation.";
    });
  }

  // -------------------------------------------------------------------------
  // Screenshot Upload & Visual Error Extraction
  // -------------------------------------------------------------------------
  function handleSelectedFile(file) {
    if (!file || !file.type.startsWith("image/")) {
      alert("Please upload a valid image file (PNG, JPG, or WEBP).");
      return;
    }

    if (file.size > 10 * 1024 * 1024) {
      alert("Image exceeds 10MB limit. Please upload a smaller screenshot.");
      return;
    }

    currentScreenshotName = file.name;
    previewFileName.textContent = file.name;
    previewFileSize.textContent = `${(file.size / 1024).toFixed(1)} KB`;

    const reader = new FileReader();
    reader.onload = (e) => {
      currentScreenshotBase64 = e.target.result;
      imagePreview.src = currentScreenshotBase64;
      dropZonePrompt.classList.add("hidden");
      imagePreviewContainer.classList.remove("hidden");
      btnAnalyzeScreenshot.disabled = false;
      logToTerminal(`Screenshot loaded: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`, "info");
    };
    reader.readAsDataURL(file);
  }

  // File input change
  screenshotFileInput.addEventListener("change", (e) => {
    if (e.target.files && e.target.files[0]) {
      handleSelectedFile(e.target.files[0]);
    }
  });

  // Drag & drop handlers
  screenshotDropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    screenshotDropZone.classList.add("drag-active");
  });
  screenshotDropZone.addEventListener("dragleave", () => {
    screenshotDropZone.classList.remove("drag-active");
  });
  screenshotDropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    screenshotDropZone.classList.remove("drag-active");
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleSelectedFile(e.dataTransfer.files[0]);
    }
  });

  // Global Clipboard paste (Ctrl+V) listener for screenshots
  window.addEventListener("paste", (e) => {
    const items = (e.clipboardData || e.originalEvent.clipboardData).items;
    for (const item of items) {
      if (item.type.indexOf("image") === 0) {
        const blob = item.getAsFile();
        const pastedFile = new File([blob], `pasted_error_${Date.now()}.png`, { type: blob.type });
        handleSelectedFile(pastedFile);
        logToTerminal("Screenshot pasted from clipboard (Ctrl+V)", "info");
        break;
      }
    }
  });

  // Remove preview button
  btnRemovePreview.addEventListener("click", (e) => {
    e.stopPropagation();
    currentScreenshotBase64 = null;
    currentScreenshotName = "";
    imagePreview.src = "";
    screenshotFileInput.value = "";
    imagePreviewContainer.classList.add("hidden");
    dropZonePrompt.classList.remove("hidden");
    btnAnalyzeScreenshot.disabled = true;
    screenshotResultCard.classList.add("hidden");
    logToTerminal("Screenshot cleared", "info");
  });

  // Analyze Screenshot API Call
  btnAnalyzeScreenshot.addEventListener("click", async () => {
    if (!currentScreenshotBase64) return;

    btnAnalyzeScreenshot.disabled = true;
    btnAnalyzeScreenshot.innerHTML = `<span class="pulse-dot"></span> Analyzing Visual Screenshot...`;
    logToTerminal(`[OCR / VISION] Extracting error signatures from ${currentScreenshotName}...`, "info");

    try {
      const res = await fetch("/api/analyze-screenshot", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          image_base64: currentScreenshotBase64,
          filename: currentScreenshotName,
          notes: screenshotNotesInput.value.trim(),
        }),
      });

      const data = await res.json();
      btnAnalyzeScreenshot.disabled = false;
      btnAnalyzeScreenshot.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
        </svg>
        Analyze Screenshot & Fetch Solution
      `;

      if (res.ok) {
        // Show result banner
        ssDetectedService.textContent = data.detected_service;
        ssExtractedText.textContent = data.extracted_error;
        ssStatusText.textContent = `Analyzed ${data.filename} (${data.dimensions}, ${data.format})`;
        screenshotResultCard.classList.remove("hidden");

        // Sync into diagnostic form
        errorMessageInput.value = data.extracted_error;
        if (serviceSelect.querySelector(`option[value="${data.detected_service}"]`)) {
          serviceSelect.value = data.detected_service;
        } else {
          serviceSelect.value = "Others";
        }

        // Render diagnosis
        if (data.diagnosis) {
          lastDiagnosedError = data.extracted_error;
          lastDiagnosedService = data.detected_service;
          resetFeedbackAndDeepCards();
          renderDiagnosisResult(data.diagnosis, clientEnvSelect.value, data.extracted_error);
        }

        logToTerminal(`[OCR / VISION] Detected: ${data.detected_service}. Root cause identified.`, "success");
      } else {
        logToTerminal(`Screenshot analysis error: ${data.error || "Unknown"}`, "warn");
      }
    } catch (err) {
      btnAnalyzeScreenshot.disabled = false;
      btnAnalyzeScreenshot.innerHTML = `Analyze Screenshot & Fetch Solution`;
      logToTerminal("Network error sending screenshot for analysis", "warn");
    }
  });

  // -------------------------------------------------------------------------
  // Copy Buttons
  // -------------------------------------------------------------------------
  btnCopySnippet.addEventListener("click", () => {
    navigator.clipboard.writeText(snippetContent.textContent);
    btnCopySnippet.textContent = "Copied!";
    setTimeout(() => {
      btnCopySnippet.textContent = "Copy Commands";
    }, 2000);
  });

  if (btnCopyDeepScript) {
    btnCopyDeepScript.addEventListener("click", () => {
      navigator.clipboard.writeText(deepScriptContent.textContent);
      btnCopyDeepScript.textContent = "Copied Script!";
      setTimeout(() => {
        btnCopyDeepScript.textContent = "Copy Script";
      }, 2000);
    });
  }

  // -------------------------------------------------------------------------
  // Check Connectivity
  // -------------------------------------------------------------------------
  btnCheckNetwork.addEventListener("click", async () => {
    btnCheckNetwork.disabled = true;
    btnCheckNetwork.textContent = "Testing...";
    logToTerminal("[NETWORK] Pinging accounts.google.com and GenAI socket endpoints...", "info");

    try {
      const res = await fetch("/api/connectivity", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const data = await res.json();
      btnCheckNetwork.disabled = false;
      btnCheckNetwork.textContent = "Ping Workshop Endpoints";

      connectivityRows.innerHTML = "";
      data.connectivity.forEach((item) => {
        const div = document.createElement("div");
        div.className = "conn-item";
        div.innerHTML = `
          <div>
            <div class="conn-name">${item.service}</div>
            <div class="conn-host">${item.host}</div>
          </div>
          <div class="conn-status ${item.reachable ? "ok" : "fail"}">
            ${item.reachable ? `✓ Reachable (${item.latency_ms}ms)` : `✗ Blocked`}
          </div>
        `;
        connectivityRows.appendChild(div);
      });

      connectivitySummaryBadge.textContent = data.summary;
      connectivityCard.classList.remove("hidden");
      logToTerminal(`[NETWORK] Reachability test complete: ${data.summary}`, "success");
    } catch (e) {
      btnCheckNetwork.disabled = false;
      btnCheckNetwork.textContent = "Ping Workshop Endpoints";
      logToTerminal("Failed to run connectivity check", "warn");
    }
  });

  // -------------------------------------------------------------------------
  // Escalation Modal
  // -------------------------------------------------------------------------
  btnOpenEscalateModal.addEventListener("click", () => {
    escalateModal.classList.remove("hidden");
    escalatedResultBox.classList.add("hidden");
    document.getElementById("escalateSummary").value = lastDiagnosedError || errorMessageInput.value;
    document.getElementById("escalateCategory").value = lastDiagnosedService || serviceSelect.value;
  });

  btnCloseEscalateModal.addEventListener("click", () => {
    escalateModal.classList.add("hidden");
  });

  escalateForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = {
      attendee_name: document.getElementById("escalateName").value,
      issue_category: document.getElementById("escalateCategory").value,
      error_summary: document.getElementById("escalateSummary").value,
      details: "Requires instructor / TA intervention during live session.",
      steps_attempted: document.getElementById("escalateSteps").value || "Self-troubleshooting tried",
      urgency: document.getElementById("escalateUrgency").value,
    };

    try {
      const res = await fetch("/api/escalate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();

      if (res.ok) {
        chatSnippetDisplay.textContent = data.chat_snippet;
        escalatedResultBox.classList.remove("hidden");
        logToTerminal(`[ESCALATE] Ticket #${data.ticket.ticket_id} generated for meeting chat`, "success");
      }
    } catch (err) {
      logToTerminal("Failed to generate escalation ticket", "warn");
    }
  });

  btnCopyChatSnippet.addEventListener("click", () => {
    navigator.clipboard.writeText(chatSnippetDisplay.textContent);
    btnCopyChatSnippet.textContent = "Copied to Clipboard!";
    setTimeout(() => {
      btnCopyChatSnippet.textContent = "Copy Message";
    }, 2000);
  });
});
