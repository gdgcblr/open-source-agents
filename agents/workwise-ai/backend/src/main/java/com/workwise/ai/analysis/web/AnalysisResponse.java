package com.workwise.ai.analysis.web;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

public record AnalysisResponse(
        UUID id,
        UUID profileId,
        UUID developmentId,
        String summary,
        List<String> confirmedFacts,
        String whyItMatters,
        List<String> historicalComparisons,
        List<String> trends,
        List<String> unknowns,
        List<String> nextSteps,
        String provider,
        Instant createdAt
) {
}
