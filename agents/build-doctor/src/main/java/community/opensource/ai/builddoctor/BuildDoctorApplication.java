package community.opensource.ai.builddoctor;

import com.google.adk.agents.LlmAgent;
import com.google.adk.tools.BaseTool;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * Executable application entry point managing the full lifecycle of ADK and MCP stdio connection.
 */
public final class BuildDoctorApplication {
  private BuildDoctorApplication() {}

  public static void main(String[] args) {
    if (args.length > 0 && ("--help".equals(args[0]) || "-h".equals(args[0]))) {
      printHelp();
      return;
    }

    String python = System.getenv().getOrDefault("BUILD_DOCTOR_PYTHON", "auto");
    LlmAgent agent;
    try {
      agent = BuildDoctorAgent.createWithMcp(python);
    } catch (Exception exception) {
      System.err.println("BuildDoctor failed to initialize ADK MCP agent: " + exception.getMessage());
      System.err.println("Troubleshooting: verify that Python 3.10+ and build-doctor-mcp are installed in your environment.");
      System.exit(1);
      return;
    }

    try {
      List<BaseTool> tools = agent.toolsets().get(0).getTools(null).toList().blockingGet();
      List<String> toolNames = tools.stream().map(BaseTool::name).sorted().collect(Collectors.toList());

      if (args.length == 0 || "--check".equals(args[0])) {
        System.out.println("BuildDoctor MCP connection ready");
        System.out.println("Discovered tools (" + toolNames.size() + "): " + String.join(", ", toolNames));
        return;
      }

      if ("--diagnose".equals(args[0]) && args.length >= 2) {
        Path logFile = Path.of(args[1]).toAbsolutePath().normalize();
        if (!Files.isRegularFile(logFile)) {
          System.err.println("Log file not found: " + logFile);
          System.exit(2);
        }
        String log = Files.readString(logFile);
        String projectRoot = args.length >= 3 ? Path.of(args[2]).toAbsolutePath().normalize().toString() : "";

        BaseTool tool = tools.stream()
            .filter(t -> t.name().equals(projectRoot.isEmpty() ? "analyze_failure" : "summarize_diagnosis"))
            .findFirst()
            .orElseThrow(() -> new IllegalStateException("Required diagnostic tool not found in MCP registry"));

        Map<String, Object> input = projectRoot.isEmpty()
            ? Map.of("log", log)
            : Map.of("log", log, "project_path", projectRoot);

        Map<String, Object> response = tool.runAsync(input, null).blockingGet();
        System.out.println("Diagnostic Result:\n" + response);
        return;
      }

      printHelp();
      System.exit(2);
    } catch (IOException exception) {
      System.err.println("I/O error during execution: " + exception.getMessage());
      System.exit(1);
    } catch (RuntimeException exception) {
      System.err.println("BuildDoctor MCP connection or execution failed: " + exception.getMessage());
      System.err.println("Troubleshooting: check your BUILD_DOCTOR_PYTHON or virtual environment.");
      System.exit(1);
    } finally {
      agent.close().blockingAwait();
    }
  }

  private static void printHelp() {
    System.out.println("BuildDoctor ADK-MCP Application");
    System.out.println("Usage:");
    System.out.println("  BuildDoctorApplication [--check]                     Validate MCP stdio connection and list tools");
    System.out.println("  BuildDoctorApplication --diagnose <log-file> [root]   Run diagnosis using live MCP toolset");
    System.out.println("  BuildDoctorApplication --help                        Show this help message");
  }
}
