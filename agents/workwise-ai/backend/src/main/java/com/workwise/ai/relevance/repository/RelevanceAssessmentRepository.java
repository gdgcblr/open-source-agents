package com.workwise.ai.relevance.repository;

import com.workwise.ai.relevance.domain.RelevanceAssessment;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;
import java.util.UUID;

public interface RelevanceAssessmentRepository extends JpaRepository<RelevanceAssessment, UUID> {
    Optional<RelevanceAssessment> findByProfileIdAndDevelopmentId(UUID profileId, UUID developmentId);
}
