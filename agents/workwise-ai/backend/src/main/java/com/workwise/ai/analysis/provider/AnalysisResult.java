package com.workwise.ai.analysis.provider;

import java.util.List;

/** Structured provider output for the opportunity-analysis report. Never free-form text alone. */
public record AnalysisResult(
        String summary,
        List<String> confirmedFacts,
        String whyItMatters,
        List<String> historicalComparisons,
        List<String> trends,
        List<String> unknowns,
        List<String> nextSteps
) {
}
