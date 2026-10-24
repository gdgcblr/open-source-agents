package com.workwise.ai.news.service;

import com.workwise.ai.common.exception.ResourceNotFoundException;
import com.workwise.ai.news.domain.Development;
import com.workwise.ai.news.domain.DevelopmentCategory;
import com.workwise.ai.news.repository.DevelopmentRepository;
import com.workwise.ai.news.repository.DevelopmentSpecifications;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

@Service
@Transactional(readOnly = true)
public class DevelopmentService {

    private final DevelopmentRepository repository;

    public DevelopmentService(DevelopmentRepository repository) {
        this.repository = repository;
    }

    public Page<Development> list(DevelopmentCategory category, String country, String region,
                                   Integer recencyDays, Pageable pageable) {
        Instant since = recencyDays != null ? Instant.now().minus(recencyDays, ChronoUnit.DAYS) : null;
        Specification<Development> spec = Specification.allOf(
                DevelopmentSpecifications.category(category),
                DevelopmentSpecifications.country(country),
                DevelopmentSpecifications.region(region),
                DevelopmentSpecifications.publishedAfter(since)
        );
        return repository.findAll(spec, pageable);
    }

    public Development get(UUID id) {
        return repository.findById(id).orElseThrow(() -> new ResourceNotFoundException("Development not found: " + id));
    }
}
