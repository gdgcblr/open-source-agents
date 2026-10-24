package com.workwise.ai.strategies.service;

import com.workwise.ai.strategies.domain.ConfidenceLevel;

import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;

/**
 * One row of a strategy comparison. Feasibility is a qualitative label derived from confidence
 * level and evidence state — never a fabricated numeric probability.
 */
public record StrategyComparisonItem(
        UUID strategyId,
        String name,
        BigDecimal requiredInvestment,
        String timeCommitment,
        List<String> requiredResources,
        List<String> risks,
        List<String> dependencies,
        String evidenceQualityLabel,
        String reversibilityLabel,
        String feasibilityLabel,
        ConfidenceLevel confidenceLevel,
        boolean waitAndResearch
) {
}
