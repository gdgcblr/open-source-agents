package dev.mutationaudit;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.*;
import java.time.Duration;
import java.util.List;
import java.util.zip.*;
import static org.junit.jupiter.api.Assertions.*;

class GradleRunnerTest {
    @TempDir Path temp;

    @Test void usesWrapperAndRejectsIncompatibleVersionsWithoutDownloadingAnything() throws Exception {
        Files.writeString(temp.resolve("gradlew"), "#!/bin/sh\n");
        Path properties = Files.createDirectories(temp.resolve("gradle/wrapper")).resolve("gradle-wrapper.properties");
        Files.writeString(properties, "distributionUrl=https://services.gradle.org/distributions/gradle-9.1.0-bin.zip");
        assertEquals(List.of("/bin/sh", temp.resolve("gradlew").toString()), GradleRuntime.command(temp, null, Duration.ofSeconds(5)));
        Files.writeString(properties, "distributionUrl=https://services.gradle.org/distributions/gradle-4.6-all.zip");
        assertThrows(Exception.class, () -> GradleRuntime.command(temp, null, Duration.ofSeconds(5)));
        assertEquals(List.of("/custom/gradle"), GradleRuntime.command(temp, "/custom/gradle", Duration.ofSeconds(5)));
    }

    @Test void archiveExtractionRejectsPathTraversal() throws Exception {
        Path zip = temp.resolve("bad.zip");
        try (var out = new ZipOutputStream(Files.newOutputStream(zip))) {
            out.putNextEntry(new ZipEntry("../escape")); out.write(1); out.closeEntry();
        }
        assertThrows(Exception.class, () -> GradleRuntime.extract(zip, temp.resolve("extract")));
        assertFalse(Files.exists(temp.resolve("escape")));
    }

    @Test void parsesGradleTestReportsAndRejectsEmptyTestRuns() throws Exception {
        Path results = Files.createDirectories(temp.resolve("build/test-results/test"));
        assertThrows(Exception.class, () -> ProjectRunner.requireTestsAt(results));
        Files.writeString(results.resolve("TEST-example.Test.xml"), "<testsuite tests='2' failures='0' errors='0' skipped='0'/>");
        assertDoesNotThrow(() -> ProjectRunner.requireTestsAt(results));
    }
}
