package com.workwise.ai.financial.domain;

import com.workwise.ai.common.domain.BaseEntity;
import com.workwise.ai.strategies.domain.Strategy;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "financial_scenario")
public class FinancialScenario extends BaseEntity {

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "strategy_id", nullable = false)
    private Strategy strategy;

    @Enumerated(EnumType.STRING)
    @Column(name = "scenario_type", nullable = false, length = 10)
    private ScenarioType scenarioType;

    // --- user-provided assumptions ---
    @Column(nullable = false, precision = 14, scale = 2)
    private BigDecimal quantity;

    @Column(name = "unit_cost", nullable = false, precision = 14, scale = 2)
    private BigDecimal unitCost;

    @Column(name = "transport_cost", precision = 14, scale = 2)
    private BigDecimal transportCost = BigDecimal.ZERO;

    @Column(name = "taxes_duties", precision = 14, scale = 2)
    private BigDecimal taxesDuties = BigDecimal.ZERO;

    @Column(name = "handling_cost", precision = 14, scale = 2)
    private BigDecimal handlingCost = BigDecimal.ZERO;

    @Column(name = "qc_cost", precision = 14, scale = 2)
    private BigDecimal qualityControlCost = BigDecimal.ZERO;

    @Column(name = "other_acquisition_cost", precision = 14, scale = 2)
    private BigDecimal otherAcquisitionCost = BigDecimal.ZERO;

    @Column(name = "selling_price", nullable = false, precision = 14, scale = 2)
    private BigDecimal sellingPrice;

    @Column(name = "variable_selling_cost", precision = 14, scale = 2)
    private BigDecimal variableSellingCostPerUnit = BigDecimal.ZERO;

    @Column(name = "other_operating_cost", precision = 14, scale = 2)
    private BigDecimal otherOperatingCost = BigDecimal.ZERO;

    @Column(name = "expected_sales_quantity", nullable = false, precision = 14, scale = 2)
    private BigDecimal expectedSalesQuantity;

    @Column(name = "unsold_inventory_assumption", precision = 14, scale = 2)
    private BigDecimal unsoldInventoryAssumption = BigDecimal.ZERO;

    // --- computed outputs ---
    @Column(name = "total_acquisition_cost", precision = 14, scale = 2)
    private BigDecimal totalAcquisitionCost;

    @Column(precision = 14, scale = 2)
    private BigDecimal revenue;

    @Column(precision = 14, scale = 2)
    private BigDecimal grossMargin;

    @Column(precision = 14, scale = 2)
    private BigDecimal contribution;

    @Column(name = "net_profit", precision = 14, scale = 2)
    private BigDecimal netProfit;

    @Column(name = "cash_required", precision = 14, scale = 2)
    private BigDecimal cashRequired;

    @Column(name = "unsold_inventory_value", precision = 14, scale = 2)
    private BigDecimal unsoldInventoryValue;

    @JdbcTypeCode(SqlTypes.ARRAY)
    @Column(columnDefinition = "text[]")
    private List<String> assumptions = new ArrayList<>();

    @Column(name = "is_incomplete", nullable = false)
    private boolean incomplete = false;

    // getters/setters

    public Strategy getStrategy() {
        return strategy;
    }

    public void setStrategy(Strategy strategy) {
        this.strategy = strategy;
    }

    public ScenarioType getScenarioType() {
        return scenarioType;
    }

    public void setScenarioType(ScenarioType scenarioType) {
        this.scenarioType = scenarioType;
    }

    public BigDecimal getQuantity() {
        return quantity;
    }

    public void setQuantity(BigDecimal quantity) {
        this.quantity = quantity;
    }

    public BigDecimal getUnitCost() {
        return unitCost;
    }

    public void setUnitCost(BigDecimal unitCost) {
        this.unitCost = unitCost;
    }

    public BigDecimal getTransportCost() {
        return transportCost;
    }

    public void setTransportCost(BigDecimal transportCost) {
        this.transportCost = transportCost;
    }

    public BigDecimal getTaxesDuties() {
        return taxesDuties;
    }

    public void setTaxesDuties(BigDecimal taxesDuties) {
        this.taxesDuties = taxesDuties;
    }

    public BigDecimal getHandlingCost() {
        return handlingCost;
    }

    public void setHandlingCost(BigDecimal handlingCost) {
        this.handlingCost = handlingCost;
    }

    public BigDecimal getQualityControlCost() {
        return qualityControlCost;
    }

    public void setQualityControlCost(BigDecimal qualityControlCost) {
        this.qualityControlCost = qualityControlCost;
    }

    public BigDecimal getOtherAcquisitionCost() {
        return otherAcquisitionCost;
    }

    public void setOtherAcquisitionCost(BigDecimal otherAcquisitionCost) {
        this.otherAcquisitionCost = otherAcquisitionCost;
    }

    public BigDecimal getSellingPrice() {
        return sellingPrice;
    }

    public void setSellingPrice(BigDecimal sellingPrice) {
        this.sellingPrice = sellingPrice;
    }

    public BigDecimal getVariableSellingCostPerUnit() {
        return variableSellingCostPerUnit;
    }

    public void setVariableSellingCostPerUnit(BigDecimal variableSellingCostPerUnit) {
        this.variableSellingCostPerUnit = variableSellingCostPerUnit;
    }

    public BigDecimal getOtherOperatingCost() {
        return otherOperatingCost;
    }

    public void setOtherOperatingCost(BigDecimal otherOperatingCost) {
        this.otherOperatingCost = otherOperatingCost;
    }

    public BigDecimal getExpectedSalesQuantity() {
        return expectedSalesQuantity;
    }

    public void setExpectedSalesQuantity(BigDecimal expectedSalesQuantity) {
        this.expectedSalesQuantity = expectedSalesQuantity;
    }

    public BigDecimal getUnsoldInventoryAssumption() {
        return unsoldInventoryAssumption;
    }

    public void setUnsoldInventoryAssumption(BigDecimal unsoldInventoryAssumption) {
        this.unsoldInventoryAssumption = unsoldInventoryAssumption;
    }

    public BigDecimal getTotalAcquisitionCost() {
        return totalAcquisitionCost;
    }

    public void setTotalAcquisitionCost(BigDecimal totalAcquisitionCost) {
        this.totalAcquisitionCost = totalAcquisitionCost;
    }

    public BigDecimal getRevenue() {
        return revenue;
    }

    public void setRevenue(BigDecimal revenue) {
        this.revenue = revenue;
    }

    public BigDecimal getGrossMargin() {
        return grossMargin;
    }

    public void setGrossMargin(BigDecimal grossMargin) {
        this.grossMargin = grossMargin;
    }

    public BigDecimal getContribution() {
        return contribution;
    }

    public void setContribution(BigDecimal contribution) {
        this.contribution = contribution;
    }

    public BigDecimal getNetProfit() {
        return netProfit;
    }

    public void setNetProfit(BigDecimal netProfit) {
        this.netProfit = netProfit;
    }

    public BigDecimal getCashRequired() {
        return cashRequired;
    }

    public void setCashRequired(BigDecimal cashRequired) {
        this.cashRequired = cashRequired;
    }

    public BigDecimal getUnsoldInventoryValue() {
        return unsoldInventoryValue;
    }

    public void setUnsoldInventoryValue(BigDecimal unsoldInventoryValue) {
        this.unsoldInventoryValue = unsoldInventoryValue;
    }

    public List<String> getAssumptions() {
        return assumptions;
    }

    public void setAssumptions(List<String> assumptions) {
        this.assumptions = assumptions;
    }

    public boolean isIncomplete() {
        return incomplete;
    }

    public void setIncomplete(boolean incomplete) {
        this.incomplete = incomplete;
    }
}
