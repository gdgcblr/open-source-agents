package community.opensource.ai.builddoctor;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Set;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;

class BuildDoctorMcpIntegrationTest {
  @Test
  void startsPythonServerDiscoversToolsAndClosesTheMcpAgent() throws Exception {
    String python = System.getenv("BUILD_DOCTOR_PYTHON");
    String pythonPath = System.getenv("BUILD_DOCTOR_MCP_PYTHONPATH");
    Assumptions.assumeTrue(python != null && !python.isBlank(), "set BUILD_DOCTOR_PYTHON for MCP integration tests");
    Assumptions.assumeTrue(pythonPath != null && !pythonPath.isBlank(), "set BUILD_DOCTOR_MCP_PYTHONPATH for MCP integration tests");

    var agent = BuildDoctorAgent.createWithMcp(python);
    try {
      var tools = agent.toolsets().get(0).getTools(null).toList().blockingGet();
      Set<String> names = tools.stream().map(tool -> tool.name()).collect(Collectors.toSet());
      assertTrue(names.contains("analyze_failure"));
      assertTrue(names.contains("inspect_project"));
      assertTrue(names.contains("verify_resolution"));
    } finally {
      agent.close().blockingAwait();
    }
  }
}
