package com.workwise.ai.analysis.web;

import com.workwise.ai.analysis.domain.OpportunityAnalysis;
import org.springframework.stereotype.Component;

@Component
public class AnalysisMapper {

    public AnalysisResponse toResponse(OpportunityAnalysis a) {
        return new AnalysisResponse(
                a.getId(),
                a.getProfile().getId(),
                a.getDevelopment().getId(),
                a.getSummary(),
                a.getConfirmedFacts(),
                a.getWhyItMatters(),
                a.getHistoricalComparisons(),
                a.getTrends(),
                a.getUnknowns(),
                a.getNextSteps(),
                a.getProvider(),
                a.getCreatedAt()
        );
    }
}
