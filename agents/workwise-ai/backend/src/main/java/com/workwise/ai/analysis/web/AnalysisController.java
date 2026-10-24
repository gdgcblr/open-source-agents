package com.workwise.ai.analysis.web;

import com.workwise.ai.analysis.service.AnalysisService;
import com.workwise.ai.strategies.web.StrategyMapper;
import com.workwise.ai.strategies.web.StrategyResponse;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/analysis")
public class AnalysisController {

    private final AnalysisService service;
    private final AnalysisMapper mapper;
    private final StrategyMapper strategyMapper;

    public AnalysisController(AnalysisService service, AnalysisMapper mapper, StrategyMapper strategyMapper) {
        this.service = service;
        this.mapper = mapper;
        this.strategyMapper = strategyMapper;
    }

    @PostMapping
    public ResponseEntity<AnalysisResponse> create(@Valid @RequestBody AnalysisRequestDto request) {
        var analysis = service.createAnalysis(request.profileId(), request.developmentId());
        return ResponseEntity.status(HttpStatus.CREATED).body(mapper.toResponse(analysis));
    }

    @GetMapping("/{id}")
    public AnalysisResponse get(@PathVariable UUID id) {
        return mapper.toResponse(service.get(id));
    }

    @GetMapping("/{id}/strategies")
    public List<StrategyResponse> getStrategies(@PathVariable UUID id) {
        return service.getStrategies(id).stream().map(strategyMapper::toResponse).toList();
    }

    @GetMapping
    public List<AnalysisResponse> listForProfile(@RequestParam UUID profileId) {
        return service.listForProfile(profileId).stream().map(mapper::toResponse).toList();
    }
}
