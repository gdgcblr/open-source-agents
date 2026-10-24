import {readFileSync} from 'node:fs';
import {z} from 'zod';

// Defaults mirror AmlRuleProperties in the original Sentinel AML (Spring Boot) project.
const RuleConfigSchema = z.object({
  thresholdEnabled: z.boolean(),
  structuringEnabled: z.boolean(),
  rapidMovementEnabled: z.boolean(),
  highRiskEnabled: z.boolean(),
  behavioralDeviationEnabled: z.boolean(),
  roundNumberEnabled: z.boolean(),
  reportThresholdInr: z.number().positive(),
  structuringMinimumInr: z.number().positive(),
  structuringCount: z.number().int().min(2),
  structuringWindowHours: z.number().int().positive(),
  rapidMovementHours: z.number().int().positive(),
  rapidMovementRatio: z.number().gt(0).max(1),
  behavioralBaselineDays: z.number().int().positive(),
  behavioralMultiplier: z.number().gt(1),
  roundAmountUnitInr: z.number().positive(),
  roundNumberCount: z.number().int().min(2),
  highRiskJurisdictions: z.array(z.string().length(2)),
  highRiskCounterparties: z.array(z.string().min(1)),
  exchangeRatesToInr: z.record(z.string(), z.number().positive()),
});

export type RuleConfig = z.infer<typeof RuleConfigSchema>;

export const DEFAULT_RULES: RuleConfig = {
  thresholdEnabled: true,
  structuringEnabled: true,
  rapidMovementEnabled: true,
  highRiskEnabled: true,
  behavioralDeviationEnabled: true,
  roundNumberEnabled: true,
  reportThresholdInr: 830_000,
  structuringMinimumInr: 747_000,
  structuringCount: 3,
  structuringWindowHours: 24,
  rapidMovementHours: 48,
  rapidMovementRatio: 0.8,
  behavioralBaselineDays: 90,
  behavioralMultiplier: 3,
  roundAmountUnitInr: 100_000,
  roundNumberCount: 2,
  highRiskJurisdictions: ['IR', 'KP', 'SY'],
  highRiskCounterparties: [],
  exchangeRatesToInr: {INR: 1, USD: 83, EUR: 90},
};

/** Rules can be tuned from a JSON file without code changes; unknown or invalid keys are rejected. */
export function loadRuleConfig(path?: string): RuleConfig {
  if (!path) return DEFAULT_RULES;
  const overrides = RuleConfigSchema.partial().strict().parse(JSON.parse(readFileSync(path, 'utf8')));
  return {...DEFAULT_RULES, ...overrides};
}
