package com.workwise.ai.outcomes.web;

import jakarta.validation.constraints.NotNull;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.UUID;

public record StrategyOutcomeRequest(
        @NotNull UUID strategyId,
        LocalDate dateStarted,
        LocalDate dateCompleted,
        BigDecimal actualExpenses,
        BigDecimal actualRevenue,
        BigDecimal timeSpentHours,
        Integer ordersReceived,
        Integer customersAcquired,
        String userReportedOutcome,
        String lessonsLearned
) {
}
