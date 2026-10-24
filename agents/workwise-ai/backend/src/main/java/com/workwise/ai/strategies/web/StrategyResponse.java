package com.workwise.ai.strategies.web;

import com.workwise.ai.strategies.domain.ConfidenceLevel;

import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;

public record StrategyResponse(
        UUID id,
        UUID analysisId,
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
        boolean waitAndResearch,
        boolean selected
) {
}
