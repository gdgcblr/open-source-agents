package com.workwise.ai.financial.repository;

import com.workwise.ai.financial.domain.FinancialScenario;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.UUID;

public interface FinancialScenarioRepository extends JpaRepository<FinancialScenario, UUID> {
    List<FinancialScenario> findByStrategyId(UUID strategyId);
}
