package com.workwise.ai.profile.web;

import com.workwise.ai.profile.domain.BusinessType;
import com.workwise.ai.profile.domain.Objective;
import com.workwise.ai.profile.domain.RiskTolerance;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

public record UserProfileResponse(
        UUID id,
        String occupation,
        String industry,
        String country,
        String region,
        String city,
        BusinessType businessType,
        Objective primaryObjective,
        List<String> secondaryObjectives,
        BigDecimal budgetAmount,
        RiskTolerance riskTolerance,
        List<String> relevantKeywords,
        String preferredLanguage,
        List<String> preferredCategories,
        Instant createdAt,
        Instant updatedAt
) {
}
