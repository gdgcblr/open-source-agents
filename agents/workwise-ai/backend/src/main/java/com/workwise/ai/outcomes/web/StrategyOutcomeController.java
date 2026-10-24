package com.workwise.ai.outcomes.web;

import com.workwise.ai.outcomes.service.StrategyOutcomeService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/outcomes")
public class StrategyOutcomeController {

    private final StrategyOutcomeService service;

    public StrategyOutcomeController(StrategyOutcomeService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<StrategyOutcomeResponse> record(@Valid @RequestBody StrategyOutcomeRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED).body(service.record(request));
    }

    @GetMapping("/by-strategy/{strategyId}")
    public List<StrategyOutcomeResponse> history(@PathVariable UUID strategyId) {
        return service.history(strategyId);
    }
}
