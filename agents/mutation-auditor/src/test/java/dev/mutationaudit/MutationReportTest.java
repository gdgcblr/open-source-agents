package dev.mutationaudit;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.*;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

class MutationReportTest {
    @TempDir Path temp;

    static String row(String status, boolean detected) {
        return "<mutation status='" + status + "' detected='" + detected + "'>"
                + "<sourceFile>Discount.java</sourceFile><mutatedClass>example.Discount</mutatedClass>"
                + "<mutatedMethod>eligible</mutatedMethod><lineNumber>6</lineNumber>"
                + "<mutator>ConditionalsBoundaryMutator</mutator><description>changed conditional boundary</description></mutation>";
    }

    private MutationReport parse(String content) throws Exception {
        Path file = temp.resolve("mutations.xml");
        Files.writeString(file, content);
        return MutationReport.read(file);
    }

    @Test void separatesCoverageGapsFromSurvivorsAndPreservesDetectionSemantics() throws Exception {
        var report = parse("<mutations>" + row("KILLED", true) + row("SURVIVED", false)
                + row("NO_COVERAGE", false) + row("TIMED_OUT", true) + "</mutations>");
        assertEquals(50.0, report.mutationScore());
        assertEquals(2, report.findings().size());
        assertEquals(List.of("SURVIVED", "NO_COVERAGE"), report.findings().stream().map(MutationReport.Mutant::status).toList());
        assertTrue(report.markdown().contains("TIMED_OUT: 1"));
    }

    @Test void emptyReportHasNoScore() throws Exception {
        assertNull(parse("<mutations/>").mutationScore());
    }

    @Test void incompleteReportCannotClaimACompletedScore() throws Exception {
        var report = parse("<mutations>" + row("KILLED", true) + row("RUN_ERROR", true) + "</mutations>");
        assertFalse(report.complete());
        assertNull(report.mutationScore());
    }

    @Test void rejectsMalformedOrUnrecognizedReports() {
        assertThrows(Exception.class, () -> parse("<notPit/>"));
        assertThrows(Exception.class, () -> parse("<mutations>" + row("NEW_UNKNOWN_STATUS", true) + "</mutations>"));
        assertThrows(Exception.class, () -> parse("<mutations>" + row("KILLED", true).replace("<lineNumber>6</lineNumber>", "") + "</mutations>"));
    }

    @Test void rejectsExternalEntities() throws Exception {
        Path secret = temp.resolve("secret.txt");
        Files.writeString(secret, "should never be read");
        String xml = "<!DOCTYPE mutations [<!ENTITY xxe SYSTEM '" + secret.toUri() + "'>]><mutations>&xxe;</mutations>";
        assertThrows(Exception.class, () -> parse(xml));
    }

    @Test void terminalSummaryShowsScoreAndActionableGapsWithoutDumpingTheReport() throws Exception {
        var report = parse("<mutations>" + row("KILLED", true) + row("SURVIVED", false) + "</mutations>");
        String summary = report.consoleSummary();
        assertTrue(summary.contains("50.0%"));
        assertTrue(summary.contains("1 caught by tests"));
        assertTrue(summary.contains("1 survived"));
        assertTrue(summary.contains("line 6"));
        assertTrue(summary.contains("report.md"));
    }
}
