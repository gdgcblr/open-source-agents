# Android Dev Assistant

> An AI-powered Android troubleshooting assistant that helps developers understand common Android development errors and find practical solutions using Google ADK and Gemini.

---

## Overview

### Problem Statement & Intended Users

- **Problem:** Android developers frequently encounter errors involving Firebase configuration, Gradle dependency resolution, Kotlin, and Jetpack Compose. Finding the cause and identifying reliable fixes can take time.
- **Intended Users:** Android developers, Kotlin developers, students learning Android development, and contributors working with Android projects.

### Key Features

- **Android Error Diagnosis:** Searches a local knowledge base to identify known Android development errors.
- **Ranked Error Matching:** Uses keyword matching to rank relevant troubleshooting entries.
- **Confidence Indicators:** Returns a confidence level based on the keyword match score.
- **Practical Fixes:** Provides likely causes, suggested fixes, and verification steps.
- **Documentation References:** Includes links to relevant official documentation.
- **Fallback Handling:** Reports when no reliable knowledge-base match is found instead of presenting an unsupported solution.

---

## Technical Stack

- **Language & Runtime:** Python 3.13+
- **Agent Framework:** Google Agent Development Kit (ADK)
- **Model:** Gemini 3.5 Flash
- **Knowledge Base:** Local JSON file
- **Testing:** Python test scripts
- **Configuration:** Environment variables using `.env`

---

## Architecture & Data Flow

The assistant uses Google ADK to coordinate the interaction between the user, Gemini, and a local troubleshooting tool.

```text
[User enters Android error]
            |
            v
    [Google ADK Agent]
            |
            v
      [Gemini Model]
            |
            v
 [Android Knowledge Search Tool]
            |
            v
 [android_errors.json]
            |
            v
 [Ranked Matching Results]
            |
            v
 [Diagnosis and Suggested Fixes]
```

The knowledge search tool normalizes the supplied error text, compares its keywords with the knowledge-base entries, ranks matching entries, and returns the best available match.

---

## Prerequisites

Before running this project, ensure you have:

- Python 3.13 or later.
- pip package manager.
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/).
- Internet access for Gemini API requests.

---

## Installation & Setup

### 1. Navigate to the project directory

```bash
cd agents/android-dev-assistant
```

### 2. Create and activate a virtual environment

**Windows PowerShell:**

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Linux/macOS:**

```bash
python3.13 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Copy the example environment file:

**Windows PowerShell:**

```powershell
Copy-Item .env.example .env
```

**Linux/macOS:**

```bash
cp .env.example .env
```

Add your Gemini API key to `.env`:

```env
GEMINI_API_KEY=your_gemini_api_key_here
MODEL_NAME=gemini-3.5-flash
```

Never commit `.env` or publish your API key.

---

## Configuration & Environment Variables

| Variable | Required | Default / Example | Description |
|---|---|---|---|
| `GEMINI_API_KEY` | Yes | None | API key used to access Gemini |
| `MODEL_NAME` | No | `gemini-3.5-flash` | Gemini model identifier |

---

## How to Run

**Important:** The contribution folder uses the required kebab-case name `android-dev-assistant`. ADK's CLI expects a Python-compatible agent directory name, so use an underscore-named local runner copy.

From the repository root, create a temporary runner directory:

```powershell
$runner = "$env:USERPROFILE\adk-workspace\android_dev_assistant"

New-Item -ItemType Directory -Force -Path "$runner\knowledge"
```

Copy the agent files:

```powershell
Copy-Item .\agents\android-dev-assistant\agent.py, .\agents\android-dev-assistant\android_tools.py, .\agents\android-dev-assistant\__init__.py "$runner\" -Force

Copy-Item .\agents\android-dev-assistant\knowledge\android_errors.json "$runner\knowledge\" -Force
```

Load your Gemini API key into the current PowerShell session:

```powershell
Get-Content .\agents\android-dev-assistant\.env | ForEach-Object {
    if ($_ -match '^\s*GEMINI_API_KEY\s*=\s*(.+)\s*$') {
        $env:GEMINI_API_KEY = $matches[1].Trim().Trim('"').Trim("'")
    }
}
```

Run the agent:

```powershell
adk run $runner
```

Enter an Android error at the `[user]:` prompt. Type `exit` to end the session.

---

## Example Input & Output

### Example Input

```text
Execution failed for task ':app:processDebugGoogleServices'.
File google-services.json is missing.
```

### Example Output

The assistant identifies the issue as a Firebase configuration problem and provides:

- **Likely cause:** The Firebase configuration file is missing from the Android app module.
- **Suggested fixes:**
  1. Open Firebase Console.
  2. Register the Android application using its application ID.
  3. Download `google-services.json`.
  4. Place the file inside the `app/` directory.
  5. Verify the Google Services Gradle plugin configuration.
- **Verification:** Sync Gradle and rebuild the project.
- **Documentation:** [Firebase Android setup](https://firebase.google.com/docs/android/setup)

The actual response is generated by the agent using the available knowledge-base result.

---

## How to Test

Navigate to the project directory:

```powershell
cd agents\android-dev-assistant
```

Run the test script:

```powershell
python test_android_tools.py
```

The tests verify Android troubleshooting knowledge searches and expected fallback behavior.

---

## Knowledge Base

The current local knowledge base contains troubleshooting entries for:

1. Firebase missing `google-services.json`.
2. Gradle dependency resolution failures.
3. Jetpack Compose unresolved references.

Each entry includes:

- Error description.
- Likely cause.
- Search keywords and alternative descriptions.
- Suggested fixes.
- Verification steps.
- Official documentation reference.

---

## Known Limitations

- The knowledge base currently covers a limited set of Android errors.
- Matching is based on keyword overlap, not a dedicated semantic search or embedding model.
- Confidence levels are heuristic indicators and are not calibrated probabilities.
- Errors outside the knowledge base may require additional investigation.
- Gemini API availability and usage limits may affect responses.
- The agent does not execute commands or modify Android project files.

---

## Security & Privacy Considerations

- **Secrets Handling:** Gemini credentials are loaded through environment variables. The actual `.env` file must remain local and must not be committed.
- **Data Privacy:** User-provided error text is sent to Gemini for processing. Do not submit passwords, API keys, tokens, or other sensitive information.
- **Local Knowledge Base:** Troubleshooting entries are stored in a local JSON file.
- **Execution Safety:** The assistant provides troubleshooting guidance; it does not execute arbitrary shell commands or modify source files.

---

## Future Improvements

- [ ] Expand the knowledge base with more Android, Kotlin, Gradle, and Compose errors.
- [ ] Improve matching with semantic search.
- [ ] Support structured diagnostic reports.
- [ ] Add more automated tests and edge-case coverage.
- [ ] Include version-aware Android troubleshooting.
- [ ] Add additional official documentation references.

---

## License

This project is contributed under the repository's open-source license.