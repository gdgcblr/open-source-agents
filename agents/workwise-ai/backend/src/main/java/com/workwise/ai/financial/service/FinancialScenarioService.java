package com.workwise.ai.financial.service;

import com.workwise.ai.financial.domain.FinancialScenario;
import com.workwise.ai.financial.domain.ScenarioType;
import com.workwise.ai.financial.repository.FinancialScenarioRepository;
import com.workwise.ai.financial.web.FinancialScenarioRequest;
import com.workwise.ai.strategies.domain.Strategy;
import com.workwise.ai.strategies.service.StrategyService;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;

@Service
@Transactional
public class FinancialScenarioService {

    private static final BigDecimal LOW_HIGH_VARIANCE = new BigDecimal("0.20");

    private final FinancialScenarioRepository repository;
    private final StrategyService strategyService;

    public FinancialScenarioService(FinancialScenarioRepository repository, StrategyService strategyService) {
        this.repository = repository;
        this.strategyService = strategyService;
    }

    /**
     * Recalculates and persists LOW/BASE/HIGH scenarios for a strategy from a single base-case
     * input, replacing any previously stored scenarios for that strategy. LOW/HIGH vary expected
     * sales quantity by -20%/+20% around the user-supplied base case; this is a documented,
     * deterministic assumption, not an AI-generated prediction.
     */
    public List<FinancialScenario> recalculate(FinancialScenarioRequest request) {
        Strategy strategy = strategyService.get(request.strategyId());
        repository.deleteAll(repository.findByStrategyId(strategy.getId()));

        BigDecimal base = request.expectedSalesQuantity();
        BigDecimal low = base.multiply(BigDecimal.ONE.subtract(LOW_HIGH_VARIANCE)).max(BigDecimal.ZERO).min(request.quantity());
        BigDecimal high = base.multiply(BigDecimal.ONE.add(LOW_HIGH_VARIANCE)).min(request.quantity());

        FinancialScenario lowScenario = buildScenario(strategy, request, ScenarioType.LOW, low);
        FinancialScenario baseScenario = buildScenario(strategy, request, ScenarioType.BASE, base);
        FinancialScenario highScenario = buildScenario(strategy, request, ScenarioType.HIGH, high);

        return List.of(
                repository.save(lowScenario),
                repository.save(baseScenario),
                repository.save(highScenario)
        );
    }

    @Transactional(readOnly = true)
    public List<FinancialScenario> getForStrategy(UUID strategyId) {
        strategyService.get(strategyId); // ownership check
        return repository.findByStrategyId(strategyId);
    }

    private FinancialScenario buildScenario(Strategy strategy, FinancialScenarioRequest request,
                                             ScenarioType type, BigDecimal expectedSalesQuantity) {
        FinancialCalculationInput input = new FinancialCalculationInput(
                request.quantity(),
                request.unitCost(),
                request.transportCost(),
                request.taxesDuties(),
                request.handlingCost(),
                request.qualityControlCost(),
                request.otherAcquisitionCost(),
                request.sellingPrice(),
                request.variableSellingCostPerUnit(),
                request.otherOperatingCost(),
                expectedSalesQuantity,
                request.unsoldInventoryAssumption()
        );
        FinancialCalculationResult result = FinancialCalculator.calculate(input);

        FinancialScenario scenario = new FinancialScenario();
        scenario.setStrategy(strategy);
        scenario.setScenarioType(type);
        scenario.setQuantity(request.quantity());
        scenario.setUnitCost(request.unitCost());
        scenario.setTransportCost(nz(request.transportCost()));
        scenario.setTaxesDuties(nz(request.taxesDuties()));
        scenario.setHandlingCost(nz(request.handlingCost()));
        scenario.setQualityControlCost(nz(request.qualityControlCost()));
        scenario.setOtherAcquisitionCost(nz(request.otherAcquisitionCost()));
        scenario.setSellingPrice(request.sellingPrice());
        scenario.setVariableSellingCostPerUnit(nz(request.variableSellingCostPerUnit()));
        scenario.setOtherOperatingCost(nz(request.otherOperatingCost()));
        scenario.setExpectedSalesQuantity(expectedSalesQuantity);
        scenario.setUnsoldInventoryAssumption(nz(request.unsoldInventoryAssumption()));
        scenario.setTotalAcquisitionCost(result.totalAcquisitionCost());
        scenario.setRevenue(result.revenue());
        scenario.setGrossMargin(result.grossMargin());
        scenario.setContribution(result.contribution());
        scenario.setNetProfit(result.netProfit());
        scenario.setCashRequired(result.cashRequired());
        scenario.setUnsoldInventoryValue(result.unsoldInventoryValue());
        scenario.setAssumptions(result.assumptions());
        scenario.setIncomplete(result.incomplete());
        return scenario;
    }

    private BigDecimal nz(BigDecimal value) {
        return value == null ? BigDecimal.ZERO : value;
    }
}
