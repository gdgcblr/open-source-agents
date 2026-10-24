function money(value, currency) {
  if (value === null || value === undefined) return 'Not calculable';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    maximumFractionDigits: 0,
  }).format(value);
}

function ratio(value) {
  return value === null ? 'Not calculable' : `${value.toFixed(3)}x`;
}

function percent(value) {
  return value === null ? 'Not calculable' : `${value.toFixed(2)}%`;
}

function change(value, suffix = 'x') {
  if (value === null) return 'Not calculable';
  return `${value > 0 ? '+' : ''}${value.toFixed(3)}${suffix}`;
}

function scenarioLines(label, scenario, currency) {
  return [
    `### ${label}`,
    '',
    `- EBITDA used: ${money(scenario.ebitdaAnnual, currency)}`,
    `- Proposed annual debt service: ${money(scenario.proposedAnnualDebtService, currency)}`,
    `- Total annual debt service: ${money(scenario.totalAnnualDebtService, currency)}`,
    `- Pro forma total debt: ${money(scenario.proFormaTotalDebt, currency)}`,
    `- DSCR: ${ratio(scenario.dscr)}`,
    `- Debt / EBITDA: ${ratio(scenario.debtToEbitda)}`,
    `- Current ratio: ${ratio(scenario.currentRatio)}`,
    `- Interest coverage: ${ratio(scenario.interestCoverage)}`,
    '',
    '| Policy metric | Result | Threshold | Status |',
    '| :--- | ---: | ---: | :--- |',
    ...Object.entries(scenario.policyChecks).map(([name, check]) =>
      `| ${name} | ${ratio(check.value)} | ${ratio(check.threshold)} | ${check.status.replaceAll('_', ' ')} |`),
    '',
  ];
}

export function toMarkdown(report) {
  const { request, assumptions, scenarios, dataQuality } = report;
  const lines = [
    `# Credit review memo: ${report.borrower}`,
    '',
    `- **As of:** ${report.asOf ?? 'Not provided'}`,
    `- **Requested amount:** ${money(request.amount, report.currency)}`,
    `- **Term:** ${request.termYears} years`,
    `- **Requested annual rate:** ${(request.annualRate * 100).toFixed(2)}%`,
    `- **Review status:** Human review required`,
    '',
    '> Decision support only. This report does not approve, decline, price, or rank an applicant.',
    '',
    '## Base case',
    '',
    ...scenarioLines('Pro forma', scenarios.base, report.currency),
    '## Downside case',
    '',
    `Stress assumptions: EBITDA decline ${(assumptions.downside.ebitdaDecline * 100).toFixed(1)}%; annual rate increase ${(assumptions.downside.annualRateIncrease * 100).toFixed(2)}%.`,
    '',
    ...scenarioLines('Stressed pro forma', scenarios.downside, report.currency),
    '## Policy headroom and reverse stress',
    '',
    'Headroom is measured against supplied policy thresholds. Reverse stress changes one variable at a time and holds all other inputs constant.',
    '',
    '| Policy metric | Base value | Threshold | Headroom | Relative headroom | Status |',
    '| :--- | ---: | ---: | ---: | ---: | :--- |',
    ...Object.entries(report.policyHeadroom.metrics).map(([name, metric]) =>
      `| ${name} | ${ratio(metric.value)} | ${ratio(metric.threshold)} | ${ratio(metric.headroom)} | ${percent(metric.relativePercent)} | ${metric.status.replaceAll('_', ' ')} |`),
    '',
  ];

  if (report.policyHeadroom.tightestWithinTolerance) {
    const tightest = report.policyHeadroom.tightestWithinTolerance;
    lines.push(`Tightest currently within-tolerance metric: **${tightest.metric}** at ${percent(tightest.relativePercent)} relative headroom.`, '');
  } else {
    lines.push('No calculable policy metric is currently within tolerance, or no relative headroom can be computed.', '');
  }

  lines.push(
    '### DSCR reverse stress',
    '',
    `- EBITDA decline to minimum DSCR: ${report.reverseStress.ebitdaDecline.maximumDecline === undefined ? report.reverseStress.ebitdaDecline.status.replaceAll('_', ' ') : `${percent(report.reverseStress.ebitdaDecline.maximumDecline * 100)} (${report.reverseStress.ebitdaDecline.status.replaceAll('_', ' ')})`}.`,
    `- Rate increase to minimum DSCR: ${report.reverseStress.rateIncrease.maximumIncrease === undefined ? report.reverseStress.rateIncrease.status.replaceAll('_', ' ') : `${percent(report.reverseStress.rateIncrease.maximumIncrease * 100)} (annual rate ${percent(report.reverseStress.rateIncrease.annualRateAtThreshold * 100)}; ${report.reverseStress.rateIncrease.status.replaceAll('_', ' ')})`}.`,
    '- Rate search is bounded to a 100% annual rate. These are model breakpoints, not forecasts, recommended terms, or lending decisions.',
    '',
    '## Facility sensitivity',
    '',
    'Illustrative combinations only; these are not recommended facility terms.',
    '',
    '| Facility amount | Annual rate | DSCR | Debt / EBITDA | DSCR policy | Leverage policy |',
    '| ---: | ---: | ---: | ---: | :--- | :--- |',
    ...report.sensitivityGrid.map((row) =>
      `| ${money(row.facilityAmount, report.currency)} (${row.amountMultiplier}x) | ${(row.annualRate * 100).toFixed(2)}% | ${ratio(row.dscr)} | ${ratio(row.debtToEbitda)} | ${row.dscrPolicyStatus.replaceAll('_', ' ')} | ${row.leveragePolicyStatus.replaceAll('_', ' ')} |`),
    '',
    '## Historical trends',
    '',
  );

  if (report.historicalTrends.length === 0) {
    lines.push('No historical periods were provided; trend analysis is unavailable.', '');
  } else {
    lines.push(
      '| Period | Revenue | Revenue growth | EBITDA margin | Margin change | DSCR | DSCR change | Debt / EBITDA | Leverage change |',
      '| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |',
      ...report.historicalTrends.map((period) =>
        `| ${period.period} | ${money(period.revenueAnnual, report.currency)} | ${percent(period.revenueGrowthPercent)} | ${percent(period.ebitdaMargin === null ? null : period.ebitdaMargin * 100)} | ${change(period.ebitdaMarginChangePoints, ' pp')} | ${ratio(period.dscr)} | ${change(period.dscrChange)} | ${ratio(period.debtToEbitda)} | ${change(period.debtToEbitdaChange)} |`),
      '',
      'Changes compare each year with the immediately preceding year. Ratios with missing or nonpositive denominators are not calculable.',
      '',
    );
  }

  lines.push(
    '## Data quality and evidence',
    '',
  );

  if (dataQuality.missingFinancials.length > 0) {
    lines.push('Missing financial inputs:', ...dataQuality.missingFinancials.map((field) => `- ${field}`), '');
  } else {
    lines.push('All supported financial input fields were provided.', '');
  }
  if (dataQuality.note) lines.push(`**Evidence note:** ${dataQuality.note}`, '');
  if (report.sources.length > 0) {
    lines.push('| Field | Source | As of |', '| :--- | :--- | :--- |');
    for (const source of report.sources) {
      lines.push(`| ${source.field} | ${source.source.replaceAll('|', '\\|')} | ${source.asOf ?? 'Not provided'} |`);
    }
    lines.push('');
  }

  lines.push(
    '## Calculation notes',
    '',
    '- Proposed annual debt service uses monthly amortization at the requested rate and term.',
    '- DSCR = EBITDA / (existing annual debt service + proposed annual debt service).',
    '- Debt / EBITDA = (existing total debt + proposed amount) / EBITDA.',
    '- Interest coverage = EBIT / (existing interest expense + proposed amount times annual rate). Proposed-loan interest is approximated using the initial balance.',
    `- Downside case: ${assumptions.stressMethod}`,
    '- “Not calculable” means required inputs were missing or the denominator was zero; it is not a passing result.',
    '- Supplied policy thresholds are comparison points, not a lending decision or a substitute for institution policy.',
    '',
    '## Analyst review prompts',
    '',
    '- Verify each financial figure against current primary records and confirm source periods are comparable.',
    '- Investigate every metric outside tolerance and every metric that could not be calculated.',
    '- Review qualitative factors and applicable lending policy independently; do not infer protected characteristics.',
    '',
  );
  return lines.join('\n');
}