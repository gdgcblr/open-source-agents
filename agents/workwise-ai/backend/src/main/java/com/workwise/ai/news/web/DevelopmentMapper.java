package com.workwise.ai.news.web;

import com.workwise.ai.news.domain.Development;
import org.springframework.stereotype.Component;

@Component
public class DevelopmentMapper {

    public DevelopmentResponse toResponse(Development d) {
        return new DevelopmentResponse(
                d.getId(),
                d.getTitle(),
                d.getSummary(),
                d.getSource() != null ? d.getSource().getName() : null,
                d.getSourceUrl(),
                d.getPublishedAt(),
                d.getEventAt(),
                d.getCountry(),
                d.getRegion(),
                d.getIndustryTags(),
                d.getCategory(),
                d.getEvidenceState(),
                d.isDemoData()
        );
    }
}
