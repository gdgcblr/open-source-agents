package com.workwise.ai.financial.web;

import com.workwise.ai.financial.domain.ScenarioType;

import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;

public record FinancialScenarioResponse(
        UUID id,
        UUID strategyId,
        ScenarioType scenarioType,
        BigDecimal quantity,
        BigDecimal unitCost,
        BigDecimal sellingPrice,
        BigDecimal expectedSalesQuantity,
        BigDecimal totalAcquisitionCost,
        BigDecimal revenue,
        BigDecimal grossMargin,
        BigDecimal contribution,
        BigDecimal netProfit,
        BigDecimal cashRequired,
        BigDecimal unsoldInventoryValue,
        List<String> assumptions
) {
}
