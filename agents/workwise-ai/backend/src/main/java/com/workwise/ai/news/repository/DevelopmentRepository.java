package com.workwise.ai.news.repository;

import com.workwise.ai.news.domain.Development;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

import java.util.Optional;
import java.util.UUID;

public interface DevelopmentRepository extends JpaRepository<Development, UUID>, JpaSpecificationExecutor<Development> {
    Optional<Development> findByContentHash(String contentHash);
}
