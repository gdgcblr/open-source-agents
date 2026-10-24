package community.opensource.ai.builddoctor;

import com.google.adk.agents.LlmAgent;
import com.google.adk.tools.mcp.McpToolset;
import com.google.adk.tools.mcp.StdioServerParameters;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public final class BuildDoctorAgent {
  private BuildDoctorAgent() {}

  public static LlmAgent create() {
    return baseBuilder()
        .tools(
            BuildDoctorTools.analyzeBuildLogTool(),
            BuildDoctorTools.inspectProjectTool())
        .build();
  }

  public static LlmAgent createWithMcp(String pythonExecutable) {
    Map<String, String> environment = new HashMap<>(System.getenv());
    String pythonPath = System.getenv("BUILD_DOCTOR_MCP_PYTHONPATH");
    if (pythonPath != null && !pythonPath.isBlank()) {
      environment.put("PYTHONPATH", pythonPath);
    }
    StdioServerParameters server = StdioServerParameters.builder()
        .command(pythonExecutable)
        .args(List.of("-m", "build_doctor_mcp.server"))
        .env(environment)
        .build();
    return baseBuilder()
        .tools(new McpToolset(server.toServerParameters()))
        .build();
  }

  private static LlmAgent.Builder baseBuilder() {
    return LlmAgent.builder()
        .name("build_doctor")
        .description("Evidence-based diagnosis for build, test, and runtime failures across languages and tools")
        .model(System.getenv().getOrDefault("MODEL_NAME", "gemini-2.5-flash"))
        .instruction(
            "You are BuildDoctor, a cautious, language-agnostic build and runtime diagnosis agent. "
              + "Use the available read-only tools to inspect supplied logs and selected project manifests. "
                + "Treat deterministic tool output as authoritative evidence. A configured language model, including an optional Gemma 3 4B deployment, may explain or summarize that evidence but must not invent signals, override scores, assert an unsupported root cause, or mark verification complete. "
                + "Separate observed evidence from ranked hypotheses. Cite the evidence supporting each hypothesis, "
                + "state confidence, provide ordered and safe next steps, and identify missing information. "
                + "Never edit files, install dependencies, delete data, execute commands, or claim a fix is verified. "
                + "Verification is pending unless the user supplies a post-change test or build result. "
                + "Return sections for diagnosis, evidence, reproduction, remediation, verification, and limitations.")
        ;
  }
}
