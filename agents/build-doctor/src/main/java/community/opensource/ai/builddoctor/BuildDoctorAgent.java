package community.opensource.ai.builddoctor;

import com.google.adk.agents.LlmAgent;

public final class BuildDoctorAgent {
  private BuildDoctorAgent() {}

  public static LlmAgent create() {
    return LlmAgent.builder()
        .name("build_doctor")
        .description("Evidence-based diagnosis for build, test, and runtime failures across languages and tools")
        .model(System.getenv().getOrDefault("MODEL_NAME", "gemini-2.5-flash"))
        .instruction(
            "You are BuildDoctor, a cautious, language-agnostic build and runtime diagnosis agent. "
              + "Use the available read-only tools to inspect supplied logs and selected project manifests. "
                + "Separate observed evidence from ranked hypotheses. Cite the evidence supporting each hypothesis, "
                + "state confidence, provide ordered and safe next steps, and identify missing information. "
                + "Never edit files, install dependencies, delete data, execute commands, or claim a fix is verified. "
                + "Verification is pending unless the user supplies a post-change test or build result. "
                + "Return sections for diagnosis, evidence, reproduction, remediation, verification, and limitations.")
        .tools(
            BuildDoctorTools.analyzeBuildLogTool(),
            BuildDoctorTools.inspectProjectTool())
        .build();
  }
}
