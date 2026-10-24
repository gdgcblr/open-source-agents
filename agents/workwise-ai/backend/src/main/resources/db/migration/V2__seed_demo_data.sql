-- Demonstration data for WorkWise AI.
-- Every development here is fictional/illustrative. None of it represents a real event, a real
-- person, or a real company, and no URL is fabricated (source_url left NULL for demo items).

INSERT INTO information_source (id, name, type, url, authoritative, active)
VALUES ('00000000-0000-0000-0000-000000000001', 'WorkWise AI Demonstration Data Set', 'DEMO', NULL, false, false);

-- Demonstration profile: fictional textile trader in Surat with a limited purchasing budget.
INSERT INTO user_profile (
    id, occupation, industry, country, region, city, business_type, primary_objective,
    secondary_objectives, budget_amount, risk_tolerance, relevant_keywords, preferred_language,
    preferred_categories, owner_user_id
) VALUES (
    '00000000-0000-0000-0000-000000000010',
    'Textile Trader', 'Textiles and Garments', 'India', 'Gujarat', 'Surat', 'SMALL_BUSINESS',
    'INCREASE_BUSINESS_PROFIT',
    ARRAY['REDUCE_EXPENSES', 'FIND_CUSTOMERS'],
    150000.00, 'MEDIUM',
    ARRAY['cotton', 'fabric', 'textile', 'garment', 'supplier'],
    'en',
    ARRAY['MARKET_PRICES', 'SUPPLY_CHAINS', 'CUSTOMER_DEMAND'],
    'demo-textile-trader'
);

-- Demonstration profile: software engineer, to show the relevance engine is not textile-only.
INSERT INTO user_profile (
    id, occupation, industry, country, region, city, business_type, primary_objective,
    secondary_objectives, budget_amount, risk_tolerance, relevant_keywords, preferred_language,
    preferred_categories, owner_user_id
) VALUES (
    '00000000-0000-0000-0000-000000000011',
    'Software Engineer', 'Information Technology', 'India', 'Karnataka', 'Bengaluru', 'SALARIED_EMPLOYEE',
    'DISCOVER_CAREER_OPPORTUNITIES',
    ARRAY['LEARN_VALUABLE_SKILLS', 'INCREASE_INCOME'],
    NULL, 'LOW',
    ARRAY['java', 'cloud', 'backend', 'software'],
    'en',
    ARRAY['EMPLOYMENT', 'TECHNOLOGY', 'TRAINING_AND_SKILLS'],
    'demo-software-engineer'
);

-- 1. Hypothetical change in fabric prices in Surat.
INSERT INTO development (
    id, title, summary, source_id, source_url, published_at, event_at, country, region,
    industry_tags, category, evidence_state, is_demo_data, content_hash
) VALUES (
    '00000000-0000-0000-0000-000000000101',
    'DEMONSTRATION DATA: Illustrative rise in raw cotton fabric prices in Surat',
    'In this illustrative scenario, wholesale cotton fabric prices in Surat are shown rising by roughly 8% over four weeks due to a hypothetical reduction in raw cotton supply. This is a fictional, illustrative figure for demonstration purposes only, not a real market report.',
    '00000000-0000-0000-0000-000000000001', NULL, now() - interval '2 days', now() - interval '2 days',
    'India', 'Surat', ARRAY['textiles', 'cotton', 'fabric'], 'MARKET_PRICES', 'DEMONSTRATION_DATA', true,
    'demo-hash-0101-surat-fabric-prices'
);

-- 2. Hypothetical announcement about new textile production capacity in China.
INSERT INTO development (
    id, title, summary, source_id, source_url, published_at, event_at, country, region,
    industry_tags, category, evidence_state, is_demo_data, content_hash
) VALUES (
    '00000000-0000-0000-0000-000000000102',
    'DEMONSTRATION DATA: Illustrative announcement of new textile production capacity in China',
    'This illustrative scenario describes a fictional announcement of new textile manufacturing capacity coming online in China, which could hypothetically increase competition on price for bulk fabric orders. This is fictional demonstration data, not an attribution to any real company or government.',
    '00000000-0000-0000-0000-000000000001', NULL, now() - interval '5 days', now() - interval '5 days',
    'China', NULL, ARRAY['textiles', 'manufacturing'], 'BUSINESS_INVESTMENTS', 'DEMONSTRATION_DATA', true,
    'demo-hash-0102-china-capacity'
);

-- 3. Illustrative change in transport costs.
INSERT INTO development (
    id, title, summary, source_id, source_url, published_at, event_at, country, region,
    industry_tags, category, evidence_state, is_demo_data, content_hash
) VALUES (
    '00000000-0000-0000-0000-000000000103',
    'DEMONSTRATION DATA: Illustrative increase in inter-state freight costs',
    'This illustrative scenario shows a fictional 5% rise in road freight costs affecting goods moved between Gujarat and neighboring states, used here only to demonstrate the financial calculator''s transport cost input.',
    '00000000-0000-0000-0000-000000000001', NULL, now() - interval '10 days', now() - interval '10 days',
    'India', 'Gujarat', ARRAY['logistics', 'transport'], 'SUPPLY_CHAINS', 'DEMONSTRATION_DATA', true,
    'demo-hash-0103-freight-costs'
);

-- 4. A fictional trader's account of testing a new supplier.
INSERT INTO development (
    id, title, summary, source_id, source_url, published_at, event_at, country, region,
    industry_tags, category, evidence_state, is_demo_data, content_hash
) VALUES (
    '00000000-0000-0000-0000-000000000104',
    'DEMONSTRATION DATA: Fictional trader account of testing a new fabric supplier',
    'In this fictional illustrative account, a hypothetical trader describes trialing a smaller batch order from a new regional supplier before committing to a full order, reporting a modestly lower per-unit cost but longer lead time. This is an invented illustrative narrative for demonstration only.',
    '00000000-0000-0000-0000-000000000001', NULL, now() - interval '20 days', now() - interval '20 days',
    'India', 'Gujarat', ARRAY['textiles', 'supplier'], 'SUPPLY_CHAINS', 'DEMONSTRATION_DATA', true,
    'demo-hash-0104-trader-account'
);

-- 5. An illustrative demand trend.
INSERT INTO development (
    id, title, summary, source_id, source_url, published_at, event_at, country, region,
    industry_tags, category, evidence_state, is_demo_data, content_hash
) VALUES (
    '00000000-0000-0000-0000-000000000105',
    'DEMONSTRATION DATA: Illustrative seasonal rise in demand for cotton garments',
    'This illustrative scenario depicts a fictional seasonal uptick in retail demand for cotton garments ahead of a festival period, used only to demonstrate customer-demand-related relevance scoring.',
    '00000000-0000-0000-0000-000000000001', NULL, now() - interval '1 days', now() - interval '1 days',
    'India', 'Gujarat', ARRAY['textiles', 'garments', 'retail'], 'CUSTOMER_DEMAND', 'DEMONSTRATION_DATA', true,
    'demo-hash-0105-demand-trend'
);

-- 6. Software-engineer-relevant illustrative development (shows relevance engine generality).
INSERT INTO development (
    id, title, summary, source_id, source_url, published_at, event_at, country, region,
    industry_tags, category, evidence_state, is_demo_data, content_hash
) VALUES (
    '00000000-0000-0000-0000-000000000106',
    'DEMONSTRATION DATA: Illustrative rise in demand for backend/cloud engineers',
    'This illustrative scenario describes a fictional increase in job postings for backend and cloud engineers in Bengaluru, used only to demonstrate employment/skills-related relevance scoring for a software engineer profile.',
    '00000000-0000-0000-0000-000000000001', NULL, now() - interval '3 days', now() - interval '3 days',
    'India', 'Karnataka', ARRAY['software', 'cloud', 'backend', 'java'], 'EMPLOYMENT', 'DEMONSTRATION_DATA', true,
    'demo-hash-0106-swe-demand'
);
