package com.workwise.ai.analysis.provider;

import java.util.List;

/**
 * Pluggable AI analysis backend. Implementations must not invent historical precedents, market
 * prices, or statistics beyond what is present in the {@link AnalysisRequest}'s development
 * evidence; when evidence is insufficient they must say so explicitly rather than fabricate it.
 */
public interface OpportunityAnalysisProvider {

    String providerName();

    AnalysisResult analyze(AnalysisRequest request);

    List<StrategyDraft> proposeStrategies(AnalysisRequest request, AnalysisResult analysis);
}
