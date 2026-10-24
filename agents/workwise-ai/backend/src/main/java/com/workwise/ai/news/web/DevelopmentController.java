package com.workwise.ai.news.web;

import com.workwise.ai.common.web.PageResponse;
import com.workwise.ai.news.domain.DevelopmentCategory;
import com.workwise.ai.news.service.DevelopmentService;
import org.springframework.data.domain.Pageable;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;

@RestController
@RequestMapping("/api/developments")
public class DevelopmentController {

    private final DevelopmentService service;
    private final DevelopmentMapper mapper;

    public DevelopmentController(DevelopmentService service, DevelopmentMapper mapper) {
        this.service = service;
        this.mapper = mapper;
    }

    @GetMapping
    public PageResponse<DevelopmentResponse> list(
            @RequestParam(required = false) DevelopmentCategory category,
            @RequestParam(required = false) String country,
            @RequestParam(required = false) String region,
            @RequestParam(required = false) Integer recencyDays,
            Pageable pageable) {
        return PageResponse.of(service.list(category, country, region, recencyDays, pageable).map(mapper::toResponse));
    }

    @GetMapping("/{id}")
    public DevelopmentResponse get(@PathVariable UUID id) {
        return mapper.toResponse(service.get(id));
    }
}
