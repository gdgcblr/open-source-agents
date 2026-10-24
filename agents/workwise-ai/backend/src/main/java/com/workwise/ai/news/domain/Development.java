package com.workwise.ai.news.domain;

import com.workwise.ai.common.domain.BaseEntity;
import com.workwise.ai.sources.domain.InformationSource;
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

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "development")
public class Development extends BaseEntity {

    @Column(nullable = false, length = 300)
    private String title;

    @Column(nullable = false, columnDefinition = "text")
    private String summary;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "source_id")
    private InformationSource source;

    @Column(name = "source_url", length = 500)
    private String sourceUrl;

    @Column(name = "published_at")
    private Instant publishedAt;

    @Column(name = "event_at")
    private Instant eventAt;

    @Column(length = 80)
    private String country;

    @Column(length = 120)
    private String region;

    @JdbcTypeCode(SqlTypes.ARRAY)
    @Column(name = "industry_tags", columnDefinition = "text[]")
    private List<String> industryTags = new ArrayList<>();

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 40)
    private DevelopmentCategory category;

    @Enumerated(EnumType.STRING)
    @Column(name = "evidence_state", nullable = false, length = 30)
    private EvidenceState evidenceState;

    @Column(name = "is_demo_data", nullable = false)
    private boolean demoData = false;

    @Column(name = "content_hash", nullable = false, unique = true, length = 64)
    private String contentHash;

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public String getSummary() {
        return summary;
    }

    public void setSummary(String summary) {
        this.summary = summary;
    }

    public InformationSource getSource() {
        return source;
    }

    public void setSource(InformationSource source) {
        this.source = source;
    }

    public String getSourceUrl() {
        return sourceUrl;
    }

    public void setSourceUrl(String sourceUrl) {
        this.sourceUrl = sourceUrl;
    }

    public Instant getPublishedAt() {
        return publishedAt;
    }

    public void setPublishedAt(Instant publishedAt) {
        this.publishedAt = publishedAt;
    }

    public Instant getEventAt() {
        return eventAt;
    }

    public void setEventAt(Instant eventAt) {
        this.eventAt = eventAt;
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

    public List<String> getIndustryTags() {
        return industryTags;
    }

    public void setIndustryTags(List<String> industryTags) {
        this.industryTags = industryTags;
    }

    public DevelopmentCategory getCategory() {
        return category;
    }

    public void setCategory(DevelopmentCategory category) {
        this.category = category;
    }

    public EvidenceState getEvidenceState() {
        return evidenceState;
    }

    public void setEvidenceState(EvidenceState evidenceState) {
        this.evidenceState = evidenceState;
    }

    public boolean isDemoData() {
        return demoData;
    }

    public void setDemoData(boolean demoData) {
        this.demoData = demoData;
    }

    public String getContentHash() {
        return contentHash;
    }

    public void setContentHash(String contentHash) {
        this.contentHash = contentHash;
    }
}
