package com.workwise.ai.actionplan.web;

import com.workwise.ai.actionplan.domain.ActionStatus;

import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;

public record ActionPlanResponse(
        UUID id,
        UUID strategyId,
        String title,
        List<ActionItemResponse> items
) {
    public record ActionItemResponse(
            UUID id,
            int sequenceNo,
            String action,
            String estimatedDuration,
            List<String> requiredResources,
            BigDecimal expectedCost,
            String successMetric,
            String mainRisk,
            ActionStatus status
    ) {
    }
}
