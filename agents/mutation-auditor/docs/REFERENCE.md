# Mutation Auditor reference

Start with the [README](../README.md) for the one-command workflow. Commands here assume you are in `agents/mutation-auditor`.

## Commands

| Task | Command |
| --- | --- |
| Local project | `./mutation-auditor /path/to/project` |
| Current folder | `./mutation-auditor` |
| GitHub repository | `./mutation-auditor https://github.com/OWNER/REPO` |
| Branch or tag | Append `--ref feature/better-tests` to a GitHub command. |
| Project inside a repository | Append `--subdir services/payments` to a GitHub command. |
| AI investigation | Append `--ai` after configuring `GOOGLE_API_KEY`. |
| GitHub browser login | `./mutation-auditor auth` |
| Import PIT XML | `./mutation-auditor report --xml /path/to/mutations.xml` |
| Explain imported results | `./mutation-auditor report --xml /path/to/mutations.xml --project /path/to/matching-source --ai` |
| All analysis options | `./mutation-auditor analyze --help` |

Explicit `analyze --project PATH` and `analyze --repo URL` syntax remains supported. Choose one source per command. `--ref` and `--subdir` apply only to GitHub input. Refs are branch/tag names, not arbitrary commit IDs.

GitHub URLs must use HTTPS on `github.com`; optional `.git` endings are accepted. Tree/blob links, embedded credentials, SSH/Enterprise URLs, submodule checkout, and Git LFS downloads are not supported. GitHub runs record the actual commit in their saved source metadata and reports.

Imported XML is labeled `not-verified-imported-report`: its baseline, age, configuration, and correspondence to the source revision cannot be verified. Supply the same source revision that produced it.

## Configuration

| Setting | Default | Meaning |
| --- | --- | --- |
| `--output` | `./mutation-audit` | Parent of the unique run folder. |
| `--timeout-seconds` | `600` | Per-command timeout; total AI investigation deadline. Valid range: 1–86400. |
| `--model` | `gemini-3.5-flash-lite` | Gemini model for `--ai`. |
| `GOOGLE_API_KEY` | None | Required only with `--ai`. |
| `MUTATION_AUDITOR_MODEL` | `gemini-3.5-flash-lite` | Model default overridden by `--model`. |
| `--maven` | Chosen by launcher | Maven executable override. |
| `--gradle` | Wrapper or automatic download | Gradle executable override. |
| `MUTATION_AUDITOR_MAVEN` | Set by launcher | Default Maven command for direct invocation. |
| `MUTATION_AUDITOR_TOOLS` | `~/.cache/mutation-auditor` | Downloaded Gradle distribution cache. |

Environment variables must be exported in your terminal. `.env.example` is a reference; `.env` is not loaded automatically. In PowerShell, use `$env:GOOGLE_API_KEY = "YOUR_KEY"`.

The first source build uses Apache Maven Wrapper. On macOS/Linux it needs curl or wget, unzip, and shasum or sha256sum. Maven uses its normal `~/.m2` cache. Gradle uses `GRADLE_USER_HOME` / `~/.gradle` for dependencies. Uncached artifacts need network access.

## Authentication

Git first uses configured HTTPS credentials. On clone failure the auditor retries using `gh auth git-credential` for that process, without writing a Git credential-helper setting. In an interactive terminal, it can offer browser login and retry. Noninteractive runs provide instructions instead.

`auth` delegates to `gh auth login --hostname github.com --git-protocol https --web`. GitHub CLI normally uses the system credential store, with a configuration-file fallback when unavailable. See [GitHub CLI authentication](https://cli.github.com/manual/gh_auth_login).

For CI, supply `GH_TOKEN` through your secret store and configure access before analysis. Organization SSO or fine-grained token approval may be required. GitHub credentials and the Gemini API key serve separate purposes. A private repository, missing repository, invalid ref, or network failure can produce similar clone errors; inspect the logs.

## Execution and reports

```text
Path or GitHub URL
  -> select a supported Java project
  -> create a temporary execution copy
  -> run existing tests and validate test XML
  -> provision PIT and run mutations
  -> calculate results and write reports
  -> optionally investigate findings with ADK + Gemini
```

Maven uses a separate analysis POM; Gradle uses a temporary init script. Neither requires PIT configuration in the target repository. Existing mutation filters are preserved where present. The auditor supplies pinned engine/adapter versions, report formats and locations, and zero failure thresholds for score reporting. Maven analysis disables dry runs, skipping, and history. No extra Maven profile is activated.

Gradle uses an existing wrapper or downloads checksum-pinned Gradle 9.1.0. Existing wrappers must be Gradle 8.4+ and compatible with the installed JDK. Java 25 requires Gradle 9.1+. Target Gradle projects must apply the standard Java plugin and use conventional test XML output. See [Gradle compatibility](https://docs.gradle.org/current/userguide/compatibility.html).

Copies exclude `.git`, `target`, `build`, `.gradle`, editor folders, `node_modules`, and `mutation-audit`. Symlinks are rejected. Only the selected project folder is copied: local parent POMs, sibling modules, and arbitrary external files are not reproduced. Repository-resolved Maven parents need `<relativePath/>`. Reactor and Gradle multi-project builds are unsupported.

Each run writes `report.md` and `report.json`. Executed analyses also save `mutations.xml`, `baseline.log`, and `pit.log`; GitHub runs add clone logs and source metadata. Successful AI runs add `recommendations.md`. Failures save `ai-error.md`; `report.json` records AI status as `completed`, `failed`, `skipped-no-findings`, or `not-requested`. The terminal shows source-tool progress during investigation. No model call is made when there are no surviving/uncovered mutants. Measured reports remain saved if AI fails.

Markdown lists the first 100 findings; JSON contains every mutant. Exit codes are `0` for completion, `1` for execution/AI errors or explicitly incomplete reports, and `2` for invalid syntax. A low score alone does not fail the command.

### Score definition

```text
mutationScore = 100 × count(detected=true) / total PIT XML mutation entries
```

This preserves PIT's detection semantics, including detected timeouts, non-viable mutations, and memory errors. Status counts remain visible. Empty reports and reports containing `STARTED`, `NOT_STARTED`, or `RUN_ERROR` have a null score (`N/A`). Compare runs using the same scope and operators. Equivalent mutations require human judgment.

## AI limits and privacy

ADK exposes read-only tools for Java source and tests. The model cannot run commands, write files, alter scores, or verify proposed tests. Suggestions are explicitly unverified.

An investigation receives at most 30 findings, can list up to 200 Java files, reads up to 32 KB per file, and makes at most 12 model calls. The timeout caps the total AI investigation; there is no separate token-cost budget. Large investigations may be incomplete.

`--ai` sends findings and selected source/test content to Gemini. No model requests occur without it. Provider charges, quotas, and privacy policies apply. Source tools check real paths and restrict access to standard Java source directories; comments are treated as untrusted data.

Builds run with your user permissions. Model key variables and common GitHub token variables are removed from build child environments, but other credentials, on-disk credentials, external services, and filesystem/network access are not isolated. Review logs and reports before sharing. Normal completion/failure removes temporary copies; forced termination can leave files. Child-process cleanup is best effort under OS restrictions.

## Troubleshooting

| Symptom | Next step |
| --- | --- |
| No Java / unsupported JDK | Install JDK 17+ and check `JAVA_HOME`; match the target build's requirements. |
| First-run setup fails | Read the build-log path printed by the launcher; check network/download tools. |
| No project / multiple projects found | Provide the project folder or a GitHub `--subdir`; it must build independently. |
| Baseline tests fail or are skipped | Read `baseline.log`; fix the existing test setup. At least one passing, non-skipped test must be recorded. |
| Gradle fails | Check wrapper/JDK compatibility, the standard Java plugin, and network access to dependencies/plugin repositories. |
| PIT fails | Read `pit.log`; inspect dependency resolution, test compatibility, and existing mutation filters. |
| No mutations | Check compiled production classes and target filters. An empty run has no meaningful score. |
| Private clone fails | Install GitHub CLI, run `auth`, and check repository permission/SSO and clone logs. |
| Missing sibling dependency | Select an independent project. `--subdir` does not preserve `../common-lib` or similar paths. |
| AI fails | Read `ai-error.md`. Check the key, model, network, and quota. If you exported an older `MUTATION_AUDITOR_MODEL`, update it or pass `--model gemini-3.5-flash-lite`. Reuse saved XML with the `report` command. |

## Development

Stack: Java 17+, Google ADK Java 1.13.0, Gemini, PIT 1.30.1, PIT JUnit 5 adapter 1.2.3, gradle-pitest-plugin 1.19.0, picocli, and Jackson. Versions are pinned in source and the dependency manifest.

```bash
./mvnw test
./mvnw package
./mutation-auditor examples/discount-service
./mutation-auditor examples/discount-gradle
```

Automated tests cover parsing/scoring, incomplete reports, XML entity rejection, source boundaries, ADK tool registration, isolated copies, process failures/timeouts, GitHub clone/authentication flows, project discovery, Maven bootstrap, Gradle wrapper validation, and archive extraction. Network authentication and model calls are simulated or omitted.

End-to-end runs verified Maven and Gradle Java examples, including Groovy/Kotlin build DSLs. The boundary-test experiment improved 66.7% to 100% after a manual test addition. Live Gemini 3.5 Flash-Lite investigation was verified against the Jenkins Java example, including actual source-tool calls and a saved recommendation. Legacy Gemini 2.5 access was rejected for the API project; Gemini 3.8 generation timed out during validation. Real private-account browser login remains unverified.

Tested locally on macOS ARM64 with OpenJDK 25.0.2, Maven 3.9.11, and Gradle 9.1.0. Linux, Windows, and a Java 17 runtime have not been tested locally.

### Manual JAR workflow

```bash
./mvnw clean package
java -jar target/mutation-auditor.jar /path/to/project
```

For Maven targets, direct JAR execution needs Maven on `PATH` or `--maven /path/to/mvn`. The source launcher supplies it automatically. Windows users can build with `mvnw.cmd clean package`; Windows execution is unverified.

### Next steps

Verify proposed tests against original code and targeted mutants; add changed-code prioritization, CI/PR integration, broader build/language support, and stronger execution isolation.
