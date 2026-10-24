package com.workwise.ai.outcomes.service;

import com.workwise.ai.common.exception.ResourceNotFoundException;
import com.workwise.ai.financial.domain.FinancialScenario;
import com.workwise.ai.financial.domain.ScenarioType;
import com.workwise.ai.financial.repository.FinancialScenarioRepository;
import com.workwise.ai.outcomes.domain.StrategyOutcome;
import com.workwise.ai.outcomes.repository.StrategyOutcomeRepository;
import com.workwise.ai.outcomes.web.StrategyOutcomeRequest;
import com.workwise.ai.outcomes.web.StrategyOutcomeResponse;
import com.workwise.ai.strategies.domain.Strategy;
import com.workwise.ai.strategies.service.StrategyService;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Service
@Transactional
public class StrategyOutcomeService {

    private final StrategyOutcomeRepository repository;
    private final StrategyService strategyService;
    private final FinancialScenarioRepository financialScenarioRepository;

    public StrategyOutcomeService(StrategyOutcomeRepository repository, StrategyService strategyService,
                                   FinancialScenarioRepository financialScenarioRepository) {
        this.repository = repository;
        this.strategyService = strategyService;
        this.financialScenarioRepository = financialScenarioRepository;
    }

    public StrategyOutcomeResponse record(StrategyOutcomeRequest request) {
        Strategy strategy = strategyService.get(request.strategyId());

        StrategyOutcome outcome = new StrategyOutcome();
        outcome.setStrategy(strategy);
        outcome.setDateStarted(request.dateStarted());
        outcome.setDateCompleted(request.dateCompleted());
        outcome.setActualExpenses(request.actualExpenses());
        outcome.setActualRevenue(request.actualRevenue());
        outcome.setTimeSpentHours(request.timeSpentHours());
        outcome.setOrdersReceived(request.ordersReceived());
        outcome.setCustomersAcquired(request.customersAcquired());
        outcome.setUserReportedOutcome(request.userReportedOutcome());
        outcome.setLessonsLearned(request.lessonsLearned());
        // User-reported by default; independent verification is not implemented in this prototype.
        outcome.setIndependentlyVerified(false);

        outcome = repository.save(outcome);
        return toResponse(outcome);
    }

    @Transactional(readOnly = true)
    public List<StrategyOutcomeResponse> history(UUID strategyId) {
        strategyService.get(strategyId); // ownership check
        return repository.findByStrategyIdOrderByCreatedAtDesc(strategyId).stream().map(this::toResponse).toList();
    }

    private StrategyOutcomeResponse toResponse(StrategyOutcome o) {
        Optional<FinancialScenario> baseScenario = financialScenarioRepository
                .findByStrategyId(o.getStrategy().getId()).stream()
                .filter(s -> s.getScenarioType() == ScenarioType.BASE)
                .findFirst();

        BigDecimal revenueVariance = baseScenario.map(s -> subtractIfBothPresent(o.getActualRevenue(), s.getRevenue())).orElse(null);
        BigDecimal expenseVariance = baseScenario.map(s -> subtractIfBothPresent(o.getActualExpenses(), s.getTotalAcquisitionCost())).orElse(null);

        return new StrategyOutcomeResponse(
                o.getId(),
                o.getStrategy().getId(),
                o.getDateStarted(),
                o.getDateCompleted(),
                o.getActualExpenses(),
                o.getActualRevenue(),
                o.getTimeSpentHours(),
                o.getOrdersReceived(),
                o.getCustomersAcquired(),
                o.getUserReportedOutcome(),
                o.getLessonsLearned(),
                o.isIndependentlyVerified(),
                revenueVariance,
                expenseVariance
        );
    }

    private BigDecimal subtractIfBothPresent(BigDecimal actual, BigDecimal assumed) {
        if (actual == null || assumed == null) {
            return null;
        }
        return actual.subtract(assumed);
    }
}
