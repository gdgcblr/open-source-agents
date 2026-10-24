package com.workwise.ai.relevance.domain;

import com.workwise.ai.common.domain.BaseEntity;
import com.workwise.ai.news.domain.Development;
import com.workwise.ai.profile.domain.UserProfile;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

@Entity
@Table(name = "relevance_assessment", uniqueConstraints = @UniqueConstraint(columnNames = {"profile_id", "development_id"}))
public class RelevanceAssessment extends BaseEntity {

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "profile_id", nullable = false)
    private UserProfile profile;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "development_id", nullable = false)
    private Development development;

    @Column(name = "job_industry_score", nullable = false)
    private double jobIndustryScore;

    @Column(name = "economic_score", nullable = false)
    private double economicScore;

    @Column(name = "actionability_score", nullable = false)
    private double actionabilityScore;

    @Column(name = "location_score", nullable = false)
    private double locationScore;

    @Column(name = "recency_score", nullable = false)
    private double recencyScore;

    @Column(name = "goal_alignment_score", nullable = false)
    private double goalAlignmentScore;

    @Column(name = "weighted_score", nullable = false)
    private double weightedScore;

    @Column(nullable = false, columnDefinition = "text")
    private String explanation;

    @Column(name = "is_dismissed", nullable = false)
    private boolean dismissed = false;

    public UserProfile getProfile() {
        return profile;
    }

    public void setProfile(UserProfile profile) {
        this.profile = profile;
    }

    public Development getDevelopment() {
        return development;
    }

    public void setDevelopment(Development development) {
        this.development = development;
    }

    public double getJobIndustryScore() {
        return jobIndustryScore;
    }

    public void setJobIndustryScore(double jobIndustryScore) {
        this.jobIndustryScore = jobIndustryScore;
    }

    public double getEconomicScore() {
        return economicScore;
    }

    public void setEconomicScore(double economicScore) {
        this.economicScore = economicScore;
    }

    public double getActionabilityScore() {
        return actionabilityScore;
    }

    public void setActionabilityScore(double actionabilityScore) {
        this.actionabilityScore = actionabilityScore;
    }

    public double getLocationScore() {
        return locationScore;
    }

    public void setLocationScore(double locationScore) {
        this.locationScore = locationScore;
    }

    public double getRecencyScore() {
        return recencyScore;
    }

    public void setRecencyScore(double recencyScore) {
        this.recencyScore = recencyScore;
    }

    public double getGoalAlignmentScore() {
        return goalAlignmentScore;
    }

    public void setGoalAlignmentScore(double goalAlignmentScore) {
        this.goalAlignmentScore = goalAlignmentScore;
    }

    public double getWeightedScore() {
        return weightedScore;
    }

    public void setWeightedScore(double weightedScore) {
        this.weightedScore = weightedScore;
    }

    public String getExplanation() {
        return explanation;
    }

    public void setExplanation(String explanation) {
        this.explanation = explanation;
    }

    public boolean isDismissed() {
        return dismissed;
    }

    public void setDismissed(boolean dismissed) {
        this.dismissed = dismissed;
    }
}
