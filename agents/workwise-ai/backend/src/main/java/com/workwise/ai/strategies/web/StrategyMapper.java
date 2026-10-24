package com.workwise.ai.strategies.web;

import com.workwise.ai.strategies.domain.Strategy;
import org.springframework.stereotype.Component;

@Component
public class StrategyMapper {

    public StrategyResponse toResponse(Strategy s) {
        return new StrategyResponse(
                s.getId(),
                s.getAnalysis().getId(),
                s.getName(),
                s.getDescription(),
                s.getRationale(),
                s.getEvidence(),
                s.getRequiredInvestment(),
                s.getRequiredResources(),
                s.getTimeCommitment(),
                s.getBenefits(),
                s.getRisks(),
                s.getDependencies(),
                s.getFailureConditions(),
                s.getValidationSteps(),
                s.getNextAction(),
                s.getConfidenceLevel(),
                s.getConfidenceJustification(),
                s.isWaitAndResearch(),
                s.isSelected()
        );
    }
}
