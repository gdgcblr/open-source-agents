package com.workwise.ai.analysis.provider;

import com.workwise.ai.news.domain.Development;
import com.workwise.ai.news.domain.EvidenceState;
import com.workwise.ai.profile.domain.RiskTolerance;
import com.workwise.ai.profile.domain.UserProfile;
import com.workwise.ai.strategies.domain.ConfidenceLevel;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

/**
 * Deterministic, rule-based provider used by default so the application runs end-to-end without
 * any external AI API key. Never invents facts beyond the given {@link Development}: historical
 * comparisons and trends are only populated when the development itself is demonstration data
 * (clearly labeled) or otherwise explicitly states them; unknown information is listed as unknown
 * rather than guessed.
 */
@Component
@ConditionalOnProperty(prefix = "workwise.ai", name = "provider", havingValue = "mock", matchIfMissing = true)
public class MockOpportunityAnalysisProvider implements OpportunityAnalysisProvider {

    @Override
    public String providerName() {
        return "MOCK";
    }

    @Override
    public AnalysisResult analyze(AnalysisRequest request) {
        Development d = request.development();
        UserProfile p = request.profile();

        List<String> confirmedFacts = new ArrayList<>();
        confirmedFacts.add(d.getTitle());
        if (d.getSummary() != null && !d.getSummary().isBlank()) {
            confirmedFacts.add(d.getSummary());
        }
        confirmedFacts.add("Source evidence state: " + d.getEvidenceState()
                + (d.isDemoData() ? " (DEMONSTRATION DATA — illustrative, not a real event)" : ""));

        String whyItMatters = "As a " + p.getOccupation() + " in " + p.getIndustry()
                + ", this " + d.getCategory().name().toLowerCase().replace('_', ' ')
                + " development is relevant to your stated objective of "
                + p.getPrimaryObjective().name().toLowerCase().replace('_', ' ') + ".";

        List<String> historicalComparisons = new ArrayList<>();
        List<String> trends = new ArrayList<>();
        if (d.isDemoData()) {
            historicalComparisons.add("DEMONSTRATION DATA: in this illustrative scenario, a similar past change " +
                    "was followed by comparable businesses adjusting supplier terms within 4-6 weeks.");
            trends.add("DEMONSTRATION DATA: illustrative trend — similar developments have recurred roughly " +
                    "every two to three quarters in this fictional scenario.");
        }

        List<String> unknowns = new ArrayList<>(List.of(
                "Exact magnitude of impact on your specific suppliers/customers is not confirmed by available sources.",
                "Whether this development will persist beyond the short term is not yet known."
        ));

        List<String> nextSteps = new ArrayList<>(List.of(
                "Review the source evidence directly before acting.",
                "Open the opportunity analysis to compare strategies and run the financial calculator with your real numbers."
        ));

        return new AnalysisResult(
                "Summary: " + d.getTitle(),
                confirmedFacts,
                whyItMatters,
                historicalComparisons,
                trends,
                unknowns,
                nextSteps
        );
    }

    @Override
    public List<StrategyDraft> proposeStrategies(AnalysisRequest request, AnalysisResult analysis) {
        UserProfile p = request.profile();
        List<StrategyDraft> drafts = new ArrayList<>();

        BigDecimal budget = p.getBudgetAmount() != null ? p.getBudgetAmount() : BigDecimal.ZERO;

        drafts.add(new StrategyDraft(
                "Small trial / pilot",
                "Commit a small, reversible portion of budget or time to test this opportunity before scaling up.",
                "Limits downside risk while generating real data about whether the opportunity holds up.",
                List.copyOf(analysis.confirmedFacts()),
                budget.multiply(new BigDecimal("0.15")),
                List.of("A few hours of research", "A small trial purchase or outreach batch"),
                "1-2 weeks",
                List.of("Low financial exposure", "Produces real evidence for a bigger decision"),
                List.of("May be too small to reveal issues that only appear at scale"),
                List.of("Availability of a trial-sized quantity or audience"),
                List.of("If the trial shows no measurable benefit within the validation window"),
                List.of("Define a clear success metric before starting", "Set a fixed trial budget and stop date"),
                "Run the financial calculator with trial-scale numbers, then execute the smallest viable version.",
                ConfidenceLevel.MEDIUM,
                "Based on the development's evidence state (" + request.development().getEvidenceState() + "); a small trial is prudent given residual uncertainty.",
                false
        ));

        drafts.add(new StrategyDraft(
                "Wait and gather more information",
                "Delay committing resources until more evidence accumulates or the situation becomes clearer.",
                "Appropriate when the evidence is unverified/partially verified or your risk tolerance is low.",
                List.copyOf(analysis.confirmedFacts()),
                BigDecimal.ZERO,
                List.of("Time to monitor follow-up developments"),
                "2-4 weeks of monitoring",
                List.of("No capital at risk", "Avoids acting on unverified information"),
                List.of("Possible missed window if the opportunity is time-limited"),
                List.of("Access to updated information sources"),
                List.of("If no corroborating evidence appears within the monitoring window"),
                List.of("Set a specific re-check date", "Define what new evidence would change the decision"),
                "Save this analysis and re-check it in 2-4 weeks.",
                ConfidenceLevel.HIGH,
                "Waiting carries essentially no downside when evidence is incomplete.",
                true
        ));

        if (p.getRiskTolerance() != RiskTolerance.LOW && budget.signum() > 0) {
            drafts.add(new StrategyDraft(
                    "Full commitment at current scale",
                    "Commit your available budget to act on this opportunity at normal operating scale now.",
                    "Appropriate if the evidence is verified and the opportunity is time-sensitive.",
                    List.copyOf(analysis.confirmedFacts()),
                    budget,
                    List.of("Full available budget", "Operational capacity to execute at scale"),
                    "Immediate, 1-2 weeks to execute",
                    List.of("Maximum potential benefit if the opportunity holds"),
                    List.of("Full budget exposed if the opportunity does not pan out",
                            "Harder to reverse than a trial"),
                    List.of("Verified or at least partially verified evidence", "Stable supplier/customer conditions"),
                    List.of("If actual results diverge materially from the assumptions used in the financial calculator"),
                    List.of("Re-verify the key facts from the source", "Confirm the financial scenario with conservative assumptions"),
                    "Only proceed after reviewing the financial scenario comparison.",
                    ConfidenceLevel.LOW,
                    "Full commitment without a trial is higher-confidence only when evidence is strong; marked LOW here as a caution given typical evidence limitations.",
                    false
            ));
        }

        return drafts;
    }
}
