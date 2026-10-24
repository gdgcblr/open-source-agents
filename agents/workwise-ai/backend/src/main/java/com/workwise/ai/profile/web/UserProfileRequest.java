package com.workwise.ai.profile.web;

import com.workwise.ai.profile.domain.BusinessType;
import com.workwise.ai.profile.domain.Objective;
import com.workwise.ai.profile.domain.RiskTolerance;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PositiveOrZero;

import java.math.BigDecimal;
import java.util.List;

public record UserProfileRequest(
        @NotBlank(message = "occupation is required") String occupation,
        @NotBlank(message = "industry is required") String industry,
        @NotBlank(message = "country is required") String country,
        String region,
        String city,
        @NotNull(message = "businessType is required") BusinessType businessType,
        @NotNull(message = "primaryObjective is required") Objective primaryObjective,
        List<String> secondaryObjectives,
        @PositiveOrZero(message = "budgetAmount must not be negative") BigDecimal budgetAmount,
        @NotNull(message = "riskTolerance is required") RiskTolerance riskTolerance,
        List<String> relevantKeywords,
        String preferredLanguage,
        List<String> preferredCategories
) {
}
