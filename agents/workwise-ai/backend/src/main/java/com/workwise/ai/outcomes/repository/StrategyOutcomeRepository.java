package com.workwise.ai.outcomes.repository;

import com.workwise.ai.outcomes.domain.StrategyOutcome;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.UUID;

public interface StrategyOutcomeRepository extends JpaRepository<StrategyOutcome, UUID> {
    List<StrategyOutcome> findByStrategyIdOrderByCreatedAtDesc(UUID strategyId);
}
