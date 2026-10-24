package dev.mutationaudit;

import java.nio.file.*;
import java.time.Duration;
import java.util.*;

/** Injects the Gradle PIT adapter through a temporary init script, without changing the build files. */
final class GradleRunner {
    static final String PLUGIN_VERSION = "1.19.0";

    static Path analyze(Path project, Path output, String override, Duration timeout) throws Exception {
        Path temporary = Files.createTempDirectory("mutation-auditor-gradle-");
        try {
            ProjectRunner.copyProject(project.toRealPath(), temporary, output);
            List<String> command = GradleRuntime.command(temporary, override, timeout);
            Path check = temporary.resolve("mutation-auditor-check.init.gradle");
            Files.writeString(check, """
                    gradle.projectsEvaluated {
                        def p = gradle.rootProject
                        if (p.allprojects.size() != 1) throw new GradleException('Multi-project Gradle builds are not supported yet. Select a standalone Java project.')
                        if (!p.plugins.hasPlugin('java')) throw new GradleException('Gradle support currently requires the standard Java plugin.')
                    }
                    """);
            System.out.println("Running Gradle baseline tests in a temporary project copy...");
            ProjectRunner.run(args(command, "--init-script", check.toString(), "clean", "test", "--rerun-tasks"), temporary, output.resolve("baseline.log"), timeout);
            ProjectRunner.requireTestsAt(temporary.resolve("build/test-results/test"));
            Path init = temporary.resolve("mutation-auditor.init.gradle");
            Files.writeString(init, initScript());
            System.out.println("Preparing PIT automatically and running Gradle mutation analysis...");
            ProjectRunner.run(args(command, "--init-script", init.toString(), "pitest"), temporary, output.resolve("pit.log"), timeout);
            Path xml = temporary.resolve("build/reports/mutation-auditor/mutations.xml");
            if (!Files.isRegularFile(xml)) throw new java.io.IOException("Gradle PIT did not produce mutations.xml. Check " + output.resolve("pit.log"));
            return Files.copy(xml, output.resolve("mutations.xml"));
        } finally { ProjectRunner.deleteTree(temporary); }
    }

    private static List<String> args(List<String> executable, String... args) {
        var result = new ArrayList<>(executable);
        result.addAll(List.of("--no-daemon", "--console=plain", "--no-configuration-cache"));
        result.addAll(Arrays.asList(args));
        return result;
    }

    static String initScript() {
        return """
                initscript {
                    repositories { maven { url = uri('https://plugins.gradle.org/m2/') }; mavenCentral() }
                    dependencies { classpath 'info.solidsoft.gradle.pitest:gradle-pitest-plugin:%s' }
                }
                gradle.beforeProject { p ->
                    p.plugins.withId('java') {
                        if (!p.plugins.hasPlugin('info.solidsoft.pitest')) {
                            p.pluginManager.apply(info.solidsoft.gradle.pitest.PitestPlugin)
                        }
                    }
                }
                gradle.projectsEvaluated {
                    def p = gradle.rootProject
                    if (p.allprojects.size() != 1) throw new GradleException('Multi-project Gradle builds are not supported yet. Select a standalone Java project.')
                    if (!p.plugins.hasPlugin('java')) throw new GradleException('Gradle support currently requires the standard Java plugin.')
                    def pit = p.extensions.getByName('pitest')
                    pit.pitestVersion.set('%s')
                    pit.junit5PluginVersion.set('%s')
                    def classNames = { directories ->
                        def targets = [] as Set
                        directories.each { directory ->
                            if (directory.isDirectory()) directory.eachFileRecurse { file ->
                                if (file.isFile() && file.name.endsWith('.class')) {
                                    def name = directory.toPath().relativize(file.toPath()).toString()
                                        .replace(File.separator, '.').replaceAll(/\\.class$/, '')
                                    if (!name.endsWith('module-info') && !name.endsWith('package-info')) targets.add(name)
                                }
                            }
                        }
                        return targets
                    }
                    if (!pit.targetClasses.isPresent()) {
                        def targets = classNames(p.sourceSets.main.output.classesDirs.files)
                        if (targets.isEmpty()) throw new GradleException('No compiled Java production classes found for mutation testing.')
                        pit.targetClasses.set(targets)
                    }
                    if (!pit.targetTests.isPresent()) pit.targetTests.set(classNames(p.sourceSets.test.output.classesDirs.files))
                    pit.outputFormats.set(['XML', 'HTML'] as Set)
                    pit.timestampedReports.set(false)
                    pit.reportDir.set(p.layout.buildDirectory.dir('reports/mutation-auditor'))
                    pit.mutationThreshold.set(0)
                    pit.coverageThreshold.set(0)
                    pit.testStrengthThreshold.set(0)
                }
                """.formatted(PLUGIN_VERSION, ProjectRunner.PIT_VERSION, PitBootstrap.JUNIT_PLUGIN_VERSION);
    }
}
