package com.workwise.ai.feed.web;

import com.workwise.ai.feed.service.FeedService;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;

@RestController
@RequestMapping("/api/feed")
public class FeedController {

    private final FeedService feedService;

    public FeedController(FeedService feedService) {
        this.feedService = feedService;
    }

    @GetMapping
    public FeedResponse getFeed(@RequestParam UUID profileId) {
        return feedService.getFeed(profileId);
    }

    @PostMapping("/feedback")
    public void submitFeedback(@Valid @RequestBody RelevanceFeedbackRequest request) {
        feedService.markIrrelevant(request.profileId(), request.developmentId(), request.note());
    }
}
