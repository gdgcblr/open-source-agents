# Repo Structure Analyzer

> A lightweight local CLI that scans a repository and provides a quick, readable summary of its structure, key files, and file-type distribution.

---

## Project Overview

Project Name: repo-structure-analyzer

Category: tools/repo-structure-analyzer

Frameworks & Technologies Used:
- Python 3.11+
- Standard library only (`pathlib`, `argparse`, `collections`)
- No external frameworks
- No AI agent framework required for this CLI tool

Description:
This tool helps developers quickly understand the structure of a project without manually browsing every folder or file. It scans a local repository path and summarizes the top-level directories, key project files, and common file types while ignoring noisy folders such as `.git`, `node_modules`, and virtual environments.

This is especially useful for new contributors, code reviewers, and developers trying to understand an unfamiliar repository in a short amount of time.

---

## Overview

This tool gives a fast answer to common questions such as:

- What folders exist in this repository?
- Is this likely a Python, JavaScript, or mixed project?
- Does the repo include docs, tests, configs, or deployment files?
- Where should I begin reading the code?

### Problem Statement & Intended Users

- **Problem**: Developers often waste time manually exploring unfamiliar repositories before understanding their structure, purpose, or setup.
- **Intended Users**: Developers, contributors, engineering teams, reviewers, and anyone onboarding into a new codebase.

### Key Features

- Scans any local repository or project folder
- Ignores noisy folders like `.git`, `.venv`, and `node_modules`
- Lists top-level directories and file counts
- Detects important files such as `README.md`, `requirements.txt`, and `package.json`
- Shows file extension distribution
- Supports JSON output for automation and scripting

---

## Technical Stack

- **Language & Runtime**: Python 3.11+
- **Agent Framework / Core Library**: Standard library CLI
- **Models**: N/A
- **External APIs / Tools**: None

---

## Architecture & Data Flow

This is a simple command-line workflow:

```text
[User Input: repo path]
        |
        v
[Python script scans filesystem]
        |
        v
[Ignores noisy folders]
        |
        v
[Counts files, folders, and extensions]
        |
        v
[Prints readable summary]