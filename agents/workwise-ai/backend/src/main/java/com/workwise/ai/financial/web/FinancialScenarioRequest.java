package com.workwise.ai.financial.web;

import jakarta.validation.constraints.NotNull;

import java.math.BigDecimal;
import java.util.UUID;

/**
 * Base-case financial assumptions submitted by the user. The service derives LOW/BASE/HIGH
 * scenarios by varying expected sales quantity by a documented +/-20% around this base case.
 */
public record FinancialScenarioRequest(
        @NotNull UUID strategyId,
        @NotNull BigDecimal quantity,
        @NotNull BigDecimal unitCost,
        BigDecimal transportCost,
        BigDecimal taxesDuties,
        BigDecimal handlingCost,
        BigDecimal qualityControlCost,
        BigDecimal otherAcquisitionCost,
        @NotNull BigDecimal sellingPrice,
        BigDecimal variableSellingCostPerUnit,
        BigDecimal otherOperatingCost,
        @NotNull BigDecimal expectedSalesQuantity,
        BigDecimal unsoldInventoryAssumption
) {
}
