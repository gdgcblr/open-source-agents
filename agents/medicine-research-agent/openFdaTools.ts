import { FunctionTool } from '@google/adk';
import { z } from 'zod';

const OPENFDA_BASE_URL = 'https://api.fda.gov/drug/label.json';

/**
 * Truncates long label sections so they don't blow up the LLM token window.
 */
function truncateText(textArr: string[] | undefined, maxLength = 800): string {
  if (!textArr || textArr.length === 0) return 'None documented.';
  const combined = textArr.join(' ');
  return combined.length > maxLength
    ? combined.slice(0, maxLength) + '... [Truncated for brevity]'
    : combined;
}

/**
 * Tool 1: Lookup official FDA monograph (Black Box, Contraindications, Pregnancy)
 */
export const openFdaDrugSafetyTool = new FunctionTool({
  name: 'openFdaDrugSafetyLookup',
  description:
    'Retrieves official FDA drug label safety data including Black Box warnings, contraindications, and pregnancy risks.',
  parameters: z.object({
    drugName: z.string().describe('Generic or brand name of the drug, e.g., "lisinopril" or "warfarin"'),
  }),
  execute: async ({ drugName }) => {
    try {
      const cleanName = drugName.trim().toLowerCase();
      // Search generic or brand name
      const query = `(openfda.generic_name:"${cleanName}"+openfda.brand_name:"${cleanName}")`;
      const url = `${OPENFDA_BASE_URL}?search=${encodeURIComponent(query)}&limit=1`;

      const response = await fetch(url);

      if (!response.ok) {
        if (response.status === 404) {
          return {
            status: 'not_found',
            message: `No FDA label found for "${drugName}". Ensure spelling is correct or try the active ingredient.`,
          };
        }
        return {
          status: 'error',
          message: `OpenFDA API error: HTTP ${response.status}`,
        };
      }

      const data = await response.json();
      const label = data.results?.[0];

      if (!label) {
        return { status: 'not_found', message: `No records found for ${drugName}.` };
      }

      return {
        status: 'success',
        drugName,
        boxedWarning: truncateText(label.boxed_warning),
        contraindications: truncateText(label.contraindications),
        pregnancyWarnings: truncateText(label.pregnancy || label.pregnancy_or_breast_feeding),
        warningsAndPrecautions: truncateText(label.warnings_and_cautions || label.warnings),
      };
    } catch (error: any) {
      return {
        status: 'error',
        message: `Failed to query OpenFDA: ${error.message}`,
      };
    }
  },
});

/**
 * Tool 2: Check specifically if Drug A mentions Drug B in its FDA Drug Interactions section
 */
export const openFdaInteractionCheckerTool = new FunctionTool({
  name: 'openFdaInteractionChecker',
  description:
    'Queries OpenFDA to check if Drug A officially lists Drug B in its drug interactions section.',
  parameters: z.object({
    primaryDrug: z.string().describe('The primary drug name to inspect'),
    interactingDrug: z.string().describe('The candidate interacting drug to search for inside the label'),
  }),
  execute: async ({ primaryDrug, interactingDrug }) => {
    try {
      const prim = primaryDrug.trim().toLowerCase();
      const sec = interactingDrug.trim().toLowerCase();

      // Query: Primary drug label where drug_interactions section contains the secondary drug name
      const query = `(openfda.generic_name:"${prim}"+openfda.brand_name:"${prim}")+AND+drug_interactions:"${sec}"`;
      const url = `${OPENFDA_BASE_URL}?search=${encodeURIComponent(query)}&limit=1`;

      const response = await fetch(url);

      if (response.status === 404) {
        return {
          interactionDocumented: false,
          summary: `No official FDA interaction section in ${primaryDrug}'s label explicitly documents ${interactingDrug}.`,
        };
      }

      const data = await response.json();
      const label = data.results?.[0];

      return {
        interactionDocumented: true,
        primaryDrug,
        interactingDrug,
        interactionText: truncateText(label?.drug_interactions, 1000),
      };
    } catch (error: any) {
      return {
        interactionDocumented: false,
        error: `Could not verify interaction: ${error.message}`,
      };
    }
  },
});