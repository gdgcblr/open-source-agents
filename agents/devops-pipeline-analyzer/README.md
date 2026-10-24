
# DevOps Pipeline Analyzer Agent

A lightweight Python tool that analyzes CI/CD log files, detects
common error patterns, and suggests troubleshooting steps.

## Features

- Detects Gradle dependency resolution failures
- Identifies compilation errors
- Flags authentication and permission errors
- Detects network connectivity issues
- Identifies SonarQube quality gate failures
- Flags possible Java memory exhaustion
- Shows matching log lines and troubleshooting suggestions
- Includes automated unit tests

## Requirements

- Python 3.8 or later
- No third-party Python packages required

## Getting Started

Clone the repository and navigate to this project directory.

## Usage

Run the analyzer against a CI/CD log file:

```bash
python analyzer.py sample.log
```

Example log:

```text
Starting Jenkins pipeline...
Could not resolve com.example:library:1.0
BUILD FAILED
```

The analyzer reports the detected issue and suggests checks
for dependency versions, repository configuration, and network access.

## Run Tests

```bash
python -m unittest discover -s tests -v
```

## How It Works

The analyzer reads a supplied log file, matches log lines against
predefined regular-expression patterns, and prints possible issues
with suggested troubleshooting steps.

## Limitations

- Uses predefined patterns rather than AI-based reasoning.
- Does not connect directly to Jenkins, Gradle, JFrog, or SonarQube.
- Does not modify code, fix failures, or rerun pipelines.
- Suggestions are indicative and do not guarantee the root cause.

## Future Improvements

- Add more error patterns and test cases.
- Support structured reports such as JSON.
- Explore optional Jenkins integration.
