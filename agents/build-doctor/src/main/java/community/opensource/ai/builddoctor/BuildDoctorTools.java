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
    List<String> manifests = List.of(
        "pom.xml", "build.gradle", "build.gradle.kts", "package.json", "pyproject.toml",
        "requirements.txt", "go.mod", "Cargo.toml", "composer.json", "mix.exs");
    StringBuilder result = new StringBuilder("Project manifests and selected metadata:\n");
    boolean found = false;
    for (String manifest : manifests) {
      Path file = root.resolve(manifest);
      if (Files.isRegularFile(file)) {
        found = true;
        result.append("\n--- ").append(manifest).append(" ---\n");
        Files.readAllLines(file).stream().limit(20).forEach(line -> result.append(line).append('\n'));
      }
    }
    return found ? result.toString() : "Project evidence: no supported manifest was found at the selected project root.";
  }
}
