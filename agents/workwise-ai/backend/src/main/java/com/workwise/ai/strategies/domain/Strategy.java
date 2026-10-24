package com.workwise.ai.strategies.domain;

import com.workwise.ai.analysis.domain.OpportunityAnalysis;
import com.workwise.ai.common.domain.BaseEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "strategy")
public class Strategy extends BaseEntity {

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "analysis_id", nullable = false)
    private OpportunityAnalysis analysis;

    @Column(nullable = false, length = 160)
    private String name;

    @Column(nullable = false, columnDefinition = "text")
    private String description;

    @Column(nullable = false, columnDefinition = "text")
    private String rationale;

    @JdbcTypeCode(SqlTypes.ARRAY)
    @Column(columnDefinition = "text[]")
    private List<String> evidence = new ArrayList<>();

    @Column(name = "required_investment", precision = 14, scale = 2)
    private BigDecimal requiredInvestment;

    @JdbcTypeCode(SqlTypes.ARRAY)
    @Column(name = "required_resources", columnDefinition = "text[]")
    private List<String> requiredResources = new ArrayList<>();

    @Column(name = "time_commitment", length = 200)
    private String timeCommitment;

    @JdbcTypeCode(SqlTypes.ARRAY)
    @Column(columnDefinition = "text[]")
    private List<String> benefits = new ArrayList<>();

    @JdbcTypeCode(SqlTypes.ARRAY)
    @Column(columnDefinition = "text[]")
    private List<String> risks = new ArrayList<>();

    @JdbcTypeCode(SqlTypes.ARRAY)
    @Column(columnDefinition = "text[]")
    private List<String> dependencies = new ArrayList<>();

    @JdbcTypeCode(SqlTypes.ARRAY)
    @Column(name = "failure_conditions", columnDefinition = "text[]")
    private List<String> failureConditions = new ArrayList<>();

    @JdbcTypeCode(SqlTypes.ARRAY)
    @Column(name = "validation_steps", columnDefinition = "text[]")
    private List<String> validationSteps = new ArrayList<>();

    @Column(name = "next_action", columnDefinition = "text")
    private String nextAction;

    @Enumerated(EnumType.STRING)
    @Column(name = "confidence_level", nullable = false, length = 10)
    private ConfidenceLevel confidenceLevel;

    @Column(name = "confidence_justification", columnDefinition = "text")
    private String confidenceJustification;

    @Column(name = "is_wait_and_research", nullable = false)
    private boolean waitAndResearch = false;

    @Column(name = "is_selected", nullable = false)
    private boolean selected = false;

    public OpportunityAnalysis getAnalysis() {
        return analysis;
    }

    public void setAnalysis(OpportunityAnalysis analysis) {
        this.analysis = analysis;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getDescription() {
        return description;
    }

    public void setDescription(String description) {
        this.description = description;
    }

    public String getRationale() {
        return rationale;
    }

    public void setRationale(String rationale) {
        this.rationale = rationale;
    }

    public List<String> getEvidence() {
        return evidence;
    }

    public void setEvidence(List<String> evidence) {
        this.evidence = evidence;
    }

    public BigDecimal getRequiredInvestment() {
        return requiredInvestment;
    }

    public void setRequiredInvestment(BigDecimal requiredInvestment) {
        this.requiredInvestment = requiredInvestment;
    }

    public List<String> getRequiredResources() {
        return requiredResources;
    }

    public void setRequiredResources(List<String> requiredResources) {
        this.requiredResources = requiredResources;
    }

    public String getTimeCommitment() {
        return timeCommitment;
    }

    public void setTimeCommitment(String timeCommitment) {
        this.timeCommitment = timeCommitment;
    }

    public List<String> getBenefits() {
        return benefits;
    }

    public void setBenefits(List<String> benefits) {
        this.benefits = benefits;
    }

    public List<String> getRisks() {
        return risks;
    }

    public void setRisks(List<String> risks) {
        this.risks = risks;
    }

    public List<String> getDependencies() {
        return dependencies;
    }

    public void setDependencies(List<String> dependencies) {
        this.dependencies = dependencies;
    }

    public List<String> getFailureConditions() {
        return failureConditions;
    }

    public void setFailureConditions(List<String> failureConditions) {
        this.failureConditions = failureConditions;
    }

    public List<String> getValidationSteps() {
        return validationSteps;
    }

    public void setValidationSteps(List<String> validationSteps) {
        this.validationSteps = validationSteps;
    }

    public String getNextAction() {
        return nextAction;
    }

    public void setNextAction(String nextAction) {
        this.nextAction = nextAction;
    }

    public ConfidenceLevel getConfidenceLevel() {
        return confidenceLevel;
    }

    public void setConfidenceLevel(ConfidenceLevel confidenceLevel) {
        this.confidenceLevel = confidenceLevel;
    }

    public String getConfidenceJustification() {
        return confidenceJustification;
    }

    public void setConfidenceJustification(String confidenceJustification) {
        this.confidenceJustification = confidenceJustification;
    }

    public boolean isWaitAndResearch() {
        return waitAndResearch;
    }

    public void setWaitAndResearch(boolean waitAndResearch) {
        this.waitAndResearch = waitAndResearch;
    }

    public boolean isSelected() {
        return selected;
    }

    public void setSelected(boolean selected) {
        this.selected = selected;
    }
}
