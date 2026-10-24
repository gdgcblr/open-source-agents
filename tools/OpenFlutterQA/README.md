# OpenFlutterQA

> An AI-powered Flutter QA automation plugin and visual test studio for generating test cases from PRDs and Figma specs, refining natural-language steps into deterministic `flutter_test` assertions, and tracking suite analytics.

---

## Overview

### Problem Statement & Intended Users
- **Problem**: Writing and maintaining Flutter widget and integration tests across evolving PRDs and Figma designs is tedious and brittle. Manual QA steps are often ambiguous (e.g., *"Navigate to the bookmarks tab"*), leading to flaky automation scripts and disconnected test analytics.
- **Intended Users**: Flutter developers, mobile QA automation engineers, and product teams who want an in-app or standalone visual studio to generate, refine, execute, and export Flutter automation tests.

### Key Features
- **Visual QA Automation Dashboard**: Dark-themed studio featuring a **Test Suites** manager (`1. New Login Feature`, `2. Cart Offer`, `4. Selection drop test`, `1. Selection Group`), **Donut Summary Ring** (`47 Total Tests`, `0 Blocked`, `39 Passed`, `8 Failed`), **Weekly Test Runs** stacked bar chart with interactive daily tooltips (`Jun 5`), and **Test Details** environment configuration (`Host`, `Build`, `Device Source` such as `LambdaTest`, and target `Devices`).
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

Before installing and running `OpenFlutterQA`, ensure your development machine meets the following requirements:

1. **Flutter SDK (`>=3.24.0`) & Dart SDK (`>=3.5.0`)**
   - Verify your installation:
     ```bash
     flutter --version
     dart --version
     ```
2. **Target Platform Support (for Visual Studio UI mode)**
   - **Web**: Google Chrome or Microsoft Edge installed (`flutter config --enable-web`), **or**
   - **Desktop**: Windows (`flutter config --enable-windows-desktop`), macOS, or Linux desktop toolchain.
   - *(Note: Headless CLI execution and `flutter test` require only the Flutter/Dart SDK and work without a display server or desktop C++ compiler.)*
3. **Google Gemini API Key (Optional)**
   - Obtain an API key from [Google AI Studio](https://aistudio.google.com/) if you want live LLM generation.
   - **Zero-Key Offline Mode**: If `GEMINI_API_KEY` is omitted or left as the placeholder, `OpenFlutterQA` automatically uses its deterministic Mock AI Engine so all features work out of the box.

---

## Installation & Setup

1. **Clone the repository and navigate to the tool directory:**
   ```bash
   cd tools/OpenFlutterQA
   ```

2. **Fetch Dart and Flutter package dependencies:**
   ```bash
   flutter pub get
   ```

3. **Set up your local environment file:**
   ```bash
   # On Linux / macOS:
   cp .env.example .env

   # On Windows (PowerShell):
   Copy-Item .env.example -Destination .env
   ```

---

## Configuration & Environment Variables

Open `.env` and configure any desired settings. `.env` is git-ignored so your credentials remain private.

| Variable Name | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | No | *Mock Fallback* | Google Gemini API key for live AI test generation and step refinement |
| `MODEL_NAME` | No | `gemini-2.5-flash` | Identifier for the Gemini model used by `AiQaService` |
| `TEMPERATURE` | No | `0.3` | Sampling temperature for AI test step refinement |
| `DEVICE_SOURCE` | No | `LambdaTest` | Default device cloud or runner label displayed in **Test Details** |
| `DEFAULT_DEVICE` | No | `iPhone 14, Pixel 8 Pro` | Default target device list displayed in **Test Details** |
| `TARGET_HOST` | No | `Staging_v2.4` | Target host environment label |
| `LOG_LEVEL` | No | `info` | Logging verbosity (`debug`, `info`, `warn`, `error`) |

---

## How to Run (Sample Invocation & Usage)

### 1. Headless CLI Invocation (Terminal / CI)
Run the CLI generator to refine test steps with AI, generate test cases from PRD/Figma specs, and output a runnable `flutter_test` script:

```bash
# Default invocation (uses seed Bookmark test case & PRD/Figma specs):
dart run bin/open_flutter_qa.dart

# Custom CLI arguments:
dart run bin/open_flutter_qa.dart \
  --step "Navigate to the bookmarks tab or page using the navigation menu." \
  --prd "checkout_flow_prd_v3.pdf" \
  --figma "ECommerce/CartScreen"

# View CLI help options:
dart run bin/open_flutter_qa.dart --help
```

### 2. Standalone Visual QA Automation Studio
Launch the interactive dark-mode Flutter application matching the studio dashboard:

```bash
# Run on Chrome (Web):
flutter run -d chrome -t lib/main.dart

# Run on Windows Desktop:
flutter run -d windows -t lib/main.dart

# Optional: Pass a live Gemini API key at runtime via --dart-define:
flutter run -d chrome -t lib/main.dart --dart-define=GEMINI_API_KEY=your_actual_api_key
```

**Interactive Studio Workflow:**
1. In **Test Suites** (top-left), toggle checkboxes for suites such as `1. New Login Feature` or `4. Selection drop test`.
2. In **Test Runs** (bottom-left), click any weekday bar (`Mon`–`Fri`) to inspect passed vs. failed counts in the floating tooltip.
3. In **TEST CASES** (bottom-right), expand a test case (e.g., `Verify Bookmark Status Reflecting Properly`), click step `4. Navigate to the bookmarks tab or page using the navigation menu.`, and click **`✨ Refine with AI`** or **`✏️ Edit Manually`**.
4. Click **`Generate from PRD`** in the right sidebar to synthesize new test cases from the attached PRD and Figma specs.
5. Click **`Run Suite`** in the top bar to execute selected test cases and watch the **Donut Summary Ring** update live, or click **`Export Flutter Test`** to copy the generated `flutter_test` Dart code.

### 3. Embeddable Plugin Usage in Any Host Flutter App
Import `package:open_flutter_qa/open_flutter_qa.dart` and wrap your app with `OpenFlutterQAWrapper` to inspect and run QA suites directly inside your app:

```dart
import 'package:flutter/material.dart';
import 'package:open_flutter_qa/open_flutter_qa.dart';

void main() {
  runApp(
    const MaterialApp(
      debugShowCheckedModeBanner: false,
      home: OpenFlutterQAWrapper(
        enabled: true,
        initiallyOpen: false, // Renders a floating "QA Studio" FAB over your app
        child: MyHostApplication(),
      ),
    ),
  );
}
```

---

## Example Input & Output

### Example Input
```bash
dart run bin/open_flutter_qa.dart \
  --step "Navigate to the bookmarks tab or page using the navigation menu." \
  --prd "very_long_file_name_v3_final.pdf" \
  --figma "NewsFeed/BookmarksPage"
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

    // Step 2: Select a news article to open its details.
    await tester.tap(find.byKey(Key('news_article_card_0')));

    // Step 3: Click the bookmark button on the article detail screen.
    await tester.tap(find.byKey(Key('bookmark_toggle_btn')));

    // Step 4: Tap the "Bookmarks" BottomNavigationBar tab (Key: nav_bookmarks_tab) and wait for the BookmarksPage route animation to settle.
    await tester.tap(find.byKey(const Key('nav_bookmarks_tab')));
    await tester.pumpAndSettle();

    // Step 5: Verify that the selected article appears on the bookmarks page.
    expect(find.byKey(Key('bookmarked_item_0')), findsOneWidget);

  });
}
```

---

## How to Test

Follow these steps to verify static analysis, unit/widget tests, CLI execution, and repository hygiene from a clean environment:

```bash
# 1. Navigate to the project folder and install dependencies
cd tools/OpenFlutterQA
flutter pub get

# 2. Run Dart/Flutter static analysis (expects: "No issues found!")
flutter analyze

# 3. Run the automated unit & widget test suite (expects: 6/6 tests passing)
flutter test

# 4. Run the headless CLI smoke test (verifies offline AI refinement & code export)
dart run bin/open_flutter_qa.dart

# 5. Verify no secrets, build artifacts, or .env files are tracked by Git
git status -uall
```

### What the Automated Test Suite (`test/open_flutter_qa_test.dart`) Verifies
1. **Default Summary Metrics**: Confirms `47 Total Tests`, `39 Passed`, `8 Failed`, and `0 Blocked` seed telemetry.
2. **AI Step Refinement**: Verifies `AiQaService.refineTestStep` transforms natural-language Step #4 into a deterministic instruction with `find.byKey(const Key('nav_bookmarks_tab'))`.
3. **Code Export**: Verifies `AiQaService.exportToFlutterTestCode` produces valid `flutter_test` `testWidgets` code.
4. **Dashboard Widget Rendering**: Pumps `OpenFlutterQADashboard` and asserts all cards (`Test Suites`, `Test Details`, `LambdaTest`, `Test Runs`, `Jun 5`, `Test Steps`, `Refine with AI`, `Edit Manually`) render without layout overflow.
5. **Interactive AI Refinement in UI**: Taps `Refine with AI` (`Key('refine_with_ai_btn')`) and verifies the step card updates in place with the `Finder` expression.
6. **Plugin Wrapper Overlay**: Pumps `OpenFlutterQAWrapper` around a host app, taps the floating `QA Studio` button (`Key('open_qa_studio_fab')`), and confirms the studio overlay opens.

---

## Known Limitations

- Live cloud device execution (`LambdaTest` / `Firebase Test Lab`) is simulated locally in the dashboard UI unless exported via **Export Flutter Test** and executed in a CI runner.
- When `GEMINI_API_KEY` is not provided, the tool uses its deterministic local rule engine so all features remain testable offline without external network calls.

---

## Security & Privacy Considerations

- **Secrets Handling**: API keys are loaded via `.env` (in CLI mode) or `--dart-define` (in Flutter UI mode). `.env` is listed in `.gitignore` and never committed.
- **Data Privacy**: When `GEMINI_API_KEY` is configured, only the selected test case title, step text, and PRD/Figma metadata strings are sent to the Google Gemini API.
- **Safety**: Generated `flutter_test` code is displayed for developer review and clipboard copy; the tool never executes arbitrary shell commands.

---

## Future Improvements

- [ ] Add live widget tree element picker with visual bounding-box inspection.
- [ ] Add direct REST webhook integration for triggering LambdaTest / Firebase Test Lab builds.
- [ ] Support local open-weights models via Ollama (`http://localhost:11434`).

---

## License

*This project is contributed under the repository's open-source license.*
