package dev.mutationaudit;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class AiReportTest {
    @TempDir Path temp;
    private final MutationReport report = new MutationReport(List.of(
            new MutationReport.Mutant("SURVIVED", false, "App.java", "App", "check", 6, "boundary", "changed boundary")));

    @Test void failedAiLeavesMeasuredReportsAndAnActionableErrorFile() throws Exception {
        var options = new Main.Options(); options.ai = true;
        int exit = Main.write(report, temp, options, temp, "baseline-passed", Map.of("type", "local"),
                (r, p, m, t) -> { throw new IllegalStateException("404 NOT_FOUND model unavailable"); });
        assertEquals(1, exit);
        var json = new ObjectMapper().readTree(temp.resolve("report.json").toFile());
        assertEquals(0.0, json.get("mutationScore").asDouble());
        assertEquals("failed", json.at("/ai/status").asText());
        assertTrue(Files.readString(temp.resolve("ai-error.md")).contains("--model"));
        assertFalse(Files.exists(temp.resolve("recommendations.md")));
    }

    @Test void successfulAiSavesRecommendationsAndCompletedStatus() throws Exception {
        var options = new Main.Options(); options.ai = true;
        int exit = Main.write(report, temp, options, temp, "baseline-passed", Map.of("type", "local"),
                (r, p, m, t) -> "UNVERIFIED: check the boundary.");
        assertEquals(0, exit);
        assertTrue(Files.exists(temp.resolve("recommendations.md")));
        assertEquals("completed", new ObjectMapper().readTree(temp.resolve("report.json").toFile()).at("/ai/status").asText());
    }

    @Test void noFindingsExplicitlySkipsAiWithoutCallingTheProvider() throws Exception {
        var options = new Main.Options(); options.ai = true;
        var killed = new MutationReport(List.of(new MutationReport.Mutant("KILLED", true, "App.java", "App", "check", 6, "boundary", "changed boundary")));
        assertEquals(0, Main.write(killed, temp, options, temp, "baseline-passed", Map.of("type", "local"),
                (r, p, m, t) -> { fail("Provider must not be called"); return ""; }));
        assertEquals("skipped-no-findings", new ObjectMapper().readTree(temp.resolve("report.json").toFile()).at("/ai/status").asText());
    }
}
