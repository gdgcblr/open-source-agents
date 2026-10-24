package com.workwise.ai.actionplan.web;

import com.workwise.ai.actionplan.domain.ActionStatus;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;

public record ActionPlanRequest(
        @NotNull UUID strategyId,
        @NotBlank String title,
        @NotEmpty List<ActionItemRequest> items
) {
    public record ActionItemRequest(
            @NotBlank String action,
            String estimatedDuration,
            List<String> requiredResources,
            BigDecimal expectedCost,
            String successMetric,
            String mainRisk
    ) {
    }

    public record ActionStatusUpdateRequest(@NotNull ActionStatus status) {
    }
}
