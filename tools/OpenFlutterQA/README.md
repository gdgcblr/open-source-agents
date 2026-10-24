# OpenFlutterQA

> An AI-powered Flutter QA automation plugin and visual test studio for generating test cases from PRDs and Figma specs, refining natural-language steps into deterministic `flutter_test` assertions, and tracking suite analytics.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Writing and maintaining Flutter widget and integration tests across evolving PRDs and Figma designs is tedious and brittle. Manual QA steps are often ambiguous (e.g., *"Navigate to the bookmarks tab"*), leading to flaky automation scripts and disconnected test analytics.
- **Intended Users**: Flutter developers, mobile QA automation engineers, and product teams who want an in-app or standalone visual studio to generate, refine, execute, and export Flutter automation tests.

### Key Features
- **Visual QA Automation Dashboard**: Dark-themed studio featuring a **Test Suites** manager, **Donut Summary Ring** (`Total Tests`, `Blocked`, `Passed`, `Failed`), **Weekly Test Runs** stacked bar chart with interactive daily tooltips, and **Test Details** environment configuration (`Host`, `Build`, `Device Source` such as `LambdaTest`, and target `Devices`).
- **AI Test Step Refinement (`✨ Refine with AI` & `✏️ Edit Manually`)**: Select any natural-language test step in the step inspector and refine it with Google Gemini (or the built-in offline Mock AI Engine) into unambiguous Flutter `Finder` expressions and `WidgetTester` commands.
- **PRD & Figma Test Case Generator**: Generate structured test cases directly from attached PRD documents and Figma page references.
- **Embeddable In-App Plugin Overlay (`OpenFlutterQAWrapper`)**: Wrap any existing Flutter application with `OpenFlutterQAWrapper` to launch the QA Studio overlay directly on top of a running app, or export test cases to standard `flutter_test` Dart code.

---

## Technical Stack

- **Language & Runtime**: Dart 3.5+ / Flutter 3.24+
- **Agent Framework / Core Library**: Custom Flutter Plugin & Visual Studio (`open_flutter_qa`) + REST AI Client (`http`)
- **Models**: Google Gemini (`gemini-2.5-flash`) with built-in deterministic Mock AI Provider fallback for zero-key offline usage
- **External APIs / Tools**: Google Generative Language API (`generativelanguage.googleapis.com`), Flutter `flutter_test` framework

---

## Architecture & Data Flow

```
[PRD & Figma Specs / User Step Selection]
                   |
                   v
       [OpenFlutterQADashboard / CLI]
                   |
                   +--> [AiQaService] --> (Gemini API or Deterministic Mock Provider)
                   |          |
                   |          +--> Refined TestStep + Flutter Finder & WidgetTester Code
                   |
                   +--> [TestExecutionEngine] --> Runs Selected Suites & Updates Telemetry
                              |
                              v
     [Donut Ring Summary + Weekly Bar Chart + Exportable flutter_test Dart Script]
```

---

## Prerequisites

Before running this project, ensure you have:
- **Flutter SDK** (`>=3.24.0`) and **Dart SDK** (`>=3.5.0`)
- *(Optional)* A **Google Gemini API Key** (`GEMINI_API_KEY`) for live LLM generation; if omitted, the tool automatically uses its built-in deterministic Mock AI Engine.

---

## Installation & Setup

1. **Navigate to the project directory:**
   ```bash
   cd tools/OpenFlutterQA
   ```

2. **Install Dart / Flutter dependencies:**
   ```bash
   flutter pub get
   ```

3. **Configure Environment Variables (Optional):**
   Copy the example environment file and fill in your Gemini API key if using live model calls:
   ```bash
   # Linux/macOS:
   cp .env.example .env

   # Windows (PowerShell):
   Copy-Item .env.example -Destination .env
   ```

---

## Configuration & Environment Variables

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | No | *Mock Fallback* | Google Gemini API key for live AI test generation and step refinement |
| `MODEL_NAME` | No | `gemini-2.5-flash` | Gemini model identifier |
| `DEVICE_SOURCE` | No | `LambdaTest` | Default device cloud or runner label shown in Test Details |
| `DEFAULT_DEVICE` | No | `iPhone 14, Pixel 8 Pro` | Default target device list |
| `LOG_LEVEL` | No | `info` | Logging verbosity (`debug`, `info`, `warn`, `error`) |

---

## How to Run

### 1. Run the Headless CLI / Code Generator
You can verify AI step refinement, PRD test generation, and `flutter_test` code export directly in your terminal:
```bash
dart run bin/open_flutter_qa.dart
```

### 2. Run the Visual Flutter Studio App
Launch the interactive dark-theme QA Automation Studio on Desktop (Windows/macOS/Linux) or Web (Chrome):
```bash
# Run on Chrome / Web:
flutter run -d chrome -t lib/main.dart

# Or on Windows Desktop (if Visual Studio C++ workload is installed):
flutter run -d windows -t lib/main.dart

# Pass a live Gemini API key via --dart-define (optional):
flutter run -d chrome -t lib/main.dart --dart-define=GEMINI_API_KEY=your_key_here
```

### 3. Embed as a Plugin Overlay in Any Flutter App
```dart
import 'package:flutter/material.dart';
import 'package:open_flutter_qa/open_flutter_qa.dart';

void main() {
  runApp(
    const MaterialApp(
      home: OpenFlutterQAWrapper(
        child: MyProductionApp(),
      ),
    ),
  );
}
```

---

## Example Input & Output

### Example Input (Selecting Step #4 & Clicking `Refine with AI` or running `dart run bin/open_flutter_qa.dart`)
```text
Test Case : Verify Bookmark Status Reflecting Properly
Step #4   : "Navigate to the bookmarks tab or page using the navigation menu."
PRD Spec  : very_long_file_name_v3_final.pdf
Figma Spec: NewsFeed/BookmarksPage
```

### Example Output
```text
==========================================================
 OpenFlutterQA - AI Test Automation CLI & Code Generator
 Provider: Deterministic Mock AI Engine (Offline Ready)
==========================================================

1. Refining Test Step #4 with AI...
   Test Case : Verify Bookmark Status Reflecting Properly
   Before    : Navigate to the bookmarks tab or page using the navigation menu.
   After     : Tap the "Bookmarks" BottomNavigationBar tab (Key: nav_bookmarks_tab) and wait for the BookmarksPage route animation to settle.
   Finder    : find.byKey(const Key('nav_bookmarks_tab'))

2. Generating Test Cases from PRD & Figma Spec...
   [+] Validate Offline Sync & Bookmark Badge State Consistency (NewsFeed/BookmarksPage) (3 steps)
   [+] Verify Deep-Link & Empty Bookmark Fallback (very_long_file_name_v3_final.pdf) (2 steps)

3. Exporting Flutter Integration Test Script:

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('Verify Bookmark Status Reflecting Properly', (WidgetTester tester) async {
    // Step 1: Navigate to the home page.
    await tester.pumpAndSettle();
...
```

---

## How to Test

Run the automated Flutter unit and widget test suite from `tools/OpenFlutterQA`:

```bash
# 1. Static analysis check
flutter analyze

# 2. Run unit and widget tests (verifies UI cards, charts, AI step refinement, and wrapper overlay)
flutter test

# 3. Run CLI smoke test
dart run bin/open_flutter_qa.dart
```

---

## Known Limitations

- Live device cloud execution (`LambdaTest` / `Firebase Test Lab`) is simulated in the local studio UI unless exported via `Export Flutter Test` and executed in a CI pipeline.
- When `GEMINI_API_KEY` is not provided, the tool uses its deterministic local rule engine so all features remain testable offline.

---

## Security & Privacy Considerations

- **Secrets Handling**: API keys are loaded via `.env` (in CLI mode) or `--dart-define` (in Flutter app mode). `.env` is ignored via `.gitignore` and never committed.
- **Data Privacy**: When `GEMINI_API_KEY` is configured, only the selected test case title, step text, and PRD/Figma metadata strings are sent to the Google Gemini API. No telemetry is collected.
- **Safety**: Generated `flutter_test` code is displayed for developer inspection and clipboard copy; the tool never executes arbitrary shell commands.

---

## Future Improvements

- [ ] Add live widget tree element picker with visual bounding-box inspection.
- [ ] Add direct REST webhook integration for triggering LambdaTest / Firebase Test Lab builds.
- [ ] Support local open-weights models via Ollama (`http://localhost:11434`).

---

## License

*This project is contributed under the repository's open-source license.*
