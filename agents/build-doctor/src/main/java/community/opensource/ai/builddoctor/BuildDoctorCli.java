package community.opensource.ai.builddoctor;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class BuildDoctorCli {
  private BuildDoctorCli() {}

  public static void main(String[] args) throws IOException {
    boolean json = args.length > 0 && "--json".equals(args[0]);
    int offset = json ? 1 : 0;
    if (args.length - offset < 1 || args.length - offset > 2) {
      System.err.println("Usage: BuildDoctorCli [--json] <failure-log-file> [project-root]");
      System.exit(2);
    }

    Path logFile = Path.of(args[offset]).toAbsolutePath().normalize();
    Path projectRoot = args.length - offset == 2 ? Path.of(args[offset + 1]).toAbsolutePath().normalize() : null;
    String log = Files.readString(logFile);
    DiagnosticReport report = new BuildDoctorEngine().analyze(log, projectRoot);
    System.out.println(json ? report.toJson() : report.toText());
  }
}
