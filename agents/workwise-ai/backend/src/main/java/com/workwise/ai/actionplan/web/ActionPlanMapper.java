package com.workwise.ai.actionplan.web;

import com.workwise.ai.actionplan.domain.ActionItem;
import com.workwise.ai.actionplan.domain.ActionPlan;
import org.springframework.stereotype.Component;

import java.util.List;

@Component
public class ActionPlanMapper {

    public ActionPlanResponse toResponse(ActionPlan plan, List<ActionItem> items) {
        return new ActionPlanResponse(
                plan.getId(),
                plan.getStrategy().getId(),
                plan.getTitle(),
                items.stream().map(this::toItemResponse).toList()
        );
    }

    private ActionPlanResponse.ActionItemResponse toItemResponse(ActionItem item) {
        return new ActionPlanResponse.ActionItemResponse(
                item.getId(),
                item.getSequenceNo(),
                item.getAction(),
                item.getEstimatedDuration(),
                item.getRequiredResources(),
                item.getExpectedCost(),
                item.getSuccessMetric(),
                item.getMainRisk(),
                item.getStatus()
        );
    }
}
