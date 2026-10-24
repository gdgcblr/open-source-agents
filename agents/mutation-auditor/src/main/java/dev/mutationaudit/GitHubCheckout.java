package dev.mutationaudit;

import java.io.IOException;
import java.nio.file.*;
import java.time.Duration;
import java.util.*;
import java.util.regex.Pattern;

/** Owns a disposable checkout. Git/gh handle credentials; no tokens enter command arguments or reports. */
final class GitHubCheckout implements AutoCloseable {
    private static final Pattern URL = Pattern.compile("https://github\\.com/([A-Za-z0-9][A-Za-z0-9-]{0,38})/([A-Za-z0-9_.-]{1,104})/?");
    private final Path temporary;
    private final Path project;
    private final Map<String, String> provenance;

    @FunctionalInterface interface Commands {
        void run(List<String> command, Path cwd, Path log, Duration timeout) throws Exception;
    }
    @FunctionalInterface interface Login {
        boolean authenticate() throws Exception;
    }

    private GitHubCheckout(Path temporary, Path project, Map<String, String> provenance) {
        this.temporary = temporary;
        this.project = project;
        this.provenance = Map.copyOf(provenance);
    }

    static String normalizeUrl(String url) {
        var match = URL.matcher(url);
        if (!match.matches()) throw new IllegalArgumentException("Use an HTTPS GitHub repository URL: https://github.com/OWNER/REPO. "
                + "Credentials, query strings, and tree/blob links are not allowed.");
        String name = match.group(2);
        if (name.endsWith(".git")) name = name.substring(0, name.length() - 4);
        if (name.equals(".") || name.equals("..") || name.isBlank() || name.length() > 100)
            throw new IllegalArgumentException("Invalid GitHub repository name.");
        return "https://github.com/" + match.group(1) + "/" + name;
    }

    static void validateSelection(String ref, Path subdir) {
        if (ref != null && (!ref.matches("[A-Za-z0-9_][A-Za-z0-9_./-]*") || ref.contains("..")
                || ref.contains("//") || ref.endsWith("/") || ref.endsWith(".") || ref.endsWith(".lock")))
            throw new IllegalArgumentException("--ref must be a branch or tag name (letters, digits, _, -, ., /); commit hashes are not supported.");
        if (subdir.isAbsolute() || subdir.normalize().startsWith(".."))
            throw new IllegalArgumentException("--subdir must stay inside the repository.");
    }

    static GitHubCheckout open(String url, String ref, Path subdir, Path output, Duration timeout) throws Exception {
        return open(url, ref, subdir, output, timeout,
                (command, cwd, log, limit) -> ProjectRunner.runCommand(command, cwd, log, limit, true), GitHubCheckout::offerLogin);
    }

    static GitHubCheckout open(String url, String ref, Path subdir, Path output, Duration timeout, Commands commands) throws Exception {
        return open(url, ref, subdir, output, timeout, commands, () -> false);
    }

    static GitHubCheckout open(String url, String ref, Path subdir, Path output, Duration timeout, Commands commands, Login login) throws Exception {
        String normalized = normalizeUrl(url);
        validateSelection(ref, subdir);
        Path temporary = Files.createTempDirectory("mutation-auditor-github-");
        Path checkout = temporary.resolve("checkout");
        try {
            var cloneArgs = new ArrayList<>(List.of("clone", "--depth", "1", "--single-branch", "--no-recurse-submodules"));
            if (ref != null) cloneArgs.addAll(List.of("--branch", ref));
            cloneArgs.addAll(List.of("--", normalized + ".git", checkout.toString()));
            var command = new ArrayList<>(List.of("git"));
            command.addAll(cloneArgs);
            System.out.println("Cloning " + normalized + " into a temporary checkout...");
            try {
                commands.run(command, temporary, output.resolve("clone.log"), timeout);
            } catch (ProjectRunner.CommandFailed initialFailure) {
                // GitHub deliberately does not distinguish a private repository from a missing one.
                // Retry using gh only for this process; do not change the user's global Git configuration.
                if (Files.exists(checkout)) ProjectRunner.deleteTree(checkout);
                command = new ArrayList<>(List.of("git", "-c", "credential.helper=", "-c", "credential.helper=!gh auth git-credential"));
                command.addAll(cloneArgs);
                try {
                    commands.run(command, temporary, output.resolve("clone-auth.log"), timeout);
                } catch (ProjectRunner.CommandFailed authFailure) {
                    if (login.authenticate()) {
                        if (Files.exists(checkout)) ProjectRunner.deleteTree(checkout);
                        try {
                            commands.run(command, temporary, output.resolve("clone-login.log"), timeout);
                        } catch (ProjectRunner.CommandFailed stillDenied) {
                            throw new IOException("Signed in, but the repository is still unavailable. Check account permissions, "
                                    + "organization SSO, URL, and branch/tag. Logs: " + output, stillDenied);
                        }
                    } else {
                    throw new IOException("Could not clone the repository. Check the URL, --ref, network, and repository access. "
                            + "For private repositories install GitHub CLI, run 'java -jar mutation-auditor.jar auth', "
                            + "and rerun analyze. Organization SSO or repository approval may also be required. Logs: " + output, authFailure);
                    }
                }
            }
            Path commitFile = output.resolve("checkout-commit.txt");
            commands.run(List.of("git", "-C", checkout.toString(), "rev-parse", "HEAD"), temporary, commitFile, timeout);
            String commit = Files.readString(commitFile).strip();
            if (!commit.matches("[0-9a-fA-F]{40}|[0-9a-fA-F]{64}")) throw new IOException("Git returned an invalid commit identifier.");
            Path selected = checkout.resolve(subdir).normalize().toRealPath();
            if (!selected.startsWith(checkout.toRealPath()) || !Files.isDirectory(selected))
                throw new IOException("Selected project directory must stay inside the repository.");
            return new GitHubCheckout(temporary, selected, Map.of("type", "github", "url", normalized,
                    "requestedRef", ref == null ? "default branch" : ref, "commit", commit,
                    "subdir", subdir.normalize().toString().isBlank() ? "." : subdir.normalize().toString()));
        } catch (Exception error) {
            try { ProjectRunner.deleteTree(temporary); } catch (IOException cleanup) { error.addSuppressed(cleanup); }
            throw error;
        }
    }

    Path project() { return project; }
    Map<String, String> provenance() { return provenance; }

    @Override public void close() throws IOException { ProjectRunner.deleteTree(temporary); }

    private static boolean offerLogin() throws Exception {
        var console = System.console();
        if (console == null) return false;
        String reply = console.readLine("Repository access failed. Sign in through GitHub now? [y/N] ");
        return reply != null && reply.strip().equalsIgnoreCase("y") && authenticate() == 0;
    }

    static int authenticate() throws Exception {
        System.out.println("Opening GitHub CLI authentication for github.com. Credentials are managed by GitHub CLI.");
        Process process;
        try {
            process = new ProcessBuilder("gh", "auth", "login", "--hostname", "github.com", "--git-protocol", "https", "--web")
                    .inheritIO().start();
        } catch (IOException missing) {
            throw new IOException("Install GitHub CLI (https://cli.github.com), then rerun auth or use your existing Git credentials.", missing);
        }
        try { return process.waitFor() == 0 ? 0 : 1; }
        catch (InterruptedException interrupted) {
            ProjectRunner.stop(process);
            Thread.currentThread().interrupt();
            throw interrupted;
        }
    }
}
