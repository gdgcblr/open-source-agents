package com.workwise.ai.relevance.service;

import com.workwise.ai.news.domain.Development;
import com.workwise.ai.profile.domain.UserProfile;
import com.workwise.ai.relevance.config.RelevanceProperties;
import com.workwise.ai.relevance.domain.RelevanceAssessment;
import com.workwise.ai.relevance.repository.RelevanceAssessmentRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Optional;

@Service
@Transactional
public class RelevanceService {

    private final RelevanceScorer scorer;
    private final RelevanceAssessmentRepository repository;
    private final RelevanceProperties properties;

    public RelevanceService(RelevanceScorer scorer, RelevanceAssessmentRepository repository, RelevanceProperties properties) {
        this.scorer = scorer;
        this.repository = repository;
        this.properties = properties;
    }

    /**
     * Scores (or re-uses a cached score for) a development against a profile. Returns empty when
     * the development has no meaningful connection to the profile's work — such developments are
     * never persisted or shown.
     */
    public Optional<RelevanceAssessment> assess(UserProfile profile, Development development) {
        Optional<RelevanceAssessment> cached = repository.findByProfileIdAndDevelopmentId(profile.getId(), development.getId());
        if (cached.isPresent()) {
            return cached;
        }

        RelevanceScorer.ScoreBreakdown scores = scorer.score(profile, development);
        if (!scores.meaningfulConnection()) {
            return Optional.empty();
        }

        RelevanceProperties.Weights w = properties.getWeights();
        double weighted = scores.jobIndustryScore() * w.getJobIndustry()
                + scores.economicScore() * w.getEconomic()
                + scores.actionabilityScore() * w.getActionability()
                + scores.locationScore() * w.getLocation()
                + scores.recencyScore() * w.getRecency()
                + scores.goalAlignmentScore() * w.getGoalAlignment();

        RelevanceAssessment assessment = new RelevanceAssessment();
        assessment.setProfile(profile);
        assessment.setDevelopment(development);
        assessment.setJobIndustryScore(scores.jobIndustryScore());
        assessment.setEconomicScore(scores.economicScore());
        assessment.setActionabilityScore(scores.actionabilityScore());
        assessment.setLocationScore(scores.locationScore());
        assessment.setRecencyScore(scores.recencyScore());
        assessment.setGoalAlignmentScore(scores.goalAlignmentScore());
        assessment.setWeightedScore(weighted);
        assessment.setExplanation(scorer.explain(profile, development, scores));

        return Optional.of(repository.save(assessment));
    }

    public List<RelevanceAssessment> assessAll(UserProfile profile, List<Development> developments) {
        return developments.stream()
                .map(d -> assess(profile, d))
                .filter(Optional::isPresent)
                .map(Optional::get)
                .filter(a -> !a.isDismissed())
                .filter(a -> a.getWeightedScore() >= properties.getThreshold())
                .toList();
    }

    public double getThreshold() {
        return properties.getThreshold();
    }

    public void markIrrelevant(UserProfile profile, Development development) {
        RelevanceAssessment assessment = assess(profile, development).orElse(null);
        if (assessment != null) {
            assessment.setDismissed(true);
            repository.save(assessment);
        }
    }
}
