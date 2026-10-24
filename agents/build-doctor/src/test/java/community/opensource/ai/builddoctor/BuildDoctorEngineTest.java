package community.opensource.ai.builddoctor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;

class BuildDoctorEngineTest {
  private final BuildDoctorEngine engine = new BuildDoctorEngine();

  @Test
  void identifiesCompilationFailuresAndKeepsVerificationPending() throws Exception {
    Path project = Files.createTempDirectory("build-doctor");
    Files.writeString(project.resolve("pom.xml"), "<project/>");

    DiagnosticReport report = engine.analyze(
        "[ERROR] COMPILATION ERROR\n[ERROR] cannot find symbol\n", project);

    assertEquals("compilation", report.failureType());
    assertTrue(report.evidence().stream().anyMatch(item -> item.contains("cannot find symbol")));
    assertTrue(report.verificationStatus().startsWith("pending:"));
  }

  @Test
  void identifiesDependencyResolutionFailures() {
    DiagnosticReport report = engine.analyze(
        "[ERROR] Failed to execute goal\n[ERROR] Could not resolve dependencies for project\n", null);

    assertEquals("dependency-resolution", report.failureType());
    assertEquals("high", report.confidence());
  }

  @Test
  void identifiesFailedTests() {
    DiagnosticReport report = engine.analyze(
        "[ERROR] Tests run: 8, Failures: 1, Errors: 0, Skipped: 0\n", null);

    assertEquals("test-failure", report.failureType());
    assertTrue(report.toText().contains("Verification: pending:"));
  }

  @Test
  void avoidsGuessingWhenEvidenceIsInsufficient() {
    DiagnosticReport report = engine.analyze("BUILD FAILURE\n", null);

    assertEquals("unknown", report.failureType());
    assertEquals("low", report.confidence());
  }
}
