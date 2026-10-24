package dev.mutationaudit;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.*;
import java.time.Duration;
import java.util.List;
import java.util.HashMap;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;

class ProjectRunnerTest {
    @TempDir Path temp;

    @Test void copyExcludesBuildArtifactsAndLeavesOriginalUntouched() throws Exception {
        Path original = Files.createDirectory(temp.resolve("original"));
        Files.createDirectories(original.resolve("target"));
        Files.writeString(original.resolve("pom.xml"), "<project/>");
        Files.writeString(original.resolve("target/stale.xml"), "stale");
        Path copy = Files.createDirectory(temp.resolve("copy"));
        ProjectRunner.copyProject(original, copy, temp.resolve("reports"));
        assertFalse(Files.exists(copy.resolve("target")));
        Files.writeString(copy.resolve("pom.xml"), "modified");
        assertEquals("<project/>", Files.readString(original.resolve("pom.xml")));
    }

    @Test void unsupportedProjectShapesFailClearly() throws Exception {
        Path pom = temp.resolve("pom.xml");
        Files.writeString(pom, "<project><modules><module>a</module></modules></project>");
        assertThrows(Exception.class, () -> ProjectRunner.validatePom(pom));
        Files.writeString(pom, "<project><parent><relativePath>../pom.xml</relativePath></parent></project>");
        assertThrows(Exception.class, () -> ProjectRunner.validatePom(pom));
        Files.writeString(pom, "<project><parent><relativePath/></parent></project>");
        assertDoesNotThrow(() -> ProjectRunner.validatePom(pom));
    }

    @Test void processFailuresAndTimeoutsCannotBecomeSuccessfulReports() throws Exception {
        Path script = temp.resolve("fake-maven.sh");
        Files.writeString(script, "#!/bin/sh\necho baseline-failed\nexit 7\n");
        var failure = assertThrows(Exception.class, () -> ProjectRunner.run(List.of("/bin/sh", script.toString()), temp,
                temp.resolve("failure.log"), Duration.ofSeconds(5)));
        assertTrue(failure.getMessage().contains("7"));
        Files.writeString(script, "#!/bin/sh\nsleep 30\n");
        var timeout = assertThrows(Exception.class, () -> ProjectRunner.run(List.of("/bin/sh", script.toString()), temp,
                temp.resolve("timeout.log"), Duration.ofSeconds(1)));
        assertTrue(timeout.getMessage().contains("exceeded"), timeout.toString());
    }

    @Test void baselineRequiresExecutedTestsEvenIfMavenExitsSuccessfully() throws Exception {
        assertThrows(Exception.class, () -> ProjectRunner.requireTestsRan(temp));
        Path reports = Files.createDirectories(temp.resolve("target/surefire-reports"));
        Path xml = reports.resolve("TEST-example.AppTest.xml");
        Files.writeString(xml, "<testsuite tests='2' skipped='2' failures='0' errors='0'/>");
        assertThrows(Exception.class, () -> ProjectRunner.requireTestsRan(temp));
        Files.writeString(xml, "<testsuite tests='2' skipped='0' failures='1' errors='0'/>");
        assertThrows(Exception.class, () -> ProjectRunner.requireTestsRan(temp));
        Files.writeString(xml, "<testsuite tests='2' skipped='0' failures='0' errors='0'/>");
        assertDoesNotThrow(() -> ProjectRunner.requireTestsRan(temp));
    }

    @Test void buildProcessesDoNotReceiveGithubOrModelTokenVariables() {
        var environment = new HashMap<>(Map.of("GH_TOKEN", "fake", "GITHUB_TOKEN", "fake", "GOOGLE_API_KEY", "fake",
                "GH_ENTERPRISE_TOKEN", "fake", "GITHUB_ENTERPRISE_TOKEN", "fake", "GEMINI_API_KEY", "fake", "PATH", "tools"));
        ProjectRunner.sanitizeBuildEnvironment(environment);
        assertEquals(Map.of("PATH", "tools"), environment);
    }
}
