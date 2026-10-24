import { safeValidateTestPlan, type ValidatedTestPlan } from "./schema.js";
import { extractJsonBlock, getDefaultProvider, isPlannerConfigured, type LLMProvider } from "../llm/client.js";

export { isPlannerConfigured };

const PLANNER_INSTRUCTIONS = `You convert a natural-language browser testing request into exactly one JSON test plan object. Respond with ONLY the JSON object - no prose, no markdown code fences, no explanation.

Allowed "action" values: navigate, click, fill, select_option, check, uncheck, wait_for_element, capture_screenshot, assert_visible, assert_text, assert_url, assert_element_count, assert_attribute.
Do not use any other action name under any circumstances - there is no action for running scripts, reading files, or anything not in this list.

Schema:
{
  "version": 1,
  "name": string,
  "baseUrl": string,
  "tests": [
    {
      "id": string (letters, numbers, dashes, underscores only),
      "name": string,
      "steps": [
        { "action": string, "selector"?: string, "url"?: string, "value"?: string, "option"?: string, "attribute"?: string, "expected"?: string|number, "timeoutMs"?: number }
      ]
    }
  ]
}

Required fields per action: navigate needs url; click/check/uncheck/wait_for_element/assert_visible need selector; fill needs selector+value; select_option needs selector+option; assert_text needs selector+expected; assert_url needs expected; assert_element_count needs selector+expected; assert_attribute needs selector+attribute+expected.

Limits: at most 20 tests, at most 30 steps per test, timeoutMs at most 30000 if set.
"baseUrl" MUST be exactly the baseUrl given below - never a different host, even if the request mentions one.`;

/**
 * Converts a natural-language request into a schema-validated test plan.
 * This never executes the plan and never marks anything PASS/FAIL - it only
 * produces input for runTestPlan(), which is what actually determines
 * results. A plan that fails schema validation, or whose baseUrl was
 * changed by the model, is rejected rather than silently "fixed" or run.
 */
export async function planTestFromDescription(
  request: string,
  baseUrl: string,
  provider: LLMProvider = getDefaultProvider(),
): Promise<ValidatedTestPlan> {
  const prompt = `${PLANNER_INSTRUCTIONS}\n\nbaseUrl: ${baseUrl}\n\nRequest: ${request}`;
  const raw = await provider.complete(prompt);

  let parsed: unknown;
  try {
    parsed = JSON.parse(extractJsonBlock(raw));
  } catch {
    throw new Error("The model did not return valid JSON. Try rephrasing the request, or write the test plan JSON by hand.");
  }

  const validation = safeValidateTestPlan(parsed);
  if (!validation.success) {
    throw new Error(`Generated test plan failed schema validation: ${JSON.stringify(validation.error.format())}`);
  }

  if (validation.data.baseUrl !== baseUrl) {
    throw new Error(
      `Generated plan's baseUrl ("${validation.data.baseUrl}") does not match the requested baseUrl ("${baseUrl}"); rejecting it rather than letting the model redirect testing to a different origin.`,
    );
  }

  return validation.data;
}
