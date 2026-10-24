package com.workwise.ai.analysis.repository;

import com.workwise.ai.analysis.domain.OpportunityAnalysis;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.UUID;

public interface OpportunityAnalysisRepository extends JpaRepository<OpportunityAnalysis, UUID> {
    List<OpportunityAnalysis> findByProfileId(UUID profileId);
}
