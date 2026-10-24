package com.workwise.ai.analysis.provider;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.workwise.ai.common.exception.AiProviderException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;
import java.util.Map;

/**
 * Configurable real-LLM-backed provider. Disabled unless {@code workwise.ai.provider=llm}.
 *
 * <p>Contract: POSTs a JSON prompt payload to {@code workwise.ai.llm.api-url} with the API key in
 * an Authorization header (never exposed to the frontend, read only from the
 * {@code WORKWISE_LLM_API_KEY} environment variable), requesting a structured JSON response that
 * is parsed directly into {@link AnalysisResult} / {@link StrategyDraft}. Any malformed response,
 * timeout, or transport error raises {@link AiProviderException} with a clear message rather than
 * silently falling back to fabricated data.</p>
 */
@Component
@ConditionalOnProperty(prefix = "workwise.ai", name = "provider", havingValue = "llm")
public class LlmOpportunityAnalysisProvider implements OpportunityAnalysisProvider {

    private final String apiUrl;
    private final String apiKey;
    private final String model;
    private final HttpClient httpClient;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public LlmOpportunityAnalysisProvider(
            @Value("${workwise.ai.llm.api-url}") String apiUrl,
            @Value("${workwise.ai.llm.api-key}") String apiKey,
            @Value("${workwise.ai.llm.model}") String model,
            @Value("${workwise.ai.llm.timeout-ms:15000}") long timeoutMs) {
        this.apiUrl = apiUrl;
        this.apiKey = apiKey;
        this.model = model;
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofMillis(timeoutMs))
                .build();
        if (apiUrl == null || apiUrl.isBlank()) {
            throw new IllegalStateException("workwise.ai.llm.api-url must be set when workwise.ai.provider=llm");
        }
    }

    @Override
    public String providerName() {
        return "LLM:" + model;
    }

    @Override
    public AnalysisResult analyze(AnalysisRequest request) {
        Map<String, Object> payload = Map.of(
                "model", model,
                "task", "opportunity_analysis",
                "profile", Map.of(
                        "occupation", request.profile().getOccupation(),
                        "industry", request.profile().getIndustry(),
                        "country", request.profile().getCountry(),
                        "primaryObjective", request.profile().getPrimaryObjective().name()
                ),
                "development", Map.of(
                        "title", request.development().getTitle(),
                        "summary", request.development().getSummary(),
                        "category", request.development().getCategory().name(),
                        "evidenceState", request.development().getEvidenceState().name(),
                        "isDemoData", request.development().isDemoData()
                )
        );
        JsonResponse response = call(payload);
        if (response.analysis() == null) {
            throw new AiProviderException("LLM response did not include an 'analysis' object");
        }
        return response.analysis();
    }

    @Override
    public List<StrategyDraft> proposeStrategies(AnalysisRequest request, AnalysisResult analysis) {
        Map<String, Object> payload = Map.of(
                "model", model,
                "task", "propose_strategies",
                "analysisSummary", analysis.summary()
        );
        JsonResponse response = call(payload);
        if (response.strategies() == null) {
            throw new AiProviderException("LLM response did not include a 'strategies' array");
        }
        return response.strategies();
    }

    private JsonResponse call(Map<String, Object> payload) {
        try {
            String body = objectMapper.writeValueAsString(payload);
            HttpRequest httpRequest = HttpRequest.newBuilder(URI.create(apiUrl))
                    .header("Content-Type", "application/json")
                    .header("Authorization", "Bearer " + apiKey)
                    .timeout(Duration.ofSeconds(30))
                    .POST(HttpRequest.BodyPublishers.ofString(body))
                    .build();
            HttpResponse<String> response = httpClient.send(httpRequest, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() / 100 != 2) {
                throw new AiProviderException("LLM provider returned HTTP " + response.statusCode());
            }
            return objectMapper.readValue(response.body(), JsonResponse.class);
        } catch (AiProviderException e) {
            throw e;
        } catch (Exception e) {
            throw new AiProviderException("LLM provider call failed: " + e.getMessage(), e);
        }
    }

    private record JsonResponse(AnalysisResult analysis, List<StrategyDraft> strategies) {
    }
}
