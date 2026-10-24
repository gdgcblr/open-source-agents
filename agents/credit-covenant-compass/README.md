# Credit Covenant Compass

> Map borrower financial trends, policy headroom, and reverse-stress breakpoints into a transparent, analyst-reviewed credit memo.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Analysts often reconcile financial figures and redo the same ratio and scenario calculations across credit cases. Missing inputs and undocumented assumptions can make reviews slower and harder to reproduce.
- **Intended Users**: Commercial credit analysts and lending teams who need a consistent first-pass analysis from normalized financial data.

### Key Features
- Calculates DSCR, debt-to-EBITDA, current ratio, working capital, interest coverage, and proposed annual debt service.
- Compares base and downside cases against explicit, user-supplied policy thresholds (or clearly disclosed example defaults).
- Captures source descriptions and dates alongside the supplied figures.
- Identifies missing or non-calculable inputs instead of treating them as passes.
- Shows year-over-year revenue, margin, DSCR, and leverage trends when ordered historical periods are supplied.
- Generates a bounded facility-size and rate sensitivity grid for transparent what-if analysis.
- Quantifies base-case policy headroom and reverse-stresses EBITDA or interest rates to the DSCR floor.
- Produces Markdown or JSON; every case remains subject to human review.

## Technical Stack

- **Language & Runtime**: Node.js 20+
- **Agent Framework / Core Library**: A deterministic, dependency-free JavaScript analysis workflow.
- **Models**: None. Ratios and scenario outputs use explicit formulas rather than opaque model-generated credit scores.
- **External APIs / Tools**: None. The agent reads a local JSON case file and writes a local report.

## Architecture & Data Flow

```text
Normalized financials + source notes + proposed facility + policy thresholds
                                  |
                     Input validation and missing-data checks
                                  |
          Amortization + base ratios + downside sensitivity calculations
                                  |
             Policy-threshold comparisons (not a credit decision)
                                  |
                  Review prompts + Markdown / JSON memo
```

No external bank systems are connected. The analyst prepares a normalized case file and records the origin/date of each financial source. Unknown fields stay unknown; the agent does not impute values.

## Prerequisites

- Node.js 20 or newer and npm.
- No API key, database, or third-party package is required.

## Installation & Setup

From this directory:

```bash
npm install
```

## Configuration & Environment Variables

No environment variables or credentials are required. `.env.example` is present as a sanitized template and documents that configuration is not needed.

## Input Format

Create a JSON file with a proposed facility, normalized financials, policy thresholds, stress assumptions, and source notes. See [`examples/sample-case.json`](examples/sample-case.json) for a synthetic case.

Supported financial fields are annual revenue, EBITDA, EBIT, interest expense, existing total debt, existing annual debt service, current assets, and current liabilities. Amounts must use the stated currency consistently. `annualRate` is a decimal (for example, `0.08` means 8%). Financial fields may be omitted; dependent calculations will be marked not calculable.

The optional `historicalFinancials` array accepts 2 to 10 unique, ascending annual records with a four-digit `period` and the supported financial fields. It calculates year-over-year revenue growth, EBITDA margin, DSCR, and debt-to-EBITDA changes; a ratio with a missing or nonpositive denominator is not calculable.

The optional `sensitivity` object accepts `amountMultipliers` and `rateIncreases` arrays, each with 1 to 5 values. The default grid uses 0.75x, 1.0x, and 1.25x the requested amount at the base and stressed rates. These are illustrative combinations, not recommended terms; configure the grid to match the analyst's question.

The report also shows the base-case distance to each policy threshold and the tightest calculable metric that remains within tolerance. Reverse stress solves for the EBITDA decline and annual-rate increase that bring DSCR to `minimumDscr`, holding all other inputs fixed. The rate search is capped at a 100% annual rate; results beyond the search range are reported as not reached. If base DSCR is already below the threshold or required inputs are missing, the report says so instead of presenting a positive headroom value.

The policy object accepts `minimumDscr`, `maximumDebtToEbitda`, `minimumCurrentRatio`, and `minimumInterestCoverage`. Example defaults are 1.25x, 3.5x, 1.1x, and 2.0x respectively; these are illustrative only and must be replaced with institution-approved thresholds before operational use. The downside object accepts `ebitdaDecline` and `annualRateIncrease` as decimals.

Each source entry should include a short `source` description and may include `field` and `asOf`. Do not put account numbers, government identifiers, credentials, or unnecessary personal data in the case file. The tool ignores extra data and only calculates from its documented financial fields.

## How to Run

```bash
node src/cli.js examples/sample-case.json
node src/cli.js --format json examples/sample-case.json
node src/cli.js --format markdown --report-file=credit-memo.md examples/sample-case.json
```

## Example Input & Output

The checked-in example uses synthetic figures and documents its sources as synthetic. Run it locally to see the precise output. A report includes:

```text
Review status: Human review required
Base case: DSCR, debt / EBITDA, current ratio, interest coverage, and policy comparison
Downside case: stressed ratios under stated EBITDA and rate assumptions
Data quality: missing fields and source references
Analyst review prompts: evidence verification and independent policy review
```

## How to Test

```bash
npm test
```

Tests cover loan amortization, known ratio values, downside/facility sensitivities, historical trends, policy headroom, reverse-stress boundaries, nonpositive denominators, missing data, memo disclaimers, and invalid input ranges.

## Known Limitations

- This is a calculation and memo-drafting aid, not a credit scoring, lending, pricing, approval, or denial system.
- Figures are only as reliable as the values and source notes supplied by the analyst; the agent does not connect to or verify bank systems.
- The default threshold values are illustrative, not recommendations. Use approved institution policy and applicable regulation.
- The downside case reduces EBITDA directly; it does not forecast revenue, margins, covenants, collateral values, or borrower behavior.
- Historical trends are descriptive and do not account for acquisitions, accounting changes, seasonality, or one-time events. Verify period comparability before interpreting a trend.
- Sensitivity cases are arithmetic comparisons around analyst-entered inputs, not optimized terms or recommendations.
- Reverse-stress breakpoints are one-variable-at-a-time mathematical thresholds, not probability estimates, forecasts, or recommended limits.
- Proposed debt service uses level monthly amortization. Actual fees, payment schedules, variable-rate terms, balloons, taxes, and covenants are not modeled.
- Proposed interest expense is approximated using the initial principal balance and annual rate.
- Ratios are not meaningful for every business or facility structure. Analysts must assess context and data periods.

## Security & Privacy Considerations

- All processing is local; the application does not make network requests.
- Do not include protected characteristics or unnecessary personal or account identifiers. Extra fields are ignored by the calculation engine.
- Treat input case files and generated memos as confidential financial records and store them according to organizational policy.
- The agent does not recommend a borrower outcome. A qualified human reviewer must verify the evidence, assess applicable policy and law, and make any decision.

## Future Improvements

- [ ] Add a configurable institution-policy file with provenance and version tracking.
- [ ] Add source-to-field mapping and reconciliation checks for imported financial statements.
- [ ] Add an optional, locally generated audit bundle with inputs, assumptions, and calculation version.

## License

This project is contributed under the repository's open-source license.