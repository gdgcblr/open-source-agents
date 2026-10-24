package com.workwise.ai.financial.service;

import java.math.BigDecimal;

/**
 * User-supplied financial assumptions for one scenario calculation. All monetary values are
 * {@link BigDecimal}; floating point is never used for money.
 */
public record FinancialCalculationInput(
        BigDecimal quantity,
        BigDecimal unitCost,
        BigDecimal transportCost,
        BigDecimal taxesDuties,
        BigDecimal handlingCost,
        BigDecimal qualityControlCost,
        BigDecimal otherAcquisitionCost,
        BigDecimal sellingPrice,
        BigDecimal variableSellingCostPerUnit,
        BigDecimal otherOperatingCost,
        BigDecimal expectedSalesQuantity,
        BigDecimal unsoldInventoryAssumption
) {
}
