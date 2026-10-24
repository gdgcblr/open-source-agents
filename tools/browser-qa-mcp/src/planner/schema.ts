import { z } from "zod";

/**
 * Supported browser actions (P0). Deliberately excludes arbitrary JS execution,
 * filesystem access, or any unrestricted browser command per the project's
 * security requirements.
 */
const ACTION_TYPES = [
  "navigate",
  "click",
  "fill",
  "select_option",
  "check",
  "uncheck",
  "wait_for_element",
  "capture_screenshot",
] as const;

const ASSERTION_TYPES = [
  "assert_visible",
  "assert_text",
  "assert_url",
  "assert_element_count",
  "assert_attribute",
] as const;

export const STEP_TYPES = [...ACTION_TYPES, ...ASSERTION_TYPES] as const;

export type StepType = (typeof STEP_TYPES)[number];

export const MAX_TESTS_PER_PLAN = 20;
export const MAX_STEPS_PER_TEST = 30;
export const MAX_STEP_TIMEOUT_MS = 30_000;
export const DEFAULT_STEP_TIMEOUT_MS = 5_000;

// Fields each action requires, so a plan missing them is rejected before execution
// rather than failing with an opaque Playwright error mid-run.
const REQUIRED_FIELDS: Record<StepType, string[]> = {
  navigate: ["url"],
  click: ["selector"],
  fill: ["selector", "value"],
  select_option: ["selector", "option"],
  check: ["selector"],
  uncheck: ["selector"],
  wait_for_element: ["selector"],
  capture_screenshot: [],
  assert_visible: ["selector"],
  assert_text: ["selector", "expected"],
  assert_url: ["expected"],
  assert_element_count: ["selector", "expected"],
  assert_attribute: ["selector", "attribute", "expected"],
};

const testStepBaseSchema = z
  .object({
    action: z.enum(STEP_TYPES),
    selector: z.string().min(1).max(500).optional(),
    url: z.string().min(1).max(2000).optional(),
    value: z.string().max(2000).optional(),
    option: z.string().max(500).optional(),
    attribute: z.string().max(200).optional(),
    expected: z.union([z.string(), z.number()]).optional(),
    timeoutMs: z.number().int().positive().max(MAX_STEP_TIMEOUT_MS).optional(),
    name: z.string().max(200).optional(),
  })
  .strict();

export const testStepSchema = testStepBaseSchema.superRefine((step, ctx) => {
  for (const field of REQUIRED_FIELDS[step.action]) {
    if ((step as Record<string, unknown>)[field] === undefined) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: [field],
        message: `"${field}" is required for action "${step.action}"`,
      });
    }
  }
});

export const testCaseSchema = z
  .object({
    id: z
      .string()
      .min(1)
      .max(100)
      .regex(/^[a-zA-Z0-9_-]+$/, "id must contain only letters, numbers, dashes, or underscores"),
    name: z.string().min(1).max(200),
    steps: z.array(testStepSchema).min(1).max(MAX_STEPS_PER_TEST),
  })
  .strict();

export const testPlanSchema = z
  .object({
    version: z.literal(1),
    name: z.string().min(1).max(200),
    baseUrl: z.string().min(1).max(2000),
    tests: z.array(testCaseSchema).min(1).max(MAX_TESTS_PER_PLAN),
  })
  .strict();

export type TestStep = z.infer<typeof testStepBaseSchema>;
export type TestCase = z.infer<typeof testCaseSchema>;
export type ValidatedTestPlan = z.infer<typeof testPlanSchema>;

export function validateTestPlan(input: unknown): ValidatedTestPlan {
  return testPlanSchema.parse(input);
}

export function safeValidateTestPlan(input: unknown) {
  return testPlanSchema.safeParse(input);
}
