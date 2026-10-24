package com.workwise.ai.analysis.domain;

import com.workwise.ai.common.domain.BaseEntity;
import com.workwise.ai.news.domain.Development;
import com.workwise.ai.profile.domain.UserProfile;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "opportunity_analysis")
public class OpportunityAnalysis extends BaseEntity {

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "profile_id", nullable = false)
    private UserProfile profile;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "development_id", nullable = false)
    private Development development;

    @Column(nullable = false, columnDefinition = "text")
    private String summary;

    @JdbcTypeCode(SqlTypes.ARRAY)
    @Column(name = "confirmed_facts", columnDefinition = "text[]")
    private List<String> confirmedFacts = new ArrayList<>();

    @Column(name = "why_it_matters", nullable = false, columnDefinition = "text")
    private String whyItMatters;

    @JdbcTypeCode(SqlTypes.ARRAY)
    @Column(name = "historical_comparisons", columnDefinition = "text[]")
    private List<String> historicalComparisons = new ArrayList<>();

    @JdbcTypeCode(SqlTypes.ARRAY)
    @Column(columnDefinition = "text[]")
    private List<String> trends = new ArrayList<>();

    @JdbcTypeCode(SqlTypes.ARRAY)
    @Column(columnDefinition = "text[]")
    private List<String> unknowns = new ArrayList<>();

    @JdbcTypeCode(SqlTypes.ARRAY)
    @Column(name = "next_steps", columnDefinition = "text[]")
    private List<String> nextSteps = new ArrayList<>();

    @Column(nullable = false, length = 10)
    private String provider;

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

    public String getSummary() {
        return summary;
    }

    public void setSummary(String summary) {
        this.summary = summary;
    }

    public List<String> getConfirmedFacts() {
        return confirmedFacts;
    }

    public void setConfirmedFacts(List<String> confirmedFacts) {
        this.confirmedFacts = confirmedFacts;
    }

    public String getWhyItMatters() {
        return whyItMatters;
    }

    public void setWhyItMatters(String whyItMatters) {
        this.whyItMatters = whyItMatters;
    }

    public List<String> getHistoricalComparisons() {
        return historicalComparisons;
    }

    public void setHistoricalComparisons(List<String> historicalComparisons) {
        this.historicalComparisons = historicalComparisons;
    }

    public List<String> getTrends() {
        return trends;
    }

    public void setTrends(List<String> trends) {
        this.trends = trends;
    }

    public List<String> getUnknowns() {
        return unknowns;
    }

    public void setUnknowns(List<String> unknowns) {
        this.unknowns = unknowns;
    }

    public List<String> getNextSteps() {
        return nextSteps;
    }

    public void setNextSteps(List<String> nextSteps) {
        this.nextSteps = nextSteps;
    }

    public String getProvider() {
        return provider;
    }

    public void setProvider(String provider) {
        this.provider = provider;
    }
}
