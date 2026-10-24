# Mutation Auditor

> Find code changes your Java tests fail to catch.

Give Mutation Auditor a **project path or GitHub link**. It runs your tests, introduces small code changes through PIT, and reports which changes your tests missed. Enable the optional AI agent to investigate those gaps and suggest focused JUnit tests.

**One command. Automatic build detection. No PIT setup in your project.**

## Why this matters

A test can execute a line without checking its behavior thoroughly.

Consider a discount rule:

```java
return amount >= 1000;
```

Tests at `500` and `1500` exercise both outcomes. Change `>=` to `>`, and those tests still pass. The missing test is the boundary: **exactly `1000`**.

Mutation testing exposes this gap by making small changes, called *mutants*, and checking whether tests detect them. Mutation Auditor brings those results into a simple workflow and helps you decide what to investigate next.

### A measured example

The included example produced these results with PIT:

| Tests | Mutants caught | Mutants missed | Mutation score |
| --- | ---: | ---: | ---: |
| Purchases at 500 and 1500 | 2 | 1 | 66.7% |
| Add a test at exactly 1000 | 3 | 0 | 100.0% |

The improvement came from a meaningful assertion. See the actual [initial report](examples/discount-service/example-report.md) and [improved report](examples/discount-service/example-report-improved.md). The boundary test was added manually for this experiment.

## Try it

You need **JDK 17+**, network access for uncached dependencies, and a supported project with working tests. The launcher runs on macOS/Linux. Git is required for GitHub links.

From this repository:

```bash
cd agents/mutation-auditor
./mutation-auditor examples/discount-service
```

Then point it at your own code:

```bash
./mutation-auditor /path/to/project
```

Or use a GitHub repository:

```bash
./mutation-auditor https://github.com/OWNER/REPO
```

The first run builds the app and downloads the required build tools and dependencies. Later runs reuse them. **You do not need to install Maven, configure PIT, edit the target repository, or supply an API key to get a score.**

You can also provide `pom.xml`, `build.gradle`, or `build.gradle.kts`. Omit the input to analyze the current folder. For a Gradle example, run `./mutation-auditor examples/discount-gradle`.

## What you get

```text
Mutation score: 66.7%
3 mutations | 2 caught by tests | 1 survived | 0 uncovered

First findings:
  example.DiscountService.eligible (line 6): changed conditional boundary
```

Each run saves results under `mutation-audit/run-...`:

| Output | Use it to |
| --- | --- |
| `report.md` | Review the score, status counts, and findings. |
| `report.json` | Inspect all mutations or integrate with other tools. |
| `mutations.xml` | Reuse the original PIT results. |
| `recommendations.md` | Read optional AI explanations and test suggestions. |
| Build and clone logs | Diagnose setup, test, or authentication failures. |

Existing tests must pass before mutation analysis begins. An empty or explicitly incomplete report has **no score**, rather than being presented as 100%.

## Where the agent adds value

PIT supplies the execution evidence. The optional **Google ADK + Gemini agent** reads the affected Java code and tests, groups related findings, explains missing behavioral checks, and proposes focused JUnit tests.

```bash
export GOOGLE_API_KEY="YOUR_KEY"
./mutation-auditor /path/to/project --ai
```

Get a key from [Google AI Studio](https://aistudio.google.com/apikey). The default model is `gemini-3.5-flash-lite`; change it with `--model`. `.env` files are not loaded automatically.

**Scores come from PIT results. AI suggestions are unverified:** the agent does not apply, compile, or execute its proposed tests. Review them against your requirements. Provider failures are reported explicitly and saved as `ai-error.md`; measured mutation results remain available.

AI mode sends findings and selected Java source/test contents to Gemini. Enable it only when you are allowed to share that code. Provider costs and quotas may apply. Without `--ai`, the tool makes no model requests.

## Private repositories and project folders

Private repositories use your existing Git credentials. If needed, install [GitHub CLI](https://cli.github.com) and sign in once:

```bash
./mutation-auditor auth
./mutation-auditor https://github.com/YOUR_ORG/PRIVATE_REPO
```

An interactive analysis can also offer login and retry in place. Your account must have repository access; tokens do not belong in repository URLs or command arguments.

For a repository with several projects, select a standalone project folder:

```bash
./mutation-auditor https://github.com/OWNER/REPO --subdir services/payments
```

A single nested project is discovered automatically. Multiple projects are listed for selection. **`--subdir` does not add multi-module support:** the selected project must build independently; sibling dependencies such as `../common-lib` are not preserved in its execution copy.

## Supported today

| Area | Support |
| --- | --- |
| Language and tests | Java with JUnit 5; conventional source and test directories. |
| Maven | Standalone projects; Maven and PIT are provisioned automatically. |
| Gradle | Single-project Java builds with Gradle 8.4+; Groovy and Kotlin build DSLs. |
| Gradle installation | Uses an existing wrapper, or downloads Gradle 9.1.0 when none exists. |
| Repository input | Local paths and HTTPS `github.com` links; optional branch/tag selection. |
| Launcher | macOS/Linux. Windows requires the manual JAR workflow and is untested. |

Your project still needs a compatible JDK and working test configuration. Older wrappers are not silently upgraded. Maven reactors, Gradle multi-project builds, Android, and non-Java languages are not supported yet.

## Read the score responsibly

- **Killed:** tests detected the mutation.
- **Survived:** tests still passed; investigate a missing check or equivalent behavior.
- **Uncovered:** no test exercised the mutation.

The score follows PIT's detection flags, which can count timeouts and some error outcomes as detected. Inspect the status counts alongside the percentage. Scores depend on the code and mutation operators analyzed; they are not a universal project-quality rating or a guarantee that changes are safe.

Only analyze builds you trust. Tests and build plugins run with your user permissions. Temporary copies protect the original source files; they are **not a security sandbox**.

## More information

- [Usage, configuration, and troubleshooting](docs/REFERENCE.md)
- [How it works and how to test it](docs/REFERENCE.md#development)
- [Measured Gradle example](examples/discount-gradle/example-report.md)

## License

Original Mutation Auditor code is contributed under the parent repository's MIT license. See [third-party notices](THIRD_PARTY_NOTICES.md) for the Apache Maven Wrapper.
