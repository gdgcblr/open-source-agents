# [Medicine research agent]

> [Multi-Agent Prescription Safety & Research Pipeline]

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Medication errors, missed drug-drug interactions, and contraindications in vulnerable demographics (e.g., pregnancy, renal failure, elderly patients) remain leading causes of preventable hospitalizations. Single-prompt AI systems frequently hallucinate clinical interactions or miss subtle drug label warnings.
- **Intended Users**: Healthtech developers, clinical informatics researchers, and digital health engineers building decision-support guardrails for e-prescribing and medication review platforms.

### Key Features
- **Multimodal OCR & Data Extraction**: Parses handwritten or printed prescription images and user notes into structured medication regimens and clinical patient profiles.
- **Authoritative OpenFDA Grounding**: Direct tool integration with the OpenFDA Drug Label API to pull official Boxed Warnings, contraindications, and documented drug-drug interactions.
- **Critic & Safety Guardrail Agent**: Dedicated reviewer agent that flags unrecommended or high-risk drugs with standardized triage labels (🔴 Critical vs. 🟡 Moderate).
- **Chronological Regimen Synthesis**: Generates intuitive, hour-by-hour medication schedules (morning, lunch, evening, bedtime) with dietary warnings (e.g., empty stomach, avoid dairy/grapefruit).


---

## Technical Stack

- **Language & Runtime**: Node.js 20+ / TypeScript 5+ (ES Modules)
- **Agent Framework / Core Library**: Google Agent Development Kit (@google/adk), Zod
- **Models**: Gemini 3.1 Flash Lite (gemini-3.1-flash-lite)
- **External APIs / Tools**: OpenFDA Drug Label API (https://api.fda.gov/drug/label.json)
---

## Architecture & Data Flow

The system employs a sequential multi-agent graph architecture orchestrated by Google ADK's Workflow and managed by InMemoryRunner:

## Architecture & Data Flow

The system runs as a directed graph workflow orchestrated by Google ADK's `Workflow` runtime. It embeds a 4-tier defense-in-depth guardrail system directly into the agent pipeline to prevent hallucinations, catch acute medical emergencies, enforce hard clinical limits, and protect patient privacy:

```text
[User Input: Prescription Image / Query + Patient Context]
                            │
                            ▼
 ┌───────────────────────────────────────────────────────────┐
 │ 1. preflight_triage_agent                                 │
 │    [🛡️ Guardrail 1: Emergency & PII Triage Tool]           │
 └──────────────────────────┬────────────────────────────────┘
                            │
             ┌──────────────┴──────────────┐
             │ (If Acute Emergency)        │ (If Cleared)
             ▼                             ▼
    🚨 Immediate ER/911 Bypass   ┌───────────────────────────┐
                                 │ 2. extractor_agent        │
                                 │    [🛡️ Guardrail 2: OCR   │
                                 │     Illegibility Check]   │
                                 └─────────────┬─────────────┘
                                               │
                                ┌──────────────┴──────────────┐
                                │ (If Confidence < 85%)       │ (If Legible)
                                ▼                             ▼
                       ⚠️ Pharmacist Review    ┌───────────────────────────┐
                          Safety Halt          │ 3. clinical_researcher    │
                                               │    [🛡️ Guardrail 3: Dose   │
                                               │     & Teratogen Validator] │
                                               │    [OpenFDA Label & DDI]   │
                                               └─────────────┬─────────────┘
                                                             │
                                                             ▼
                                               ┌───────────────────────────┐
                                               │ 4. safety_reviewer_agent  │
                                               │    (Anti-Hallucination    │
                                               │     Clinical Critic)      │
                                               └─────────────┬─────────────┘
                                                             │
                                                             ▼
                                               ┌───────────────────────────┐
                                               │ 5. care_planner_agent     │
                                               │    [🛡️ Guardrail 4: Assist │
                                               │     Language & Disclaimer] │
                                               └─────────────┬─────────────┘
                                                             │
                                                             ▼
                                               [Final Verified Care Plan]

```

## Pipeline Stages & Guardrails

1. **Pre-Flight Triage & Privacy (`preflight_triage_agent`)**:
   - **🛡️ Guardrail 1 (Emergency & PII Triage):** Deterministically scans queries for acute red-flag keywords (chest pain, shortness of breath, anaphylaxis, overdose). If detected, triggers an immediate `[EMERGENCY_HALT]` to direct the user to 911 / 112 without wasting LLM tokens. Concurrently flags unmasked SSNs and phone numbers under HIPAA/GDPR best practices.

2. **Perception & OCR (`extractor_agent`)**:
   - **🛡️ Guardrail 2 (OCR Confidence & Illegibility Check):** Transcribes handwriting, dosages, forms, and instructions into structured JSON. If the image is blurry, ambiguous, or confidence falls below 85%, halts execution with `[ILLEGIBLE_HALT]`, advising manual pharmacist verification to prevent medication errors.

3. **Clinical Grounding & Safety (`clinical_researcher_agent`)**:
   - **🛡️ Guardrail 3 (Deterministic Dose & Teratogen Validator):** Runs hard-coded physiological ceilings (e.g., Acetaminophen > 4,000 mg/day, Ibuprofen > 3,200 mg/day) and cross-checks known pregnancy-contraindicated drug classes (ACE inhibitors, ARBs, retinoids, warfarin).
   - **OpenFDA Regulatory Tools:** Queries live FDA drug monograph endpoints for official Boxed Warnings, contraindications, and drug-drug interactions (DDIs).

4. **Auditor & Critic (`safety_reviewer_agent`)**:
   - **Anti-Hallucination Grounding:** Enforces that only interactions and contraindications backed by deterministic tools or OpenFDA API receipts are flagged. Triages risks into 🔴 **CRITICAL ALERT**, 🟡 **MODERATE WARNING**, and 🟢 **CLEARED**.

5. **Regimen Synthesizer & Writer (`care_planner_agent`)**:
   - **🛡️ Guardrail 4 (Prescriptive Language Filter & Legal Disclaimer):** Converts findings into a 24-hour schedule (morning/lunch/bedtime) with dietary warnings. Enforces non-prescriptive, assistive advisory wording (*"Hold this medication and consult your doctor"* vs. direct orders), and automatically stamps the non-negotiable statutory medical disclaimer at the bottom.

## Prerequisites

Before running this project, ensure you have:
- **Node.js**: v20.0.0 or higher
- **Package Manager**: npm (v10+) or pnpm
- **Google AI Studio API Key**: A valid Gemini API key with access to gemini-2.5-flash
- **(Optional) OpenFDA API Key**: OpenFDA provides public access without an API key (up to 240 req/min), but a free key unlocks 1,000 req/min.

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd agents/medicine-agent
   ```

2. **Install project dependencies:**
   
   ```bash
     npm install
   ```

3. **Configure Environment Variables:**
   Create a .env file in the root directory:
   ```bash
   cp .env.example .env
   ```
   Add your API credentials:
   ```bash
   GOOGLE_GENAI_API_KEY=your_gemini_api_key_here
   OPENFDA_API_KEY=your_optional_openfda_key_here
   ```
---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GOOGLE_GENAI_API_KEY` | Yes | *None* | Google Gemini API key used by ADK agents |
| `MODEL_NAME` | No | `gemini-2.5-flash` | Identifier for the LLM model to use |
| `OPENFDA_API_KEY` | No | *None* | Multimodal model utilized by all pipeline agents |

---

## How to Run

Provide the exact command(s) to run the agent or tool:

```bash
npx adk web
```

---

## Example Input & Output

### Example 1: Prescription Analysis with Contraindications (Multimodal)

#### Input
- **Uploaded Image**: `sample_prescription.jpg` (Contains: *Lisinopril 10mg once daily* and *Ibuprofen 400mg every 6 hours as needed*)
- **User Prompt**:
  ```text
  "Please evaluate this prescription for a 29-year-old female patient in her 2nd trimester of pregnancy with hypertension."

### Example Output
[preflight_triage_agent]: [PROCEED_TO_EXTRACTION] Input cleared for prescription processing.
[extractor_agent]: Confidence Score: 96%. Extracted Lisinopril 10mg QD, Ibuprofen 400mg Q6H PRN.
[clinical_researcher_agent]: Grounded OpenFDA warnings and deterministic clinical checks completed.

==================================================
📋 CLINICAL MEDICATION AUDIT & REGIMEN
==================================================

🔴 CRITICAL ALERT: MEDICATIONS NOT RECOMMENDED
- Lisinopril 10mg Oral Tablet (CONTRAINDICATED IN PREGNANCY)
  - Deterministic Teratogen Guardrail: ACE inhibitors are strictly contraindicated during pregnancy due to high risk of fetal toxicity, malformations, and fetal demise.
  - FDA Boxed Warning: Discontinue as soon as possible when pregnancy is detected.
  - Action: DO NOT TAKE. Immediately contact your prescriber for pregnancy-safe alternatives (e.g., Labetalol, Methyldopa).

- Ibuprofen 400mg Oral Tablet (CAUTION IN 2ND/3RD TRIMESTER)
  - FDA Warning: NSAID use around 20 weeks gestation or later may cause rare kidney problems in the fetus, oligohydramnios, and premature closure of the ductus arteriosus.
  - Action: Hold medication and discuss alternative pain management with your OB-GYN.

--------------------------------------------------
📅 24-HOUR MEDICATION SCHEDULE
--------------------------------------------------
All current prescription items are on safety hold due to pregnancy contraindications. 
Do not start this regimen until cleared by your licensed healthcare provider.
---
⚠️ **Medical Disclaimer:** This analysis is an AI synthesis grounded on OpenFDA regulatory data for educational and research support only. It does not constitute medical advice or a formal prescription review. Always consult your licensed physician or pharmacist before starting, changing, or discontinuing any medication.

---

### Example 2: Pre-Flight Emergency Triage (Guardrail 1 Bypass)

"I took my blood pressure medication an hour ago and now I have severe chest pain and trouble breathing."

### Example Output
🚨 CRITICAL EMERGENCY DETECTED (CHEST PAIN): This system is an informational research agent and cannot triage acute medical emergencies. Please call emergency dispatch (911 / 112) or go to the nearest Emergency Room immediately.

## How to Test

Verify that all agents, guardrails, and OpenFDA tools function properly using the built-in ADK Web interface:

1. **Start the ADK Web Environment:**
   ```bash
   npx adk web
  

Open [http://localhost:8000](http://localhost:8000) in your browser.

- **Test Guardrail 1 (Emergency Bypass):**
  - **Type:** `"I have severe chest pain and shortness of breath."`
  - **Expected Result:** Immediate `🚨 CRITICAL EMERGENCY DETECTED` response. The pipeline halts and skips all OpenFDA tool calls.

- **Test Guardrail 2 (OCR Illegibility Check):**
  - **Action:** Upload an intentionally blurry, unreadable, or corrupted image.
  - **Expected Result:** `extractor_agent` outputs `[ILLEGIBLE_HALT] ⚠️ PRESCRIPTION AMBIGUOUS / UNCLEAR` and prompts for manual pharmacist verification.

- **Test Guardrail 3 (Deterministic Dosage Ceiling):**
  - **Type:** `"My doctor told me to take Ibuprofen 1000mg 4 times a day for back pain."` (Total: 4,000 mg/day).
  - **Expected Result:** Open the **Traces / Events** tab in `adk web`. Observe `verifySafeDosageCeiling` execute and return:  
    `🔴 DOSAGE CEILING EXCEEDED: ibuprofen at 4000mg/day exceeds the absolute clinical safe ceiling of 3200mg/day.`

- **Test Guardrail 4 (Statutory Disclaimer & Assistive Language):**
  - **Action:** Enter any standard prescription query.
  - **Expected Result:** Verify the output uses assistive phrasing (*"Hold this medication and review with your prescriber"*) and finishes with the verbatim **Medical Disclaimer** banner.
  

## Known Limitations

- **Brand vs. Generic Resolution**: OpenFDA drug monographs index most reliably by active pharmaceutical ingredient (generic chemical name). Obscure trade names or multi-component combination drugs may fail label lookup if the extractor cannot resolve the underlying active molecules.
- **Handwriting Ambiguity Threshold**: Severe doctor handwriting illegibility will intentionally trigger `[ILLEGIBLE_HALT]`. The system prioritizes false-negative halts over misreading dangerous dosages (e.g., misreading 10mg as 70mg).
- **Not a Diagnostic Device (SaMD)**: The agent audits packaged label warnings and hard dosage ceilings. It does not evaluate patient-specific laboratory values (e.g., eGFR, serum creatinine, liver enzymes) or active therapeutic drug monitoring (TDM).
- **Public Rate Limits**: The OpenFDA API limits anonymous calls to 240 requests/minute. For high-volume multi-agent interaction checks, configure an `OPENFDA_API_KEY` in `.env` to unlock 1,000 requests/minute.

---

## Security & Privacy Considerations

- **Secrets Handling**: API keys (`GOOGLE_GENAI_API_KEY` and optional `OPENFDA_API_KEY`) are managed exclusively through environment variables via `dotenv` and `config.ts`. No secrets or tokens are checked into version control (`.gitignore` enforced).
- **Data Privacy & PHI (HIPAA / GDPR)**: Guardrail 1 programmatically scans for sensitive personal identifiers (SSNs, National IDs, phone numbers) to flag unmasked records. In clinical production, client-side de-identification should scrub patient names from images before transmitting to external multimodal model endpoints.
- **Sandboxed Execution & Tool Safety**: The agents execute zero arbitrary system commands or shell scripts. All tools (`FunctionTool`) are deterministic TypeScript modules restricted to mathematical threshold validation and read-only HTTP GET requests to the official US FDA REST API.

## Future Improvements

- [ ] Add caching for external API responses.
- [ ] Support local models via Ollama.

---

## License
*This project is contributed under the repository's open-source license.*
