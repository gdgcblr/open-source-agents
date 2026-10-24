package dev.mutationaudit;

import java.io.*;
import java.net.URI;
import java.net.http.*;
import java.nio.file.*;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.*;
import java.util.zip.ZipInputStream;

/** Uses a project's wrapper, or downloads a checksum-pinned Gradle distribution for wrapperless projects. */
final class GradleRuntime {
    static final String VERSION = "9.1.0";
    static final String SHA256 = "a17ddd85a26b6a7f5ddb71ff8b05fc5104c0202c6e64782429790c933686c806";

    static List<String> command(Path project, String override, Duration timeout) throws Exception {
        if (override != null) return List.of(override);
        if (Files.isRegularFile(project.resolve("gradlew"))) {
            Path properties = project.resolve("gradle/wrapper/gradle-wrapper.properties");
            if (Files.isRegularFile(properties)) {
                var props = new Properties();
                try (var input = Files.newInputStream(properties)) { props.load(input); }
                var version = java.util.regex.Pattern.compile("gradle-(\\d+)\\.(\\d+)").matcher(props.getProperty("distributionUrl", ""));
                if (version.find() && (Integer.parseInt(version.group(1)) < 8
                        || Integer.parseInt(version.group(1)) == 8 && Integer.parseInt(version.group(2)) < 4))
                    throw new IOException("Gradle mutation testing requires Gradle 8.4+. This project's wrapper uses "
                            + version.group(1) + "." + version.group(2) + ". Upgrade it with a compatible JDK before analysis.");
            }
            return List.of("/bin/sh", project.resolve("gradlew").toString());
        }
        Path cache = Path.of(System.getenv().getOrDefault("MUTATION_AUDITOR_TOOLS",
                Path.of(System.getProperty("user.home"), ".cache", "mutation-auditor").toString()));
        return List.of(install(cache, timeout).toString());
    }

    static Path install(Path cache, Duration timeout) throws Exception {
        Path binary = cache.resolve("gradle-" + VERSION + "/bin/gradle").toAbsolutePath();
        if (Files.isExecutable(binary)) return binary;
        Files.createDirectories(cache);
        Path staging = Files.createTempDirectory(cache, "gradle-download-");
        try {
            System.out.println("Preparing Gradle " + VERSION + " (first run only)...");
            Path zip = staging.resolve("gradle.zip");
            var client = HttpClient.newBuilder().followRedirects(HttpClient.Redirect.NORMAL).connectTimeout(Duration.ofSeconds(30)).build();
            var response = client.send(HttpRequest.newBuilder(URI.create("https://downloads.gradle.org/distributions/gradle-" + VERSION + "-bin.zip"))
                    .timeout(timeout).build(), HttpResponse.BodyHandlers.ofFile(zip));
            if (response.statusCode() != 200) throw new IOException("Could not download Gradle: HTTP " + response.statusCode());
            var digest = MessageDigest.getInstance("SHA-256");
            try (var input = Files.newInputStream(zip)) {
                byte[] bytes = new byte[65536];
                for (int n; (n = input.read(bytes)) != -1;) digest.update(bytes, 0, n);
            }
            if (!HexFormat.of().formatHex(digest.digest()).equals(SHA256)) throw new IOException("Gradle checksum validation failed.");
            extract(zip, staging);
            Path destination = binary.getParent().getParent();
            try { Files.move(staging.resolve("gradle-" + VERSION), destination); }
            catch (FileAlreadyExistsException anotherDownload) { /* A concurrent installation completed. */ }
            if (!binary.toFile().setExecutable(true) || !Files.isExecutable(binary)) throw new IOException("Cannot make the Gradle launcher executable.");
            return binary;
        } finally { ProjectRunner.deleteTree(staging); }
    }

    static void extract(Path zip, Path destination) throws IOException {
        Path base = destination.toAbsolutePath().normalize();
        try (var input = new ZipInputStream(Files.newInputStream(zip))) {
            for (var entry = input.getNextEntry(); entry != null; entry = input.getNextEntry()) {
                Path file = base.resolve(entry.getName()).normalize();
                if (!file.startsWith(base)) throw new IOException("Archive entry escapes extraction directory.");
                if (entry.isDirectory()) Files.createDirectories(file);
                else { Files.createDirectories(file.getParent()); Files.copy(input, file); }
            }
        }
    }
}
