import 'dart:io';
import 'package:open_flutter_qa/src/models/qa_models.dart';
import 'package:open_flutter_qa/src/services/ai_qa_service.dart';

/// CLI utility for OpenFlutterQA to generate test cases, refine steps with AI,
/// and export runnable `flutter_test` Dart code from the command line or CI.
Future<void> main(List<String> args) async {
  final envVars = _loadDotEnv();
  final apiKey =
      Platform.environment['GEMINI_API_KEY'] ?? envVars['GEMINI_API_KEY'] ?? '';
  final modelName = Platform.environment['MODEL_NAME'] ??
      envVars['MODEL_NAME'] ??
      'gemini-2.5-flash';

  final aiService = AiQaService(apiKey: apiKey, modelName: modelName);

  stdout.writeln('==========================================================');
  stdout.writeln(' OpenFlutterQA - AI Test Automation CLI & Code Generator');
  stdout.writeln(
    ' Provider: ${aiService.hasLiveApiKey ? "Google Gemini ($modelName)" : "Deterministic Mock AI Engine (Offline Ready)"}',
  );
  stdout.writeln('==========================================================\n');

  final cases = QADefaultData.initialTestCases();
  final targetCase = cases[1]; // "Verify Bookmark Status Reflecting Properly"
  final targetStep = targetCase.steps[3]; // Step 4

  stdout.writeln('1. Refining Test Step #4 with AI...');
  stdout.writeln('   Test Case : ${targetCase.title}');
  stdout.writeln('   Before    : ${targetStep.instruction}');

  final refinedStep = await aiService.refineTestStep(
    testCase: targetCase,
    step: targetStep,
  );
  stdout.writeln('   After     : ${refinedStep.instruction}');
  stdout.writeln('   Finder    : ${refinedStep.expectedFinder}\n');

  stdout.writeln('2. Generating Test Cases from PRD & Figma Spec...');
  final generated = await aiService.generateTestCasesFromSpec(
    prdDocument: 'very_long_file_name_v3_final.pdf',
    figmaSpec: 'NewsFeed/BookmarksPage',
  );
  for (final tc in generated) {
    stdout.writeln('   [+] ${tc.title} (${tc.steps.length} steps)');
  }
  stdout.writeln('');

  final updatedCase = targetCase.copyWith(
    steps: targetCase.steps
        .map((s) => s.index == refinedStep.index ? refinedStep : s)
        .toList(),
  );

  stdout.writeln('3. Exporting Flutter Integration Test Script:\n');
  stdout.writeln(aiService.exportToFlutterTestCode(updatedCase));
}

Map<String, String> _loadDotEnv() {
  final file = File('.env');
  if (!file.existsSync()) return {};
  final map = <String, String>{};
  for (final rawLine in file.readAsLinesSync()) {
    final line = rawLine.trim();
    if (line.isEmpty || line.startsWith('#')) continue;
    final idx = line.indexOf('=');
    if (idx <= 0) continue;
    final key = line.substring(0, idx).trim();
    final value = line.substring(idx + 1).trim();
    map[key] = value;
  }
  return map;
}
