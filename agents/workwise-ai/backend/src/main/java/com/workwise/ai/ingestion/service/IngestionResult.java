package com.workwise.ai.ingestion.service;

import java.util.List;

/** Result of a single ingestion run, for observability — never silently swallowed. */
public record IngestionResult(
        int sourcesAttempted,
        int sourcesFailed,
        int itemsFetched,
        int itemsCreated,
        int itemsDuplicate,
        List<String> errors
) {
}
