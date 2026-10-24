package com.workwise.ai.sources.repository;

import com.workwise.ai.sources.domain.InformationSource;
import com.workwise.ai.sources.domain.SourceType;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.UUID;

public interface InformationSourceRepository extends JpaRepository<InformationSource, UUID> {
    List<InformationSource> findByActiveTrueAndType(SourceType type);
}
