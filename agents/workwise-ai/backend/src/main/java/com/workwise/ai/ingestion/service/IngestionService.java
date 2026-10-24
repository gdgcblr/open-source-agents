package com.workwise.ai.ingestion.service;

import com.workwise.ai.news.domain.Development;
import com.workwise.ai.news.domain.DevelopmentCategory;
import com.workwise.ai.news.domain.DevelopmentEvidence;
import com.workwise.ai.news.domain.EvidenceState;
import com.workwise.ai.news.repository.DevelopmentRepository;
import com.workwise.ai.sources.adapter.RawDevelopmentItem;
import com.workwise.ai.sources.adapter.SourceAdapter;
import com.workwise.ai.sources.adapter.SourceUnavailableException;
import com.workwise.ai.sources.domain.InformationSource;
import com.workwise.ai.sources.domain.SourceType;
import com.workwise.ai.sources.repository.InformationSourceRepository;
import jakarta.persistence.EntityManager;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.function.Function;
import java.util.stream.Collectors;

/**
 * Pulls raw items from every active, non-demo {@link InformationSource} via the matching
 * {@link SourceAdapter}, deduplicates by content hash, and applies the evidence-state rules
 * documented on {@link EvidenceState}. Demonstration data is seeded separately via Flyway and is
 * never produced by this service.
 */
@Service
public class IngestionService {

    private final InformationSourceRepository sourceRepository;
    private final DevelopmentRepository developmentRepository;
    private final Map<SourceType, SourceAdapter> adaptersByType;
    private final EntityManager entityManager;

    public IngestionService(InformationSourceRepository sourceRepository,
                             DevelopmentRepository developmentRepository,
                             List<SourceAdapter> adapters,
                             EntityManager entityManager) {
        this.sourceRepository = sourceRepository;
        this.developmentRepository = developmentRepository;
        this.adaptersByType = adapters.stream().collect(Collectors.toMap(SourceAdapter::supportedType, Function.identity()));
        this.entityManager = entityManager;
    }

    @Transactional
    public IngestionResult runIngestion() {
        List<InformationSource> activeNonDemoSources = sourceRepository.findAll().stream()
                .filter(InformationSource::isActive)
                .filter(s -> s.getType() != SourceType.DEMO)
                .toList();

        int fetched = 0;
        int created = 0;
        int duplicate = 0;
        int failed = 0;
        List<String> errors = new ArrayList<>();

        for (InformationSource source : activeNonDemoSources) {
            SourceAdapter adapter = adaptersByType.get(source.getType());
            if (adapter == null) {
                failed++;
                errors.add("No adapter registered for source type " + source.getType() + " (" + source.getName() + ")");
                continue;
            }
            try {
                List<RawDevelopmentItem> items = adapter.fetch(source);
                fetched += items.size();
                for (RawDevelopmentItem item : items) {
                    boolean wasCreated = persistIfNew(item, source);
                    if (wasCreated) {
                        created++;
                    } else {
                        duplicate++;
                    }
                }
            } catch (SourceUnavailableException e) {
                failed++;
                errors.add(e.getMessage());
            }
        }

        return new IngestionResult(activeNonDemoSources.size(), failed, fetched, created, duplicate, errors);
    }

    private boolean persistIfNew(RawDevelopmentItem item, InformationSource source) {
        String hash = contentHash(item.title(), item.sourceUrl());
        Optional<Development> existing = developmentRepository.findByContentHash(hash);
        if (existing.isPresent()) {
            return false;
        }

        Development development = new Development();
        development.setTitle(item.title());
        development.setSummary(item.summary() == null ? "" : item.summary());
        development.setSource(source);
        development.setSourceUrl(item.sourceUrl());
        development.setPublishedAt(item.publishedAt());
        development.setEventAt(item.eventAt());
        development.setCountry(item.country());
        development.setRegion(item.region());
        development.setIndustryTags(item.industryTags() == null ? List.of() : item.industryTags());
        development.setCategory(resolveCategory(item.category()));
        development.setDemoData(false);
        development.setContentHash(hash);
        development.setEvidenceState(resolveEvidenceState(item, source));

        developmentRepository.save(development);

        DevelopmentEvidence evidence = new DevelopmentEvidence();
        evidence.setDevelopment(development);
        evidence.setEvidenceText(item.summary() == null ? item.title() : item.summary());
        evidence.setSource(source);
        evidence.setSourceUrl(item.sourceUrl());
        entityManager.persist(evidence);

        return true;
    }

    /**
     * Simple, explainable heuristic: an item becomes PARTIALLY_VERIFIED when an existing
     * development shares a near-identical normalized title (independent source corroboration),
     * and VERIFIED additionally when either contributing source is authoritative.
     */
    private EvidenceState resolveEvidenceState(RawDevelopmentItem item, InformationSource source) {
        String normalizedTitle = normalize(item.title());
        boolean corroborated = developmentRepository.findAll().stream()
                .filter(d -> !d.isDemoData())
                .anyMatch(d -> normalize(d.getTitle()).equals(normalizedTitle)
                        && d.getSource() != null && !d.getSource().getId().equals(source.getId()));
        if (!corroborated) {
            return EvidenceState.UNVERIFIED;
        }
        return source.isAuthoritative() ? EvidenceState.VERIFIED : EvidenceState.PARTIALLY_VERIFIED;
    }

    private DevelopmentCategory resolveCategory(String rawCategory) {
        if (rawCategory == null) {
            return DevelopmentCategory.INDUSTRY_CHANGES;
        }
        try {
            return DevelopmentCategory.valueOf(rawCategory);
        } catch (IllegalArgumentException e) {
            return DevelopmentCategory.INDUSTRY_CHANGES;
        }
    }

    private String normalize(String text) {
        return text == null ? "" : text.trim().toLowerCase(Locale.ROOT).replaceAll("\\s+", " ");
    }

    private String contentHash(String title, String sourceUrl) {
        String raw = normalize(title) + "|" + (sourceUrl == null ? "" : sourceUrl.trim());
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(raw.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(hash);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 not available", e);
        }
    }
}
