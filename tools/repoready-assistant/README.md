# RepoGuide AI — Repository Onboarding Assistant

RepoGuide AI helps developers understand unfamiliar software repositories by combining local repository checks with optional AI-generated onboarding guidance.

## Problem

When joining an unfamiliar project, developers may struggle to identify setup requirements, dependency files, test instructions, and missing documentation.

RepoGuide AI automates basic file checks and can use Gemini to turn the findings and README content into a structured onboarding guide.

## Key Features

- Checks for documentation, Git ignore rules, a license, dependency manifests, tests, CI workflows, and an optional environment template.
- Reports local findings using `PASS`, `WARN`, and `INFO`.
- Provides a local fallback when no Gemini API key is configured.
- Optionally generates onboarding guidance using Google's Gemini API.
- Does not execute the inspected repository's code.

## Technical Stack

- Python 3.10+
- Python standard library
- Google Gen AI Python SDK for optional AI functionality
- `unittest` for automated tests

## Prerequisites

- Python 3.10 or later
- Internet access and a valid Gemini API key only when using AI mode

## Setup

From the project directory, install the dependencies:

```bash
python -m pip install -r requirements.txt
```

## Configuration

Set the `GEMINI_API_KEY` environment variable to enable AI-generated guidance.

PowerShell example:

```powershell
$env:GEMINI_API_KEY = "YOUR_API_KEY"
```

Do not commit real API keys or share them in source code.

## Usage

Run local checks and the onboarding assistant against the current repository:

```bash
python main.py .
python ai_guide.py .
```

To inspect another repository, pass its path:

```bash
python ai_guide.py /path/to/repository
```

Without `GEMINI_API_KEY`, the assistant displays local inspection results and explains that AI mode is unavailable.

With a valid key, the assistant sends the README content and local check results to Gemini to generate an onboarding guide. Review repository content for confidential information before enabling AI mode.

## Testing

Run the automated tests:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

## Limitations

- Checks use common filenames and directory conventions.
- File presence does not guarantee quality or correctness.
- AI-generated guidance may be inaccurate and should be verified.
- The tool is not a security audit.
- AI mode requires network access and a valid API key.

## Security and Privacy

The local checker does not send repository data to external services. AI mode sends the README content and check results to the configured Gemini service. Do not inspect sensitive repositories using AI mode unless you are authorized to share that content.

The assistant does not execute suggested commands automatically.

## Future Improvements

- JSON output for CI integration
- Configurable repository checks
- More detailed project-type detection
- Additional tests for AI-provider failures

## License

Follow the parent repository's license and contribution requirements.
