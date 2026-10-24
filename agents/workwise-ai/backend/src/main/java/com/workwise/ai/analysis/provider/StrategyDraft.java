package com.workwise.ai.analysis.provider;

import com.workwise.ai.strategies.domain.ConfidenceLevel;

import java.math.BigDecimal;
import java.util.List;

/** Structured strategy proposal from a provider, mapped 1:1 onto {@link com.workwise.ai.strategies.domain.Strategy}. */
public record StrategyDraft(
        String name,
        String description,
        String rationale,
        List<String> evidence,
        BigDecimal requiredInvestment,
        List<String> requiredResources,
        String timeCommitment,
        List<String> benefits,
        List<String> risks,
        List<String> dependencies,
        List<String> failureConditions,
        List<String> validationSteps,
        String nextAction,
        ConfidenceLevel confidenceLevel,
        String confidenceJustification,
        boolean waitAndResearch
) {
}
