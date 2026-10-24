package com.workwise.ai.news.domain;

import com.workwise.ai.common.domain.BaseEntity;
import com.workwise.ai.sources.domain.InformationSource;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

/**
 * Preserves distinct provenance when multiple sources report on the same {@link Development},
 * so independent claims are never silently merged into one.
 */
@Entity
@Table(name = "development_evidence")
public class DevelopmentEvidence extends BaseEntity {

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "development_id", nullable = false)
    private Development development;

    @Column(name = "evidence_text", nullable = false, columnDefinition = "text")
    private String evidenceText;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "source_id")
    private InformationSource source;

    @Column(name = "source_url", length = 500)
    private String sourceUrl;

    public Development getDevelopment() {
        return development;
    }

    public void setDevelopment(Development development) {
        this.development = development;
    }

    public String getEvidenceText() {
        return evidenceText;
    }

    public void setEvidenceText(String evidenceText) {
        this.evidenceText = evidenceText;
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
}
