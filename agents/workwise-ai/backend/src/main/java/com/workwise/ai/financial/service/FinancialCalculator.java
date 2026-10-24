package com.workwise.ai.financial.service;

import com.workwise.ai.common.exception.InvalidRequestException;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.List;

/**
 * Deterministic financial arithmetic. No LLM is ever used to compute these figures.
 *
 * <p>Formulas (per product spec):</p>
 * <ul>
 *   <li>totalAcquisitionCost = quantity*unitCost + transport + taxesDuties + handling + qc + otherAcquisition</li>
 *   <li>revenue = expectedSalesQuantity * sellingPrice</li>
 *   <li>costOfUnitsSold = (totalAcquisitionCost / quantity) * expectedSalesQuantity</li>
 *   <li>grossMargin = revenue - costOfUnitsSold</li>
 *   <li>contribution = revenue - costOfUnitsSold - (variableSellingCostPerUnit * expectedSalesQuantity)</li>
 *   <li>netProfit = contribution - otherOperatingCost</li>
 *   <li>cashRequired = totalAcquisitionCost (full upfront purchase outlay)</li>
 *   <li>unsoldInventoryValue = max(0, quantity - expectedSalesQuantity) * (totalAcquisitionCost / quantity)</li>
 * </ul>
 */
public final class FinancialCalculator {

    private static final int SCALE = 2;
    private static final RoundingMode ROUNDING = RoundingMode.HALF_UP;

    private FinancialCalculator() {
    }

    public static FinancialCalculationResult calculate(FinancialCalculationInput input) {
        List<String> missing = new ArrayList<>();
        if (input.quantity() == null) missing.add("quantity");
        if (input.unitCost() == null) missing.add("unitCost");
        if (input.sellingPrice() == null) missing.add("sellingPrice");
        if (input.expectedSalesQuantity() == null) missing.add("expectedSalesQuantity");

        if (!missing.isEmpty()) {
            throw new InvalidRequestException("Missing required financial inputs: " + String.join(", ", missing));
        }
        if (input.quantity().signum() <= 0) {
            throw new InvalidRequestException("quantity must be greater than zero");
        }
        if (input.unitCost().signum() < 0 || input.sellingPrice().signum() < 0) {
            throw new InvalidRequestException("unitCost and sellingPrice must not be negative");
        }
        if (input.expectedSalesQuantity().signum() < 0) {
            throw new InvalidRequestException("expectedSalesQuantity must not be negative");
        }
        if (input.expectedSalesQuantity().compareTo(input.quantity()) > 0) {
            throw new InvalidRequestException("expectedSalesQuantity cannot exceed purchased quantity");
        }

        BigDecimal transport = nz(input.transportCost());
        BigDecimal taxes = nz(input.taxesDuties());
        BigDecimal handling = nz(input.handlingCost());
        BigDecimal qc = nz(input.qualityControlCost());
        BigDecimal otherAcquisition = nz(input.otherAcquisitionCost());
        BigDecimal variableSellingPerUnit = nz(input.variableSellingCostPerUnit());
        BigDecimal otherOperating = nz(input.otherOperatingCost());

        BigDecimal purchaseCost = input.quantity().multiply(input.unitCost());
        BigDecimal totalAcquisitionCost = purchaseCost.add(transport).add(taxes).add(handling).add(qc).add(otherAcquisition);

        BigDecimal acquisitionCostPerUnit = totalAcquisitionCost.divide(input.quantity(), 6, ROUNDING);
        BigDecimal costOfUnitsSold = acquisitionCostPerUnit.multiply(input.expectedSalesQuantity());

        BigDecimal revenue = input.expectedSalesQuantity().multiply(input.sellingPrice());
        BigDecimal grossMargin = revenue.subtract(costOfUnitsSold);

        BigDecimal variableSellingExpensesTotal = variableSellingPerUnit.multiply(input.expectedSalesQuantity());
        BigDecimal contribution = grossMargin.subtract(variableSellingExpensesTotal);

        BigDecimal netProfit = contribution.subtract(otherOperating);

        BigDecimal cashRequired = totalAcquisitionCost;

        BigDecimal unsoldQuantity = input.quantity().subtract(input.expectedSalesQuantity());
        if (unsoldQuantity.signum() < 0) {
            unsoldQuantity = BigDecimal.ZERO;
        }
        BigDecimal unsoldInventoryValue = unsoldQuantity.multiply(acquisitionCostPerUnit);

        List<String> assumptions = new ArrayList<>();
        assumptions.add("Purchase quantity: " + input.quantity());
        assumptions.add("Unit purchase cost: " + input.unitCost());
        assumptions.add("Selling price per unit: " + input.sellingPrice());
        assumptions.add("Expected sales quantity: " + input.expectedSalesQuantity());
        if (input.unsoldInventoryAssumption() != null) {
            assumptions.add("Unsold inventory salvage assumption (informational only, not included in net profit): "
                    + input.unsoldInventoryAssumption());
        }
        assumptions.add("All acquisition surcharges (transport/taxes/handling/QC/other) are treated as lump-sum totals for the full purchased quantity.");

        return new FinancialCalculationResult(
                round(totalAcquisitionCost),
                round(revenue),
                round(grossMargin),
                round(contribution),
                round(netProfit),
                round(cashRequired),
                round(unsoldInventoryValue),
                assumptions,
                false
        );
    }

    private static BigDecimal nz(BigDecimal value) {
        return value == null ? BigDecimal.ZERO : value;
    }

    private static BigDecimal round(BigDecimal value) {
        return value.setScale(SCALE, ROUNDING);
    }
}
