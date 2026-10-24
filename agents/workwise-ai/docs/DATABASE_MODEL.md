# WorkWise AI — Database Model

PostgreSQL, managed by Flyway migrations in `backend/src/main/resources/db/migration`.
All monetary columns use `NUMERIC(14,2)`. All timestamps are `TIMESTAMPTZ` stored in UTC.

## Tables

### user_profile
| column | type | notes |
|---|---|---|
| id | UUID PK | |
| occupation | VARCHAR(120) | |
| industry | VARCHAR(120) | |
| country | VARCHAR(80) | |
| region | VARCHAR(120) | state/region |
| city | VARCHAR(120) | nullable |
| business_type | VARCHAR(60) | enum-like string |
| primary_objective | VARCHAR(60) | enum string |
| secondary_objectives | TEXT[] | |
| budget_amount | NUMERIC(14,2) | nullable |
| risk_tolerance | VARCHAR(20) | LOW/MEDIUM/HIGH |
| relevant_keywords | TEXT[] | products/services/technologies |
| preferred_language | VARCHAR(10) | default 'en' |
| preferred_categories | TEXT[] | |
| owner_user_id | VARCHAR(60) | demo-user id |
| created_at / updated_at | TIMESTAMPTZ | |

### information_source
id, name, type (DEMO/RSS), url, authoritative (bool), active (bool), created_at

### development
id, title, summary, source_id FK, source_url, published_at, event_at, country, region,
industry_tags TEXT[], category, evidence_state, is_demo_data (bool), content_hash (dedup key),
created_at

### development_evidence
id, development_id FK, evidence_text, source_id FK, source_url, created_at
(supports multiple distinct provenance records per development)

### relevance_assessment
id, profile_id FK, development_id FK, job_industry_score, economic_score, actionability_score,
location_score, recency_score, goal_alignment_score, weighted_score, explanation TEXT,
is_dismissed (bool, from user feedback), created_at
UNIQUE(profile_id, development_id)

### opportunity_analysis
id, profile_id FK, development_id FK, summary, confirmed_facts TEXT[], why_it_matters,
historical_comparisons TEXT[], trends TEXT[], unknowns TEXT[], next_steps TEXT[],
provider (MOCK/LLM), created_at

### strategy
id, analysis_id FK, name, description, rationale, evidence TEXT[], required_investment,
required_resources TEXT[], time_commitment, benefits TEXT[], risks TEXT[], dependencies TEXT[],
failure_conditions TEXT[], validation_steps TEXT[], next_action, confidence_level (LOW/MEDIUM/HIGH),
confidence_justification, is_wait_and_research (bool), created_at

### financial_scenario
id, strategy_id FK, scenario_type (LOW/BASE/HIGH), quantity, unit_cost, transport_cost,
taxes_duties, handling_cost, qc_cost, other_acquisition_cost, selling_price, variable_selling_cost,
other_operating_cost, expected_sales_quantity, unsold_inventory_assumption,
total_acquisition_cost (computed), revenue (computed), contribution (computed),
net_profit (computed, nullable), cash_required (computed), assumptions TEXT[], created_at

### action_plan
id, strategy_id FK, title, created_at

### action_item
id, action_plan_id FK, sequence_no, action, estimated_duration, required_resources TEXT[],
expected_cost, success_metric, main_risk, status (NOT_STARTED/IN_PROGRESS/COMPLETED/SKIPPED)

### strategy_outcome
id, strategy_id FK, date_started, date_completed, actual_expenses, actual_revenue,
time_spent_hours, orders_received, customers_acquired, user_reported_outcome TEXT,
lessons_learned TEXT, is_independently_verified (bool), created_at

### user_feedback
id, profile_id FK, development_id FK, feedback_type (IRRELEVANT), note, created_at

## Indexes
- `development(published_at)`, `development(category)`, `development(content_hash)` unique
- `relevance_assessment(profile_id, weighted_score DESC)`
- `strategy(analysis_id)`, `financial_scenario(strategy_id)`, `action_item(action_plan_id, sequence_no)`
