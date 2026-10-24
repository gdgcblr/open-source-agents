package com.workwise.ai.sources.adapter;

import java.time.Instant;

/**
 * A single raw item retrieved from a source, before persistence/deduplication.
 * Never contains invented fields — adapters must leave a field null/blank rather than guess.
 */
public record RawDevelopmentItem(
        String title,
        String summary,
        String sourceUrl,
        Instant publishedAt,
        Instant eventAt,
        String country,
        String region,
        java.util.List<String> industryTags,
        String category
) {
}
