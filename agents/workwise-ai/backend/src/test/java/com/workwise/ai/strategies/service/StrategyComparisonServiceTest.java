package com.workwise.ai.strategies.service;

import com.workwise.ai.analysis.domain.OpportunityAnalysis;
import com.workwise.ai.news.domain.Development;
import com.workwise.ai.news.domain.EvidenceState;
import com.workwise.ai.strategies.domain.ConfidenceLevel;
import com.workwise.ai.strategies.domain.Strategy;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;

import static org.assertj.core.api.Assertions.assertThat;

class StrategyComparisonServiceTest {

    private final StrategyComparisonService service = new StrategyComparisonService();

    private Strategy strategyWith(EvidenceState evidenceState, ConfidenceLevel confidence,
                                   BigDecimal investment, boolean waitAndResearch) {
        Development development = new Development();
        development.setEvidenceState(evidenceState);

        OpportunityAnalysis analysis = new OpportunityAnalysis();
        analysis.setDevelopment(development);

        Strategy strategy = new Strategy();
        strategy.setAnalysis(analysis);
        strategy.setName("Test strategy");
        strategy.setConfidenceLevel(confidence);
        strategy.setRequiredInvestment(investment);
        strategy.setWaitAndResearch(waitAndResearch);
        return strategy;
    }

    @Test
    void demonstrationDataYieldsNotAssessableFeasibility() {
        Strategy strategy = strategyWith(EvidenceState.DEMONSTRATION_DATA, ConfidenceLevel.HIGH, BigDecimal.TEN, false);

        StrategyComparisonItem item = service.toComparisonItem(strategy);

        assertThat(item.feasibilityLabel()).contains("Not assessable");
        assertThat(item.evidenceQualityLabel()).contains("Demonstration data");
    }

    @Test
    void waitAndResearchStrategyIsHighlyReversible() {
        Strategy strategy = strategyWith(EvidenceState.UNVERIFIED, ConfidenceLevel.HIGH, BigDecimal.ZERO, true);

        StrategyComparisonItem item = service.toComparisonItem(strategy);

        assertThat(item.reversibilityLabel()).contains("High");
    }

    @Test
    void largeInvestmentIsLowReversibility() {
        Strategy strategy = strategyWith(EvidenceState.VERIFIED, ConfidenceLevel.HIGH, new BigDecimal("50000"), false);

        StrategyComparisonItem item = service.toComparisonItem(strategy);

        assertThat(item.reversibilityLabel()).contains("Low");
    }

    @Test
    void feasibilityNeverExpressedAsNumericProbability() {
        Strategy strategy = strategyWith(EvidenceState.PARTIALLY_VERIFIED, ConfidenceLevel.MEDIUM, new BigDecimal("500"), false);

        StrategyComparisonItem item = service.toComparisonItem(strategy);

        assertThat(item.feasibilityLabel()).doesNotContain("%");
        assertThat(item.feasibilityLabel()).isIn("High", "Medium", "Low");
    }
}
