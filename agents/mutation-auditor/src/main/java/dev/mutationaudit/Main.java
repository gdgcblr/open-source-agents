package dev.mutationaudit;

import com.fasterxml.jackson.databind.ObjectMapper;
import picocli.CommandLine;
import picocli.CommandLine.*;
import java.nio.file.*;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.Callable;

@Command(name = "mutation-auditor", version = "0.1.0", mixinStandardHelpOptions = true,
        description = "Give a project path or GitHub link to measure how well its Java tests catch changes.",
        footer = {"Quick start:", "  mutation-auditor /path/to/project", "  mutation-auditor https://github.com/OWNER/REPO", "  mutation-auditor . --ai", "Omit the path to analyze the current folder. Advanced commands remain available below."},
        subcommands = {Main.Analyze.class, Main.Report.class, Main.Auth.class})
public final class Main implements Runnable {
    public static void main(String[] args) {
        System.exit(execute(args));
    }

    static int execute(String... args) {
        var cli = new CommandLine(new Main());
        cli.setExecutionExceptionHandler((error, command, parsed) -> {
            command.getErr().println("Error: " + error.getMessage());
            return 1;
        });
        return cli.execute(normalizeArguments(args));
    }

    static String[] normalizeArguments(String... args) {
        if (args.length == 0) return new String[]{"analyze", "--project", "."};
        int index = args[0].equals("analyze") ? 1 : 0;
        if (index >= args.length) return args;
        String first = args[index];
        if (index == 0 && Set.of("--ai", "--output", "--model", "--maven", "--gradle", "--timeout-seconds").contains(first)) {
            var result = new ArrayList<>(List.of("analyze", "--project", "."));
            result.addAll(Arrays.asList(args));
            return result.toArray(String[]::new);
        }
        if (Set.of("report", "auth", "help").contains(args[0]) || first.startsWith("-")) {
            if (Set.of("--project", "--repo").contains(args[0])) {
                var result = new ArrayList<>(List.of("analyze"));
                result.addAll(Arrays.asList(args));
                return result.toArray(String[]::new);
            }
            return args;
        }
        var result = new ArrayList<>(List.of("analyze", first.startsWith("https://") || first.startsWith("http://") ? "--repo" : "--project", first));
        result.addAll(Arrays.asList(args).subList(index + 1, args.length));
        return result.toArray(String[]::new);
    }

    @Override public void run() { CommandLine.usage(this, System.out); }

    static final class Options {
        @Option(names = "--output", description = "Parent directory for a unique run folder (default: ${DEFAULT-VALUE}).")
        Path output = Path.of("mutation-audit");
        @Option(names = "--ai", description = "Send mutation findings and selected Java source/tests to Gemini through ADK.")
        boolean ai;
        @Option(names = "--model", description = "Gemini model (default: ${DEFAULT-VALUE}).")
        String model = System.getenv().getOrDefault("MUTATION_AUDITOR_MODEL", "gemini-2.5-flash");
        @Option(names = "--timeout-seconds", description = "Time limit per Maven stage / AI inactivity (default: ${DEFAULT-VALUE}).")
        long timeout = 600;

        Path newOutput() throws Exception {
            if (timeout < 1 || timeout > 86_400) throw new IllegalArgumentException("Timeout must be between 1 and 86400 seconds.");
            Path parent = output.toAbsolutePath().normalize();
            Files.createDirectories(parent);
            return Files.createTempDirectory(parent, "run-");
        }
    }

    @Command(name = "analyze", mixinStandardHelpOptions = true,
            description = "Run tests and PIT in a temporary copy. Only analyze projects whose build code you trust.")
    static final class Analyze implements Callable<Integer> {
        static final class Source {
            @Option(names = "--project", description = "Local Maven or Gradle Java project directory.") Path project;
            @Option(names = "--repo", description = "HTTPS GitHub URL: https://github.com/OWNER/REPO.") String repo;
        }
        @ArgGroup(exclusive = true, multiplicity = "1") Source source;
        @Option(names = "--ref", description = "GitHub branch/tag to analyze; default is the repository's default branch.") String ref;
        @Option(names = "--subdir", description = "Project folder within the GitHub repository (default: repository root).") Path subdir;
        @Option(names = "--maven", description = "Maven executable (normally selected automatically by the launcher).")
        String maven = System.getenv().getOrDefault("MUTATION_AUDITOR_MAVEN", "mvn");
        @Option(names = "--gradle", description = "Gradle executable override; otherwise use the project's wrapper or download Gradle automatically.") String gradle;
        @Mixin Options options;

        public Integer call() throws Exception {
            if (source.project != null && (ref != null || subdir != null))
                throw new IllegalArgumentException("--ref and --subdir require --repo.");
            if (source.repo != null) {
                GitHubCheckout.normalizeUrl(source.repo);
                GitHubCheckout.validateSelection(ref, subdir == null ? Path.of("") : subdir);
            }
            if (options.ai) validateAiKey();
            Path output = options.newOutput();
            System.out.println("Results and logs: " + output);
            if (source.repo != null) {
                try (var checkout = GitHubCheckout.open(source.repo, ref, subdir == null ? Path.of("") : subdir,
                        output, Duration.ofSeconds(options.timeout))) {
                    var metadata = checkout.provenance();
                    System.out.println("Analyzing commit: " + metadata.get("commit"));
                    return analyze(checkout.project(), output, metadata);
                }
            }
            return analyze(source.project, output, Map.of("type", "local"));
        }

        private int analyze(Path project, Path output, Map<String, String> metadata) throws Exception {
            Path original = project.toRealPath();
            if (Files.isRegularFile(original)) original = original.getParent();
            project = ProjectLocator.find(project);
            if (!project.equals(original)) System.out.println("Found Java project: " + original.relativize(project));
            if (metadata.get("type").equals("github")) {
                metadata = new LinkedHashMap<>(metadata);
                String subdir = Path.of(metadata.get("subdir")).resolve(original.relativize(project)).normalize().toString();
                metadata.put("subdir", subdir.isBlank() ? "." : subdir);
                new ObjectMapper().writerWithDefaultPrettyPrinter().writeValue(output.resolve("source.json").toFile(), metadata);
            }
            boolean useGradle = ProjectLocator.gradle(project);
            if (useGradle && Files.isRegularFile(project.resolve("pom.xml")))
                throw new IllegalArgumentException("Both Maven and Gradle builds found. Choose a project with one build system.");
            metadata = new LinkedHashMap<>(metadata);
            metadata.put("buildSystem", useGradle ? "Gradle" : "Maven");
            Path xml = useGradle ? GradleRunner.analyze(project, output, gradle, Duration.ofSeconds(options.timeout))
                    : ProjectRunner.analyze(project, output, maven, Duration.ofSeconds(options.timeout));
            return write(MutationReport.read(xml), project, options, output, "baseline-passed", metadata);
        }
    }

    @Command(name = "auth", mixinStandardHelpOptions = true, description = "Authenticate with GitHub using GitHub CLI's browser login.")
    static final class Auth implements Callable<Integer> {
        public Integer call() throws Exception { return GitHubCheckout.authenticate(); }
    }

    @Command(name = "report", mixinStandardHelpOptions = true, description = "Read an existing PIT XML report; no Maven execution.")
    static final class Report implements Callable<Integer> {
        @Option(names = "--xml", required = true, description = "Path to PIT mutations.xml.") Path xml;
        @Option(names = "--project", description = "Matching source project, required with --ai.") Path project;
        @Mixin Options options;

        public Integer call() throws Exception {
            if (options.ai) validateAi(project);
            var report = MutationReport.read(xml);
            return write(report, project, options, options.newOutput(), "not-verified-imported-report", Map.of("type", "imported"));
        }
    }

    private static void validateAi(Path project) throws Exception {
        if (project == null || !Files.isDirectory(project)) throw new IllegalArgumentException("--ai requires --project with matching source code.");
        validateAiKey();
    }

    private static void validateAiKey() {
        if (System.getenv("GOOGLE_API_KEY") == null || System.getenv("GOOGLE_API_KEY").isBlank())
            throw new IllegalArgumentException("--ai requires the GOOGLE_API_KEY environment variable.");
    }

    private static int write(MutationReport report, Path project, Options options, Path output, String baseline,
                             Map<String, String> source) throws Exception {
        var summary = new LinkedHashMap<>(report.summary());
        summary.put("baseline", baseline);
        summary.put("source", source);
        if (baseline.equals("baseline-passed")) summary.put("analysisSetup", Map.of(
                "pitVersion", ProjectRunner.PIT_VERSION, "junit5AdapterVersion", PitBootstrap.JUNIT_PLUGIN_VERSION,
                "configuration", "Automatically provisioned in a temporary build configuration; existing target filters are preserved."));
        summary.put("scope", "Configured PIT targets; inspect mutations.xml for the analyzed classes. Not necessarily the entire project.");
        new ObjectMapper().writerWithDefaultPrettyPrinter().writeValue(output.resolve("report.json").toFile(), summary);
        String provenance = source.get("type").equals("github")
                ? "\n## Repository\n\nURL: " + source.get("url") + "\n\nCommit: `" + source.get("commit")
                    + "`\n\nRequested ref: `" + source.get("requestedRef") + "`\n\nSubdirectory: `" + source.get("subdir").replace('`', '_') + "`\n"
                : "";
        Files.writeString(output.resolve("report.md"), report.markdown() + provenance);
        System.out.println(report.consoleSummary());
        System.out.println("Reports: " + output);
        if (options.ai && !report.findings().isEmpty()) {
            System.out.println("Sending findings and selected Java source/tests to Gemini via ADK...");
            try {
                String advice = AiAdvisor.explain(report, project, options.model, Duration.ofSeconds(options.timeout));
                Files.writeString(output.resolve("recommendations.md"), advice);
                System.out.println(advice);
            } catch (Exception error) {
                System.err.println("AI explanation failed. Measured reports are saved at " + output);
                throw error;
            }
        }
        return report.complete() ? 0 : 1;
    }
}
