package com.workwise.ai.news.repository;

import com.workwise.ai.news.domain.Development;
import com.workwise.ai.news.domain.DevelopmentCategory;
import org.springframework.data.jpa.domain.Specification;

import java.time.Instant;

public final class DevelopmentSpecifications {

    private DevelopmentSpecifications() {
    }

    public static Specification<Development> category(DevelopmentCategory category) {
        return (root, query, cb) -> category == null ? null : cb.equal(root.get("category"), category);
    }

    public static Specification<Development> country(String country) {
        return (root, query, cb) -> (country == null || country.isBlank())
                ? null : cb.equal(cb.lower(root.get("country")), country.toLowerCase());
    }

    public static Specification<Development> region(String region) {
        return (root, query, cb) -> (region == null || region.isBlank())
                ? null : cb.equal(cb.lower(root.get("region")), region.toLowerCase());
    }

    public static Specification<Development> publishedAfter(Instant since) {
        return (root, query, cb) -> since == null ? null : cb.greaterThanOrEqualTo(root.get("publishedAt"), since);
    }
}
