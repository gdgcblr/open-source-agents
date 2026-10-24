package com.workwise.ai.news.web;

import com.workwise.ai.news.domain.DevelopmentCategory;
import com.workwise.ai.news.domain.EvidenceState;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

public record DevelopmentResponse(
        UUID id,
        String title,
        String summary,
        String sourceName,
        String sourceUrl,
        Instant publishedAt,
        Instant eventAt,
        String country,
        String region,
        List<String> industryTags,
        DevelopmentCategory category,
        EvidenceState evidenceState,
        boolean demoData
) {
}
