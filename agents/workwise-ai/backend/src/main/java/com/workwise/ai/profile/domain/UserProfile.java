package com.workwise.ai.profile.domain;

import com.workwise.ai.common.domain.BaseEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Table;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "user_profile")
public class UserProfile extends BaseEntity {

    @Column(nullable = false, length = 120)
    private String occupation;

    @Column(nullable = false, length = 120)
    private String industry;

    @Column(nullable = false, length = 80)
    private String country;

    @Column(length = 120)
    private String region;

    @Column(length = 120)
    private String city;

    @Enumerated(EnumType.STRING)
    @Column(name = "business_type", nullable = false, length = 60)
    private BusinessType businessType;

    @Enumerated(EnumType.STRING)
    @Column(name = "primary_objective", nullable = false, length = 60)
    private Objective primaryObjective;

    @JdbcTypeCode(SqlTypes.ARRAY)
    @Column(name = "secondary_objectives", columnDefinition = "text[]")
    private List<String> secondaryObjectives = new ArrayList<>();

    @Column(name = "budget_amount", precision = 14, scale = 2)
    private BigDecimal budgetAmount;

    @Enumerated(EnumType.STRING)
    @Column(name = "risk_tolerance", nullable = false, length = 20)
    private RiskTolerance riskTolerance;

    @JdbcTypeCode(SqlTypes.ARRAY)
    @Column(name = "relevant_keywords", columnDefinition = "text[]")
    private List<String> relevantKeywords = new ArrayList<>();

    @Column(name = "preferred_language", nullable = false, length = 10)
    private String preferredLanguage = "en";

    @JdbcTypeCode(SqlTypes.ARRAY)
    @Column(name = "preferred_categories", columnDefinition = "text[]")
    private List<String> preferredCategories = new ArrayList<>();

    @Column(name = "owner_user_id", nullable = false, length = 60)
    private String ownerUserId;

    public String getOccupation() {
        return occupation;
    }

    public void setOccupation(String occupation) {
        this.occupation = occupation;
    }

    public String getIndustry() {
        return industry;
    }

    public void setIndustry(String industry) {
        this.industry = industry;
    }

    public String getCountry() {
        return country;
    }

    public void setCountry(String country) {
        this.country = country;
    }

    public String getRegion() {
        return region;
    }

    public void setRegion(String region) {
        this.region = region;
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }

    public BusinessType getBusinessType() {
        return businessType;
    }

    public void setBusinessType(BusinessType businessType) {
        this.businessType = businessType;
    }

    public Objective getPrimaryObjective() {
        return primaryObjective;
    }

    public void setPrimaryObjective(Objective primaryObjective) {
        this.primaryObjective = primaryObjective;
    }

    public List<String> getSecondaryObjectives() {
        return secondaryObjectives;
    }

    public void setSecondaryObjectives(List<String> secondaryObjectives) {
        this.secondaryObjectives = secondaryObjectives;
    }

    public BigDecimal getBudgetAmount() {
        return budgetAmount;
    }

    public void setBudgetAmount(BigDecimal budgetAmount) {
        this.budgetAmount = budgetAmount;
    }

    public RiskTolerance getRiskTolerance() {
        return riskTolerance;
    }

    public void setRiskTolerance(RiskTolerance riskTolerance) {
        this.riskTolerance = riskTolerance;
    }

    public List<String> getRelevantKeywords() {
        return relevantKeywords;
    }

    public void setRelevantKeywords(List<String> relevantKeywords) {
        this.relevantKeywords = relevantKeywords;
    }

    public String getPreferredLanguage() {
        return preferredLanguage;
    }

    public void setPreferredLanguage(String preferredLanguage) {
        this.preferredLanguage = preferredLanguage;
    }

    public List<String> getPreferredCategories() {
        return preferredCategories;
    }

    public void setPreferredCategories(List<String> preferredCategories) {
        this.preferredCategories = preferredCategories;
    }

    public String getOwnerUserId() {
        return ownerUserId;
    }

    public void setOwnerUserId(String ownerUserId) {
        this.ownerUserId = ownerUserId;
    }
}
