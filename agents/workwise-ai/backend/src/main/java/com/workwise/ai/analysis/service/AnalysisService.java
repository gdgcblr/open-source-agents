package com.workwise.ai.analysis.service;

import com.workwise.ai.analysis.domain.OpportunityAnalysis;
import com.workwise.ai.analysis.provider.AnalysisRequest;
import com.workwise.ai.analysis.provider.AnalysisResult;
import com.workwise.ai.analysis.provider.OpportunityAnalysisProvider;
import com.workwise.ai.analysis.provider.StrategyDraft;
import com.workwise.ai.analysis.repository.OpportunityAnalysisRepository;
import com.workwise.ai.common.exception.AccessDeniedException;
import com.workwise.ai.common.exception.ResourceNotFoundException;
import com.workwise.ai.news.domain.Development;
import com.workwise.ai.news.service.DevelopmentService;
import com.workwise.ai.profile.domain.UserProfile;
import com.workwise.ai.profile.service.UserProfileService;
import com.workwise.ai.strategies.domain.Strategy;
import com.workwise.ai.strategies.repository.StrategyRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.UUID;

@Service
@Transactional
public class AnalysisService {

    private final UserProfileService userProfileService;
    private final DevelopmentService developmentService;
    private final OpportunityAnalysisProvider provider;
    private final OpportunityAnalysisRepository analysisRepository;
    private final StrategyRepository strategyRepository;

    public AnalysisService(UserProfileService userProfileService,
                            DevelopmentService developmentService,
                            OpportunityAnalysisProvider provider,
                            OpportunityAnalysisRepository analysisRepository,
                            StrategyRepository strategyRepository) {
        this.userProfileService = userProfileService;
        this.developmentService = developmentService;
        this.provider = provider;
        this.analysisRepository = analysisRepository;
        this.strategyRepository = strategyRepository;
    }

    public OpportunityAnalysis createAnalysis(UUID profileId, UUID developmentId) {
        UserProfile profile = userProfileService.findOwned(profileId);
        Development development = developmentService.get(developmentId);

        AnalysisRequest request = new AnalysisRequest(profile, development);
        AnalysisResult result = provider.analyze(request);

        OpportunityAnalysis analysis = new OpportunityAnalysis();
        analysis.setProfile(profile);
        analysis.setDevelopment(development);
        analysis.setSummary(result.summary());
        analysis.setConfirmedFacts(result.confirmedFacts());
        analysis.setWhyItMatters(result.whyItMatters());
        analysis.setHistoricalComparisons(result.historicalComparisons());
        analysis.setTrends(result.trends());
        analysis.setUnknowns(result.unknowns());
        analysis.setNextSteps(result.nextSteps());
        analysis.setProvider(provider.providerName());
        analysis = analysisRepository.save(analysis);

        List<StrategyDraft> drafts = provider.proposeStrategies(request, result);
        for (StrategyDraft draft : drafts) {
            Strategy strategy = new Strategy();
            strategy.setAnalysis(analysis);
            strategy.setName(draft.name());
            strategy.setDescription(draft.description());
            strategy.setRationale(draft.rationale());
            strategy.setEvidence(draft.evidence());
            strategy.setRequiredInvestment(draft.requiredInvestment());
            strategy.setRequiredResources(draft.requiredResources());
            strategy.setTimeCommitment(draft.timeCommitment());
            strategy.setBenefits(draft.benefits());
            strategy.setRisks(draft.risks());
            strategy.setDependencies(draft.dependencies());
            strategy.setFailureConditions(draft.failureConditions());
            strategy.setValidationSteps(draft.validationSteps());
            strategy.setNextAction(draft.nextAction());
            strategy.setConfidenceLevel(draft.confidenceLevel());
            strategy.setConfidenceJustification(draft.confidenceJustification());
            strategy.setWaitAndResearch(draft.waitAndResearch());
            strategyRepository.save(strategy);
        }

        return analysis;
    }

    @Transactional(readOnly = true)
    public OpportunityAnalysis get(UUID id) {
        OpportunityAnalysis analysis = analysisRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Analysis not found: " + id));
        // Access control: verify ownership via the linked profile.
        userProfileService.findOwned(analysis.getProfile().getId());
        return analysis;
    }

    @Transactional(readOnly = true)
    public List<Strategy> getStrategies(UUID analysisId) {
        OpportunityAnalysis analysis = get(analysisId);
        return strategyRepository.findByAnalysisId(analysis.getId());
    }

    @Transactional(readOnly = true)
    public List<OpportunityAnalysis> listForProfile(UUID profileId) {
        userProfileService.findOwned(profileId);
        return analysisRepository.findByProfileId(profileId);
    }
}
