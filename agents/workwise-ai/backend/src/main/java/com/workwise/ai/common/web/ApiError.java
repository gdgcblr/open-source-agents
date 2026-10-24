package com.workwise.ai.common.web;

import java.time.Instant;
import java.util.List;

/**
 * Consistent error response body. Never includes stack traces or secrets.
 */
public record ApiError(
        Instant timestamp,
        int status,
        String error,
        String message,
        String path,
        List<String> details
) {
    public static ApiError of(int status, String error, String message, String path, List<String> details) {
        return new ApiError(Instant.now(), status, error, message, path, details);
    }
}
