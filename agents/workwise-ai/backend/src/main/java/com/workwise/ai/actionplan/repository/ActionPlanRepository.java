package com.workwise.ai.actionplan.repository;

import com.workwise.ai.actionplan.domain.ActionPlan;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.UUID;

public interface ActionPlanRepository extends JpaRepository<ActionPlan, UUID> {
    List<ActionPlan> findByStrategyId(UUID strategyId);
}
