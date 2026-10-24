package community.opensource.ai.builddoctor;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Set;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;

class BuildDoctorMcpIntegrationTest {
  @Test
  void startsPythonServerDiscoversToolsAndInvokesAnalyzeFailure() throws Exception {
    String python = resolvePython();
    Assumptions.assumeTrue(python != null && !python.isBlank(), "set BUILD_DOCTOR_PYTHON for MCP integration tests");

    var agent = BuildDoctorAgent.createWithMcp(python);
    try {
      var tools = agent.toolsets().get(0).getTools(null).toList().blockingGet();
      Set<String> names = tools.stream().map(tool -> tool.name()).collect(Collectors.toSet());
      assertTrue(names.contains("analyze_failure"));
      assertTrue(names.contains("inspect_project"));
      assertTrue(names.contains("verify_resolution"));

      var analyzeTool = tools.stream().filter(t -> t.name().equals("analyze_failure")).findFirst().orElseThrow();
      var result = analyzeTool.runAsync(java.util.Map.of("log", "error: cannot find symbol"), null).blockingGet();
      assertTrue(result != null);
      assertTrue(result.toString().contains("compilation"));
      assertTrue(result.toString().contains("1.1"));
    } finally {
      agent.close().blockingAwait();
    }
  }

  @Test
  void invokesInspectProjectAndVerifyResolutionOverMcp() throws Exception {
    String python = resolvePython();
    Assumptions.assumeTrue(python != null && !python.isBlank(), "set BUILD_DOCTOR_PYTHON for MCP integration tests");

    var agent = BuildDoctorAgent.createWithMcp(python);
    try {
      var tools = agent.toolsets().get(0).getTools(null).toList().blockingGet();
      var verifyTool = tools.stream().filter(t -> t.name().equals("verify_resolution")).findFirst().orElseThrow();
      var verifyResult = verifyTool.runAsync(
          java.util.Map.of(
              "before_log", "error: cannot find symbol",
              "after_log", "build success\ntests passed"),
          null).blockingGet();
      assertTrue(verifyResult != null);
      assertTrue(verifyResult.toString().contains("verified"));
    } finally {
      agent.close().blockingAwait();
    }
  }

  private static String resolvePython() {
    String python = System.getenv("BUILD_DOCTOR_PYTHON");
    if (python == null || python.isBlank()) {
      java.nio.file.Path venv = java.nio.file.Path.of("../../tools/build-doctor-mcp/.venv/bin/python").toAbsolutePath().normalize();
      if (java.nio.file.Files.isExecutable(venv)) {
        return venv.toString();
      }
    }
    return python;
  }
}
