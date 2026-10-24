package dev.mutationaudit;

import com.google.adk.tools.FunctionTool;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.*;
import static org.junit.jupiter.api.Assertions.*;

class SourceToolsTest {
    @TempDir Path temp;

    private Path source() throws Exception {
        Path path = temp.resolve("src/main/java/example/App.java");
        Files.createDirectories(path.getParent());
        Files.writeString(path, "package example;\nclass App {}\n");
        return path;
    }

    @Test void readsNumberedSourceButRejectsSecretsAndTraversal() throws Exception {
        source();
        Files.writeString(temp.resolve(".env"), "SECRET=value");
        var tools = new SourceTools(temp);
        assertTrue(tools.readJavaFile("src/main/java/example/App.java").get("content").toString().contains("2: class App {}"));
        assertThrows(Exception.class, () -> tools.readJavaFile(".env"));
        assertThrows(Exception.class, () -> tools.readJavaFile("src/main/java/../../../.env"));
        assertThrows(Exception.class, () -> tools.readJavaFile(source().toString()));
    }

    @Test void rejectsOversizedSourceAndSymlinkEscapes() throws Exception {
        Path file = source();
        Files.writeString(file, "x".repeat(32_769));
        var tools = new SourceTools(temp);
        assertThrows(Exception.class, () -> tools.readJavaFile("src/main/java/example/App.java"));
        Path outside = temp.resolve("outside.java");
        Files.writeString(outside, "class Outside {}");
        Path link = file.resolveSibling("Link.java");
        Files.createSymbolicLink(link, outside);
        assertThrows(Exception.class, () -> tools.readJavaFile("src/main/java/example/Link.java"));
    }

    @Test void adkCanRegisterTheReadOnlyTools() throws Exception {
        var tools = new SourceTools(temp);
        assertNotNull(FunctionTool.create(tools, "listJavaFiles"));
        assertNotNull(FunctionTool.create(tools, "readJavaFile"));
    }
}
