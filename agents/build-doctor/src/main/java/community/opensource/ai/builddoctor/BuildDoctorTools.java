package community.opensource.ai.builddoctor;

import com.google.adk.tools.FunctionTool;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.regex.Pattern;

public final class BuildDoctorTools {
  private static final int MAX_INPUT_CHARS = 200_000;
  private static final int MAX_OUTPUT_CHARS = 200_000;
  private static final Pattern BEARER_PATTERN =
      Pattern.compile("(?i)(authorization\\s*:\\s*bearer\\s+)[^\\s,;]+");
  private static final Pattern SECRET_PATTERN =
      Pattern.compile("(?i)([\\\"']?(?:api[_-]?key|token|password|secret|client_secret)[\\\"']?\\s*[:=]\\s*[\\\"']?)[^\\\"'\\s,;}]+");
  private static final Pattern PRIVATE_KEY_PATTERN =
      Pattern.compile("(?i)(-----BEGIN [A-Z ]+ PRIVATE KEY-----).*?(-----END [A-Z ]+ PRIVATE KEY-----)", Pattern.DOTALL);
  private static final Pattern PROMPT_INJECTION_PATTERN =
      Pattern.compile("(?i)(ignore (?:all )?previous instructions|system message:|you are now |reveal (?:the )?secret)");

  private BuildDoctorTools() {}

  public static FunctionTool analyzeBuildLogTool() {
    return FunctionTool.create(BuildDoctorTools.class, "analyzeBuildLog");
  }

  public static FunctionTool inspectProjectTool() {
    return FunctionTool.create(BuildDoctorTools.class, "inspectProject");
  }

  public static String analyzeBuildLog(String log, String projectRoot) throws IOException {
    if (!isToolAllowed("analyzeBuildLog")) {
      throw new IOException("tool 'analyzeBuildLog' is disabled by BUILD_DOCTOR_ALLOWED_TOOLS");
    }
    String boundedLog = redact(log == null ? "" : log.substring(0, Math.min(log.length(), MAX_INPUT_CHARS)));
    Path root = projectRoot == null || projectRoot.isBlank() ? null : safeRoot(projectRoot);
    return new BuildDoctorEngine().analyze(boundedLog, root).toText();
  }

  public static String inspectProject(String projectRoot) throws IOException {
    if (!isToolAllowed("inspectProject")) {
      throw new IOException("tool 'inspectProject' is disabled by BUILD_DOCTOR_ALLOWED_TOOLS");
    }
    if (projectRoot == null || projectRoot.isBlank()) {
      return "Project evidence: no project root was provided.";
    }
    Path root = safeRoot(projectRoot);
    List<String> manifests = List.of(
        "pom.xml", "build.gradle", "build.gradle.kts", "package.json", "pyproject.toml",
        "requirements.txt", "go.mod", "Cargo.toml", "composer.json", "mix.exs");
    StringBuilder result = new StringBuilder("Project manifests and selected metadata:\n");
    boolean found = false;
    for (String manifest : manifests) {
      Path file = root.resolve(manifest);
      if (Files.isRegularFile(file) && !Files.isSymbolicLink(file)) {
        found = true;
        result.append("\n--- ").append(manifest).append(" ---\n");
        for (String line : Files.readAllLines(file).stream().limit(20).toList()) {
          result.append(redact(line)).append('\n');
          if (result.length() >= MAX_OUTPUT_CHARS) {
            result.append("[output truncated by BuildDoctor guardrail]\n");
            return result.toString();
          }
        }
      }
    }
    return found ? result.toString() : "Project evidence: no supported manifest was found at the selected project root.";
  }

  private static boolean isToolAllowed(String name) {
    String allowed = System.getenv("BUILD_DOCTOR_ALLOWED_TOOLS");
    if (allowed == null || allowed.isBlank()) {
      return true;
    }
    for (String item : allowed.split(",")) {
      if (item.trim().equalsIgnoreCase(name)) {
        return true;
      }
    }
    return false;
  }

  private static Path safeRoot(String projectRoot) throws IOException {
    if (projectRoot == null || projectRoot.isBlank()) {
      throw new IOException("invalid project root");
    }
    try {
      Path requested = Path.of(projectRoot);
      if (Files.isSymbolicLink(requested)) {
        throw new IOException("project root symlinks are not permitted");
      }
      Path root = requested.toAbsolutePath().normalize();
      if (!Files.isDirectory(root)) {
        throw new IOException("project root is not an existing directory");
      }
      String allowedValue = System.getenv("BUILD_DOCTOR_ALLOWED_ROOT");
      boolean requireAllowed = "true".equalsIgnoreCase(System.getenv("BUILD_DOCTOR_REQUIRE_ALLOWED_ROOT"));
      if (requireAllowed && (allowedValue == null || allowedValue.isBlank())) {
        throw new IOException("BUILD_DOCTOR_ALLOWED_ROOT is required");
      }
      if (allowedValue != null && !allowedValue.isBlank()) {
        Path allowed = Path.of(allowedValue).toAbsolutePath().normalize();
        if (!root.startsWith(allowed)) {
          throw new IOException("project root is outside BUILD_DOCTOR_ALLOWED_ROOT");
        }
      }
      return root;
    } catch (IllegalArgumentException exception) {
      throw new IOException("invalid project root", exception);
    }
  }

  private static String redact(String value) {
    if (value == null) {
      return "";
    }
    String result = BEARER_PATTERN.matcher(value).replaceAll("$1[REDACTED]");
    result = SECRET_PATTERN.matcher(result).replaceAll("$1=[REDACTED]");
    result = PRIVATE_KEY_PATTERN.matcher(result).replaceAll("$1[REDACTED]$2");
    return PROMPT_INJECTION_PATTERN.matcher(result).replaceAll("[UNTRUSTED_TEXT]");
  }
}
