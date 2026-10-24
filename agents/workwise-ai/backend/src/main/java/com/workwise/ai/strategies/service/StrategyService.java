package com.workwise.ai.strategies.service;

import com.workwise.ai.common.exception.ResourceNotFoundException;
import com.workwise.ai.profile.service.UserProfileService;
import com.workwise.ai.strategies.domain.Strategy;
import com.workwise.ai.strategies.repository.StrategyRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.UUID;

@Service
@Transactional
public class StrategyService {

    private final StrategyRepository repository;
    private final UserProfileService userProfileService;
    private final StrategyComparisonService comparisonService;

    public StrategyService(StrategyRepository repository, UserProfileService userProfileService,
                            StrategyComparisonService comparisonService) {
        this.repository = repository;
        this.userProfileService = userProfileService;
        this.comparisonService = comparisonService;
    }

    @Transactional(readOnly = true)
    public Strategy get(UUID id) {
        Strategy strategy = repository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Strategy not found: " + id));
        userProfileService.findOwned(strategy.getAnalysis().getProfile().getId());
        return strategy;
    }

    @Transactional(readOnly = true)
    public List<StrategyComparisonItem> compare(List<UUID> strategyIds) {
        return strategyIds.stream().map(this::get).map(comparisonService::toComparisonItem).toList();
    }

    public Strategy select(UUID id) {
        Strategy strategy = get(id);
        strategy.setSelected(true);
        return repository.save(strategy);
    }
}
