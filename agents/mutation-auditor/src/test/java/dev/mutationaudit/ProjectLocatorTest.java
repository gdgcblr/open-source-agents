package dev.mutationaudit;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.*;
import static org.junit.jupiter.api.Assertions.*;

class ProjectLocatorTest {
    @TempDir Path temp;

    private Path project(String name) throws Exception {
        Path folder = Files.createDirectories(temp.resolve(name));
        Files.writeString(folder.resolve("pom.xml"), "<project/>");
        return folder;
    }

    @Test void acceptsAProjectFolderOrItsPom() throws Exception {
        Path project = project("service");
        assertEquals(project.toRealPath(), ProjectLocator.find(project));
        assertEquals(project.toRealPath(), ProjectLocator.find(project.resolve("pom.xml")));
    }

    @Test void findsOneNestedProjectAndIgnoresBuildFoldersAndSymlinks() throws Exception {
        Path expected = project("services/discount");
        project("target/generated");
        project("node_modules/example");
        Files.createSymbolicLink(temp.resolve("duplicate-link"), expected);
        assertEquals(expected.toRealPath(), ProjectLocator.find(temp));
    }

    @Test void neverGuessesBetweenMultipleProjects() throws Exception {
        project("one"); project("two");
        var error = assertThrows(Exception.class, () -> ProjectLocator.find(temp));
        assertTrue(error.getMessage().contains("one"));
        assertTrue(error.getMessage().contains("two"));
        assertTrue(error.getMessage().contains("--subdir"));
    }

    @Test void explainsWhenNoMavenProjectIsFound() {
        var error = assertThrows(Exception.class, () -> ProjectLocator.find(temp));
        assertTrue(error.getMessage().contains("No Maven or Gradle project"));
    }

    @Test void detectsGroovyAndKotlinGradleBuilds() throws Exception {
        Path groovy = Files.createDirectories(temp.resolve("groovy"));
        Files.writeString(groovy.resolve("build.gradle"), "plugins { id 'java' }");
        assertEquals(groovy.toRealPath(), ProjectLocator.find(groovy));
        assertEquals(groovy.toRealPath(), ProjectLocator.find(groovy.resolve("build.gradle")));
        Path kotlin = Files.createDirectories(temp.resolve("kotlin"));
        Files.writeString(kotlin.resolve("build.gradle.kts"), "plugins { java }");
        assertEquals(kotlin.toRealPath(), ProjectLocator.find(kotlin.resolve("build.gradle.kts")));
        assertTrue(ProjectLocator.gradle(kotlin));
    }
}
