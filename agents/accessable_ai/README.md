# ♿ AccessAble AI — Accessibility Detective

**Turn website screenshots and URLs into actionable accessibility insights and PDF reports with AI.**

AccessAble AI is an AI-powered accessibility assistant that examines website screenshots or public website URLs, identifies potential accessibility barriers, explains how they may affect users, and recommends practical fixes.

Our goal is simple: **make accessibility reviews easier to start, easier to understand, and easier to act on.**

Instead of requiring every team to begin with specialized accessibility expertise, AccessAble AI provides a first-pass review that helps developers, QA engineers, designers, and product teams spot potential problems earlier in the development lifecycle.

---

## 🚨 The Problem

Accessibility issues can prevent people with low vision and other disabilities from using websites comfortably and independently.

However, accessibility reviews can be overlooked because:

- Teams may lack dedicated accessibility specialists.
- Manual reviews require time, knowledge, and consistent processes.
- Visual issues can be missed during regular functional testing.
- Findings without clear evidence or recommended fixes are difficult to act on.
- Accessibility observations are not always documented in a format that teams can share and track.

The result? Potential barriers may reach production and affect real users.

## 💡 Our Solution

**AccessAble AI acts as an accessibility detective for your website.**

Provide a website screenshot or a public website URL. The AI analyzes visible interface elements and, for URL-based reviews, uses a browser to collect additional page information. It identifies potential accessibility concerns, explains the evidence, describes possible user impact, prioritizes findings, and suggests improvements.

The analysis is then used to generate a structured PDF report for review and sharing.

### How it works

1. **Choose** — Start with a website screenshot or a public website URL.
2. **Inspect** — For URL reviews, Playwright opens the website, captures a screenshot, and collects information about headings, images, buttons, and links.
3. **Analyze** — Gemma examines the screenshot and, for URL reviews, the collected page observations.
4. **Understand** — Review findings, evidence, potential user impact, and priority.
5. **Fix** — Get practical recommendations and ways to verify improvements.
6. **Report** — Generate a PDF report that can be shared with developers, QA engineers, designers, and stakeholders.

---

## ✨ Key Features

### 🔍 AI-powered accessibility review

Analyze screenshots and public website URLs for potential accessibility issues.

Examples include:

- **Text contrast:** Text that may be difficult to distinguish from its background.
- **Interactive controls:** Buttons, icons, or controls that may be difficult to identify or use.
- **Visual hierarchy:** Links, labels, or actions that may not be easy to distinguish.
- **Image alternatives:** Images that may require further review of their alternative text.
- **Page structure:** Heading organization and the presence of important interface elements.
- **Control labeling:** Buttons and links whose visible text or labels may need further inspection.

These are potential issues to investigate, not guaranteed defects. Some checks require browser inspection or manual testing beyond a screenshot.

### 🌐 Website URL inspection with Playwright

Provide a public website URL to trigger a browser-based inspection.

The current implementation:

- Validates the URL format and checks for non-public network addresses.
- Opens the website in headless Chromium.
- Captures a browser screenshot.
- Collects selected page observations, including headings, images, buttons, and links.
- Sends the screenshot and observations to Gemma for analysis.

This supplements visual inspection with basic information extracted from the page.

### 🎯 Prioritized findings

Each finding is structured to help teams understand what to do next.

| Field | What it tells you |
|---|---|
| Issue | What may be wrong |
| Evidence | What was observed in the screenshot or page information |
| User impact | Who may be affected and how |
| Priority | High, Medium, or Low, as an initial triage |
| Recommended fix | A practical improvement to consider |
| Verification | How to check whether the issue has been resolved |

### 📄 Automatic PDF report generation

The agent is instructed to generate a PDF after a successful accessibility review, without requiring the user to request the report separately.

The report includes:

- Accessibility findings
- Supporting observations
- Potential impact on users
- Suggested remediation
- Verification guidance
- A reminder that findings require validation

The PDF is saved locally under `reports/accessibility_report.pdf`. The application also attempts to save a copy as an ADK artifact.

> **Implementation note:** PDF generation currently depends on the agent invoking the report-generation tool. For guaranteed report creation after every successful review, deterministic Python orchestration is a future reliability improvement.

### 🧠 Responsible AI analysis

AccessAble AI distinguishes visible evidence from assumptions.

It does not intentionally invent contrast ratios or claim to know keyboard navigation and screen-reader behavior from a screenshot alone.

The output is intended to guide further testing—not to certify accessibility compliance.

---

## 👥 Who Can Use It?

- **QA engineers:** Add accessibility-focused observations to existing testing workflows.
- **Developers:** Receive actionable suggestions before releasing changes.
- **UI/UX designers:** Identify potential visual usability concerns earlier.
- **Product managers:** Understand potential user impact and prioritize improvements.
- **Small teams and startups:** Get a starting point for accessibility reviews without beginning with a complex toolchain.

---

## 🏆 Why AccessAble AI?

Many accessibility workflows rely on specialist knowledge, dedicated testing tools, or manual inspection.

AccessAble AI explores a simpler entry point: **use a screenshot or public website URL to start an accessibility review and turn observations into a shareable report.**

Its value comes from combining:

- Visual AI analysis
- Browser-based website inspection
- Evidence-based findings
- User-impact explanations
- Actionable recommendations
- Verification guidance
- PDF report generation

This makes the output more useful than a list of suspected issues alone.

> **Hackathon vision:** Move accessibility feedback closer to the point where websites are designed, developed, and tested—so teams can discover potential barriers earlier and make more informed decisions.

---

## 🛠️ Technology Stack

- **Python** — Application logic, tool orchestration, and report generation
- **Google Agent Development Kit (ADK)** — Agent configuration and orchestration
- **Gemma** — Language model used for accessibility analysis
- **Google Gen AI SDK** — Sends screenshots and observations to the configured model
- **Playwright** — Browser automation, website inspection, and screenshot capture
- **ReportLab** — PDF report generation
- **ADK Web** — Local interface for interacting with the agent

---

## 🏗️ Project Structure

```text
accessable-ai/
├── .env                         # API key; do not commit
├── .gitignore                   # Excludes secrets and generated files
├── requirements.txt             # Python dependencies
├── reports/
│   ├── accessibility_report.pdf # Generated PDF report
│   └── screenshots/
│       └── website.png          # Captured website screenshot
└── accessable_ai/
    ├── __init__.py
    └── agent.py                 # Agent, inspection, and PDF tools
```

The `reports/` files are generated at runtime and may not exist until the application processes a request.

---

## 🚀 Installation and Setup

Follow these instructions to run AccessAble AI locally on macOS.

### Prerequisites

Install or prepare:

- Python version supported by your installed dependencies
- `pip`, Python's package installer
- Git
- PyCharm or another code editor
- A Google API key with access to the configured model
- Node.js and npm if you plan to customize the ADK Web frontend

> **Note:** If you encounter dependency installation errors with Python 3.15, use a stable Python version supported by the installed ADK, Google Gen AI SDK, Playwright, and ReportLab versions.

### Step 1: Clone the repository

Replace the example repository URL with your actual Git repository URL.

```bash
git clone <YOUR_REPOSITORY_URL>
cd accessable-ai
```

If you already have the project open in PyCharm, open its terminal at the outer `accessable-ai` project folder and continue to Step 2.

### Step 2: Create a virtual environment

```bash
python3 -m venv .venv
```

Activate it:

```bash
source .venv/bin/activate
```

Confirm Python is available:

```bash
python --version
```

### Step 3: Install dependencies

Make sure `requirements.txt` contains:

```text
google-adk==2.13.0
reportlab
playwright
```

Install the dependencies:

```bash
python -m pip install -r requirements.txt
```

Install Chromium for Playwright:

```bash
python -m playwright install chromium
```

Verify the ADK installation:

```bash
adk --version
```

### Step 4: Configure your Google API key

Obtain an API key through [Google AI Studio](https://aistudio.google.com/).

Create a file named `.env` in the outer `accessable-ai` directory:

```dotenv
GOOGLE_API_KEY=your_google_api_key_here
```

Replace the placeholder with your own key.

**Security reminders:**

- Never commit `.env` to Git.
- Never paste your API key into source code.
- Never publish your key in screenshots, logs, or public repositories.

Ensure your `.gitignore` includes:

```gitignore
.env
.venv/
__pycache__/
*.py[cod]
.DS_Store
reports/*.pdf
reports/screenshots/
```

### Step 5: Verify the agent configuration

Open `accessable_ai/agent.py` and confirm that:

- The agent is configured to use the intended Gemma model.
- The `review_website_url` tool is registered.
- The `create_accessibility_report` tool is registered.
- The local reports directory is created when needed.
- The agent instructions tell it to generate a report after a successful review.

The current model configuration is:

```python
MODEL_NAME = "gemma-4-26b-a4b-it"

root_agent = LlmAgent(
    name="accessable_ai",
    model=Gemini(model=MODEL_NAME),
    # Additional configuration and tools...
)
```

Model availability and image-input support depend on the provider and API access available to your account. If you receive a model-not-found, unsupported-input, or access error, verify the supported model identifier and capabilities before proceeding.

### Step 6: Start AccessAble AI

From the **outer project directory**, run:

```bash
adk web --port 8001
```

Open the local interface:

[http://localhost:8001](http://localhost:8001)

Select the `accessable_ai` agent if it appears in the application selector.

Keep the terminal running while you use the application.

> **Welcome-screen note:** The current agent instructions define a welcome message, but standard ADK Web does not automatically invoke the agent when a new chat opens. Showing a welcome screen and selectable options before the first message requires frontend customization.

---

## 🧪 How to Use It

### Option 1: Review a website URL

1. Start the ADK Web server.
2. Open the local interface.
3. Select `accessable_ai`.
4. Submit a public website URL.
5. Allow Playwright to inspect the website.
6. Review the findings returned by Gemma.
7. Check the `reports/` directory for the generated PDF.

Example prompt:

```text
Review https://example.com for accessibility issues.
Generate a PDF report with the findings and recommended fixes.
```

### Option 2: Review a screenshot

1. Open the ADK Web interface.
2. Upload a website screenshot through the chat interface.
3. Ask the agent to review the screenshot.
4. Review the findings and recommendations.
5. Check the `reports/` directory for the generated PDF.

Example prompt:

```text
Analyze this screenshot for potential visual accessibility issues.

Identify the three most important findings.
For each finding, provide:
- Evidence from the screenshot
- Potential user impact
- Priority
- Recommended fix
- How to verify the fix

Generate a PDF accessibility report.
```

### Example output

A review might flag:

- Body text that appears difficult to distinguish from its background
- Interactive elements whose visual affordances are unclear
- Images whose alternative-text requirements need further investigation

These are illustrative examples, not guaranteed findings. Actual results depend on the website, screenshot, and model output.

---

## 📁 Generated Files

The current implementation uses these paths:

| File | Purpose |
|---|---|
| `reports/accessibility_report.pdf` | Locally generated accessibility report |
| `reports/screenshots/website.png` | Screenshot captured during a URL review |

The current implementation uses fixed filenames, so a later review can overwrite the previous report and screenshot.

If the PDF is not created, inspect the ADK chat response and terminal logs. Confirm that the accessibility review succeeded and that the agent invoked `create_accessibility_report`.

---

## 📏 Important Limitations

AccessAble AI is a preliminary accessibility screening assistant, not a complete accessibility testing platform.

A screenshot alone cannot reliably establish:

- Exact text-to-background contrast ratios
- Actual clickable target dimensions
- Keyboard accessibility and focus order
- Screen-reader announcements and accessible names
- Correct semantic HTML and ARIA usage
- Full WCAG conformance

The URL inspection tool collects selected page observations but does not currently perform a comprehensive accessibility audit.

For a thorough review, combine this assistant with browser-based accessibility checks, keyboard-only testing, screen-reader testing, and applicable WCAG guidance.

The URL validation and request filtering are prototype safeguards. A production deployment should implement robust outbound network restrictions, redirect handling, and DNS protections.

Priorities generated by AI are initial triage recommendations, not a substitute for a formal risk assessment.

---

## 🔮 Future Roadmap

Potential next steps for the project include:

- **Custom welcome screen:** Display Screenshot and Website URL options when a new chat opens.
- **Reliable report orchestration:** Generate a PDF deterministically after every successful review.
- **Unique report filenames:** Retain a history of reports instead of overwriting previous results.
- **Automated accessibility checks:** Integrate established browser accessibility testing libraries.
- **Contrast verification:** Measure actual foreground and background colors where possible.
- **DOM-aware analysis:** Inspect accessible names, semantic elements, and interactive target dimensions.
- **WCAG mapping:** Link validated findings to relevant success criteria.
- **Regression detection:** Compare results across builds to identify newly introduced issues.
- **Developer-ready output:** Export findings in formats suitable for Jira or GitHub issues.
- **AI-assisted remediation:** Suggest code changes and help verify fixes.

These are proposed enhancements and are not necessarily implemented in the current version.

---

## 🤝 Contributing

Contributions and ideas are welcome.

1. Fork the repository.
2. Create a feature branch.
3. Make your changes.
4. Test your changes locally.
5. Open a pull request describing the problem solved and the validation performed.

Potential contribution areas include improving screenshot analysis, adding automated verification, improving report formatting, and expanding testing coverage.

---

## 📜 License

A license has not yet been specified. Add a `LICENSE` file before distributing the project under an open-source license.

---

## ❤️ Our Mission

**Accessibility should not be an afterthought.**

AccessAble AI aims to help teams notice potential accessibility barriers earlier, understand their impact, and take practical steps toward more inclusive digital experiences.

*Build with accessibility in mind. Detect potential barriers. Make the web more inclusive.*