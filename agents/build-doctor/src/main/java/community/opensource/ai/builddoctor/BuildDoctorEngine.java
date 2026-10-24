package community.opensource.ai.builddoctor;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Pattern;

public final class BuildDoctorEngine {
  private static final Pattern COMPILATION_ERROR =
      Pattern.compile("(?i)(compilation error|cannot find symbol|compilation failure)");
  private static final Pattern DEPENDENCY_ERROR =
      Pattern.compile("(?i)(could not resolve dependencies|could not transfer artifact|dependency resolution)");
  private static final Pattern TEST_FAILURE =
      Pattern.compile("(?i)(tests run:.*(failures|errors): [1-9]|there are test failures|assertionerror)");

  public DiagnosticReport analyze(String log, Path projectRoot) {
    if (log == null || log.isBlank()) {
      return unknownReport("No build output was provided.");
    }

    List<String> evidence = extractEvidence(log);
    if (COMPILATION_ERROR.matcher(log).find()) {
      return report(
          "compilation",
          "The build contains a Java compilation failure.",
          "high",
          evidence,
          List.of(
              "Inspect the first compiler error and its source location.",
              "Check the referenced type, import, method signature, and Java release configuration."),
          projectRoot);
    }
    if (DEPENDENCY_ERROR.matcher(log).find()) {
      return report(
          "dependency-resolution",
          "Maven could not resolve or download one or more dependencies.",
          "high",
          evidence,
          List.of(
              "Inspect the dependency coordinates and version in pom.xml.",
              "Check repository access and whether the requested version exists."),
          projectRoot);
    }
    if (TEST_FAILURE.matcher(log).find()) {
      return report(
          "test-failure",
          "The build completed far enough to run tests, but at least one test failed.",
          "moderate",
          evidence,
          List.of(
              "Run the failing test alone to isolate its assertion and setup.",
              "Inspect the test report and compare expected versus actual values.",
              "Rerun the targeted test after applying a change; verification is pending until then."),
          projectRoot);
    }

    return unknownReport("The supplied output does not match a supported Maven failure signature.");
  }

  private DiagnosticReport report(
      String failureType,
      String summary,
      String confidence,
      List<String> evidence,
      List<String> nextSteps,
      Path projectRoot) {
    List<String> enrichedEvidence = new ArrayList<>(evidence);
    if (projectRoot != null && Files.exists(projectRoot.resolve("pom.xml"))) {
      enrichedEvidence.add("Project evidence: pom.xml is present at the selected project root.");
    }
    return new DiagnosticReport(
        failureType, summary, confidence, enrichedEvidence, nextSteps, "pending: no verification run was supplied");
  }

  private List<String> extractEvidence(String log) {
    return log.lines()
        .map(String::trim)
        .filter(line -> line.startsWith("[ERROR]") || line.matches(".*Tests run:.*"))
        .limit(5)
        .toList();
  }

  private DiagnosticReport unknownReport(String summary) {
    return new DiagnosticReport(
        "unknown",
        summary,
        "low",
        List.of("No supported failure signature was confidently identified."),
        List.of("Provide the complete Maven output, including the first error and its surrounding context."),
        "pending: no verification run was supplied");
  }
}
