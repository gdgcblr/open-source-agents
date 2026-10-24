package com.workwise.ai.financial.web;

import com.workwise.ai.financial.domain.FinancialScenario;
import org.springframework.stereotype.Component;

@Component
public class FinancialScenarioMapper {

    public FinancialScenarioResponse toResponse(FinancialScenario s) {
        return new FinancialScenarioResponse(
                s.getId(),
                s.getStrategy().getId(),
                s.getScenarioType(),
                s.getQuantity(),
                s.getUnitCost(),
                s.getSellingPrice(),
                s.getExpectedSalesQuantity(),
                s.getTotalAcquisitionCost(),
                s.getRevenue(),
                s.getGrossMargin(),
                s.getContribution(),
                s.getNetProfit(),
                s.getCashRequired(),
                s.getUnsoldInventoryValue(),
                s.getAssumptions()
        );
    }
}
