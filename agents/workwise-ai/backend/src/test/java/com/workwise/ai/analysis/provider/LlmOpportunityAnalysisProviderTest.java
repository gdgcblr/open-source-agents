package com.workwise.ai.analysis.provider;

import com.workwise.ai.common.exception.AiProviderException;
import com.workwise.ai.news.domain.Development;
import com.workwise.ai.news.domain.DevelopmentCategory;
import com.workwise.ai.news.domain.EvidenceState;
import com.workwise.ai.profile.domain.BusinessType;
import com.workwise.ai.profile.domain.Objective;
import com.workwise.ai.profile.domain.RiskTolerance;
import com.workwise.ai.profile.domain.UserProfile;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

class LlmOpportunityAnalysisProviderTest {

    @Test
    void connectionFailureRaisesAiProviderExceptionRatherThanFabricatingData() {
        // Port 1 is a reserved/closed port, guaranteeing an immediate connection failure.
        LlmOpportunityAnalysisProvider provider = new LlmOpportunityAnalysisProvider(
                "http://127.0.0.1:1/analyze", "test-key", "test-model", 2000L);

        UserProfile profile = new UserProfile();
        profile.setOccupation("Textile Trader");
        profile.setIndustry("Textiles");
        profile.setCountry("India");
        profile.setBusinessType(BusinessType.SMALL_BUSINESS);
        profile.setPrimaryObjective(Objective.INCREASE_BUSINESS_PROFIT);
        profile.setRiskTolerance(RiskTolerance.MEDIUM);

        Development development = new Development();
        development.setTitle("Test development");
        development.setSummary("Test summary");
        development.setCategory(DevelopmentCategory.MARKET_PRICES);
        development.setEvidenceState(EvidenceState.UNVERIFIED);

        AnalysisRequest request = new AnalysisRequest(profile, development);

        assertThatThrownBy(() -> provider.analyze(request))
                .isInstanceOf(AiProviderException.class);
    }
}
