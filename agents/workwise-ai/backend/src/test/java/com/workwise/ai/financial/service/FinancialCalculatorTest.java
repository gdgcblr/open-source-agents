package com.workwise.ai.financial.service;

import com.workwise.ai.common.exception.InvalidRequestException;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class FinancialCalculatorTest {

    @Test
    void calculatesTotalsForACompleteBaseCase() {
        FinancialCalculationInput input = new FinancialCalculationInput(
                new BigDecimal("1000"),   // quantity
                new BigDecimal("100"),    // unitCost
                new BigDecimal("5000"),   // transport
                new BigDecimal("2000"),   // taxes
                new BigDecimal("1000"),   // handling
                new BigDecimal("1000"),   // qc
                new BigDecimal("1000"),   // other acquisition
                new BigDecimal("150"),    // sellingPrice
                new BigDecimal("5"),      // variableSellingCostPerUnit
                new BigDecimal("2000"),   // otherOperatingCost
                new BigDecimal("900"),    // expectedSalesQuantity
                BigDecimal.ZERO
        );

        FinancialCalculationResult result = FinancialCalculator.calculate(input);

        // totalAcquisitionCost = 1000*100 + 5000+2000+1000+1000+1000 = 100000 + 10000 = 110000
        assertThat(result.totalAcquisitionCost()).isEqualByComparingTo("110000.00");
        // revenue = 900 * 150 = 135000
        assertThat(result.revenue()).isEqualByComparingTo("135000.00");
        // acquisitionCostPerUnit = 110000/1000 = 110; costOfUnitsSold = 110*900=99000
        // grossMargin = 135000 - 99000 = 36000
        assertThat(result.grossMargin()).isEqualByComparingTo("36000.00");
        // variableSellingExpensesTotal = 5*900=4500; contribution = 36000-4500=31500
        assertThat(result.contribution()).isEqualByComparingTo("31500.00");
        // netProfit = 31500 - 2000 = 29500
        assertThat(result.netProfit()).isEqualByComparingTo("29500.00");
        assertThat(result.cashRequired()).isEqualByComparingTo("110000.00");
        // unsold quantity = 100; unsoldInventoryValue = 100*110=11000
        assertThat(result.unsoldInventoryValue()).isEqualByComparingTo("11000.00");
        assertThat(result.incomplete()).isFalse();
    }

    @Test
    void throwsOnMissingRequiredInputs() {
        FinancialCalculationInput input = new FinancialCalculationInput(
                null, new BigDecimal("100"), null, null, null, null, null,
                new BigDecimal("150"), null, null, new BigDecimal("900"), null
        );

        assertThatThrownBy(() -> FinancialCalculator.calculate(input))
                .isInstanceOf(InvalidRequestException.class)
                .hasMessageContaining("quantity");
    }

    @Test
    void throwsWhenExpectedSalesExceedQuantity() {
        FinancialCalculationInput input = new FinancialCalculationInput(
                new BigDecimal("100"), new BigDecimal("10"), null, null, null, null, null,
                new BigDecimal("20"), null, null, new BigDecimal("200"), null
        );

        assertThatThrownBy(() -> FinancialCalculator.calculate(input))
                .isInstanceOf(InvalidRequestException.class)
                .hasMessageContaining("cannot exceed");
    }

    @Test
    void throwsOnNegativeQuantity() {
        FinancialCalculationInput input = new FinancialCalculationInput(
                new BigDecimal("-10"), new BigDecimal("10"), null, null, null, null, null,
                new BigDecimal("20"), null, null, new BigDecimal("5"), null
        );

        assertThatThrownBy(() -> FinancialCalculator.calculate(input))
                .isInstanceOf(InvalidRequestException.class)
                .hasMessageContaining("greater than zero");
    }

    @Test
    void contributionIsNotLabeledAsNetProfitWhenOperatingCostsExist() {
        FinancialCalculationInput input = new FinancialCalculationInput(
                new BigDecimal("100"), new BigDecimal("10"), null, null, null, null, null,
                new BigDecimal("20"), BigDecimal.ZERO, new BigDecimal("500"), new BigDecimal("100"), null
        );

        FinancialCalculationResult result = FinancialCalculator.calculate(input);

        // revenue=2000, cost=1000, grossMargin=1000, contribution=1000 (no variable selling), netProfit=1000-500=500
        assertThat(result.contribution()).isEqualByComparingTo("1000.00");
        assertThat(result.netProfit()).isEqualByComparingTo("500.00");
        assertThat(result.contribution()).isNotEqualByComparingTo(result.netProfit());
    }
}
