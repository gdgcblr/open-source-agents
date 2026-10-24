package dev.mutationaudit;

import java.io.IOException;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.TimeUnit;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;

/** Fixed Maven commands, no model-controlled command execution. Copies are not a security sandbox. */
final class ProjectRunner {
    static final String PIT_VERSION = "1.30.1";
    private static final Set<String> EXCLUDED = Set.of(".git", "target", "build", ".gradle", ".idea", ".vscode", "node_modules", "mutation-audit");

    static Path analyze(Path project, Path output, String maven, Duration timeout) throws Exception {
        project = project.toRealPath();
        if (!Files.isRegularFile(project.resolve("pom.xml")))
            throw new IllegalArgumentException("Expected a Maven project containing pom.xml.");
        validatePom(project.resolve("pom.xml"));
        Path temporary = Files.createTempDirectory("mutation-auditor-");
        try {
            copyProject(project, temporary, output);
            System.out.println("Running baseline tests in a temporary project copy...");
            run(List.of(maven, "-B", "-ntp", "clean", "test", "-DskipTests=false", "-Dmaven.test.skip=false", "-DfailIfNoTests=true"),
                    temporary, output.resolve("baseline.log"), timeout);
            requireTestsRan(temporary);
            System.out.println("Preparing PIT " + PIT_VERSION + " and its JUnit 5 adapter in the temporary copy...");
            Path analysisPom = PitBootstrap.prepare(temporary);
            System.out.println("Running PIT mutation analysis...");
            run(List.of(maven, "-B", "-ntp", "-f", analysisPom.toString(), "test-compile", "org.pitest:pitest-maven:" + PIT_VERSION + ":mutationCoverage",
                            "-DoutputFormats=XML,HTML", "-DtimestampedReports=false", "-DreportsDirectory=" + temporary.resolve("target/auditor-pit"),
                            "-DmutationThreshold=0", "-DcoverageThreshold=0", "-DtestStrengthThreshold=0"),
                    temporary, output.resolve("pit.log"), timeout);
            Path xml = temporary.resolve("target/auditor-pit/mutations.xml");
            if (!Files.isRegularFile(xml)) throw new IOException("PIT did not produce mutations.xml. Check " + output.resolve("pit.log"));
            Files.copy(xml, output.resolve("mutations.xml"));
            return output.resolve("mutations.xml");
        } finally {
            deleteTree(temporary);
        }
    }

    static void validatePom(Path pom) throws Exception {
        var factory = DocumentBuilderFactory.newInstance();
        factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        var doc = factory.newDocumentBuilder().parse(pom.toFile());
        if (doc.getElementsByTagName("modules").getLength() > 0)
            throw new IllegalArgumentException("Multi-module projects are not supported yet; select a standalone module.");
        if (doc.getElementsByTagName("parent").getLength() > 0) {
            var parents = doc.getElementsByTagName("relativePath");
            // External parents from Maven repositories are allowed; local relative parents cannot be copied reliably.
            if (parents.getLength() == 0 || !parents.item(0).getTextContent().isBlank())
                throw new IllegalArgumentException("Local/default parent paths are unsupported. For a repository-resolved parent, use <relativePath/>.");
        }
    }

    static void requireTestsRan(Path project) throws Exception {
        requireTestsAt(project.resolve("target/surefire-reports"));
    }

    static void requireTestsAt(Path reports) throws Exception {
        long executed = 0;
        if (Files.isDirectory(reports)) {
            try (var files = Files.list(reports)) {
                for (Path file : files.filter(p -> p.getFileName().toString().startsWith("TEST-")
                        && p.toString().endsWith(".xml")).toList()) {
                    var factory = DocumentBuilderFactory.newInstance();
                    factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
                    factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
                    factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
                    var suite = factory.newDocumentBuilder().parse(file.toFile()).getDocumentElement();
                    if (!suite.getTagName().equals("testsuite")) throw new IOException("Unsupported Surefire report format.");
                    long tests = Long.parseLong(suite.getAttribute("tests"));
                    long skipped = Long.parseLong(suite.getAttribute("skipped"));
                    long failures = Long.parseLong(suite.getAttribute("failures"));
                    long errors = Long.parseLong(suite.getAttribute("errors"));
                    if (failures > 0 || errors > 0) throw new IOException("Baseline reports contain failed tests.");
                    executed += tests - skipped;
                }
            }
        }
        if (executed <= 0) throw new IOException("No executed baseline tests found in " + reports + ". "
                + "Enable test XML reports and ensure tests are not skipped. See baseline.log.");
    }

    static void copyProject(Path source, Path destination, Path output) throws IOException {
        Path excludedOutput = output.toAbsolutePath().normalize();
        Files.walkFileTree(source, new SimpleFileVisitor<>() {
            @Override public FileVisitResult preVisitDirectory(Path dir, BasicFileAttributes attrs) throws IOException {
                if (!dir.equals(source) && (EXCLUDED.contains(dir.getFileName().toString()) || dir.equals(excludedOutput)))
                    return FileVisitResult.SKIP_SUBTREE;
                Files.createDirectories(destination.resolve(source.relativize(dir)));
                return FileVisitResult.CONTINUE;
            }
            @Override public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) throws IOException {
                if (attrs.isSymbolicLink()) throw new IOException("Project contains a symlink; remove it or use report mode: " + file);
                if (attrs.isRegularFile()) Files.copy(file, destination.resolve(source.relativize(file)), StandardCopyOption.COPY_ATTRIBUTES);
                return FileVisitResult.CONTINUE;
            }
        });
    }

    static void run(List<String> command, Path project, Path log, Duration timeout) throws Exception {
        runCommand(command, project, log, timeout, false);
    }

    static final class CommandFailed extends IOException {
        CommandFailed(int code, Path log) { super("Command exited with " + code + ". Log: " + log); }
    }

    static void sanitizeBuildEnvironment(Map<String, String> environment) {
        for (String key : List.of("GOOGLE_API_KEY", "GEMINI_API_KEY", "GH_TOKEN", "GITHUB_TOKEN",
                "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN")) environment.remove(key);
    }

    static void runCommand(List<String> command, Path project, Path log, Duration timeout, boolean git) throws Exception {
        var builder = new ProcessBuilder(command).directory(project.toFile()).redirectErrorStream(true).redirectOutput(log.toFile());
        if (git) {
            builder.environment().remove("GOOGLE_API_KEY");
            builder.environment().remove("GEMINI_API_KEY");
            builder.environment().put("GIT_TERMINAL_PROMPT", "0");
            builder.environment().put("GCM_INTERACTIVE", "Never");
            builder.environment().put("GIT_LFS_SKIP_SMUDGE", "1");
        } else {
            sanitizeBuildEnvironment(builder.environment());
        }
        Process process;
        try { process = builder.start(); }
        catch (IOException e) { throw new IOException(git ? "Cannot start Git. Install Git and add it to PATH."
                : "Cannot start the build command. Check the selected Maven/Gradle executable and Java installation.", e); }
        try {
            if (!process.waitFor(timeout.toSeconds(), TimeUnit.SECONDS)) {
                stop(process);
                throw new IOException("Command exceeded " + timeout.toSeconds() + " seconds. Log: " + log);
            }
            if (process.exitValue() != 0) throw new CommandFailed(process.exitValue(), log);
        } catch (InterruptedException e) {
            stop(process);
            Thread.currentThread().interrupt();
            throw e;
        }
    }

    static void stop(Process process) throws InterruptedException {
        try {
            process.descendants().forEach(ProcessHandle::destroyForcibly);
        } catch (RuntimeException restrictedProcessAccess) {
            System.err.println("Could not enumerate child processes; stopping the command directly. Child cleanup is best effort.");
        } finally {
            process.destroyForcibly();
        }
        process.waitFor(10, TimeUnit.SECONDS);
    }

    static void deleteTree(Path root) throws IOException {
        Files.walkFileTree(root, new SimpleFileVisitor<>() {
            @Override public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) throws IOException {
                Files.delete(file); return FileVisitResult.CONTINUE;
            }
            @Override public FileVisitResult postVisitDirectory(Path dir, IOException error) throws IOException {
                if (error != null) throw error;
                Files.delete(dir); return FileVisitResult.CONTINUE;
            }
        });
    }
}
