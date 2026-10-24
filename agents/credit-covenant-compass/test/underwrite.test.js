import test from 'node:test';
import assert from 'node:assert/strict';
import { analyzeCreditCase, annualLoanPayment } from '../src/underwrite.js';
import { toMarkdown } from '../src/report.js';

const completeCase = {
  borrower: 'Synthetic borrower',
  currency: 'USD',
  financials: {
    revenueAnnual: 1000000,
    ebitdaAnnual: 90000,
    ebitAnnual: 60000,
    interestExpenseAnnual: 10000,
    totalDebt: 100000,
    annualDebtService: 25000,
    currentAssets: 200000,
    currentLiabilities: 100000,
  },
  request: { amount: 100000, termYears: 5, annualRate: 0 },
  policy: {
    minimumDscr: 1.25,
    maximumDebtToEbitda: 3.5,
    minimumCurrentRatio: 1.1,
    minimumInterestCoverage: 2,
  },
  stress: { ebitdaDecline: 0.2, annualRateIncrease: 0.02 },
  sources: [{ field: 'financials', source: 'Synthetic test statement', asOf: '2025-12-31' }],
};

test('calculates zero-interest amortizing annual payment', () => {
  assert.equal(annualLoanPayment(120000, 0, 5), 24000);
});

test('calculates a level-payment loan with positive interest', () => {
  assert.ok(Math.abs(annualLoanPayment(100000, 0.06, 5) - 23199.3) < 1);
});

test('calculates base ratios and keeps the result non-decisional', () => {
  const report = analyzeCreditCase(completeCase);
  assert.equal(report.scenarios.base.dscr, 2);
  assert.equal(report.scenarios.base.debtToEbitda, 2.222);
  assert.equal(report.scenarios.base.currentRatio, 2);
  assert.equal(report.scenarios.base.interestCoverage, 6);
  assert.equal(report.scenarios.base.policyChecks.dscr.status, 'within_tolerance');
  assert.equal(report.decision, 'human_review_required');
});

test('stress scenario reduces EBITDA and applies a higher proposed rate', () => {
  const report = analyzeCreditCase(completeCase);
  assert.equal(report.scenarios.downside.ebitdaAnnual, 72000);
  assert.ok(report.scenarios.downside.proposedAnnualDebtService > report.scenarios.base.proposedAnnualDebtService);
  assert.ok(report.scenarios.downside.dscr < report.scenarios.base.dscr);
});

test('missing inputs become not-calculable checks, not passes', () => {
  const report = analyzeCreditCase({ request: completeCase.request, financials: {} });
  assert.ok(report.dataQuality.missingFinancials.length > 0);
  assert.equal(report.scenarios.base.policyChecks.dscr.status, 'not_calculable');
  assert.equal(report.scenarios.base.policyChecks.dscr.value, null);
});

test('policy exceptions and missing sources appear in the memo', () => {
  const report = analyzeCreditCase({
    ...completeCase,
    policy: { minimumDscr: 2.1 },
    sources: [],
  });
  const markdown = toMarkdown(report);
  assert.equal(report.scenarios.base.policyChecks.dscr.status, 'outside_tolerance');
  assert.match(markdown, /outside tolerance/);
  assert.match(markdown, /No source references were provided/);
  assert.match(markdown, /does not approve, decline, price, or rank/);
});

test('rejects invalid request ranges instead of silently coercing values', () => {
  assert.throws(() => analyzeCreditCase({ request: { ...completeCase.request, annualRate: 1.2 } }), /request\.annualRate/);
  assert.throws(() => analyzeCreditCase({ request: { ...completeCase.request, termYears: 0 } }), /request\.termYears/);
});

test('sensitivity grid shows lower DSCR as facility size increases', () => {
  const report = analyzeCreditCase(completeCase);
  const baseRateRows = report.sensitivityGrid.filter((row) => row.annualRate === 0);
  assert.deepEqual(baseRateRows.map((row) => row.amountMultiplier), [0.75, 1, 1.25]);
  assert.ok(baseRateRows[0].dscr > baseRateRows[1].dscr);
  assert.ok(baseRateRows[1].dscr > baseRateRows[2].dscr);
  assert.equal(report.sensitivityGrid.length, 6);
});

test('sensitivity inputs are bounded and reject impossible effective rates', () => {
  assert.throws(() => analyzeCreditCase({
    ...completeCase,
    sensitivity: { amountMultipliers: [1, 2, 3, 4, 5, 6] },
  }), /1 to 5 values/);
  assert.throws(() => analyzeCreditCase({
    ...completeCase,
    request: { ...completeCase.request, annualRate: 0.95 },
    sensitivity: { rateIncreases: [0.1] },
  }), /annual rate above 1/);
});

test('historical analysis calculates growth, margins, DSCR, and leverage trends', () => {
  const report = analyzeCreditCase({
    ...completeCase,
    historicalFinancials: [
      { period: '2023', revenueAnnual: 800000, ebitdaAnnual: 80000, totalDebt: 160000, annualDebtService: 40000 },
      { period: '2024', revenueAnnual: 1000000, ebitdaAnnual: 90000, totalDebt: 180000, annualDebtService: 45000 },
    ],
  });
  assert.equal(report.historicalTrends[0].ebitdaMargin, 0.1);
  assert.equal(report.historicalTrends[1].revenueGrowthPercent, 25);
  assert.equal(report.historicalTrends[1].ebitdaMarginChangePoints, -1);
  assert.equal(report.historicalTrends[0].dscr, 2);
  assert.equal(report.historicalTrends[1].debtToEbitda, 2);
});

test('historical periods must be unique and ordered', () => {
  assert.throws(() => analyzeCreditCase({
    ...completeCase,
    historicalFinancials: [{ period: '2024' }, { period: '2023' }],
  }), /sorted by unique year/);
});

test('debt-to-EBITDA is unavailable when EBITDA is nonpositive', () => {
  const report = analyzeCreditCase({
    ...completeCase,
    financials: { ...completeCase.financials, ebitdaAnnual: -10000 },
  });
  assert.equal(report.scenarios.base.debtToEbitda, null);
  assert.equal(report.scenarios.base.policyChecks.debtToEbitda.status, 'not_calculable');
});

test('reports policy headroom and reverse DSCR stress thresholds', () => {
  const report = analyzeCreditCase(completeCase);
  assert.equal(report.policyHeadroom.metrics.dscr.headroom, 0.75);
  assert.ok(report.policyHeadroom.tightestWithinTolerance);
  assert.equal(report.reverseStress.ebitdaDecline.status, 'threshold_reached');
  assert.equal(report.reverseStress.ebitdaDecline.maximumDecline, 0.375);
  assert.ok(report.reverseStress.rateIncrease.maximumIncrease > 0);
  assert.equal(report.reverseStress.rateIncrease.status, 'threshold_reached');
  assert.equal(report.reverseStress.rateIncrease.dscrAtThreshold, 1.25);
});

test('reverse stress distinguishes breached and unavailable DSCR cases', () => {
  const breached = analyzeCreditCase({
    ...completeCase,
    policy: { ...completeCase.policy, minimumDscr: 2.1 },
  });
  assert.equal(breached.reverseStress.ebitdaDecline.status, 'already_outside_tolerance');

  const unavailable = analyzeCreditCase({ request: completeCase.request, financials: {} });
  assert.equal(unavailable.reverseStress.rateIncrease.status, 'not_calculable');
});

test('reverse rate stress reports when threshold is not reached in search bounds', () => {
  const report = analyzeCreditCase({
    ...completeCase,
    financials: { ...completeCase.financials, annualDebtService: 100 },
    request: { ...completeCase.request, amount: 0 },
  });
  assert.equal(report.reverseStress.rateIncrease.status, 'not_reached_within_search_range');
});

test('reverse stress reports zero headroom when base DSCR is exactly at the floor', () => {
  const report = analyzeCreditCase({
    ...completeCase,
    financials: { ...completeCase.financials, annualDebtService: 45000 },
    request: { ...completeCase.request, amount: 0 },
    policy: { ...completeCase.policy, minimumDscr: 2 },
  });
  assert.equal(report.reverseStress.ebitdaDecline.status, 'at_threshold');
  assert.equal(report.reverseStress.ebitdaDecline.maximumDecline, 0);
  assert.equal(report.reverseStress.rateIncrease.status, 'at_threshold');
  assert.equal(report.reverseStress.rateIncrease.maximumIncrease, 0);
});

test('memo shows policy headroom and reverse stress disclaimers', () => {
  const markdown = toMarkdown(analyzeCreditCase(completeCase));
  assert.match(markdown, /Policy headroom and reverse stress/);
  assert.match(markdown, /Tightest currently within-tolerance metric/);
  assert.match(markdown, /not forecasts, recommended terms, or lending decisions/);
});