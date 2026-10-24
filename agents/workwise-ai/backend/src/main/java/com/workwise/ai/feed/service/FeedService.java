package com.workwise.ai.feed.service;

import com.workwise.ai.analysis.repository.OpportunityAnalysisRepository;
import com.workwise.ai.feed.web.FeedItemResponse;
import com.workwise.ai.feed.web.FeedResponse;
import com.workwise.ai.feedback.domain.FeedbackType;
import com.workwise.ai.feedback.domain.UserFeedback;
import com.workwise.ai.feedback.repository.UserFeedbackRepository;
import com.workwise.ai.news.domain.Development;
import com.workwise.ai.news.domain.DevelopmentCategory;
import com.workwise.ai.news.repository.DevelopmentRepository;
import com.workwise.ai.profile.domain.UserProfile;
import com.workwise.ai.profile.service.UserProfileService;
import com.workwise.ai.relevance.domain.RelevanceAssessment;
import com.workwise.ai.relevance.service.RelevanceService;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Comparator;
import java.util.EnumSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

/**
 * Builds the personalized home feed by scoring every development against the profile via
 * {@link RelevanceService} and grouping qualifying items into the four required buckets. Never
 * pads the feed with irrelevant content: a bucket is simply empty if nothing qualifies.
 */
@Service
@Transactional
public class FeedService {

    private static final Set<DevelopmentCategory> OPPORTUNITY_CATEGORIES = EnumSet.of(
            DevelopmentCategory.CUSTOMER_DEMAND, DevelopmentCategory.BUSINESS_INVESTMENTS,
            DevelopmentCategory.COMPETITOR_DEVELOPMENTS, DevelopmentCategory.MARKET_PRICES);

    private final UserProfileService userProfileService;
    private final DevelopmentRepository developmentRepository;
    private final RelevanceService relevanceService;
    private final OpportunityAnalysisRepository analysisRepository;
    private final UserFeedbackRepository feedbackRepository;

    public FeedService(UserProfileService userProfileService, DevelopmentRepository developmentRepository,
                        RelevanceService relevanceService, OpportunityAnalysisRepository analysisRepository,
                        UserFeedbackRepository feedbackRepository) {
        this.userProfileService = userProfileService;
        this.developmentRepository = developmentRepository;
        this.relevanceService = relevanceService;
        this.analysisRepository = analysisRepository;
        this.feedbackRepository = feedbackRepository;
    }

    public FeedResponse getFeed(UUID profileId) {
        UserProfile profile = userProfileService.findOwned(profileId);
        List<Development> allDevelopments = developmentRepository.findAll(Sort.by(Sort.Direction.DESC, "publishedAt"));

        List<RelevanceAssessment> assessments = relevanceService.assessAll(profile, allDevelopments);

        Map<UUID, UUID> savedAnalysisByDevelopmentId = analysisRepository.findByProfileId(profileId).stream()
                .collect(Collectors.toMap(a -> a.getDevelopment().getId(), a -> a.getId(), (a, b) -> a));

        double highScoreBar = relevanceService.getThreshold() + 20;

        List<FeedItemResponse> savedAnalyses = assessments.stream()
                .filter(a -> savedAnalysisByDevelopmentId.containsKey(a.getDevelopment().getId()))
                .map(a -> toItem(a, savedAnalysisByDevelopmentId))
                .sorted(Comparator.comparingDouble(FeedItemResponse::relevanceScore).reversed())
                .toList();

        List<RelevanceAssessment> remaining = assessments.stream()
                .filter(a -> !savedAnalysisByDevelopmentId.containsKey(a.getDevelopment().getId()))
                .toList();

        List<FeedItemResponse> important = remaining.stream()
                .filter(a -> a.getWeightedScore() >= highScoreBar)
                .map(a -> toItem(a, savedAnalysisByDevelopmentId))
                .sorted(Comparator.comparingDouble(FeedItemResponse::relevanceScore).reversed())
                .toList();

        List<FeedItemResponse> opportunities = remaining.stream()
                .filter(a -> a.getWeightedScore() < highScoreBar)
                .filter(a -> OPPORTUNITY_CATEGORIES.contains(a.getDevelopment().getCategory()))
                .map(a -> toItem(a, savedAnalysisByDevelopmentId))
                .sorted(Comparator.comparingDouble(FeedItemResponse::relevanceScore).reversed())
                .toList();

        Set<UUID> alreadyBucketed = remaining.stream()
                .filter(a -> a.getWeightedScore() >= highScoreBar || OPPORTUNITY_CATEGORIES.contains(a.getDevelopment().getCategory()))
                .map(a -> a.getDevelopment().getId())
                .collect(Collectors.toSet());

        List<FeedItemResponse> trends = remaining.stream()
                .filter(a -> !alreadyBucketed.contains(a.getDevelopment().getId()))
                .map(a -> toItem(a, savedAnalysisByDevelopmentId))
                .sorted(Comparator.comparingDouble(FeedItemResponse::relevanceScore).reversed())
                .toList();

        return new FeedResponse(important, opportunities, trends, savedAnalyses);
    }

    public void markIrrelevant(UUID profileId, UUID developmentId, String note) {
        UserProfile profile = userProfileService.findOwned(profileId);
        Development development = developmentRepository.findById(developmentId)
                .orElseThrow(() -> new com.workwise.ai.common.exception.ResourceNotFoundException("Development not found: " + developmentId));

        relevanceService.markIrrelevant(profile, development);

        UserFeedback feedback = new UserFeedback();
        feedback.setProfile(profile);
        feedback.setDevelopment(development);
        feedback.setFeedbackType(FeedbackType.IRRELEVANT);
        feedback.setNote(note);
        feedbackRepository.save(feedback);
    }

    private FeedItemResponse toItem(RelevanceAssessment a, Map<UUID, UUID> savedAnalysisByDevelopmentId) {
        Development d = a.getDevelopment();
        String label = a.getWeightedScore() >= 70 ? "High" : a.getWeightedScore() >= 40 ? "Medium" : "Low";
        return new FeedItemResponse(
                d.getId(),
                d.getTitle(),
                d.getSummary(),
                d.getSource() != null ? d.getSource().getName() : null,
                d.getSourceUrl(),
                d.getPublishedAt(),
                d.getIndustryTags(),
                d.getCategory(),
                d.getEvidenceState(),
                d.isDemoData(),
                a.getWeightedScore(),
                label,
                a.getExplanation(),
                savedAnalysisByDevelopmentId.get(d.getId())
        );
    }
}
