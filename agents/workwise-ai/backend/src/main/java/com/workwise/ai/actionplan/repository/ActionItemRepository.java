package com.workwise.ai.actionplan.repository;

import com.workwise.ai.actionplan.domain.ActionItem;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.UUID;

public interface ActionItemRepository extends JpaRepository<ActionItem, UUID> {
    List<ActionItem> findByActionPlanIdOrderBySequenceNoAsc(UUID actionPlanId);
}
