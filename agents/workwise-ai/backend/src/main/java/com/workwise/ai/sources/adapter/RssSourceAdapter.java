package com.workwise.ai.sources.adapter;

import com.rometools.rome.feed.synd.SyndEntry;
import com.rometools.rome.feed.synd.SyndFeed;
import com.rometools.rome.io.SyndFeedInput;
import com.rometools.rome.io.XmlReader;
import com.workwise.ai.sources.domain.InformationSource;
import com.workwise.ai.sources.domain.SourceType;
import org.springframework.stereotype.Component;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

/**
 * Pulls items from a configured, permitted RSS feed URL. Only ever reads the feed itself (no
 * scraping of linked pages, no authentication bypass). On any network/parse failure, raises
 * {@link SourceUnavailableException} so the caller can record/skip the error rather than invent data.
 */
@Component
public class RssSourceAdapter implements SourceAdapter {

    private final HttpClient httpClient = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .build();

    @Override
    public SourceType supportedType() {
        return SourceType.RSS;
    }

    @Override
    public List<RawDevelopmentItem> fetch(InformationSource source) throws SourceUnavailableException {
        if (source.getUrl() == null || source.getUrl().isBlank()) {
            throw new SourceUnavailableException("RSS source '" + source.getName() + "' has no configured URL");
        }
        try {
            HttpRequest request = HttpRequest.newBuilder(URI.create(source.getUrl()))
                    .timeout(Duration.ofSeconds(15))
                    .GET()
                    .build();
            HttpResponse<byte[]> response = httpClient.send(request, HttpResponse.BodyHandlers.ofByteArray());
            if (response.statusCode() / 100 != 2) {
                throw new SourceUnavailableException(
                        "RSS source '" + source.getName() + "' returned HTTP " + response.statusCode());
            }
            SyndFeedInput input = new SyndFeedInput();
            SyndFeed feed = input.build(new XmlReader(new java.io.ByteArrayInputStream(response.body())));

            List<RawDevelopmentItem> items = new ArrayList<>();
            for (SyndEntry entry : feed.getEntries()) {
                String summary = entry.getDescription() != null ? entry.getDescription().getValue() : "";
                Instant published = entry.getPublishedDate() != null ? entry.getPublishedDate().toInstant() : null;
                items.add(new RawDevelopmentItem(
                        entry.getTitle(),
                        summary,
                        entry.getLink(),
                        published,
                        published,
                        null,
                        null,
                        List.of(),
                        "INDUSTRY_CHANGES"
                ));
            }
            return items;
        } catch (SourceUnavailableException e) {
            throw e;
        } catch (Exception e) {
            throw new SourceUnavailableException(
                    "Failed to fetch/parse RSS source '" + source.getName() + "': " + e.getMessage(), e);
        }
    }
}
