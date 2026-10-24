package com.workwise.ai.profile.web;

import com.workwise.ai.profile.domain.UserProfile;
import org.springframework.stereotype.Component;

import java.util.ArrayList;

@Component
public class UserProfileMapper {

    public UserProfileResponse toResponse(UserProfile entity) {
        return new UserProfileResponse(
                entity.getId(),
                entity.getOccupation(),
                entity.getIndustry(),
                entity.getCountry(),
                entity.getRegion(),
                entity.getCity(),
                entity.getBusinessType(),
                entity.getPrimaryObjective(),
                entity.getSecondaryObjectives(),
                entity.getBudgetAmount(),
                entity.getRiskTolerance(),
                entity.getRelevantKeywords(),
                entity.getPreferredLanguage(),
                entity.getPreferredCategories(),
                entity.getCreatedAt(),
                entity.getUpdatedAt()
        );
    }

    public void applyToEntity(UserProfileRequest request, UserProfile entity) {
        entity.setOccupation(request.occupation());
        entity.setIndustry(request.industry());
        entity.setCountry(request.country());
        entity.setRegion(request.region());
        entity.setCity(request.city());
        entity.setBusinessType(request.businessType());
        entity.setPrimaryObjective(request.primaryObjective());
        entity.setSecondaryObjectives(request.secondaryObjectives() == null ? new ArrayList<>() : request.secondaryObjectives());
        entity.setBudgetAmount(request.budgetAmount());
        entity.setRiskTolerance(request.riskTolerance());
        entity.setRelevantKeywords(request.relevantKeywords() == null ? new ArrayList<>() : request.relevantKeywords());
        entity.setPreferredLanguage(request.preferredLanguage() == null || request.preferredLanguage().isBlank()
                ? "en" : request.preferredLanguage());
        entity.setPreferredCategories(request.preferredCategories() == null ? new ArrayList<>() : request.preferredCategories());
    }
}
