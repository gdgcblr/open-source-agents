package com.workwise.ai.outcomes.web;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.UUID;

public record StrategyOutcomeResponse(
        UUID id,
        UUID strategyId,
        LocalDate dateStarted,
        LocalDate dateCompleted,
        BigDecimal actualExpenses,
        BigDecimal actualRevenue,
        BigDecimal timeSpentHours,
        Integer ordersReceived,
        Integer customersAcquired,
        String userReportedOutcome,
        String lessonsLearned,
        boolean independentlyVerified,
        /** Difference vs the strategy's BASE financial scenario, if one was computed. Null if unavailable. Purely informational — not a causal claim. */
        BigDecimal revenueVarianceVsBaseAssumption,
        BigDecimal expenseVarianceVsBaseAssumption
) {
}
