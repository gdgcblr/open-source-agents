package community.opensource.ai.builddoctor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class BuildDoctorAgentTest {
  @Test
  void createsAnAdkRootAgentWithReadOnlyDiagnosticTools() {
    var agent = BuildDoctorAgent.create();

    assertEquals("build_doctor", agent.name());
    assertTrue(agent.toolsUnion().size() >= 2);
    assertTrue(agent.instruction().toString().contains("Verification is pending"));
  }

  @Test
  void canConnectTheAgentToTheCompanionMcpServerOverStdio() {
    var agent = BuildDoctorAgent.createWithMcp("python3");

    assertEquals(1, agent.toolsets().size());
  }
}
