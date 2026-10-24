package com.workwise.ai.relevance.service;

import com.workwise.ai.news.domain.Development;
import com.workwise.ai.news.domain.DevelopmentCategory;
import com.workwise.ai.profile.domain.Objective;
import com.workwise.ai.profile.domain.UserProfile;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.time.Instant;
import java.util.EnumMap;
import java.util.EnumSet;
import java.util.HashSet;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/**
 * Pure, explainable, deterministic scoring logic — no persistence, no AI calls. Kept separate from
 * {@link RelevanceService} so it can be unit tested in isolation.
 *
 * <p>"Meaningful connection" gate: a development is only considered for a profile's feed when it
 * has some real industry/keyword overlap (jobIndustryScore &gt;= 15) <b>and</b> at least one other
 * dimension (economic relevance, actionability, or a strong goal match) also clears a minimum bar.
 * This intentionally prevents a development from appearing solely because of a shallow keyword
 * match, per product requirements.</p>
 */
@Component
public class RelevanceScorer {

    private static final Map<DevelopmentCategory, Double> ECONOMIC_BASE = new EnumMap<>(DevelopmentCategory.class);
    private static final Map<DevelopmentCategory, Double> ACTIONABILITY_BASE = new EnumMap<>(DevelopmentCategory.class);
    private static final Map<Objective, Set<DevelopmentCategory>> GOAL_CATEGORY_MAP = new EnumMap<>(Objective.class);

    static {
        ECONOMIC_BASE.put(DevelopmentCategory.MARKET_PRICES, 90.0);
        ECONOMIC_BASE.put(DevelopmentCategory.BUSINESS_INVESTMENTS, 80.0);
        ECONOMIC_BASE.put(DevelopmentCategory.SUPPLY_CHAINS, 75.0);
        ECONOMIC_BASE.put(DevelopmentCategory.GOVERNMENT_POLICY, 70.0);
        ECONOMIC_BASE.put(DevelopmentCategory.CUSTOMER_DEMAND, 70.0);
        ECONOMIC_BASE.put(DevelopmentCategory.COMPETITOR_DEVELOPMENTS, 65.0);
        ECONOMIC_BASE.put(DevelopmentCategory.EMPLOYMENT, 60.0);
        ECONOMIC_BASE.put(DevelopmentCategory.INDUSTRY_CHANGES, 60.0);
        ECONOMIC_BASE.put(DevelopmentCategory.TECHNOLOGY, 55.0);
        ECONOMIC_BASE.put(DevelopmentCategory.WEATHER_AND_CLIMATE, 50.0);
        ECONOMIC_BASE.put(DevelopmentCategory.TRAINING_AND_SKILLS, 40.0);

        ACTIONABILITY_BASE.put(DevelopmentCategory.MARKET_PRICES, 85.0);
        ACTIONABILITY_BASE.put(DevelopmentCategory.SUPPLY_CHAINS, 80.0);
        ACTIONABILITY_BASE.put(DevelopmentCategory.CUSTOMER_DEMAND, 75.0);
        ACTIONABILITY_BASE.put(DevelopmentCategory.TRAINING_AND_SKILLS, 70.0);
        ACTIONABILITY_BASE.put(DevelopmentCategory.TECHNOLOGY, 65.0);
        ACTIONABILITY_BASE.put(DevelopmentCategory.COMPETITOR_DEVELOPMENTS, 60.0);
        ACTIONABILITY_BASE.put(DevelopmentCategory.BUSINESS_INVESTMENTS, 60.0);
        ACTIONABILITY_BASE.put(DevelopmentCategory.GOVERNMENT_POLICY, 55.0);
        ACTIONABILITY_BASE.put(DevelopmentCategory.EMPLOYMENT, 55.0);
        ACTIONABILITY_BASE.put(DevelopmentCategory.WEATHER_AND_CLIMATE, 50.0);
        ACTIONABILITY_BASE.put(DevelopmentCategory.INDUSTRY_CHANGES, 55.0);

        GOAL_CATEGORY_MAP.put(Objective.INCREASE_INCOME, EnumSet.of(
                DevelopmentCategory.MARKET_PRICES, DevelopmentCategory.CUSTOMER_DEMAND, DevelopmentCategory.EMPLOYMENT));
        GOAL_CATEGORY_MAP.put(Objective.INCREASE_BUSINESS_PROFIT, EnumSet.of(
                DevelopmentCategory.MARKET_PRICES, DevelopmentCategory.BUSINESS_INVESTMENTS, DevelopmentCategory.CUSTOMER_DEMAND));
        GOAL_CATEGORY_MAP.put(Objective.REDUCE_EXPENSES, EnumSet.of(
                DevelopmentCategory.SUPPLY_CHAINS, DevelopmentCategory.MARKET_PRICES));
        GOAL_CATEGORY_MAP.put(Objective.FIND_CUSTOMERS, EnumSet.of(
                DevelopmentCategory.CUSTOMER_DEMAND, DevelopmentCategory.COMPETITOR_DEVELOPMENTS));
        GOAL_CATEGORY_MAP.put(Objective.IMPROVE_PRODUCTIVITY, EnumSet.of(
                DevelopmentCategory.TECHNOLOGY, DevelopmentCategory.TRAINING_AND_SKILLS));
        GOAL_CATEGORY_MAP.put(Objective.DISCOVER_CAREER_OPPORTUNITIES, EnumSet.of(
                DevelopmentCategory.EMPLOYMENT, DevelopmentCategory.TRAINING_AND_SKILLS));
        GOAL_CATEGORY_MAP.put(Objective.LEARN_VALUABLE_SKILLS, EnumSet.of(
                DevelopmentCategory.TRAINING_AND_SKILLS, DevelopmentCategory.TECHNOLOGY));
        GOAL_CATEGORY_MAP.put(Objective.IDENTIFY_MARKET_CHANGES, EnumSet.of(
                DevelopmentCategory.MARKET_PRICES, DevelopmentCategory.INDUSTRY_CHANGES, DevelopmentCategory.COMPETITOR_DEVELOPMENTS));
        GOAL_CATEGORY_MAP.put(Objective.IMPROVE_OPERATIONAL_EFFICIENCY, EnumSet.of(
                DevelopmentCategory.TECHNOLOGY, DevelopmentCategory.SUPPLY_CHAINS));
    }

    public ScoreBreakdown score(UserProfile profile, Development development) {
        double jobIndustryScore = scoreJobIndustry(profile, development);
        double economicScore = ECONOMIC_BASE.getOrDefault(development.getCategory(), 40.0);
        double actionabilityScore = ACTIONABILITY_BASE.getOrDefault(development.getCategory(), 40.0);
        double locationScore = scoreLocation(profile, development);
        double recencyScore = scoreRecency(development.getPublishedAt());
        double goalAlignmentScore = scoreGoalAlignment(profile, development);

        // A single incidental shared word (e.g. the profile's industry name appearing once in a
        // mostly-unrelated summary) must not alone satisfy the gate - require a stronger overlap
        // ratio than a lone coincidental match would produce before combining with the other
        // signals below.
        boolean meaningfulConnection = jobIndustryScore >= 25
                && (economicScore >= 35 || actionabilityScore >= 35 || goalAlignmentScore >= 70);

        return new ScoreBreakdown(jobIndustryScore, economicScore, actionabilityScore, locationScore,
                recencyScore, goalAlignmentScore, meaningfulConnection);
    }

    public String explain(UserProfile profile, Development development, ScoreBreakdown scores) {
        if (!scores.meaningfulConnection()) {
            return "This development does not have a clear, meaningful connection to your work and was excluded.";
        }
        String categoryPhrase = switch (development.getCategory()) {
            case MARKET_PRICES -> "prices you pay or charge";
            case SUPPLY_CHAINS -> "the availability or cost of your supplies";
            case BUSINESS_INVESTMENTS -> "investment and funding conditions in your industry";
            case GOVERNMENT_POLICY -> "regulations or policy affecting your work";
            case CUSTOMER_DEMAND -> "demand from your customers";
            case COMPETITOR_DEVELOPMENTS -> "what your competitors are doing";
            case EMPLOYMENT -> "hiring and compensation in your field";
            case TECHNOLOGY -> "tools and technology relevant to your work";
            case TRAINING_AND_SKILLS -> "skills that are becoming more or less valuable";
            case WEATHER_AND_CLIMATE -> "conditions that could disrupt your operations";
            case INDUSTRY_CHANGES -> "broader changes in your industry";
        };
        return "This development may matter to your " + profile.getIndustry()
                + " work as a " + profile.getOccupation() + " because it could affect " + categoryPhrase + ".";
    }

    private double scoreJobIndustry(UserProfile profile, Development development) {
        Set<String> profileTerms = new HashSet<>();
        addTerms(profileTerms, profile.getIndustry());
        addTerms(profileTerms, profile.getOccupation());
        profile.getRelevantKeywords().forEach(k -> addTerms(profileTerms, k));

        Set<String> developmentTerms = new HashSet<>();
        addTerms(developmentTerms, development.getTitle());
        addTerms(developmentTerms, development.getSummary());
        development.getIndustryTags().forEach(t -> addTerms(developmentTerms, t));

        if (profileTerms.isEmpty() || developmentTerms.isEmpty()) {
            return 0.0;
        }
        long matches = profileTerms.stream().filter(developmentTerms::contains).count();
        double ratio = (double) matches / profileTerms.size();
        return Math.min(100.0, ratio * 140.0);
    }

    private double scoreLocation(UserProfile profile, Development development) {
        if (development.getCountry() == null && development.getRegion() == null) {
            return 40.0;
        }
        if (profile.getCity() != null && development.getRegion() != null
                && equalsIgnoreCase(profile.getCity(), development.getRegion())) {
            return 100.0;
        }
        if (profile.getRegion() != null && equalsIgnoreCase(profile.getRegion(), development.getRegion())) {
            return 85.0;
        }
        if (equalsIgnoreCase(profile.getCountry(), development.getCountry())) {
            return 55.0;
        }
        return 10.0;
    }

    private double scoreRecency(Instant publishedAt) {
        if (publishedAt == null) {
            return 30.0;
        }
        long days = Duration.between(publishedAt, Instant.now()).toDays();
        if (days <= 1) return 100.0;
        if (days <= 3) return 90.0;
        if (days <= 7) return 75.0;
        if (days <= 14) return 60.0;
        if (days <= 30) return 40.0;
        if (days <= 90) return 20.0;
        return 10.0;
    }

    private double scoreGoalAlignment(UserProfile profile, Development development) {
        Set<DevelopmentCategory> primarySet = GOAL_CATEGORY_MAP.getOrDefault(profile.getPrimaryObjective(), Set.of());
        if (primarySet.contains(development.getCategory())) {
            return 100.0;
        }
        for (String secondary : profile.getSecondaryObjectives()) {
            try {
                Objective objective = Objective.valueOf(secondary);
                if (GOAL_CATEGORY_MAP.getOrDefault(objective, Set.of()).contains(development.getCategory())) {
                    return 70.0;
                }
            } catch (IllegalArgumentException ignored) {
                // secondary objective stored as free text, not a mapped enum - ignore for scoring
            }
        }
        return 25.0;
    }

    private void addTerms(Set<String> bag, String text) {
        if (text == null || text.isBlank()) {
            return;
        }
        for (String term : text.toLowerCase(Locale.ROOT).split("[^a-z0-9]+")) {
            if (term.length() >= 3) {
                bag.add(term);
            }
        }
    }

    private boolean equalsIgnoreCase(String a, String b) {
        return a != null && b != null && a.equalsIgnoreCase(b);
    }

    public record ScoreBreakdown(
            double jobIndustryScore,
            double economicScore,
            double actionabilityScore,
            double locationScore,
            double recencyScore,
            double goalAlignmentScore,
            boolean meaningfulConnection
    ) {
    }
}
