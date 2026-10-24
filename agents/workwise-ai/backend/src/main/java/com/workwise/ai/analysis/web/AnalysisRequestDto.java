package com.workwise.ai.analysis.web;

import jakarta.validation.constraints.NotNull;

import java.util.UUID;

public record AnalysisRequestDto(
        @NotNull(message = "profileId is required") UUID profileId,
        @NotNull(message = "developmentId is required") UUID developmentId
) {
}
