package com.workwise.ai.ingestion.service;

import com.workwise.ai.news.domain.Development;
import com.workwise.ai.news.domain.EvidenceState;
import com.workwise.ai.news.repository.DevelopmentRepository;
import com.workwise.ai.sources.adapter.RawDevelopmentItem;
import com.workwise.ai.sources.adapter.SourceAdapter;
import com.workwise.ai.sources.adapter.SourceUnavailableException;
import com.workwise.ai.sources.domain.InformationSource;
import com.workwise.ai.sources.domain.SourceType;
import com.workwise.ai.sources.repository.InformationSourceRepository;
import jakarta.persistence.EntityManager;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class IngestionServiceTest {

    private InformationSourceRepository sourceRepository;
    private DevelopmentRepository developmentRepository;
    private EntityManager entityManager;
    private List<Development> savedDevelopments;

    @BeforeEach
    void setUp() {
        sourceRepository = mock(InformationSourceRepository.class);
        developmentRepository = mock(DevelopmentRepository.class);
        entityManager = mock(EntityManager.class);
        savedDevelopments = new ArrayList<>();
    }

    private InformationSource rssSource(boolean authoritative) {
        InformationSource source = new InformationSource();
        source.setId(UUID.randomUUID());
        source.setName("Test RSS Feed");
        source.setType(SourceType.RSS);
        source.setUrl("https://example.invalid/feed");
        source.setAuthoritative(authoritative);
        source.setActive(true);
        return source;
    }

    @Test
    void firstIngestionCreatesDevelopmentAsUnverified() throws SourceUnavailableException {
        InformationSource source = rssSource(false);
        when(sourceRepository.findAll()).thenReturn(List.of(source));
        when(developmentRepository.findByContentHash(any())).thenReturn(Optional.empty());
        when(developmentRepository.findAll()).thenReturn(List.of());
        when(developmentRepository.save(any())).thenAnswer(invocation -> {
            Development d = invocation.getArgument(0);
            savedDevelopments.add(d);
            return d;
        });

        RawDevelopmentItem item = new RawDevelopmentItem(
                "Example Title", "Example summary", "https://example.invalid/a", Instant.now(), Instant.now(),
                "India", "Gujarat", List.of("textiles"), "MARKET_PRICES");
        SourceAdapter adapter = fakeAdapter(List.of(item));

        IngestionService service = new IngestionService(sourceRepository, developmentRepository, List.of(adapter), entityManager);
        IngestionResult result = service.runIngestion();

        assertThat(result.itemsCreated()).isEqualTo(1);
        assertThat(result.itemsDuplicate()).isEqualTo(0);
        assertThat(savedDevelopments).hasSize(1);
        assertThat(savedDevelopments.get(0).getEvidenceState()).isEqualTo(EvidenceState.UNVERIFIED);
    }

    @Test
    void duplicateItemIsNotPersistedAgain() throws SourceUnavailableException {
        InformationSource source = rssSource(false);
        when(sourceRepository.findAll()).thenReturn(List.of(source));

        Development existing = new Development();
        existing.setTitle("Example Title");
        when(developmentRepository.findByContentHash(any())).thenReturn(Optional.of(existing));

        RawDevelopmentItem item = new RawDevelopmentItem(
                "Example Title", "Example summary", "https://example.invalid/a", Instant.now(), Instant.now(),
                null, null, List.of(), "MARKET_PRICES");
        SourceAdapter adapter = fakeAdapter(List.of(item));

        IngestionService service = new IngestionService(sourceRepository, developmentRepository, List.of(adapter), entityManager);
        IngestionResult result = service.runIngestion();

        assertThat(result.itemsCreated()).isEqualTo(0);
        assertThat(result.itemsDuplicate()).isEqualTo(1);
        verify(developmentRepository, org.mockito.Mockito.never()).save(any());
    }

    @Test
    void sourceFailureIsRecordedAsErrorNotFabricatedData() throws SourceUnavailableException {
        InformationSource source = rssSource(false);
        when(sourceRepository.findAll()).thenReturn(List.of(source));

        SourceAdapter failingAdapter = mock(SourceAdapter.class);
        when(failingAdapter.supportedType()).thenReturn(SourceType.RSS);
        when(failingAdapter.fetch(any())).thenThrow(new SourceUnavailableException("feed unreachable"));

        IngestionService service = new IngestionService(sourceRepository, developmentRepository, List.of(failingAdapter), entityManager);
        IngestionResult result = service.runIngestion();

        assertThat(result.sourcesFailed()).isEqualTo(1);
        assertThat(result.errors()).anyMatch(e -> e.contains("feed unreachable"));
        assertThat(result.itemsCreated()).isEqualTo(0);
    }

    @Test
    void corroboratedItemFromAuthoritativeSourceBecomesVerified() throws SourceUnavailableException {
        InformationSource authoritative = rssSource(true);
        when(sourceRepository.findAll()).thenReturn(List.of(authoritative));
        when(developmentRepository.findByContentHash(any())).thenReturn(Optional.empty());

        Development existingFromOtherSource = new Development();
        existingFromOtherSource.setTitle("Fabric prices rise sharply");
        InformationSource otherSource = rssSource(false);
        otherSource.setId(UUID.randomUUID());
        existingFromOtherSource.setSource(otherSource);
        when(developmentRepository.findAll()).thenReturn(List.of(existingFromOtherSource));
        when(developmentRepository.save(any())).thenAnswer(invocation -> {
            Development d = invocation.getArgument(0);
            savedDevelopments.add(d);
            return d;
        });

        RawDevelopmentItem item = new RawDevelopmentItem(
                "Fabric prices rise sharply", "summary", "https://example.invalid/b", Instant.now(), Instant.now(),
                null, null, List.of(), "MARKET_PRICES");
        SourceAdapter adapter = fakeAdapter(List.of(item));

        IngestionService service = new IngestionService(sourceRepository, developmentRepository, List.of(adapter), entityManager);
        service.runIngestion();

        assertThat(savedDevelopments).hasSize(1);
        assertThat(savedDevelopments.get(0).getEvidenceState()).isEqualTo(EvidenceState.VERIFIED);
    }

    private SourceAdapter fakeAdapter(List<RawDevelopmentItem> items) throws SourceUnavailableException {
        SourceAdapter adapter = mock(SourceAdapter.class);
        when(adapter.supportedType()).thenReturn(SourceType.RSS);
        when(adapter.fetch(any())).thenReturn(items);
        return adapter;
    }
}
