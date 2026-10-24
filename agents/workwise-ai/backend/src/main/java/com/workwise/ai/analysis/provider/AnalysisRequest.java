package com.workwise.ai.analysis.provider;

import com.workwise.ai.news.domain.Development;
import com.workwise.ai.profile.domain.UserProfile;

/** Everything the provider needs, with no more personal data than necessary. */
public record AnalysisRequest(
        UserProfile profile,
        Development development
) {
}
