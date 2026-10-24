-- WorkWise AI initial schema

CREATE TABLE user_profile (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    occupation VARCHAR(120) NOT NULL,
    industry VARCHAR(120) NOT NULL,
    country VARCHAR(80) NOT NULL,
    region VARCHAR(120),
    city VARCHAR(120),
    business_type VARCHAR(60) NOT NULL,
    primary_objective VARCHAR(60) NOT NULL,
    secondary_objectives TEXT[] NOT NULL DEFAULT '{}',
    budget_amount NUMERIC(14,2),
    risk_tolerance VARCHAR(20) NOT NULL,
    relevant_keywords TEXT[] NOT NULL DEFAULT '{}',
    preferred_language VARCHAR(10) NOT NULL DEFAULT 'en',
    preferred_categories TEXT[] NOT NULL DEFAULT '{}',
    owner_user_id VARCHAR(60) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_user_profile_owner ON user_profile(owner_user_id);

CREATE TABLE information_source (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(160) NOT NULL,
    type VARCHAR(20) NOT NULL,
    url VARCHAR(500),
    authoritative BOOLEAN NOT NULL DEFAULT false,
    active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE development (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(300) NOT NULL,
    summary TEXT NOT NULL,
    source_id UUID REFERENCES information_source(id),
    source_url VARCHAR(500),
    published_at TIMESTAMPTZ,
    event_at TIMESTAMPTZ,
    country VARCHAR(80),
    region VARCHAR(120),
    industry_tags TEXT[] NOT NULL DEFAULT '{}',
    category VARCHAR(40) NOT NULL,
    evidence_state VARCHAR(30) NOT NULL,
    is_demo_data BOOLEAN NOT NULL DEFAULT false,
    content_hash VARCHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_development_published_at ON development(published_at);
CREATE INDEX idx_development_category ON development(category);

CREATE TABLE development_evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    development_id UUID NOT NULL REFERENCES development(id),
    evidence_text TEXT NOT NULL,
    source_id UUID REFERENCES information_source(id),
    source_url VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_development_evidence_development ON development_evidence(development_id);

CREATE TABLE relevance_assessment (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id UUID NOT NULL REFERENCES user_profile(id),
    development_id UUID NOT NULL REFERENCES development(id),
    job_industry_score DOUBLE PRECISION NOT NULL,
    economic_score DOUBLE PRECISION NOT NULL,
    actionability_score DOUBLE PRECISION NOT NULL,
    location_score DOUBLE PRECISION NOT NULL,
    recency_score DOUBLE PRECISION NOT NULL,
    goal_alignment_score DOUBLE PRECISION NOT NULL,
    weighted_score DOUBLE PRECISION NOT NULL,
    explanation TEXT NOT NULL,
    is_dismissed BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_relevance_profile_development UNIQUE (profile_id, development_id)
);
CREATE INDEX idx_relevance_profile_score ON relevance_assessment(profile_id, weighted_score DESC);

CREATE TABLE opportunity_analysis (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id UUID NOT NULL REFERENCES user_profile(id),
    development_id UUID NOT NULL REFERENCES development(id),
    summary TEXT NOT NULL,
    confirmed_facts TEXT[] NOT NULL DEFAULT '{}',
    why_it_matters TEXT NOT NULL,
    historical_comparisons TEXT[] NOT NULL DEFAULT '{}',
    trends TEXT[] NOT NULL DEFAULT '{}',
    unknowns TEXT[] NOT NULL DEFAULT '{}',
    next_steps TEXT[] NOT NULL DEFAULT '{}',
    provider VARCHAR(10) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_analysis_profile ON opportunity_analysis(profile_id);

CREATE TABLE strategy (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID NOT NULL REFERENCES opportunity_analysis(id),
    name VARCHAR(160) NOT NULL,
    description TEXT NOT NULL,
    rationale TEXT NOT NULL,
    evidence TEXT[] NOT NULL DEFAULT '{}',
    required_investment NUMERIC(14,2),
    required_resources TEXT[] NOT NULL DEFAULT '{}',
    time_commitment VARCHAR(200),
    benefits TEXT[] NOT NULL DEFAULT '{}',
    risks TEXT[] NOT NULL DEFAULT '{}',
    dependencies TEXT[] NOT NULL DEFAULT '{}',
    failure_conditions TEXT[] NOT NULL DEFAULT '{}',
    validation_steps TEXT[] NOT NULL DEFAULT '{}',
    next_action TEXT,
    confidence_level VARCHAR(10) NOT NULL,
    confidence_justification TEXT,
    is_wait_and_research BOOLEAN NOT NULL DEFAULT false,
    is_selected BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_strategy_analysis ON strategy(analysis_id);

CREATE TABLE financial_scenario (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_id UUID NOT NULL REFERENCES strategy(id),
    scenario_type VARCHAR(10) NOT NULL,
    quantity NUMERIC(14,2) NOT NULL,
    unit_cost NUMERIC(14,2) NOT NULL,
    transport_cost NUMERIC(14,2) NOT NULL DEFAULT 0,
    taxes_duties NUMERIC(14,2) NOT NULL DEFAULT 0,
    handling_cost NUMERIC(14,2) NOT NULL DEFAULT 0,
    qc_cost NUMERIC(14,2) NOT NULL DEFAULT 0,
    other_acquisition_cost NUMERIC(14,2) NOT NULL DEFAULT 0,
    selling_price NUMERIC(14,2) NOT NULL,
    variable_selling_cost NUMERIC(14,2) NOT NULL DEFAULT 0,
    other_operating_cost NUMERIC(14,2) NOT NULL DEFAULT 0,
    expected_sales_quantity NUMERIC(14,2) NOT NULL,
    unsold_inventory_assumption NUMERIC(14,2) NOT NULL DEFAULT 0,
    total_acquisition_cost NUMERIC(14,2),
    revenue NUMERIC(14,2),
    gross_margin NUMERIC(14,2),
    contribution NUMERIC(14,2),
    net_profit NUMERIC(14,2),
    cash_required NUMERIC(14,2),
    unsold_inventory_value NUMERIC(14,2),
    assumptions TEXT[] NOT NULL DEFAULT '{}',
    is_incomplete BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_financial_scenario_strategy ON financial_scenario(strategy_id);

CREATE TABLE action_plan (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_id UUID NOT NULL REFERENCES strategy(id),
    title VARCHAR(200) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE action_item (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    action_plan_id UUID NOT NULL REFERENCES action_plan(id),
    sequence_no INT NOT NULL,
    action TEXT NOT NULL,
    estimated_duration VARCHAR(100),
    required_resources TEXT[] NOT NULL DEFAULT '{}',
    expected_cost NUMERIC(14,2),
    success_metric TEXT,
    main_risk TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'NOT_STARTED',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_action_item_plan ON action_item(action_plan_id, sequence_no);

CREATE TABLE strategy_outcome (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_id UUID NOT NULL REFERENCES strategy(id),
    date_started DATE,
    date_completed DATE,
    actual_expenses NUMERIC(14,2),
    actual_revenue NUMERIC(14,2),
    time_spent_hours NUMERIC(10,2),
    orders_received INT,
    customers_acquired INT,
    user_reported_outcome TEXT,
    lessons_learned TEXT,
    is_independently_verified BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_strategy_outcome_strategy ON strategy_outcome(strategy_id);

CREATE TABLE user_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id UUID NOT NULL REFERENCES user_profile(id),
    development_id UUID NOT NULL REFERENCES development(id),
    feedback_type VARCHAR(30) NOT NULL,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
