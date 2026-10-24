package dev.mutationaudit;

import java.util.*;

/** Turns nested SDK failures into actionable messages without exposing credentials. */
final class AiDiagnostics {
    static final String DEFAULT_MODEL = "gemini-3.5-flash-lite";

    static String message(Throwable error, String model) {
        var seen = Collections.newSetFromMap(new IdentityHashMap<Throwable, Boolean>());
        StringBuilder messages = new StringBuilder();
        for (Throwable cause = error; cause != null && seen.add(cause); cause = cause.getCause())
            messages.append(cause.getClass().getSimpleName()).append(": ").append(cause.getMessage()).append('\n');
        String detail = redact(messages.toString());
        String lower = detail.toLowerCase(Locale.ROOT);
        if (lower.contains("404") || lower.contains("not_found"))
            return "Model '" + model + "' is unavailable to this API project. Select an available model with --model "
                    + DEFAULT_MODEL + " (or update MUTATION_AUDITOR_MODEL). Gemini 2.5 access is restricted for new projects.";
        if (lower.contains("429") || lower.contains("resource_exhausted"))
            return "Gemini quota or rate limit reached. Check this project's quota/billing, wait if the limit is temporary, then retry the saved XML report.";
        if (lower.contains("401") || lower.contains("403") || lower.contains("api_key_invalid") || lower.contains("api key not valid"))
            return "Gemini rejected authentication or model access. Check GOOGLE_API_KEY and the API project's permissions.";
        if (lower.contains("timeout") || lower.contains("timed out"))
            return "AI analysis reached its time limit. Retry the saved XML or increase --timeout-seconds.";
        Throwable deepest = error;
        seen.clear();
        while (deepest.getCause() != null && seen.add(deepest.getCause())) deepest = deepest.getCause();
        return "AI analysis failed: " + redact(Objects.toString(deepest.getMessage(), deepest.getClass().getSimpleName()));
    }

    static String redact(String text) {
        String key = System.getenv("GOOGLE_API_KEY");
        if (key != null && !key.isBlank()) text = text.replace(key, "[REDACTED]");
        return text.replaceAll("AIza[0-9A-Za-z_-]+", "[REDACTED]")
                .replaceAll("(?i)([?&](?:key|api_key)=)[^&\\s]+", "$1[REDACTED]")
                .replaceAll("(?i)Bearer\\s+[A-Za-z0-9._-]+", "Bearer [REDACTED]");
    }
}
