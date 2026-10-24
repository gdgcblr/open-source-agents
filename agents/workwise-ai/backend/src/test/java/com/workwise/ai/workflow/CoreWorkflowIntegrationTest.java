package com.workwise.ai.workflow;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.workwise.ai.support.AbstractIntegrationTest;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Covers the required core workflow end-to-end using the seeded demonstration textile-trader
 * profile and the mock AI provider (no external API key needed), per the project's testing
 * requirements:
 * Create/load profile -&gt; feed -&gt; select development -&gt; analysis -&gt; strategies -&gt;
 * financial scenario -&gt; action plan -&gt; outcome.
 */
@org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
class CoreWorkflowIntegrationTest extends AbstractIntegrationTest {

    private static final UUID SEEDED_TEXTILE_TRADER_PROFILE_ID =
            UUID.fromString("00000000-0000-0000-0000-000000000010");

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Test
    void fullWorkflowFromFeedToOutcome() throws Exception {
        // 1. Load existing seeded profile (demo-textile-trader is the default demo user).
        JsonNode profile = asJson(mockMvc.perform(get("/api/profiles/" + SEEDED_TEXTILE_TRADER_PROFILE_ID))
                .andExpect(status().isOk()));
        assertThat(profile.get("occupation").asText()).isEqualTo("Textile Trader");

        // 2. Retrieve personalized feed; expect at least one relevant demonstration development.
        JsonNode feed = asJson(mockMvc.perform(get("/api/feed").param("profileId", SEEDED_TEXTILE_TRADER_PROFILE_ID.toString()))
                .andExpect(status().isOk()));

        JsonNode candidate = firstItem(feed);
        assertThat(candidate).isNotNull();
        UUID developmentId = UUID.fromString(candidate.get("developmentId").asText());
        assertThat(candidate.get("demoData").asBoolean()).isTrue();

        // 3. Generate opportunity analysis for the selected development.
        JsonNode analysis = asJson(mockMvc.perform(post("/api/analysis")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of(
                                "profileId", SEEDED_TEXTILE_TRADER_PROFILE_ID.toString(),
                                "developmentId", developmentId.toString()))))
                .andExpect(status().isCreated()));
        UUID analysisId = UUID.fromString(analysis.get("id").asText());
        assertThat(analysis.get("provider").asText()).isEqualTo("MOCK");

        // 4. Retrieve generated strategies (2-4 expected).
        JsonNode strategies = asJson(mockMvc.perform(get("/api/analysis/" + analysisId + "/strategies"))
                .andExpect(status().isOk()));
        assertThat(strategies.size()).isBetween(2, 4);

        JsonNode trialStrategy = strategies.get(0);
        UUID strategyId = UUID.fromString(trialStrategy.get("id").asText());

        // 5. Compare strategies.
        List<String> strategyIds = List.of(strategyId.toString());
        JsonNode comparison = asJson(mockMvc.perform(post("/api/strategies/compare")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of("strategyIds", strategyIds))))
                .andExpect(status().isOk()));
        assertThat(comparison.get(0).get("feasibilityLabel").asText()).doesNotContain("%");

        // 6. Calculate financial scenario with real assumptions.
        JsonNode scenarios = asJson(mockMvc.perform(post("/api/financial-scenarios")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of(
                                "strategyId", strategyId.toString(),
                                "quantity", 1000,
                                "unitCost", 100,
                                "transportCost", 5000,
                                "sellingPrice", 150,
                                "expectedSalesQuantity", 900
                        ))))
                .andExpect(status().isOk()));
        assertThat(scenarios.size()).isEqualTo(3);

        // 7. Create an action plan for the strategy.
        JsonNode actionPlan = asJson(mockMvc.perform(post("/api/action-plans")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of(
                                "strategyId", strategyId.toString(),
                                "title", "Trial plan",
                                "items", List.of(Map.of("action", "Contact supplier for sample batch"))
                        ))))
                .andExpect(status().isCreated()));
        UUID planId = UUID.fromString(actionPlan.get("id").asText());
        UUID itemId = UUID.fromString(actionPlan.get("items").get(0).get("id").asText());

        // 8. Mark the action item completed.
        asJson(mockMvc.perform(put("/api/action-plans/" + planId + "/items/" + itemId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of("status", "COMPLETED"))))
                .andExpect(status().isOk()));

        // 9. Record the outcome.
        JsonNode outcome = asJson(mockMvc.perform(post("/api/outcomes")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(Map.of(
                                "strategyId", strategyId.toString(),
                                "actualRevenue", 130000,
                                "actualExpenses", 112000,
                                "userReportedOutcome", "Trial batch sold out within two weeks."
                        ))))
                .andExpect(status().isCreated()));
        assertThat(outcome.get("independentlyVerified").asBoolean()).isFalse();

        JsonNode history = asJson(mockMvc.perform(get("/api/outcomes/by-strategy/" + strategyId))
                .andExpect(status().isOk()));
        assertThat(history.size()).isEqualTo(1);
    }

    private JsonNode firstItem(JsonNode feed) {
        for (String bucket : List.of("importantForYourWork", "potentialOpportunities", "trends")) {
            JsonNode items = feed.get(bucket);
            if (items != null && items.size() > 0) {
                return items.get(0);
            }
        }
        return null;
    }

    private JsonNode asJson(org.springframework.test.web.servlet.ResultActions result) throws Exception {
        return objectMapper.readTree(result.andReturn().getResponse().getContentAsString());
    }
}
