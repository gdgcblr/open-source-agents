package com.workwise.ai.feed.web;

import com.workwise.ai.news.domain.DevelopmentCategory;
import com.workwise.ai.news.domain.EvidenceState;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

public record FeedItemResponse(
        UUID developmentId,
        String title,
        String summary,
        String sourceName,
        String sourceUrl,
        Instant publishedAt,
        List<String> industryTags,
        DevelopmentCategory category,
        EvidenceState evidenceState,
        boolean demoData,
        double relevanceScore,
        String relevanceLabel,
        String whyItMatters,
        UUID savedAnalysisId
) {
}
