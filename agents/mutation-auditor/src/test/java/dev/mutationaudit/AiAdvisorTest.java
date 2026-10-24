package dev.mutationaudit;

import com.google.adk.events.Event;
import com.google.genai.types.Content;
import com.google.genai.types.Part;
import com.google.genai.types.FunctionCall;
import io.reactivex.rxjava3.core.Flowable;
import org.junit.jupiter.api.Test;
import java.time.Duration;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;

class AiAdvisorTest {
    @Test void collectsFinalTextAfterToolCallsWithoutShowingThoughtParts() {
        var tool = Event.builder().author("mutation_auditor").content(Content.fromParts(
                Part.builder().functionCall(FunctionCall.builder().name("readJavaFile").args(Map.of("path", "src/main/java/App.java")).build()).build())).build();
        var answer = Event.builder().author("mutation_auditor").content(Content.fromParts(
                Part.builder().text("private reasoning").thought(true).build(), Part.fromText("UNVERIFIED: add a boundary test."))).build();
        assertEquals("UNVERIFIED: add a boundary test.", AiAdvisor.collect(Flowable.just(tool, answer), Duration.ofSeconds(5)));
    }

    @Test void surfacesAdkErrorEventsInsteadOfTreatingThemAsEmptyAnswers() {
        var event = Event.builder().author("mutation_auditor").errorMessage("404 NOT_FOUND: model unavailable").build();
        var error = assertThrows(Exception.class, () -> AiAdvisor.collect(Flowable.just(event), Duration.ofSeconds(5)));
        assertTrue(AiDiagnostics.message(error, "old-model").contains("--model"));
    }

    @Test void rejectsEmptyAnswersAndEnforcesAnAbsoluteDeadline() {
        assertThrows(Exception.class, () -> AiAdvisor.collect(Flowable.empty(), Duration.ofSeconds(5)));
        long started = System.nanoTime();
        var error = assertThrows(Exception.class, () -> AiAdvisor.collect(Flowable.never(), Duration.ofMillis(100)));
        assertTrue(AiDiagnostics.message(error, "model").contains("time limit"));
        assertTrue(Duration.ofNanos(System.nanoTime() - started).toSeconds() < 3);
    }

    @Test void actionableErrorsRedactKeysAndExplainQuotaAndAuthentication() {
        var error = new RuntimeException(new IllegalStateException("404 NOT_FOUND: models/old-model"));
        assertTrue(AiDiagnostics.message(error, "old-model").contains(AiDiagnostics.DEFAULT_MODEL));
        assertTrue(AiDiagnostics.message(new IllegalStateException("429 RESOURCE_EXHAUSTED"), "model").contains("quota"));
        assertTrue(AiDiagnostics.message(new IllegalStateException("403 PERMISSION_DENIED"), "model").contains("GOOGLE_API_KEY"));
        String fakeKey = "AIza" + "x".repeat(35);
        assertFalse(AiDiagnostics.message(new IllegalStateException("Failure: " + fakeKey), "model").contains(fakeKey));
    }
}
