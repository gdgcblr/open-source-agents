package com.workwise.ai.feed.web;

import java.util.List;

public record FeedResponse(
        List<FeedItemResponse> importantForYourWork,
        List<FeedItemResponse> potentialOpportunities,
        List<FeedItemResponse> trends,
        List<FeedItemResponse> savedAnalyses
) {
}
