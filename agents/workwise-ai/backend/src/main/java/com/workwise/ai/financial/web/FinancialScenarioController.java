package com.workwise.ai.financial.web;

import com.workwise.ai.financial.service.FinancialScenarioService;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/financial-scenarios")
public class FinancialScenarioController {

    private final FinancialScenarioService service;
    private final FinancialScenarioMapper mapper;

    public FinancialScenarioController(FinancialScenarioService service, FinancialScenarioMapper mapper) {
        this.service = service;
        this.mapper = mapper;
    }

    @PostMapping
    public List<FinancialScenarioResponse> recalculate(@Valid @RequestBody FinancialScenarioRequest request) {
        return service.recalculate(request).stream().map(mapper::toResponse).toList();
    }

    @GetMapping("/by-strategy/{strategyId}")
    public List<FinancialScenarioResponse> getForStrategy(@PathVariable UUID strategyId) {
        return service.getForStrategy(strategyId).stream().map(mapper::toResponse).toList();
    }
}
