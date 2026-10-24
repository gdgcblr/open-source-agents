package dev.mutationaudit;

import java.io.IOException;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.*;

/** Selects an unambiguous Java build without following symlinks or guessing between projects. */
final class ProjectLocator {
    static boolean gradle(Path dir) { return Files.isRegularFile(dir.resolve("build.gradle")) || Files.isRegularFile(dir.resolve("build.gradle.kts")); }
    private static boolean build(Path dir) { return Files.isRegularFile(dir.resolve("pom.xml")) || gradle(dir); }
    static Path find(Path input) throws IOException {
        Path root = input.toRealPath();
        if (Files.isRegularFile(root) && Set.of("pom.xml", "build.gradle", "build.gradle.kts").contains(root.getFileName().toString())) return root.getParent();
        if (!Files.isDirectory(root)) throw new IOException("Provide a project folder or its Maven/Gradle build file.");
        if (build(root)) return root;
        var matches = new ArrayList<Path>();
        Files.walkFileTree(root, Set.of(), 5, new SimpleFileVisitor<>() {
            @Override public FileVisitResult preVisitDirectory(Path dir, BasicFileAttributes attrs) {
                if (!dir.equals(root) && Set.of(".git", "target", "build", ".gradle", "node_modules", ".idea", "mutation-audit").contains(dir.getFileName().toString()))
                    return FileVisitResult.SKIP_SUBTREE;
                if (build(dir)) {
                    matches.add(dir);
                    return matches.size() > 20 ? FileVisitResult.TERMINATE : FileVisitResult.SKIP_SUBTREE;
                }
                return FileVisitResult.CONTINUE;
            }
        });
        if (matches.size() == 1) return matches.get(0);
        if (matches.isEmpty()) throw new IOException("No Maven or Gradle project found. Choose a Java project with pom.xml, build.gradle, or build.gradle.kts and working tests.");
        var names = matches.stream().map(root::relativize).map(Path::toString).sorted().toList();
        throw new IOException("Found multiple Java projects: " + String.join(", ", names)
                + ". Provide the specific project folder, or use --subdir for a GitHub repository.");
    }
}
