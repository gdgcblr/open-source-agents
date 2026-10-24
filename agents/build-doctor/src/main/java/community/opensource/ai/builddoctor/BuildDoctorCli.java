package community.opensource.ai.builddoctor;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class BuildDoctorCli {
  private BuildDoctorCli() {}

  public static void main(String[] args) throws IOException {
    if (args.length < 1 || args.length > 2) {
      System.err.println("Usage: BuildDoctorCli <maven-log-file> [project-root]");
      System.exit(2);
    }

    Path logFile = Path.of(args[0]).toAbsolutePath().normalize();
    Path projectRoot = args.length == 2 ? Path.of(args[1]).toAbsolutePath().normalize() : null;
    String log = Files.readString(logFile);
    System.out.println(new BuildDoctorEngine().analyze(log, projectRoot).toText());
  }
}
