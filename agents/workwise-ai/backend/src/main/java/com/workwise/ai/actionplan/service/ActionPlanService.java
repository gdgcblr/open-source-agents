package com.workwise.ai.actionplan.service;

import com.workwise.ai.actionplan.domain.ActionItem;
import com.workwise.ai.actionplan.domain.ActionPlan;
import com.workwise.ai.actionplan.domain.ActionStatus;
import com.workwise.ai.actionplan.repository.ActionItemRepository;
import com.workwise.ai.actionplan.repository.ActionPlanRepository;
import com.workwise.ai.actionplan.web.ActionPlanRequest;
import com.workwise.ai.common.exception.ResourceNotFoundException;
import com.workwise.ai.strategies.domain.Strategy;
import com.workwise.ai.strategies.service.StrategyService;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.UUID;

@Service
@Transactional
public class ActionPlanService {

    private final ActionPlanRepository planRepository;
    private final ActionItemRepository itemRepository;
    private final StrategyService strategyService;

    public ActionPlanService(ActionPlanRepository planRepository, ActionItemRepository itemRepository,
                              StrategyService strategyService) {
        this.planRepository = planRepository;
        this.itemRepository = itemRepository;
        this.strategyService = strategyService;
    }

    public ActionPlan create(ActionPlanRequest request) {
        Strategy strategy = strategyService.get(request.strategyId());

        ActionPlan plan = new ActionPlan();
        plan.setStrategy(strategy);
        plan.setTitle(request.title());
        plan = planRepository.save(plan);

        int sequence = 1;
        for (ActionPlanRequest.ActionItemRequest itemRequest : request.items()) {
            ActionItem item = new ActionItem();
            item.setActionPlan(plan);
            item.setSequenceNo(sequence++);
            item.setAction(itemRequest.action());
            item.setEstimatedDuration(itemRequest.estimatedDuration());
            item.setRequiredResources(itemRequest.requiredResources() == null ? List.of() : itemRequest.requiredResources());
            item.setExpectedCost(itemRequest.expectedCost());
            item.setSuccessMetric(itemRequest.successMetric());
            item.setMainRisk(itemRequest.mainRisk());
            itemRepository.save(item);
        }
        return plan;
    }

    @Transactional(readOnly = true)
    public ActionPlan get(UUID id) {
        ActionPlan plan = planRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Action plan not found: " + id));
        strategyService.get(plan.getStrategy().getId()); // ownership check
        return plan;
    }

    @Transactional(readOnly = true)
    public List<ActionItem> getItems(UUID planId) {
        return itemRepository.findByActionPlanIdOrderBySequenceNoAsc(planId);
    }

    public ActionItem updateItemStatus(UUID planId, UUID itemId, ActionStatus status) {
        get(planId); // ownership check
        ActionItem item = itemRepository.findById(itemId)
                .orElseThrow(() -> new ResourceNotFoundException("Action item not found: " + itemId));
        if (!item.getActionPlan().getId().equals(planId)) {
            throw new ResourceNotFoundException("Action item " + itemId + " does not belong to plan " + planId);
        }
        item.setStatus(status);
        return itemRepository.save(item);
    }
}
