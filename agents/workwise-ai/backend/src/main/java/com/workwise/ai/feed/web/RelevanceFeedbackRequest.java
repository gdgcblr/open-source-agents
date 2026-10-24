package com.workwise.ai.feed.web;

import jakarta.validation.constraints.NotNull;

import java.util.UUID;

public record RelevanceFeedbackRequest(
        @NotNull UUID profileId,
        @NotNull UUID developmentId,
        String note
) {
}
