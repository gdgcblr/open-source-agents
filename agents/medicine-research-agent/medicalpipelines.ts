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

const PII_SSN_REGEX = /\b\d{3}-\d{2}-\d{4}\b/;
const PII_PHONE_REGEX = /\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b/;

const triageAndPiiGuardrailTool = new FunctionTool({
  name: 'triageAndPiiGuardrail',
  description: 'Pre-flight check for acute medical emergencies and sensitive PII in user text.',
  parameters: z.object({
    userInputText: z
      .string()
      .optional()
      .default('')
      .describe('User text message. Pass empty string if only an image was attached.'),
  }),
  execute: async ({ userInputText = '' }) => {
    if (!userInputText || userInputText.trim() === '') {
      return { 
        status: 'SAFE_TO_PROCEED', 
        message: 'No text provided (direct prescription image upload). Cleared for OCR.' 
      };
    }

    const lower = userInputText.toLowerCase();
    for (const keyword of EMERGENCY_KEYWORDS) {
      if (lower.includes(keyword)) {
        return {
          status: 'EMERGENCY_HALT',
          message: `🚨 CRITICAL EMERGENCY DETECTED (${keyword.toUpperCase()}): This system cannot triage acute medical emergencies. Call 911 / 112 or visit the nearest Emergency Room immediately.`,
        };
      }
    }

    const hasSSN = PII_SSN_REGEX.test(userInputText);
    const hasPhone = PII_PHONE_REGEX.test(userInputText);
    if (hasSSN || hasPhone) {
      return {
        status: 'PII_WARNING',
        message: '⚠️ PRIVACY NOTICE: Sensitive identifiers detected and flagged for masking.',
      };
    }

    return { status: 'SAFE_TO_PROCEED', message: 'No emergency detected. Cleared to process prescription.' };
  },
});

// ========================================================
// 🛡️ GUARDRAIL 3: DETERMINISTIC DOSE & TERATOGEN VALIDATOR
// ========================================================
const MAX_DAILY_DOSES_MG: Record<string, number> = {
  acetaminophen: 4000, paracetamol: 4000, ibuprofen: 3200,
  aspirin: 4000, metformin: 2550, lisinopril: 80, amoxicillin: 3000,
};

const KNOWN_TERATOGENS = [
  'lisinopril', 'losartan', 'enalapril', 'valsartan',
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

    // Teratogen Guardrail
    if (isPregnant) {
      const isContraindicated = KNOWN_TERATOGENS.some(t => key.includes(t));
      if (isContraindicated) {
        violations.push(`🔴 CRITICAL TERATOGEN CONTRAINDICATION: ${drugName.toUpperCase()} is strictly contraindicated during pregnancy due to high risk of fetal toxicity and malformations.`);
      }
    }

    // Dosage Ceiling Guardrail
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
// NODE 1: INTAKE & OCR EXTRACTOR (Direct Image Receiver)
// ========================================================
export const extractorAgent = new LlmAgent({
  name: 'extractor_agent',
  model: MODEL_NAME,
  tools: [triageAndPiiGuardrailTool],
  instruction: `You are an expert Medical OCR & Clinical Intake Specialist.

YOUR TASKS IN ORDER:
1. 🛡️ PRE-FLIGHT CHECK:
   Call "triageAndPiiGuardrail" ONCE passing the user's text prompt (or "" if they only uploaded an image).
   If the tool returns status "EMERGENCY_HALT":
   Output ONLY: "[EMERGENCY_HALT] " followed by the alert message, and STOP immediately.

2. 📷 MULTIMODAL PRESCRIPTION READING:
   Examine the attached prescription image carefully.
   Transcribe the doctor's handwriting, clinic details, patient info, drug names, strengths, dosages, and instructions.

3. 🛡️ ILLEGIBILITY GUARDRAIL:
   ONLY if the image is completely pitch black, corrupted, or not a prescription at all, output:
   "[ILLEGIBLE_HALT] ⚠️ PRESCRIPTION AMBIGUOUS / UNCLEAR: Image resolution is insufficient. Please have this verified manually by a pharmacist."

4. 📋 STRUCTURED OUTPUT:
   If legible, output structured JSON with the extracted details:
   \`\`\`json
   {
     "confidenceScore": 95,
     "patientProfile": {
       "age": number or null,
       "conditions": string[],
       "pregnant": boolean,
       "allergies": string[]
     },
     "extractedMedications": [
       { "drugName": string, "dosage": string, "frequency": string, "dailyMg": number }
     ]
   }
   \`\`\`
   Pass this structured JSON forward for clinical research.`,
});

// ========================================================
// NODE 2: CLINICAL PHARMACOLOGIST (OpenFDA + Guardrail 3)
// ========================================================
export const clinicalResearcherAgent = new LlmAgent({
  name: 'clinical_researcher_agent',
  model: MODEL_NAME,
  tools: [openFdaDrugSafetyTool, openFdaInteractionCheckerTool, deterministicClinicalValidatorTool],
  instruction: `You are a Clinical Pharmacologist Agent backed by OpenFDA and deterministic clinical safety filters.
If "[EMERGENCY_HALT]" or "[ILLEGIBLE_HALT]" is in the previous output, pass it through and do NOT call any tools.

Otherwise:
1. Look at the JSON extracted by the extractor_agent.
2. For each medication:
   - Call "deterministicClinicalValidator" passing the drugName, dailyMg, and isPregnant.
   - Call "openFdaDrugSafetyLookup" for Boxed Warnings and Contraindications.
3. Call "openFdaInteractionChecker" for medication pairs.
4. Summarize all findings clearly with citations from OpenFDA and the clinical validator.`,
});

// ========================================================
// NODE 3: SAFETY REVIEWER & CRITIC
// ========================================================
export const safetyReviewerAgent = new LlmAgent({
  name: 'safety_reviewer_agent',
  model: MODEL_NAME,
  instruction: `You are the Lead Safety Reviewer and Medical Guardrail.
If "[EMERGENCY_HALT]" or "[ILLEGIBLE_HALT]" is active, pass it through.

Anti-Hallucination Guardrail:
- Only validate warnings that were confirmed by OpenFDA or the deterministic validator tools.
- Triage findings into:
  - 🔴 [CRITICAL ALERT: NOT RECOMMENDED]
  - 🟡 [MODERATE WARNING]
  - 🟢 [CLEARED]`,
});

// ========================================================
// NODE 4: CARE PLANNER + 🛡️ STATUTORY DISCLAIMER
// ========================================================
export const carePlannerAgent = new LlmAgent({
  name: 'care_planner_agent',
  model: MODEL_NAME,
  instruction: `You are a Patient Care Planning Specialist.
If an "[EMERGENCY_HALT]" or "[ILLEGIBLE_HALT]" is present, output only that halt message.

Otherwise:
1. Synthesize an actionable 24-hour schedule (Morning, Lunch, Dinner, Bedtime).
2. Group medications clearly into "✅ Cleared to Take" vs "❌ On Hold / Not Recommended".
3. Use assistive language: "Hold this medication and review with your prescriber."

🛡️ MANDATORY LEGAL DISCLAIMER:
You MUST append the following exact markdown block at the absolute end of your response, verbatim:

---
⚠️ **Medical Disclaimer:** This analysis is an AI synthesis grounded on OpenFDA regulatory data for educational and research support only. It does not constitute medical advice or a formal prescription review. Always consult your licensed physician or pharmacist before starting, changing, or discontinuing any medication.`,
});

// ========================================================
// GRAPH WORKFLOW EXPORT (4-Stage Pipeline)
// ========================================================
export const prescriptionResearchWorkflow = new Workflow({
  name: 'prescription_research_workflow',
  description: 'Full multi-agent pipeline with all 4 clinical guardrails embedded.',
  edges: [
    [
      'START',
      extractorAgent,           // 1. Receives file directly + Runs Guardrail 1 & 2
      clinicalResearcherAgent,  // 2. Runs Guardrail 3 (Doses/Teratogens) + OpenFDA
      safetyReviewerAgent,      // 3. Grounding critic
      carePlannerAgent,         // 4. Care plan + Guardrail 4 (Disclaimer)
    ],
  ],
});