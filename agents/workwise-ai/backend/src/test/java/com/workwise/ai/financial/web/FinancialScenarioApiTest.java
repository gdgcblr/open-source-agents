package com.workwise.ai.financial.web;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.workwise.ai.support.AbstractIntegrationTest;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;

import java.util.Map;
import java.util.UUID;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
class FinancialScenarioApiTest extends AbstractIntegrationTest {

    @Autowired
    private org.springframework.test.web.servlet.MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Test
    void missingRequiredFieldsReturnsBadRequest() throws Exception {
        Map<String, Object> incompleteRequest = Map.of(
                "strategyId", UUID.randomUUID().toString()
                // quantity, unitCost, sellingPrice, expectedSalesQuantity all missing
        );

        mockMvc.perform(post("/api/financial-scenarios")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(incompleteRequest)))
                .andExpect(status().isBadRequest());
    }

    @Test
    void unknownStrategyReturnsNotFound() throws Exception {
        Map<String, Object> request = Map.of(
                "strategyId", UUID.randomUUID().toString(),
                "quantity", 100,
                "unitCost", 10,
                "sellingPrice", 20,
                "expectedSalesQuantity", 50
        );

        mockMvc.perform(post("/api/financial-scenarios")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isNotFound());
    }
}
