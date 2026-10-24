package com.workwise.ai.strategies.service;

import com.workwise.ai.news.domain.EvidenceState;
import com.workwise.ai.strategies.domain.Strategy;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;

/**
 * Compares strategies on investment, risk, evidence quality, reversibility and dependencies.
 * Deliberately does NOT rank strategies by estimated revenue/benefit alone, and never invents a
 * numerical success probability — only qualitative feasibility labels.
 */
@Service
public class StrategyComparisonService {

    public StrategyComparisonItem toComparisonItem(Strategy strategy) {
        EvidenceState evidenceState = strategy.getAnalysis().getDevelopment().getEvidenceState();
        String evidenceQuality = switch (evidenceState) {
            case VERIFIED -> "Strong (verified)";
            case PARTIALLY_VERIFIED -> "Moderate (partially verified)";
            case UNVERIFIED -> "Weak (unverified, single source)";
            case DEMONSTRATION_DATA -> "Demonstration data only — not real evidence";
        };

        String reversibility = reversibilityLabel(strategy);
        String feasibility = feasibilityLabel(strategy, evidenceState);

        return new StrategyComparisonItem(
                strategy.getId(),
                strategy.getName(),
                strategy.getRequiredInvestment(),
                strategy.getTimeCommitment(),
                strategy.getRequiredResources(),
                strategy.getRisks(),
                strategy.getDependencies(),
                evidenceQuality,
                reversibility,
                feasibility,
                strategy.getConfidenceLevel(),
                strategy.isWaitAndResearch()
        );
    }

    private String reversibilityLabel(Strategy strategy) {
        BigDecimal investment = strategy.getRequiredInvestment();
        if (strategy.isWaitAndResearch() || investment == null || investment.signum() == 0) {
            return "High (little to no committed capital)";
        }
        return investment.compareTo(new BigDecimal("10000")) > 0
                ? "Low (significant capital committed)"
                : "Medium (modest capital committed)";
    }

    private String feasibilityLabel(Strategy strategy, EvidenceState evidenceState) {
        if (evidenceState == EvidenceState.DEMONSTRATION_DATA) {
            return "Not assessable — demonstration data";
        }
        boolean strongEvidence = evidenceState == EvidenceState.VERIFIED || evidenceState == EvidenceState.PARTIALLY_VERIFIED;
        return switch (strategy.getConfidenceLevel()) {
            case HIGH -> strongEvidence ? "High" : "Medium";
            case MEDIUM -> "Medium";
            case LOW -> "Low";
        };
    }
}
