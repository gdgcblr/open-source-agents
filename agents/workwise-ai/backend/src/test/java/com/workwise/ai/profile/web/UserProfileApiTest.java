package com.workwise.ai.profile.web;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.workwise.ai.common.auth.DemoUserFilter;
import com.workwise.ai.support.AbstractIntegrationTest;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.util.Map;
import java.util.UUID;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
class UserProfileApiTest extends AbstractIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Test
    void createProfileFailsValidationWhenRequiredFieldsMissing() throws Exception {
        Map<String, Object> invalid = Map.of("occupation", "");

        mockMvc.perform(post("/api/profiles")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(invalid)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value(400));
    }

    @Test
    void createAndRetrieveProfileSucceedsForOwner() throws Exception {
        Map<String, Object> request = validProfileRequest();

        MvcResult createResult = mockMvc.perform(post("/api/profiles")
                        .header(DemoUserFilter.HEADER_NAME, "user-a")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isCreated())
                .andReturn();

        UserProfileResponse created = objectMapper.readValue(
                createResult.getResponse().getContentAsString(), UserProfileResponse.class);

        mockMvc.perform(get("/api/profiles/" + created.id())
                        .header(DemoUserFilter.HEADER_NAME, "user-a"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.occupation").value("Textile Trader"));
    }

    @Test
    void retrievingAnotherUsersProfileIsForbidden() throws Exception {
        Map<String, Object> request = validProfileRequest();

        MvcResult createResult = mockMvc.perform(post("/api/profiles")
                        .header(DemoUserFilter.HEADER_NAME, "user-a")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isCreated())
                .andReturn();

        UserProfileResponse created = objectMapper.readValue(
                createResult.getResponse().getContentAsString(), UserProfileResponse.class);

        mockMvc.perform(get("/api/profiles/" + created.id())
                        .header(DemoUserFilter.HEADER_NAME, "user-b"))
                .andExpect(status().isForbidden());
    }

    @Test
    void retrievingUnknownProfileReturnsNotFound() throws Exception {
        mockMvc.perform(get("/api/profiles/" + UUID.randomUUID())
                        .header(DemoUserFilter.HEADER_NAME, "user-a"))
                .andExpect(status().isNotFound());
    }

    private Map<String, Object> validProfileRequest() {
        return Map.ofEntries(
                Map.entry("occupation", "Textile Trader"),
                Map.entry("industry", "Textiles and Garments"),
                Map.entry("country", "India"),
                Map.entry("region", "Gujarat"),
                Map.entry("city", "Surat"),
                Map.entry("businessType", "SMALL_BUSINESS"),
                Map.entry("primaryObjective", "INCREASE_BUSINESS_PROFIT"),
                Map.entry("secondaryObjectives", java.util.List.of("REDUCE_EXPENSES")),
                Map.entry("budgetAmount", 150000),
                Map.entry("riskTolerance", "MEDIUM"),
                Map.entry("relevantKeywords", java.util.List.of("cotton", "fabric")),
                Map.entry("preferredLanguage", "en"),
                Map.entry("preferredCategories", java.util.List.of("MARKET_PRICES"))
        );
    }
}
