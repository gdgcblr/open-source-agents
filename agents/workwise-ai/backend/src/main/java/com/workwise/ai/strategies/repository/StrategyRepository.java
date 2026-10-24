package com.workwise.ai.strategies.repository;

import com.workwise.ai.strategies.domain.Strategy;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.UUID;

public interface StrategyRepository extends JpaRepository<Strategy, UUID> {
    List<Strategy> findByAnalysisId(UUID analysisId);
}
