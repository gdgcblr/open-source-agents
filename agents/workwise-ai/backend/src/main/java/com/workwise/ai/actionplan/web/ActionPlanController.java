package com.workwise.ai.actionplan.web;

import com.workwise.ai.actionplan.service.ActionPlanService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;

@RestController
@RequestMapping("/api/action-plans")
public class ActionPlanController {

    private final ActionPlanService service;
    private final ActionPlanMapper mapper;

    public ActionPlanController(ActionPlanService service, ActionPlanMapper mapper) {
        this.service = service;
        this.mapper = mapper;
    }

    @PostMapping
    public ResponseEntity<ActionPlanResponse> create(@Valid @RequestBody ActionPlanRequest request) {
        var plan = service.create(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(mapper.toResponse(plan, service.getItems(plan.getId())));
    }

    @GetMapping("/{id}")
    public ActionPlanResponse get(@PathVariable UUID id) {
        var plan = service.get(id);
        return mapper.toResponse(plan, service.getItems(id));
    }

    @PutMapping("/{id}/items/{itemId}")
    public ActionPlanResponse updateItemStatus(@PathVariable UUID id, @PathVariable UUID itemId,
                                                @Valid @RequestBody ActionPlanRequest.ActionStatusUpdateRequest request) {
        service.updateItemStatus(id, itemId, request.status());
        var plan = service.get(id);
        return mapper.toResponse(plan, service.getItems(id));
    }
}
