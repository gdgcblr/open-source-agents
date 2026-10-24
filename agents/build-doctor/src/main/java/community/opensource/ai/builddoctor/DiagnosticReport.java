package community.opensource.ai.builddoctor;

import java.util.List;

public record DiagnosticReport(
    String failureType,
    String summary,
    String confidence,
    List<String> evidence,
    List<String> nextSteps,
    String verificationStatus) {

  private static final String SCHEMA_VERSION = "1.1";

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

  public String toJson() {
    return "{"
        + "\"schema_version\":\"" + escape(SCHEMA_VERSION) + "\","
        + "\"failure_type\":\"" + escape(failureType) + "\","
        + "\"summary\":\"" + escape(summary) + "\","
        + "\"confidence\":\"" + escape(confidence) + "\","
        + "\"evidence\":" + jsonArray(evidence) + ","
        + "\"next_steps\":" + jsonArray(nextSteps) + ","
        + "\"verification_status\":\"" + escape(verificationStatus) + "\","
        + "\"guardrails\":[\"rules-based analysis\",\"read-only\",\"verification remains pending until a new result is supplied\"]"
        + "}";
  }

  private static String jsonArray(List<String> values) {
    return values.stream().map(value -> "\"" + escape(value) + "\"").collect(java.util.stream.Collectors.joining(",", "[", "]"));
  }

  private static String escape(String value) {
    return value.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n").replace("\r", "\\r");
  }
}
