package community.opensource.ai.builddoctor;

import com.google.adk.tools.FunctionTool;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public final class BuildDoctorTools {
  private BuildDoctorTools() {}

  public static FunctionTool analyzeBuildLogTool() {
    return FunctionTool.create(BuildDoctorTools.class, "analyzeBuildLog");
  }

  public static FunctionTool inspectProjectTool() {
    return FunctionTool.create(BuildDoctorTools.class, "inspectProject");
  }

  public static String analyzeBuildLog(String log, String projectRoot) {
    Path root = projectRoot == null || projectRoot.isBlank() ? null : Path.of(projectRoot).toAbsolutePath().normalize();
    return new BuildDoctorEngine().analyze(log, root).toText();
  }

  public static String inspectProject(String projectRoot) throws IOException {
    Path root = Path.of(projectRoot).toAbsolutePath().normalize();
    Path pom = root.resolve("pom.xml");
    if (!Files.isRegularFile(pom)) {
      return "Project evidence: no pom.xml was found at the selected project root.";
    }

    List<String> relevantLines = Files.readAllLines(pom).stream()
        .filter(line -> line.contains("<groupId>") || line.contains("<artifactId>") || line.contains("<version>"))
        .limit(20)
        .toList();
    return "Project evidence from pom.xml:\n" + String.join("\n", relevantLines);
  }
}
