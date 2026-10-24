package com.workwise.ai.financial.service;

import java.math.BigDecimal;
import java.util.List;

public record FinancialCalculationResult(
        BigDecimal totalAcquisitionCost,
        BigDecimal revenue,
        BigDecimal grossMargin,
        BigDecimal contribution,
        BigDecimal netProfit,
        BigDecimal cashRequired,
        BigDecimal unsoldInventoryValue,
        List<String> assumptions,
        boolean incomplete
) {
}
