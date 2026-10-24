package community.opensource.ai.builddoctor;

import com.google.adk.agents.LlmAgent;
import java.util.List;
import java.util.stream.Collectors;

/**
 * Minimal process entry point for validating the ADK-to-MCP connection without calling a model.
 */
public final class BuildDoctorApplication {
  private BuildDoctorApplication() {}

  public static void main(String[] args) {
    String python = System.getenv().getOrDefault("BUILD_DOCTOR_PYTHON", "python");
    LlmAgent agent = BuildDoctorAgent.createWithMcp(python);
    try {
      List<String> toolNames = agent.toolsets().get(0).getTools(null).toList().blockingGet().stream()
          .map(tool -> tool.name())
          .sorted()
          .collect(Collectors.toList());
      System.out.println("BuildDoctor MCP connection ready");
      System.out.println("Discovered tools: " + String.join(", ", toolNames));
    } catch (RuntimeException exception) {
      System.err.println("BuildDoctor MCP connection failed: " + exception.getMessage());
      throw exception;
    } finally {
      agent.close().blockingAwait();
    }
  }
}
