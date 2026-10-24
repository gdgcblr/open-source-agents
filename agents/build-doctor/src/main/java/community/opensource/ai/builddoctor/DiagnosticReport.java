package community.opensource.ai.builddoctor;

import java.util.List;

public record DiagnosticReport(
    String failureType,
    String summary,
    String confidence,
    List<String> evidence,
    List<String> nextSteps,
    String verificationStatus) {

  public DiagnosticReport {
    evidence = List.copyOf(evidence);
    nextSteps = List.copyOf(nextSteps);
  }

  public String toText() {
    StringBuilder report = new StringBuilder();
    report.append("Failure type: ").append(failureType).append('\n');
    report.append("Summary: ").append(summary).append('\n');
    report.append("Confidence: ").append(confidence).append('\n');
    report.append("Evidence:\n");
    evidence.forEach(item -> report.append("- ").append(item).append('\n'));
    report.append("Next steps:\n");
    nextSteps.forEach(item -> report.append("- ").append(item).append('\n'));
    report.append("Verification: ").append(verificationStatus).append('\n');
    return report.toString();
  }
}
