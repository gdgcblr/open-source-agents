export interface Requirement {
  id: string;
  text: string;
}

export interface TestScenario {
  id: string;
  title: string;
  category: string;
  priority: 'P1' | 'P2' | 'P3';
  preconditions: string[];
  steps: string[];
  expectedResult: string;
  requirementIds: string[];
}

export interface ValidationResult {
  valid: boolean;
  requirementCount: number;
  scenarioCount: number;
  issues: string[];
  uncoveredRequirementIds: string[];
}

/** Check objective structure and traceability; this does not judge semantic quality. */
export function validateScenarios(
  requirements: Requirement[],
  scenarios: TestScenario[],
): ValidationResult {
  const issues: string[] = [];
  const requirementIds = new Set(requirements.map(({id}) => id));
  const scenarioIds = new Set<string>();
  const coveredRequirementIds = new Set<string>();
  const scenarioTitles = new Set<string>();

  if (requirements.length === 0) issues.push('At least one explicit requirement is required.');
  if (scenarios.length === 0) issues.push('At least one test scenario is required.');
  if (requirementIds.size !== requirements.length) issues.push('Requirement IDs must be unique.');

  for (const [index, scenario] of scenarios.entries()) {
    const label = scenario.id.trim() || `Scenario ${index + 1}`;
    if (!scenario.id.trim()) issues.push(`${label}: ID must be non-empty.`);
    if (scenarioIds.has(scenario.id)) issues.push(`${label}: duplicate scenario ID.`);
    scenarioIds.add(scenario.id);

    for (const [field, value] of [
      ['title', scenario.title],
      ['category', scenario.category],
      ['expected result', scenario.expectedResult],
    ] as const) {
      if (!value.trim()) issues.push(`${label}: ${field} must be non-empty.`);
    }
    if (!['P1', 'P2', 'P3'].includes(scenario.priority)) {
      issues.push(`${label}: priority must be P1, P2, or P3.`);
    }
    if (scenario.steps.length === 0 || scenario.steps.some((step) => !step.trim())) {
      issues.push(`${label}: steps must contain non-empty actions.`);
    }
    if (scenario.requirementIds.length === 0) {
      issues.push(`${label}: link at least one requirement ID.`);
    }

    const normalizedTitle = scenario.title.trim().toLocaleLowerCase();
    if (normalizedTitle && scenarioTitles.has(normalizedTitle)) {
      issues.push(`${label}: duplicate scenario title.`);
    }
    scenarioTitles.add(normalizedTitle);

    for (const requirementId of scenario.requirementIds) {
      if (!requirementIds.has(requirementId)) {
        issues.push(`${label}: unknown requirement ID ${requirementId}.`);
      } else {
        coveredRequirementIds.add(requirementId);
      }
    }
  }

  const uncoveredRequirementIds = [...requirementIds]
    .filter((id) => !coveredRequirementIds.has(id))
    .sort();
  if (uncoveredRequirementIds.length > 0) {
    issues.push(`Requirements without linked scenarios: ${uncoveredRequirementIds.join(', ')}.`);
  }

  return {
    valid: issues.length === 0,
    requirementCount: requirements.length,
    scenarioCount: scenarios.length,
    issues,
    uncoveredRequirementIds,
  };
}