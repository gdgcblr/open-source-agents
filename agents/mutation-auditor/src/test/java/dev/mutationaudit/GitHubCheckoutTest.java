package dev.mutationaudit;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.io.IOException;
import java.nio.file.*;
import java.time.Duration;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class GitHubCheckoutTest {
    @TempDir Path temp;
    private static final String COMMIT = "abc123" + "0".repeat(34);

    @Test void rejectsCredentialsNonGithubHostsAndNonRepositoryLinks() {
        assertEquals("https://github.com/example/demo", GitHubCheckout.normalizeUrl("https://github.com/example/demo.git/"));
        for (String url : List.of("https://token@github.com/example/demo", "http://github.com/example/demo",
                "https://github.com.evil.test/example/demo", "file:///tmp/project", "https://github.com/example/demo/tree/main",
                "https://github.com/example/demo?token=secret", "https://github.com/example/..", "https://github.com/example/%2e%2e"))
            assertThrows(IllegalArgumentException.class, () -> GitHubCheckout.normalizeUrl(url));
    }

    @Test void validatesBranchAndSubdirectoryBeforeCloning() {
        assertDoesNotThrow(() -> GitHubCheckout.validateSelection("feature/boundaries", Path.of("apps/service")));
        for (String ref : List.of("--upload-pack=bad", "main..secret", "bad ref", "bad@{ref", "main/", "x.lock"))
            assertThrows(IllegalArgumentException.class, () -> GitHubCheckout.validateSelection(ref, Path.of("")));
        assertThrows(IllegalArgumentException.class, () -> GitHubCheckout.validateSelection(null, Path.of("../outside")));
        assertThrows(IllegalArgumentException.class, () -> GitHubCheckout.validateSelection(null, temp));
    }

    @Test void publicCloneRecordsActualCommitAndLivesUntilAnalysisFinishes() throws Exception {
        List<List<String>> calls = new ArrayList<>();
        GitHubCheckout.Commands runner = (command, cwd, log, timeout) -> {
            calls.add(List.copyOf(command));
            if (command.contains("clone")) {
                Files.createDirectories(cwd.resolve("checkout/apps/service"));
            } else Files.writeString(log, COMMIT + "\n");
        };
        Path selected;
        try (var checkout = GitHubCheckout.open("https://github.com/example/demo", "release/v1", Path.of("apps/service"),
                temp, Duration.ofSeconds(5), runner)) {
            selected = checkout.project();
            assertTrue(Files.isDirectory(selected));
            assertEquals(COMMIT, checkout.provenance().get("commit"));
            assertEquals("release/v1", checkout.provenance().get("requestedRef"));
            assertEquals("apps/service", checkout.provenance().get("subdir"));
        }
        assertFalse(Files.exists(selected));
        assertEquals(2, calls.size());
        assertTrue(calls.get(0).contains("--no-recurse-submodules"));
        assertTrue(calls.get(0).contains("--branch"));
        assertFalse(calls.get(0).contains("credential.helper=!gh auth git-credential"));
    }

    @Test void privateCloneRetriesUsingGhWithoutChangingGlobalGitConfiguration() throws Exception {
        List<List<String>> calls = new ArrayList<>();
        GitHubCheckout.Commands runner = (command, cwd, log, timeout) -> {
            calls.add(List.copyOf(command));
            if (calls.size() == 1) {
                Files.createDirectories(cwd.resolve("checkout"));
                Files.writeString(cwd.resolve("checkout/partial"), "partial checkout");
                throw new ProjectRunner.CommandFailed(128, log);
            }
            if (command.contains("clone")) {
                assertFalse(Files.exists(cwd.resolve("checkout/partial")));
                Files.createDirectories(cwd.resolve("checkout"));
            } else Files.writeString(log, COMMIT);
        };
        try (var checkout = GitHubCheckout.open("https://github.com/example/private", null, Path.of(""),
                temp, Duration.ofSeconds(5), runner)) {
            assertTrue(Files.isDirectory(checkout.project()));
        }
        assertTrue(calls.get(1).contains("credential.helper=!gh auth git-credential"));
        assertTrue(calls.get(1).contains("credential.helper="));
        assertTrue(calls.stream().flatMap(List::stream).noneMatch(s -> s.equals("--global") || s.contains("token=")));
    }

    @Test void deniedAccessProvidesAuthenticationInstructionsAndCleansCheckout() throws Exception {
        List<Path> roots = new ArrayList<>();
        var error = assertThrows(IOException.class, () -> GitHubCheckout.open("https://github.com/example/private", null, Path.of(""),
                temp, Duration.ofSeconds(5), (command, cwd, log, timeout) -> {
                    roots.add(cwd);
                    Files.createDirectories(cwd.resolve("checkout"));
                    throw new ProjectRunner.CommandFailed(128, log);
                }));
        assertTrue(error.getMessage().contains("auth"));
        assertTrue(error.getMessage().contains("SSO"));
        roots.forEach(root -> assertFalse(Files.exists(root)));
    }

    @Test void timeoutDoesNotTriggerAuthenticationRetryAndStillCleansUp() throws Exception {
        List<Path> roots = new ArrayList<>();
        assertThrows(IOException.class, () -> GitHubCheckout.open("https://github.com/example/demo", null, Path.of(""),
                temp, Duration.ofSeconds(5), (command, cwd, log, timeout) -> {
                    roots.add(cwd);
                    throw new IOException("Command exceeded timeout");
                }));
        assertEquals(1, roots.size());
        assertFalse(Files.exists(roots.get(0)));
    }

    @Test void rejectsSubdirectorySymlinkEscapingCheckout() throws Exception {
        List<Path> roots = new ArrayList<>();
        assertThrows(IOException.class, () -> GitHubCheckout.open("https://github.com/example/demo", null, Path.of("escape"),
                temp, Duration.ofSeconds(5), (command, cwd, log, timeout) -> {
                    roots.add(cwd);
                    if (command.contains("clone")) {
                        Path clone = Files.createDirectories(cwd.resolve("checkout"));
                        Files.createSymbolicLink(clone.resolve("escape"), temp);
                    } else Files.writeString(log, COMMIT);
                }));
        assertFalse(Files.exists(roots.get(0)));
        assertTrue(Files.isDirectory(temp));
    }

    @Test void offeredLoginRetriesTheSameRepositoryWithoutRequiringAnotherCommand() throws Exception {
        var attempts = new ArrayList<List<String>>();
        var loginCalls = new ArrayList<Boolean>();
        try (var checkout = GitHubCheckout.open("https://github.com/example/private", null, Path.of(""), temp,
                Duration.ofSeconds(5), (command, cwd, log, timeout) -> {
                    attempts.add(List.copyOf(command));
                    if (attempts.size() <= 2) throw new ProjectRunner.CommandFailed(128, log);
                    if (command.contains("clone")) Files.createDirectories(cwd.resolve("checkout"));
                    else Files.writeString(log, COMMIT);
                }, () -> { loginCalls.add(true); return true; })) {
            assertEquals(COMMIT, checkout.provenance().get("commit"));
        }
        assertEquals(1, loginCalls.size());
        assertEquals(attempts.get(1), attempts.get(2));
    }
}
