const FINANCIAL_FIELDS = {
  revenueAnnual: 'annual revenue',
  ebitdaAnnual: 'annual EBITDA',
  ebitAnnual: 'annual EBIT',
  interestExpenseAnnual: 'annual interest expense',
  totalDebt: 'existing total debt',
  annualDebtService: 'existing annual debt service',
  currentAssets: 'current assets',
  currentLiabilities: 'current liabilities',
};

const DEFAULT_POLICY = {
  minimumDscr: 1.25,
  maximumDebtToEbitda: 3.5,
  minimumCurrentRatio: 1.1,
  minimumInterestCoverage: 2,
};

const DEFAULT_STRESS = {
  ebitdaDecline: 0.2,
  annualRateIncrease: 0.02,
};

function finiteNumber(value, label, { min = -Infinity, max = Infinity } = {}) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < min || value > max) {
    throw new TypeError(`${label} must be a finite number between ${min} and ${max}.`);
  }
  return value;
}

function round(value, digits = 3) {
  return Number.isFinite(value) ? Number(value.toFixed(digits)) : null;
}

function getFinancials(raw = {}) {
  const values = {};
  const missing = [];
  for (const [key, label] of Object.entries(FINANCIAL_FIELDS)) {
    if (raw[key] === undefined || raw[key] === null) {
      values[key] = null;
      missing.push(label);
      continue;
    }
    const minimum = ['ebitdaAnnual', 'ebitAnnual'].includes(key) ? -Infinity : 0;
    values[key] = finiteNumber(raw[key], `financials.${key}`, { min: minimum });
  }
  return { values, missing };
}

export function annualLoanPayment(principal, annualRate, termYears) {
  if (principal === 0) return 0;
  const months = termYears * 12;
  const monthlyRate = annualRate / 12;
  if (monthlyRate === 0) return principal / months * 12;
  return principal * monthlyRate / (1 - (1 + monthlyRate) ** -months) * 12;
}

function divide(numerator, denominator) {
  if (numerator === null || denominator === null || denominator === 0) return null;
  return round(numerator / denominator);
}

function debtToEbitda(debt, ebitda) {
  return ebitda === null || ebitda <= 0 ? null : divide(debt, ebitda);
}

function analyzeScenario(financials, request, policy, stress) {
  const annualRate = request.annualRate + stress.rateIncrease;
  const proposedDebtService = annualLoanPayment(request.amount, annualRate, request.termYears);
  const totalDebtService = financials.annualDebtService === null
    ? null
    : financials.annualDebtService + proposedDebtService;
  const ebitda = financials.ebitdaAnnual === null
    ? null
    : financials.ebitdaAnnual * (1 - stress.ebitdaDecline);
  const interestExpense = financials.interestExpenseAnnual === null
    ? null
    : financials.interestExpenseAnnual + request.amount * annualRate;
  const proFormaDebt = financials.totalDebt === null
    ? null
    : financials.totalDebt + request.amount;
  const ebit = financials.ebitAnnual === null
    ? null
    : financials.ebitAnnual * (1 - stress.ebitdaDecline);
  const leverage = debtToEbitda(proFormaDebt, ebitda);

  return {
    ebitdaAnnual: round(ebitda),
    proposedAnnualDebtService: round(proposedDebtService),
    totalAnnualDebtService: round(totalDebtService),
    proFormaTotalDebt: round(proFormaDebt),
    dscr: divide(ebitda, totalDebtService),
    debtToEbitda: leverage,
    currentRatio: divide(financials.currentAssets, financials.currentLiabilities),
    workingCapital: financials.currentAssets === null || financials.currentLiabilities === null
      ? null
      : round(financials.currentAssets - financials.currentLiabilities),
    interestCoverage: divide(ebit, interestExpense),
    annualInterestExpenseIncludingRequest: round(interestExpense),
    policyChecks: {
      dscr: compare(divide(ebitda, totalDebtService), policy.minimumDscr, 'minimum'),
      debtToEbitda: compare(leverage, policy.maximumDebtToEbitda, 'maximum'),
      currentRatio: compare(divide(financials.currentAssets, financials.currentLiabilities), policy.minimumCurrentRatio, 'minimum'),
      interestCoverage: compare(divide(ebit, interestExpense), policy.minimumInterestCoverage, 'minimum'),
    },
  };
}

function compare(value, threshold, direction) {
  if (value === null) return { status: 'not_calculable', value: null, threshold };
  const passes = direction === 'minimum' ? value >= threshold : value <= threshold;
  return { status: passes ? 'within_tolerance' : 'outside_tolerance', value, threshold };
}

function calculatePolicyHeadroom(policyChecks) {
  const directions = {
    dscr: 'minimum',
    debtToEbitda: 'maximum',
    currentRatio: 'minimum',
    interestCoverage: 'minimum',
  };
  const metrics = Object.fromEntries(Object.entries(directions).map(([metric, direction]) => {
    const check = policyChecks[metric];
    const headroom = check.value === null
      ? null
      : direction === 'minimum'
        ? check.value - check.threshold
        : check.threshold - check.value;
    return [metric, {
      value: check.value,
      threshold: check.threshold,
      headroom: headroom === null ? null : round(headroom),
      relativePercent: headroom === null || check.threshold === 0
        ? null
        : round((headroom / Math.abs(check.threshold)) * 100, 2),
      status: check.status,
    }];
  }));
  const eligible = Object.entries(metrics)
    .filter(([, metric]) => metric.status === 'within_tolerance' && metric.relativePercent !== null)
    .sort((left, right) => left[1].relativePercent - right[1].relativePercent);

  return {
    metrics,
    tightestWithinTolerance: eligible.length === 0
      ? null
      : { metric: eligible[0][0], relativePercent: eligible[0][1].relativePercent },
  };
}

function calculateReverseDscrStress(financials, request, minimumDscr) {
  if (financials.ebitdaAnnual === null || financials.annualDebtService === null) {
    const unavailable = { status: 'not_calculable', threshold: minimumDscr };
    return { ebitdaDecline: unavailable, rateIncrease: unavailable };
  }

  const baseDebtService = financials.annualDebtService
    + annualLoanPayment(request.amount, request.annualRate, request.termYears);
  const baseDscr = baseDebtService === 0 ? null : financials.ebitdaAnnual / baseDebtService;
  if (baseDscr === null) {
    const unavailable = { status: 'not_calculable', threshold: minimumDscr };
    return { ebitdaDecline: unavailable, rateIncrease: unavailable };
  }
  if (baseDscr < minimumDscr) {
    const outside = { status: 'already_outside_tolerance', threshold: minimumDscr, dscrAtThreshold: round(baseDscr) };
    return { ebitdaDecline: outside, rateIncrease: outside };
  }

  const decline = financials.ebitdaAnnual === 0
    ? 0
    : Math.max(0, Math.min(1, 1 - (minimumDscr * baseDebtService) / financials.ebitdaAnnual));
  const ebitdaDecline = {
    status: decline === 0 ? 'at_threshold' : 'threshold_reached',
    maximumDecline: round(decline, 6),
    threshold: minimumDscr,
    dscrAtThreshold: round(minimumDscr),
  };

  if (baseDscr === minimumDscr) {
    return {
      ebitdaDecline,
      rateIncrease: {
        status: 'at_threshold',
        maximumIncrease: 0,
        annualRateAtThreshold: request.annualRate,
        threshold: minimumDscr,
        dscrAtThreshold: round(baseDscr),
      },
    };
  }

  const maxRateIncrease = 1 - request.annualRate;
  const dscrAtRateIncrease = (rateIncrease) => {
    const debtService = financials.annualDebtService
      + annualLoanPayment(request.amount, request.annualRate + rateIncrease, request.termYears);
    return debtService === 0 ? null : financials.ebitdaAnnual / debtService;
  };
  if (dscrAtRateIncrease(maxRateIncrease) > minimumDscr) {
    return {
      ebitdaDecline,
      rateIncrease: {
        status: 'not_reached_within_search_range',
        maximumRateIncreaseTested: round(maxRateIncrease, 6),
        threshold: minimumDscr,
      },
    };
  }

  let lower = 0;
  let upper = maxRateIncrease;
  for (let iteration = 0; iteration < 60; iteration += 1) {
    const midpoint = (lower + upper) / 2;
    if (dscrAtRateIncrease(midpoint) > minimumDscr) lower = midpoint;
    else upper = midpoint;
  }
  return {
    ebitdaDecline,
    rateIncrease: {
      status: round(upper, 6) === 0 ? 'at_threshold' : 'threshold_reached',
      maximumIncrease: round(upper, 6),
      annualRateAtThreshold: round(request.annualRate + upper, 6),
      threshold: minimumDscr,
      dscrAtThreshold: round(dscrAtRateIncrease(upper)),
    },
  };
}

function mergePolicy(raw = {}) {
  const policy = {};
  for (const [key, fallback] of Object.entries(DEFAULT_POLICY)) {
    policy[key] = raw[key] === undefined
      ? fallback
      : finiteNumber(raw[key], `policy.${key}`, { min: 0 });
  }
  return policy;
}

function boundedList(raw, fallback, label, { min, max }) {
  if (raw === undefined) return fallback;
  if (!Array.isArray(raw) || raw.length === 0 || raw.length > 5) {
    throw new TypeError(`${label} must be an array containing 1 to 5 values.`);
  }
  return raw.map((value, index) => finiteNumber(value, `${label}[${index}]`, { min, max }));
}

function buildSensitivity(financials, request, policy, stress, sensitivity) {
  const amountMultipliers = boundedList(
    sensitivity.amountMultipliers,
    [0.75, 1, 1.25],
    'sensitivity.amountMultipliers',
    { min: 0, max: 5 },
  );
  const rateIncreases = boundedList(
    sensitivity.rateIncreases,
    [0, stress.annualRateIncrease],
    'sensitivity.rateIncreases',
    { min: 0, max: 1 },
  );

  if (request.annualRate + Math.max(...rateIncreases) > 1) {
    throw new RangeError('sensitivity rate increases cannot produce an annual rate above 1.');
  }

  return amountMultipliers.flatMap((amountMultiplier) => rateIncreases.map((rateIncrease) => {
    const scenario = analyzeScenario(financials, {
      ...request,
      amount: request.amount * amountMultiplier,
    }, policy, { ebitdaDecline: 0, rateIncrease });
    return {
      amountMultiplier,
      facilityAmount: round(request.amount * amountMultiplier),
      annualRate: round(request.annualRate + rateIncrease),
      dscr: scenario.dscr,
      debtToEbitda: scenario.debtToEbitda,
      dscrPolicyStatus: scenario.policyChecks.dscr.status,
      leveragePolicyStatus: scenario.policyChecks.debtToEbitda.status,
    };
  }));
}

function percentChange(current, previous) {
  if (current === null || previous === null || previous === 0) return null;
  return round(((current - previous) / Math.abs(previous)) * 100);
}

function analyzeHistoricalTrends(rawHistory) {
  if (rawHistory === undefined) return [];
  if (!Array.isArray(rawHistory) || rawHistory.length < 2 || rawHistory.length > 10) {
    throw new TypeError('historicalFinancials must contain 2 to 10 annual periods.');
  }

  let previousPeriod = 0;
  let previous = null;
  return rawHistory.map((record, index) => {
    if (!record || typeof record !== 'object' || !/^\d{4}$/.test(record.period ?? '')) {
      throw new TypeError(`historicalFinancials[${index}].period must be a four-digit year.`);
    }
    const period = Number(record.period);
    if (period <= previousPeriod) {
      throw new TypeError('historicalFinancials must be sorted by unique year in ascending order.');
    }
    previousPeriod = period;

    const { values } = getFinancials(record);
    const current = {
      period: record.period,
      revenueAnnual: values.revenueAnnual,
      ebitdaAnnual: values.ebitdaAnnual,
      ebitdaMargin: divide(values.ebitdaAnnual, values.revenueAnnual),
      dscr: divide(values.ebitdaAnnual, values.annualDebtService),
      debtToEbitda: debtToEbitda(values.totalDebt, values.ebitdaAnnual),
      revenueGrowthPercent: previous
        ? percentChange(values.revenueAnnual, previous.revenueAnnual)
        : null,
      ebitdaMarginChangePoints: previous && values.ebitdaAnnual !== null && values.revenueAnnual > 0
        && previous.ebitdaMargin !== null
        ? round((values.ebitdaAnnual / values.revenueAnnual - previous.ebitdaMargin) * 100)
        : null,
      dscrChange: previous && values.ebitdaAnnual !== null && values.annualDebtService > 0
        && previous.dscr !== null
        ? round(values.ebitdaAnnual / values.annualDebtService - previous.dscr)
        : null,
      debtToEbitdaChange: previous && values.totalDebt !== null && values.ebitdaAnnual > 0
        && values.ebitdaAnnual > 0 && previous.debtToEbitda !== null
        ? round(values.totalDebt / values.ebitdaAnnual - previous.debtToEbitda)
        : null,
    };
    previous = current;
    return current;
  });
}

export function analyzeCreditCase(input) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) {
    throw new TypeError('Input must be a JSON object.');
  }
  if (!input.request || typeof input.request !== 'object') {
    throw new TypeError('request is required.');
  }

  const amount = finiteNumber(input.request.amount, 'request.amount', { min: 0 });
  const termYears = finiteNumber(input.request.termYears, 'request.termYears', { min: 1, max: 50 });
  const annualRate = finiteNumber(input.request.annualRate, 'request.annualRate', { min: 0, max: 1 });
  const currency = input.currency ?? 'USD';
  if (typeof currency !== 'string' || !/^[A-Z]{3}$/.test(currency)) {
    throw new TypeError('currency must be a three-letter uppercase currency code.');
  }

  const rawStress = input.stress ?? {};
  const stress = {
    ebitdaDecline: rawStress.ebitdaDecline === undefined
      ? DEFAULT_STRESS.ebitdaDecline
      : finiteNumber(rawStress.ebitdaDecline, 'stress.ebitdaDecline', { min: 0, max: 1 }),
    annualRateIncrease: rawStress.annualRateIncrease === undefined
      ? DEFAULT_STRESS.annualRateIncrease
      : finiteNumber(rawStress.annualRateIncrease, 'stress.annualRateIncrease', { min: 0, max: 1 }),
  };
  const policy = mergePolicy(input.policy);
  const { values: financials, missing } = getFinancials(input.financials ?? {});
  const sensitivity = input.sensitivity ?? {};
  if (typeof sensitivity !== 'object' || Array.isArray(sensitivity)) {
    throw new TypeError('sensitivity must be an object.');
  }
  const base = analyzeScenario(financials, { amount, termYears, annualRate }, policy, {
    ebitdaDecline: 0,
    rateIncrease: 0,
  });
  const downside = analyzeScenario(financials, { amount, termYears, annualRate }, policy, {
    ebitdaDecline: stress.ebitdaDecline,
    rateIncrease: stress.annualRateIncrease,
  });
  const sensitivityGrid = buildSensitivity(
    financials,
    { amount, termYears, annualRate },
    policy,
    stress,
    sensitivity,
  );
  const historicalTrends = analyzeHistoricalTrends(input.historicalFinancials);
  const policyHeadroom = calculatePolicyHeadroom(base.policyChecks);
  const reverseStress = calculateReverseDscrStress(
    financials,
    { amount, termYears, annualRate },
    policy.minimumDscr,
  );
  const sources = Array.isArray(input.sources) ? input.sources.map((source, index) => {
    if (!source || typeof source !== 'object' || typeof source.source !== 'string') {
      throw new TypeError(`sources[${index}] must include a source description.`);
    }
    return {
      field: typeof source.field === 'string' ? source.field : 'unspecified',
      source: source.source,
      asOf: typeof source.asOf === 'string' ? source.asOf : null,
    };
  }) : [];

  return {
    reportVersion: 1,
    borrower: typeof input.borrower === 'string' ? input.borrower : 'Unspecified borrower',
    asOf: typeof input.asOf === 'string' ? input.asOf : null,
    currency,
    request: { amount, termYears, annualRate },
    assumptions: {
      policy,
      downside: {
        ebitdaDecline: stress.ebitdaDecline,
        annualRateIncrease: stress.annualRateIncrease,
      },
      paymentFrequency: 'monthly, displayed as annual debt service',
      stressMethod: 'EBITDA is reduced directly by the specified decline; revenue is not re-forecast.',
    },
    scenarios: { base, downside },
    policyHeadroom,
    reverseStress,
    sensitivityGrid,
    historicalTrends,
    dataQuality: {
      missingFinancials: missing,
      sourcesProvided: sources.length,
      note: sources.length === 0 ? 'No source references were provided; verify all inputs against primary records.' : null,
    },
    sources,
    decision: 'human_review_required',
    decisionNote: 'This analysis is decision support only. It does not approve, decline, price, or rank an applicant.',
  };
}