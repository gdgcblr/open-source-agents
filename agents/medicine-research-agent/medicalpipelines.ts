import { LlmAgent, Workflow, FunctionTool } from '@google/adk';
import { z } from 'zod';
import { MODEL_NAME } from './config.js';
import { openFdaDrugSafetyTool, openFdaInteractionCheckerTool } from './openFdaTools.js';

// ========================================================
// 🛡️ GUARDRAIL 1: EMERGENCY & PII TRIAGE TOOL
// ========================================================
const EMERGENCY_KEYWORDS = [
  'chest pain', 'shortness of breath', 'difficulty breathing',
  'swollen tongue', 'throat swelling', 'anaphylaxis', 'suicide',
  'overdose', 'unconscious', 'severe bleeding'
];

// Regex for SSNs (XXX-XX-XXXX) and 10-digit phone numbers
const PII_SSN_REGEX = /\b\d{3}-\d{2}-\d{4}\b/;
const PII_PHONE_REGEX = /\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b/;

const triageAndPiiGuardrailTool = new FunctionTool({
  name: 'triageAndPiiGuardrail',
  description: 'Pre-flight check for acute emergencies and sensitive PII (SSN, Phone Numbers).',
  parameters: z.object({
    userInputText: z.string().describe('User input text'),
  }),
  execute: async ({ userInputText }) => {
    // 1. Emergency Check
    const lower = userInputText.toLowerCase();
    for (const keyword of EMERGENCY_KEYWORDS) {
      if (lower.includes(keyword)) {
        return {
          status: 'EMERGENCY_HALT',
          message: `🚨 CRITICAL EMERGENCY DETECTED (${keyword.toUpperCase()}): This system cannot triage acute medical emergencies. Call 911 / 112 or visit the nearest Emergency Room immediately.`,
        };
      }
    }

    // 2. PII Detection Check
    const hasSSN = PII_SSN_REGEX.test(userInputText);
    const hasPhone = PII_PHONE_REGEX.test(userInputText);
    if (hasSSN || hasPhone) {
      return {
        status: 'PII_WARNING',
        message: '⚠️ PRIVACY NOTICE: Sensitive identifiers (SSN or contact numbers) detected and flagged for masking under HIPAA/GDPR best practices.',
      };
    }

    return { status: 'SAFE_TO_PROCEED', message: 'No acute emergency or exposed high-risk identifiers detected.' };
  },
});

// ========================================================
// 🛡️ GUARDRAIL 3: DETERMINISTIC DOSE & TERATOGEN VALIDATOR
// ========================================================
const MAX_DAILY_DOSES_MG: Record<string, number> = {
  acetaminophen: 4000, paracetamol: 4000, ibuprofen: 3200,
  aspirin: 4000, metformin: 2550, lisinopril: 80, amoxicillin: 3000,
};

// Known absolute teratogens / FDA pregnancy category X or D contraindications
const KNOWN_TERATOGENS = [
  'lisinopril', 'losartan', 'enalapril', 'valsartan', // ACEi / ARBs
  'isotretinoin', 'methotrexate', 'warfarin', 'valproate', 'finasteride'
];

const deterministicClinicalValidatorTool = new FunctionTool({
  name: 'deterministicClinicalValidator',
  description: 'Deterministic clinical guardrail: checks hard dosage ceilings and absolute pregnancy contraindications.',
  parameters: z.object({
    drugName: z.string().describe('Active pharmaceutical ingredient'),
    totalDailyMg: z.number().optional().describe('Total calculated daily dose in mg'),
    isPregnant: z.boolean().default(false).describe('Whether patient is confirmed pregnant'),
  }),
  execute: async ({ drugName, totalDailyMg, isPregnant }) => {
    const key = drugName.toLowerCase().trim();
    const violations: string[] = [];

    // 1. Teratogen Guardrail
    if (isPregnant) {
      const isContraindicated = KNOWN_TERATOGENS.some(t => key.includes(t));
      if (isContraindicated) {
        violations.push(`🔴 CRITICAL TERATOGEN CONTRAINDICATION: ${drugName.toUpperCase()} is strictly contraindicated during pregnancy due to high risk of fetal toxicity and malformations.`);
      }
    }

    // 2. Dosage Ceiling Guardrail
    const maxAllowed = MAX_DAILY_DOSES_MG[key];
    if (maxAllowed && totalDailyMg && totalDailyMg > maxAllowed) {
      violations.push(`🔴 DOSAGE CEILING EXCEEDED: ${drugName} at ${totalDailyMg}mg/day exceeds the absolute clinical safe ceiling of ${maxAllowed}mg/day.`);
    }

    if (violations.length > 0) {
      return { safe: false, severity: 'CRITICAL', violations };
    }

    return { safe: true, message: `${drugName} passed deterministic dosage and pregnancy safety filters.` };
  },
});

// ========================================================
// AGENTS SETUP
// ========================================================

// 🛡️ AGENT 1: PRE-FLIGHT TRIAGE & PII GATEKEEPER
export const triageAgent = new LlmAgent({
  name: 'preflight_triage_agent',
  model: MODEL_NAME,
  tools: [triageAndPiiGuardrailTool],
  instruction: `You are the Pre-Flight Emergency & Privacy Gatekeeper.
1. Call "triageAndPiiGuardrail" on the user's input.
2. If status is "EMERGENCY_HALT": Output ONLY the alert message prefixed with "[EMERGENCY_HALT]".
3. Otherwise, pass forward: "[PROCEED_TO_EXTRACTION]".`,
});

// 🛡️ AGENT 2: OCR EXTRACTOR + ILLEGIBILITY / CONFIDENCE GUARDRAIL
export const extractorAgent = new LlmAgent({
  name: 'extractor_agent',
  model: MODEL_NAME,
  instruction: `You are an expert Medical OCR & Prescription Transcriber with an embedded ILLEGIBILITY GUARDRAIL.
If the previous agent triggered "[EMERGENCY_HALT]", halt immediately and repeat the emergency alert.

🛡️ GUARDRAIL 2: ILLEGIBILITY & CONFIDENCE CHECK:
Evaluate the clarity of the prescription image or text.
- If the prescription image is too blurry, handwriting is ambiguous, or drug name/dosage cannot be verified with >85% confidence:
  Output ONLY:
  "[ILLEGIBLE_HALT] ⚠️ PRESCRIPTION AMBIGUOUS / UNCLEAR: Handwriting or image resolution is insufficient to safely confirm drug names or dosages. To prevent medication errors, please have this prescription verified manually by a licensed pharmacist."

Otherwise, output structured JSON:
{
  "confidenceScore": number (0-100),
  "patientProfile": { "age": number | null, "conditions": string[], "pregnant": boolean, "allergies": string[] },
  "extractedMedications": [{ "drugName": string, "dosage": string, "frequency": string, "dailyMg": number }]
}`,
});

// 🛡️ AGENT 3: PHARMACOLOGIST RESEARCHER (OpenFDA + Deterministic Validator)
export const clinicalResearcherAgent = new LlmAgent({
  name: 'clinical_researcher_agent',
  model: MODEL_NAME,
  tools: [openFdaDrugSafetyTool, openFdaInteractionCheckerTool, deterministicClinicalValidatorTool],
  instruction: `You are a Clinical Pharmacologist Agent backed by OpenFDA and deterministic clinical safety filters.
If "[EMERGENCY_HALT]" or "[ILLEGIBLE_HALT]" is active, halt and pass it forward.

Otherwise:
1. For each medication, call "deterministicClinicalValidator" passing the drugName, dailyMg, and isPregnant.
2. Call "openFdaDrugSafetyLookup" for each drug for Boxed Warnings and Contraindications.
3. Call "openFdaInteractionChecker" for drug pairs.
4. Synthesize all verified warnings.`,
});

// AGENT 4: SAFETY REVIEWER & CRITIC
export const safetyReviewerAgent = new LlmAgent({
  name: 'safety_reviewer_agent',
  model: MODEL_NAME,
  instruction: `You are the Lead Safety Reviewer and Medical Guardrail.
If "[EMERGENCY_HALT]" or "[ILLEGIBLE_HALT]" is active, pass it forward.

Enforce anti-hallucination: Only validate warnings that were confirmed by OpenFDA or the deterministic validator.
Group alerts into 🔴 [CRITICAL ALERT: NOT RECOMMENDED], 🟡 [MODERATE WARNING], and 🟢 [CLEARED].`,
});

// 🛡️ AGENT 5: CARE PLANNER + LANGUAGE FILTER & DISCLAIMER
export const carePlannerAgent = new LlmAgent({
  name: 'care_planner_agent',
  model: MODEL_NAME,
  instruction: `You are a Patient Care Planning Specialist.
If an "[EMERGENCY_HALT]" or "[ILLEGIBLE_HALT]" is present, output only that halt message.

Otherwise:
1. Synthesize an actionable 24-hour schedule (Morning, Lunch, Dinner, Bedtime).
2. Group medications into "✅ Cleared to Take" vs "❌ On Hold / Not Recommended".

🛡️ GUARDRAIL 4: PRESCRIPTIVE LANGUAGE & STATUTORY DISCLAIMER:
- Do NOT prescribe or diagnose ("You have disease X" or "I order you to discontinue").
- Use assistive language: "Hold this medication and review this potential contraindication with your prescribing physician."
- You MUST append this verbatim disclaimer at the bottom:

---
⚠️ **Medical Disclaimer:** This analysis is an AI synthesis grounded on OpenFDA regulatory data for educational and research support only. It does not constitute medical advice or a formal prescription review. Always consult your licensed physician or pharmacist before starting, changing, or discontinuing any medication.`,
});

// ========================================================
// GRAPH WORKFLOW EXPORT
// ========================================================
export const prescriptionResearchWorkflow = new Workflow({
  name: 'prescription_research_workflow',
  description: 'Full multi-agent pipeline with all 4 clinical guardrails embedded.',
  edges: [
    [
      'START',
      triageAgent,              // 🛡️ Guardrail 1: Emergency & PII Triage
      extractorAgent,           // 🛡️ Guardrail 2: OCR & Illegibility Check
      clinicalResearcherAgent,  // 🛡️ Guardrail 3: Deterministic Dose & Teratogen Validator
      safetyReviewerAgent,      // Auditor
      carePlannerAgent,         // 🛡️ Guardrail 4: Assistive Language & Disclaimer
    ],
  ],
});