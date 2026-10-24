package dev.mutationaudit;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import picocli.CommandLine;
import java.nio.file.*;
import static org.junit.jupiter.api.Assertions.*;

class CliTest {
    @TempDir Path temp;

    @Test void importsRealPitReportWithoutMavenOrModelAccess() throws Exception {
        Path output = temp.resolve("output");
        int exit = new CommandLine(new Main()).execute("report", "--xml", "examples/discount-service/example-mutations.xml",
                "--output", output.toString());
        assertEquals(0, exit);
        try (var files = Files.list(output)) {
            Path run = files.findFirst().orElseThrow();
            var json = new ObjectMapper().readTree(run.resolve("report.json").toFile());
            assertEquals(3, json.get("totalMutants").asInt());
            assertEquals(66.66666666666667, json.get("mutationScore").asDouble(), 0.0001);
            assertEquals("not-verified-imported-report", json.get("baseline").asText());
            assertTrue(Files.exists(run.resolve("report.md")));
            assertFalse(Files.exists(run.resolve("recommendations.md")));
        }
    }

    @Test void rejectsInvalidCommandSyntax() {
        assertEquals(2, new CommandLine(new Main()).execute("analyze"));
        assertEquals(2, new CommandLine(new Main()).execute("report", "--unknown"));
        assertEquals(2, new CommandLine(new Main()).execute("analyze", "--repo", "https://github.com/example/demo", "--project", "."));
    }

    @Test void localModeRejectsRemoteOnlyFlagsWithoutExecutingAProject() {
        var command = new CommandLine(new Main());
        command.setExecutionExceptionHandler((exception, cmd, result) -> {
            assertTrue(exception.getMessage().contains("require --repo"));
            return 1;
        });
        assertEquals(1, command.execute("analyze", "--project", ".", "--ref", "main"));
    }

    @Test void directInputAndAdvancedSyntaxNormalizeToTheSameAnalysisCommand() {
        assertArrayEquals(new String[]{"analyze", "--project", "some folder", "--ai"}, Main.normalizeArguments("some folder", "--ai"));
        assertArrayEquals(new String[]{"analyze", "--repo", "https://github.com/example/demo"}, Main.normalizeArguments("https://github.com/example/demo"));
        assertArrayEquals(new String[]{"analyze", "--project", "pom.xml"}, Main.normalizeArguments("analyze", "pom.xml"));
        assertArrayEquals(new String[]{"analyze", "--project", "."}, Main.normalizeArguments());
        assertArrayEquals(new String[]{"analyze", "--project", ".", "--ai"}, Main.normalizeArguments("--ai"));
        assertArrayEquals(new String[]{"analyze", "--repo", "https://github.com/example/demo"}, Main.normalizeArguments("--repo", "https://github.com/example/demo"));
    }

    @Test void helpAndReportCommandsRemainAvailableWithoutProjectDetection() {
        assertArrayEquals(new String[]{"--help"}, Main.normalizeArguments("--help"));
        assertArrayEquals(new String[]{"report", "--xml", "results.xml"}, Main.normalizeArguments("report", "--xml", "results.xml"));
        assertArrayEquals(new String[]{"auth"}, Main.normalizeArguments("auth"));
        assertEquals(0, Main.execute("--help"));
    }
}
