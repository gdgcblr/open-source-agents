package com.workwise.ai.strategies.web;

import com.workwise.ai.strategies.service.StrategyComparisonItem;
import com.workwise.ai.strategies.service.StrategyService;
import jakarta.validation.constraints.NotEmpty;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/strategies")
public class StrategyController {

    private final StrategyService service;
    private final StrategyMapper mapper;

    public StrategyController(StrategyService service, StrategyMapper mapper) {
        this.service = service;
        this.mapper = mapper;
    }

    @GetMapping("/{id}")
    public StrategyResponse get(@PathVariable UUID id) {
        return mapper.toResponse(service.get(id));
    }

    @PostMapping("/compare")
    public List<StrategyComparisonItem> compare(@RequestBody CompareRequest request) {
        return service.compare(request.strategyIds());
    }

    @PostMapping("/{id}/select")
    public StrategyResponse select(@PathVariable UUID id) {
        return mapper.toResponse(service.select(id));
    }

    public record CompareRequest(@NotEmpty List<UUID> strategyIds) {
    }
}
