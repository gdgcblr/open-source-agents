import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/qa_models.dart';

class AiQaService {
  final String? apiKey;
  final String modelName;
  final http.Client _httpClient;

  AiQaService({
    String? apiKey,
    this.modelName = const String.fromEnvironment(
      'MODEL_NAME',
      defaultValue: 'gemini-2.5-flash',
    ),
    http.Client? httpClient,
  })  : apiKey = apiKey ??
            const String.fromEnvironment(
              'GEMINI_API_KEY',
              defaultValue: '',
            ),
        _httpClient = httpClient ?? http.Client();

  bool get hasLiveApiKey {
    final key = apiKey?.trim() ?? '';
    return key.isNotEmpty && key != 'your_gemini_api_key_here';
  }

  /// Refines a single [TestStep] using Gemini AI (or deterministic fallback)
  /// to include unambiguous UI navigation criteria and Flutter WidgetTester code.
  Future<TestStep> refineTestStep({
    required TestCase testCase,
    required TestStep step,
    String? customPrompt,
  }) async {
    if (hasLiveApiKey) {
      try {
        final uri = Uri.parse(
          'https://generativelanguage.googleapis.com/v1beta/models/$modelName:generateContent?key=$apiKey',
        );
        final prompt = '''
You are an expert Flutter QA automation engineer.
Refine step #${step.index} of test case "${testCase.title}".
Original step: "${step.instruction}"
${customPrompt != null ? 'User guidance: $customPrompt\n' : ''}
Respond strictly in JSON with keys:
- "instruction": Clear, deterministic QA test step instruction (1-2 sentences).
- "expectedFinder": Flutter Finder expression (e.g. find.byKey(Key('nav_bookmarks_tab'))).
- "flutterAction": Flutter WidgetTester command (e.g. await tester.tap(...); await tester.pumpAndSettle();).
''';
        final response = await _httpClient
            .post(
              uri,
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode({
                'contents': [
                  {
                    'parts': [
                      {'text': prompt}
                    ]
                  }
                ],
                'generationConfig': {
                  'temperature': 0.2,
                  'responseMimeType': 'application/json',
                },
              }),
            )
            .timeout(const Duration(seconds: 12));

        if (response.statusCode == 200) {
          final decoded = jsonDecode(response.body) as Map<String, dynamic>;
          final text = decoded['candidates']?[0]?['content']?['parts']?[0]
              ?['text'] as String?;
          if (text != null && text.isNotEmpty) {
            final stepJson = jsonDecode(text) as Map<String, dynamic>;
            return step.copyWith(
              instruction:
                  (stepJson['instruction'] as String?) ?? step.instruction,
              expectedFinder:
                  (stepJson['expectedFinder'] as String?) ?? step.expectedFinder,
              flutterAction:
                  (stepJson['flutterAction'] as String?) ?? step.flutterAction,
              isRefinedByAi: true,
            );
          }
        }
      } catch (_) {
        // Fall through to deterministic local refinement if offline or rate-limited
      }
    }

    // Deterministic intelligent mock refinement
    await Future<void>.delayed(const Duration(milliseconds: 350));
    final lower = step.instruction.toLowerCase();

    if (lower.contains('bookmark') && lower.contains('navigat')) {
      return step.copyWith(
        instruction:
            'Tap the "Bookmarks" BottomNavigationBar tab (Key: nav_bookmarks_tab) and wait for the BookmarksPage route animation to settle.',
        expectedFinder: "find.byKey(const Key('nav_bookmarks_tab'))",
        flutterAction:
            "await tester.tap(find.byKey(const Key('nav_bookmarks_tab')));\nawait tester.pumpAndSettle();",
        isRefinedByAi: true,
      );
    } else if (lower.contains('bookmark') && lower.contains('click')) {
      return step.copyWith(
        instruction:
            'Tap the article bookmark IconButton (Key: bookmark_toggle_btn) and assert the icon transitions from Icons.bookmark_border to Icons.bookmark.',
        expectedFinder: "find.byKey(const Key('bookmark_toggle_btn'))",
        flutterAction:
            "await tester.tap(find.byKey(const Key('bookmark_toggle_btn')));\nawait tester.pump();\nexpect(find.byIcon(Icons.bookmark), findsOneWidget);",
        isRefinedByAi: true,
      );
    } else if (lower.contains('home page')) {
      return step.copyWith(
        instruction:
            'Pump the root MaterialApp widget tree and verify the HomeFeedScreen scaffold and primary AppBar are visible.',
        expectedFinder: "find.byKey(const Key('home_screen'))",
        flutterAction:
            "await tester.pumpWidget(const MyApp());\nawait tester.pumpAndSettle();\nexpect(find.byKey(const Key('home_screen')), findsOneWidget);",
        isRefinedByAi: true,
      );
    } else if (lower.contains('verify') && lower.contains('bookmark')) {
      return step.copyWith(
        instruction:
            'Verify the saved article ListTile is rendered inside the Bookmarks list with matching article title and non-empty state.',
        expectedFinder: "find.byKey(const Key('bookmarked_item_0'))",
        flutterAction:
            "expect(find.byKey(const Key('bookmarked_item_0')), findsOneWidget);",
        isRefinedByAi: true,
      );
    }

    return step.copyWith(
      instruction:
          '${step.instruction} [AI Refined: Assert target widget is visible and wait for frame settle]',
      expectedFinder:
          step.expectedFinder ?? "find.byKey(const Key('step_${step.index}_target'))",
      flutterAction: step.flutterAction ??
          "await tester.tap(find.byKey(const Key('step_${step.index}_target')));\nawait tester.pumpAndSettle();",
      isRefinedByAi: true,
    );
  }

  /// Generates new [TestCase] entries from PRD and Figma specifications.
  Future<List<TestCase>> generateTestCasesFromSpec({
    required String prdDocument,
    required String figmaSpec,
    String? featurePrompt,
  }) async {
    if (hasLiveApiKey) {
      try {
        final uri = Uri.parse(
          'https://generativelanguage.googleapis.com/v1beta/models/$modelName:generateContent?key=$apiKey',
        );
        final prompt = '''
Generate 2 Flutter QA automation test cases based on:
- PRD Document: $prdDocument
- Figma Spec: $figmaSpec
- Focus Area: ${featurePrompt ?? 'Core user flows & edge cases'}

Respond strictly in JSON array format where each object has:
- "title": string
- "steps": array of strings (4-5 actionable test steps)
''';
        final response = await _httpClient
            .post(
              uri,
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode({
                'contents': [
                  {
                    'parts': [
                      {'text': prompt}
                    ]
                  }
                ],
                'generationConfig': {
                  'temperature': 0.3,
                  'responseMimeType': 'application/json',
                },
              }),
            )
            .timeout(const Duration(seconds: 12));

        if (response.statusCode == 200) {
          final decoded = jsonDecode(response.body) as Map<String, dynamic>;
          final text = decoded['candidates']?[0]?['content']?['parts']?[0]
              ?['text'] as String?;
          if (text != null && text.isNotEmpty) {
            final list = jsonDecode(text) as List<dynamic>;
            final now = DateTime.now().millisecondsSinceEpoch;
            return list.asMap().entries.map((entry) {
              final map = entry.value as Map<String, dynamic>;
              final rawSteps = (map['steps'] as List<dynamic>? ?? []);
              return TestCase(
                id: 'tc-ai-$now-${entry.key}',
                title: (map['title'] as String?) ?? 'AI Generated Test Case',
                status: TestStatus.ready,
                steps: rawSteps.asMap().entries.map((s) {
                  return TestStep(
                    index: s.key + 1,
                    instruction: s.value.toString(),
                    isRefinedByAi: true,
                  );
                }).toList(),
              );
            }).toList();
          }
        }
      } catch (_) {
        // Fallback to deterministic generator below
      }
    }

    await Future<void>.delayed(const Duration(milliseconds: 450));
    final topic = (featurePrompt != null && featurePrompt.trim().isNotEmpty)
        ? featurePrompt.trim()
        : 'Offline Sync & Bookmark Badge';
    final timestamp = DateTime.now().millisecondsSinceEpoch % 10000;

    return [
      TestCase(
        id: 'tc-ai-$timestamp-1',
        title: 'Validate $topic State Consistency ($figmaSpec)',
        status: TestStatus.ready,
        steps: const [
          TestStep(
            index: 1,
            instruction: 'Launch app and wait for initial feed hydration.',
            expectedFinder: "find.byKey(const Key('home_screen'))",
            flutterAction: 'await tester.pumpAndSettle();',
            isRefinedByAi: true,
          ),
          TestStep(
            index: 2,
            instruction:
                'Trigger bookmark action on primary card and verify optimistic UI badge update.',
            expectedFinder: "find.byKey(const Key('bookmark_badge_count'))",
            flutterAction:
                "await tester.tap(find.byKey(const Key('bookmark_toggle_btn')));\nawait tester.pump();",
            isRefinedByAi: true,
          ),
          TestStep(
            index: 3,
            instruction:
                'Open Bookmarks tab and verify item order matches PRD specification.',
            expectedFinder: "find.byKey(const Key('nav_bookmarks_tab'))",
            flutterAction:
                "await tester.tap(find.byKey(const Key('nav_bookmarks_tab')));\nawait tester.pumpAndSettle();",
            isRefinedByAi: true,
          ),
        ],
      ),
      TestCase(
        id: 'tc-ai-$timestamp-2',
        title: 'Verify Deep-Link & Empty Bookmark Fallback ($prdDocument)',
        status: TestStatus.draft,
        steps: const [
          TestStep(
            index: 1,
            instruction: 'Navigate directly to Bookmarks tab with empty storage.',
            isRefinedByAi: true,
          ),
          TestStep(
            index: 2,
            instruction:
                'Verify empty-state illustration and CTA button match Figma component.',
            isRefinedByAi: true,
          ),
        ],
      ),
    ];
  }

  /// Generates runnable Flutter `flutter_test` / `integration_test` Dart code
  /// for a given [TestCase].
  String exportToFlutterTestCode(TestCase testCase) {
    final buffer = StringBuffer();
    buffer.writeln("import 'package:flutter/material.dart';");
    buffer.writeln("import 'package:flutter_test/flutter_test.dart';");
    buffer.writeln('');
    buffer.writeln('void main() {');
    buffer.writeln(
      "  testWidgets('${testCase.title.replaceAll("'", "\\'")}', (WidgetTester tester) async {",
    );
    for (final step in testCase.steps) {
      buffer.writeln('    // Step ${step.index}: ${step.instruction}');
      if (step.flutterAction != null && step.flutterAction!.isNotEmpty) {
        for (final line in step.flutterAction!.split('\n')) {
          buffer.writeln('    $line');
        }
      } else {
        buffer.writeln('    await tester.pumpAndSettle();');
      }
      buffer.writeln('');
    }
    buffer.writeln('  });');
    buffer.writeln('}');
    return buffer.toString();
  }
}
