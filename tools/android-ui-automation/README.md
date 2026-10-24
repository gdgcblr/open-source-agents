# Autonomous Android UI Automation Agent

## Problem Statement

Android UI automation typically requires users to manually define a sequence of low-level actions such as launching an application, finding UI elements, clicking buttons, entering text, navigating between screens, and verifying the resulting state.

While deterministic automation tools can execute these individual actions reliably, they do not understand the **intent behind a user's request** or determine which actions should be performed to achieve a goal.

For example, a user may provide a requirement such as:

> "Open Brave and search for youtube.com."

A traditional automation script requires the complete workflow to be predefined:

1. Launch Brave.
2. Find the search field.
3. Click the search field.
4. Enter `youtube.com`.
5. Press Enter.
6. Verify that navigation/search was successful.

This approach becomes difficult to maintain when the application state changes or when the required workflow is not known beforehand.

### Problem

There is a gap between:

- **What the user wants to achieve**, expressed in natural language.
- **The low-level Android actions** required to achieve that goal.

This project addresses that gap by introducing an **AI-powered orchestration layer using Google ADK**.

The deterministic Android automation tool remains responsible for safely interacting with the Android device, while the ADK agent is responsible for understanding the user's goal, deciding the next action, observing the result, and adapting the workflow when necessary.

---

## Solution

The **Autonomous Android UI Automation Agent** is a Google ADK-based agent that converts natural-language Android automation requirements into a sequence of executable UI actions.

The agent follows an:

**Observe → Act → Observe → Verify → Adapt**

loop.

### High-Level Architecture

```text
User Requirement
       │
       ▼
┌─────────────────────────┐
│    Google ADK Agent     │
│                         │
│  Understand Goal        │
│  Plan Next Action       │
│  Observe Result         │
│  Verify State           │
│  Recover / Adapt        │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Android Tool Adapters   │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Android UI Automation   │
│ Tool                    │
│                         │
│ ADB + UIAutomator       │
└────────────┬────────────┘
             │
             ▼
       Android Device
       / Emulator
```

The existing Android automation layer remains deterministic and does not contain LLM-based planning.

The ADK agent acts as the reasoning layer on top of it.

---

# Features

## 1. Natural Language Android Automation

Users can provide an Android task using natural language instead of manually defining every UI action.

Example:

```text
Open Brave and search for youtube.com.
```

The agent determines the required sequence of actions using the available Android automation tools.

---

## 2. Autonomous Action Planning

The agent determines the next action based on:

- User's requested goal
- Current Android application state
- UI hierarchy
- Previous tool results
- Verification results

The workflow is not hard-coded for a specific application.

For example:

```text
User Goal
   ↓
Inspect current state
   ↓
Launch application if required
   ↓
Inspect UI
   ↓
Find relevant element
   ↓
Perform action
   ↓
Observe result
   ↓
Verify state
   ↓
Continue / Recover / Complete
```

---

## 3. UI Hierarchy-Based Interaction

The agent uses the existing Android UI automation layer to inspect the UI hierarchy and identify elements.

Semantic selectors are preferred over screen coordinates.

The agent can work with selectors such as:

- Resource ID
- Exact text
- Content description
- Hint
- Partial text
- Class name
- Element index

This makes automation less dependent on fixed screen coordinates.

---

## 4. Adaptive UI Navigation

The agent does not assume that the Android device is always in a particular state.

Before performing an action, it can inspect the current state and determine what needs to happen next.

For example, if the requested application is not currently open:

```text
Inspect state
    ↓
Application not running
    ↓
Launch application
    ↓
Inspect UI again
```

Similarly, if an expected element is not immediately available, the agent can inspect the UI and determine an alternative action rather than blindly executing a predefined sequence.

---

## 5. Tool-Result-Driven Execution

Every Android action produces a structured result from the underlying automation layer.

The agent uses these results to determine what to do next.

Example:

```text
Tool:
    click_element("Search")

Result:
    success = true

Agent:
    Continue to input text
```

or:

```text
Tool:
    click_element("Search")

Result:
    success = false
    error = ELEMENT_NOT_FOUND

Agent:
    Inspect UI hierarchy
    Find alternative selector
    Retry with controlled recovery
```

This creates a feedback loop between reasoning and execution.

---

## 6. Action Verification

The agent distinguishes between:

> **An action being executed successfully**

and:

> **The user's intended result being achieved.**

For example, a tap operation may succeed at the ADB level, but the expected screen may not appear.

The agent can therefore use UI state verification after important actions.

Supported verification signals include:

- Expected text
- Expected resource ID
- Expected activity
- UI hierarchy state
- Tool execution result

---

## 7. Recovery and Controlled Retries

When an action fails, the agent can analyze the failure and attempt a controlled recovery.

Example:

```text
Find search field
      ↓
Element not found
      ↓
Inspect UI hierarchy
      ↓
Identify alternative selector
      ↓
Retry action
```

Retries are bounded to prevent infinite loops.

The agent also supports configurable limits for:

- Maximum retries
- Maximum tool calls

---

## 8. Handling Inconclusive Verification

Android UI frameworks may not always expose the latest UI state through the UI hierarchy.

For example, text input may successfully reach an Android application while the entered value cannot be read back from the UI hierarchy.

The agent therefore distinguishes between:

```text
Action failed
```

and:

```text
Action executed but verification is inconclusive
```

Instead of immediately abandoning the workflow, the agent can observe the resulting application state and determine whether the overall task has progressed successfully.

---

## 9. Semantic Selector Preference

The agent follows a selector preference hierarchy to improve automation reliability.

Preferred order:

```text
Resource ID
    ↓
Exact text
    ↓
Content description
    ↓
Hint
    ↓
Partial text
    ↓
Class / index
    ↓
Raw coordinates
```

The agent should prefer stable semantic identifiers whenever available.

---

## 10. Safety Controls

The agent is designed to operate within the available Android automation tools rather than exposing arbitrary shell execution to the LLM.

Safety controls include:

- Limited tool access
- Maximum tool-call limits
- Maximum retry limits
- No arbitrary shell commands exposed as agent tools
- Avoidance of destructive actions unless explicitly requested
- Structured tool responses
- Configurable logging

---

## 11. Reusable Android Automation Tool Layer

The agent does not implement ADB operations itself.

Instead, it uses the existing deterministic Android UI automation layer:

```text
agents/android-automation-agent/
              │
              ▼
tools/android-ui-automation/
              │
              ▼
             ADB
              │
              ▼
       Android Device
```

This separation provides a clear responsibility boundary:

### Android Automation Tool

> **Knows how to operate Android.**

Responsible for:

- ADB communication
- Device interaction
- Application launch
- UI inspection
- Clicking
- Text input
- Navigation
- Screenshots
- State verification

### ADK Agent

> **Knows what to do.**

Responsible for:

- Understanding user intent
- Deciding the next action
- Selecting appropriate tools
- Observing results
- Adapting to failures
- Determining whether the overall goal has been achieved

---

# Example

### User

```text
Open Brave and search for youtube.com.
```

### Agent

```text
1. Inspect Android device
2. Launch Brave
3. Inspect UI hierarchy
4. Identify the search field
5. Click the search field
6. Enter youtube.com
7. Press Enter
8. Observe resulting state
9. Verify that navigation/search was completed
```

The exact sequence is determined dynamically by the agent based on the current device state and tool responses.

---

# Technical Stack

- Python 3.9+
- Google ADK
- Gemini
- Android ADB
- Android UIAutomator
- Existing Android UI Automation Tool
- python-dotenv

---

# Project Structure

```text
agents/android-automation-agent/
├── README.md
├── .env.example
├── .gitignore
├── requirements.txt
├── src/
│   ├── __init__.py
│   ├── __main__.py
│   ├── agent.py
│   ├── prompts.py
│   ├── tools.py
│   ├── callbacks.py
│   └── config.py
└── tests/
    └── test_smoke.py
```

---

# Configuration

The agent is configured using environment variables.

Example:

```env
GOOGLE_API_KEY=
GOOGLE_GENAI_USE_VERTEXAI=FALSE

AGENT_MODEL=gemini-flash-latest
AGENT_MAX_RETRIES=2
AGENT_MAX_TOOL_CALLS=40
AGENT_LOG_LEVEL=INFO
AGENT_LOG_TYPED_TEXT=false

ANDROID_AUTOMATION_PATH=../../tools/android-ui-automation

ADB_PATH=adb
ANDROID_DEVICE_ID=

COMMAND_TIMEOUT_SECONDS=30
UI_WAIT_TIMEOUT_SECONDS=5
```

Secrets such as API keys should be stored in `.env` and must not be committed to the repository.

---

# Running the Agent

### Install dependencies

```bash
cd agents/android-automation-agent

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

### Configure environment

```bash
cp .env.example .env
```

Configure the required API key and Android device settings.

### Run

```bash
python -m src "Open Brave and search for youtube.com."
```

The agent requires an Android emulator or physical Android device with ADB connectivity.

---

# Current Scope

This PR focuses on establishing the AI orchestration layer for Android UI automation.

### Included

- Google ADK agent
- Natural-language task execution
- Android automation tool integration
- UI hierarchy inspection
- Semantic element selection
- Application launch/navigation
- Click actions
- Text input
- State verification
- Tool-result-driven decision making
- Controlled retries
- Tool-call limits
- Basic safety controls
- Structured logging/configuration
- Smoke-test structure

### Not Included

The following are intentionally outside the scope of this PR:

- Computer vision
- OCR
- Screenshot-based visual reasoning
- APK malware/security analysis
- Network interception
- Android bug detection
- Multi-agent orchestration
- Long-term workflow memory
- Autonomous arbitrary shell execution

These can be introduced as separate capabilities in future iterations.

---

# Limitations

The current implementation inherits limitations from the underlying Android UI automation layer.

These include:

- UIAutomator hierarchy limitations
- Limited support for custom WebView/Canvas-based interfaces
- Limited visibility into some Jetpack Compose/custom UI implementations
- ASCII-oriented text input
- Password field values cannot be read back
- Off-screen elements may require scrolling
- One Android device is supported at a time
- No computer-vision or OCR fallback

---

# Acceptance Test

The primary end-to-end acceptance test for this agent is:

```text
Open Brave and search for youtube.com.
```

Expected behavior:

1. Agent understands the requested goal.
2. Agent identifies the required Android actions.
3. Brave is launched.
4. The search field is identified using the UI hierarchy.
5. `youtube.com` is entered.
6. Search/navigation is triggered.
7. The resulting state is observed.
8. The agent determines whether the requested task was completed.
9. The agent reports the final result to the user.

---

# Future Improvements

Potential future extensions include:

- Screenshot-based visual reasoning
- OCR support
- More advanced UI element matching
- Fuzzy element identification
- Better handling of WebView/Compose/custom UI
- Workflow memory
- Reusable automation workflows
- Multi-agent orchestration
- Android application behavioral analysis
- Autonomous application testing
- APK behavioral investigation
- Cross-version behavioral comparison

---

# Design Principle

The project follows a clear separation of responsibilities:

> **The automation tool knows how to operate Android.  
> The ADK agent knows what the user wants to accomplish.**

This allows the deterministic automation layer to remain reusable while the AI layer provides flexible, goal-oriented orchestration.