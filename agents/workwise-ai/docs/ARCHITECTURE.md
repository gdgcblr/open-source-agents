# WorkWise AI — Architecture Document

## 1. Overview

WorkWise AI is a personalized work/business opportunity intelligence platform. It is built as a
**modular monolith**: a single Spring Boot backend application, internally separated into clear
modules with their own entities, repositories, services, DTOs, and controllers, paired with an
Angular single-page frontend.

No microservices, message queues, or big-data infrastructure are used in this first version, per
the project requirements.

## 2. High-level component diagram

```
┌──────────────────────────────┐        REST/JSON        ┌───────────────────────────────────────┐
│        Angular Frontend       │ ───────────────────────▶│          Spring Boot Backend           │
│  (feed, analysis, strategies, │ ◀─────────────────────── │  (modular monolith, see modules below) │
│  financial calc, action plan) │                          └───────────────────────────────────────┘
└──────────────────────────────┘                                          │
                                                                           ▼
                                                              ┌─────────────────────────┐
                                                              │  PostgreSQL (Flyway)    │
                                                              └─────────────────────────┘
                                                                           │
                                                      ┌────────────────────┼─────────────────────┐
                                                      ▼                    ▼                     ▼
                                           Source adapters          AI provider          (future: real
                                           (Demo, RSS)             (Mock / real LLM)      news/licensed APIs)
```

## 3. Backend modules (package `com.workwise.ai.*`)

| Module | Responsibility |
|---|---|
| `common` | Shared base entities, pagination, API error model, exception handling, demo-user auth filter |
| `profile` | `UserProfile` CRUD, objectives, preferences |
| `sources` | `InformationSource` registry + `SourceAdapter` interface (Demo, RSS) |
| `ingestion` | Pulls from source adapters, deduplicates, persists `Development` + `DevelopmentEvidence` |
| `news` | `Development` read model: list/detail/filter endpoints |
| `relevance` | Explainable scoring engine producing `RelevanceAssessment` per (profile, development) |
| `analysis` | `OpportunityAnalysis` orchestration + `OpportunityAnalysisProvider` interface (Mock/LLM) |
| `strategies` | `Strategy` generation (via analysis provider) + comparison logic |
| `financial` | Deterministic Java financial calculator (`FinancialScenario`) — **no LLM arithmetic** |
| `actionplan` | `ActionPlan` / `ActionItem` CRUD and status transitions |
| `outcomes` | `StrategyOutcome` recording and comparison vs. assumptions |
| `feedback` | `UserFeedback` ("mark irrelevant") |

Each module (excluding `common`) follows: `domain` (JPA entities + enums) → `repository` →
`service` (business logic) → `web` (controller + DTOs + mapper).

## 4. Data flow for the core workflow

1. **Profile**: user creates/edits `UserProfile`.
2. **Ingestion**: `IngestionService` runs (on-demand endpoint + scheduled job) pulling from all
   active `InformationSource`s via `SourceAdapter`, dedups by `(sourceUrl, title-hash)`, persists
   `Development` rows with `EvidenceState`.
3. **Relevance**: `RelevanceService` scores every `(profile, development)` pair lazily when the
   feed is requested (and caches the result as `RelevanceAssessment`), using the explainable
   weighted model from the spec. Only developments above the configured threshold are returned.
4. **Feed**: `FeedController` groups scored developments into "Important for your work",
   "Potential opportunities", "Trends", "Saved analyses".
5. **Analysis**: user triggers `POST /api/analysis` for a development + profile. `AnalysisService`
   calls `OpportunityAnalysisProvider` (mock by default) to build the structured report AND to
   propose 2-4 `Strategy` drafts. Source facts/evidence are attached from the `Development` record,
   never invented by the provider.
6. **Financial scenario**: for a chosen strategy, the user supplies purchase/selling assumptions;
   `FinancialCalculatorService` (pure deterministic Java, `BigDecimal`) computes
   low/base/high scenarios.
7. **Strategy comparison**: `StrategyComparisonService` compares strategies on investment, risk,
   evidence quality, reversibility — never ranks by revenue alone.
8. **Action plan**: user converts a chosen strategy into an `ActionPlan` with ordered `ActionItem`s.
9. **Outcome**: user records actual results; `OutcomeService` compares against the original
   financial assumptions and strategy expectations.

## 5. AI provider abstraction

```java
public interface OpportunityAnalysisProvider {
    AnalysisResult analyze(AnalysisRequest request);
    List<StrategyDraft> proposeStrategies(AnalysisRequest request, AnalysisResult analysis);
}
```

- `MockOpportunityAnalysisProvider`: deterministic, rule-based, no network calls — default active
  profile so the whole app runs with zero API keys.
- `LlmOpportunityAnalysisProvider`: calls a configurable HTTP LLM endpoint (model + key from env
  vars only, never sent to the frontend), validates the JSON response against the same
  `AnalysisResult`/`StrategyDraft` schema, and falls back to a clear error (never silently invents
  data) if the response is malformed or the call times out.

Selection is via `workwise.ai.provider=mock|llm` (Spring profile/property), defaulting to `mock`.

## 6. Evidence / verification model

`EvidenceState` enum: `UNVERIFIED`, `PARTIALLY_VERIFIED`, `VERIFIED`, `DEMONSTRATION_DATA`.

Rules (enforced in `ingestion`):
- Items from the `demo` seed adapter are always `DEMONSTRATION_DATA` and additionally flagged
  `isDemoData=true` at the entity level, surfaced in every DTO.
- Items from a single RSS source default to `UNVERIFIED`.
- An item becomes `PARTIALLY_VERIFIED` when a second independent source reports a materially
  similar claim (matched by simple title/entity overlap heuristic) and `VERIFIED` only when the
  item also carries a recognized authoritative source flag (`InformationSource.authoritative=true`)
  — this is the single implemented verification rule for the prototype; it is intentionally simple
  and documented as a limitation.

## 7. Authentication (prototype)

Full OAuth/login is out of scope for the first prototype per the spec's allowance. A
`DemoUserFilter` reads `X-Demo-User-Id` header (defaults to a seeded demo user id) and populates a
request-scoped `CurrentUser`. All profile-scoped endpoints check that the resource's owning
`userId` matches `CurrentUser` — this still enforces per-user isolation (it is not "whatever id the
frontend passes wins" — the frontend never asserts *other* users' ids, and the filter is the single
place that would be replaced by real authentication later). This is documented as a known
limitation in the README.

## 8. Technology versions

- Java 21, Spring Boot 3.3.x, Maven
- PostgreSQL 16, Flyway
- Angular 17 (CLI 17.3.17), TypeScript 5, Node 18.19
- Docker Compose for local orchestration

## 9. Known limitations

See `docs/LIMITATIONS.md`.
