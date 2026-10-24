package com.workwise.ai.relevance.service;

import com.workwise.ai.news.domain.Development;
import com.workwise.ai.news.domain.DevelopmentCategory;
import com.workwise.ai.profile.domain.BusinessType;
import com.workwise.ai.profile.domain.Objective;
import com.workwise.ai.profile.domain.RiskTolerance;
import com.workwise.ai.profile.domain.UserProfile;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class RelevanceScorerTest {

    private final RelevanceScorer scorer = new RelevanceScorer();

    private UserProfile textileTraderProfile() {
        UserProfile profile = new UserProfile();
        profile.setOccupation("Textile Trader");
        profile.setIndustry("Textiles and Garments");
        profile.setCountry("India");
        profile.setRegion("Gujarat");
        profile.setCity("Surat");
        profile.setBusinessType(BusinessType.SMALL_BUSINESS);
        profile.setPrimaryObjective(Objective.INCREASE_BUSINESS_PROFIT);
        profile.setSecondaryObjectives(List.of("REDUCE_EXPENSES"));
        profile.setRiskTolerance(RiskTolerance.MEDIUM);
        profile.setRelevantKeywords(List.of("cotton", "fabric", "textile"));
        return profile;
    }

    private Development matchingDevelopment() {
        Development d = new Development();
        d.setTitle("Cotton fabric prices rise in Surat textile market");
        d.setSummary("Fabric and cotton costs have increased for textile traders.");
        d.setCategory(DevelopmentCategory.MARKET_PRICES);
        d.setCountry("India");
        d.setRegion("Surat");
        d.setIndustryTags(List.of("textiles", "cotton"));
        d.setPublishedAt(Instant.now());
        return d;
    }

    @Test
    void scoresHighlyRelevantDevelopmentAboveThreshold() {
        RelevanceScorer.ScoreBreakdown scores = scorer.score(textileTraderProfile(), matchingDevelopment());

        assertThat(scores.meaningfulConnection()).isTrue();
        assertThat(scores.jobIndustryScore()).isGreaterThan(15);
        assertThat(scores.economicScore()).isGreaterThan(0);
    }

    @Test
    void excludesDevelopmentWithNoMeaningfulConnection() {
        Development unrelated = new Development();
        unrelated.setTitle("New smartphone model launched with improved camera");
        unrelated.setSummary("A consumer electronics company unveiled a new phone.");
        unrelated.setCategory(DevelopmentCategory.TECHNOLOGY);
        unrelated.setIndustryTags(List.of("electronics", "smartphones"));
        unrelated.setPublishedAt(Instant.now());

        RelevanceScorer.ScoreBreakdown scores = scorer.score(textileTraderProfile(), unrelated);

        assertThat(scores.meaningfulConnection()).isFalse();
    }

    @Test
    void doesNotIncludeItemSolelyOnSharedKeywordWithoutOtherSignal() {
        // Shares the word "market" loosely but category/goal alignment are weak and no real
        // industry overlap exists beyond a generic term.
        UserProfile profile = textileTraderProfile();
        Development weaklyRelated = new Development();
        weaklyRelated.setTitle("Stock market volatility affects investor sentiment");
        weaklyRelated.setSummary("General financial market news unrelated to textiles.");
        weaklyRelated.setCategory(DevelopmentCategory.BUSINESS_INVESTMENTS);
        weaklyRelated.setIndustryTags(List.of("finance"));
        weaklyRelated.setPublishedAt(Instant.now());

        RelevanceScorer.ScoreBreakdown scores = scorer.score(profile, weaklyRelated);

        assertThat(scores.meaningfulConnection()).isFalse();
    }

    @Test
    void explainsConnectionWithProfileSpecificLanguage() {
        UserProfile profile = textileTraderProfile();
        Development d = matchingDevelopment();
        RelevanceScorer.ScoreBreakdown scores = scorer.score(profile, d);

        String explanation = scorer.explain(profile, d, scores);

        assertThat(explanation).contains("Textile Trader");
        assertThat(explanation).contains("Textiles and Garments");
    }

    @Test
    void recencyScoreDecaysWithAge() {
        Development recent = matchingDevelopment();
        recent.setPublishedAt(Instant.now());

        Development old = matchingDevelopment();
        old.setPublishedAt(Instant.now().minus(200, java.time.temporal.ChronoUnit.DAYS));

        UserProfile profile = textileTraderProfile();
        RelevanceScorer.ScoreBreakdown recentScores = scorer.score(profile, recent);
        RelevanceScorer.ScoreBreakdown oldScores = scorer.score(profile, old);

        assertThat(recentScores.recencyScore()).isGreaterThan(oldScores.recencyScore());
    }
}
