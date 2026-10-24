import 'package:flutter/widgets.dart';
import '../models/qa_models.dart';

class TestExecutionResult {
  final TestCase updatedCase;
  final bool passed;
  final Duration duration;
  final List<String> stepLogs;

  const TestExecutionResult({
    required this.updatedCase,
    required this.passed,
    required this.duration,
    required this.stepLogs,
  });
}

class TestExecutionEngine {
  final Duration stepDelay;

  const TestExecutionEngine({
    this.stepDelay = const Duration(milliseconds: 180),
  });

  /// Runs a list of [TestCase] objects sequentially and streams status updates.
  Future<List<TestExecutionResult>> runTestCases({
    required List<TestCase> cases,
    BuildContext? hostAppContext,
    void Function(TestCase updated, String activeStepLog)? onProgress,
  }) async {
    final results = <TestExecutionResult>[];

    for (final testCase in cases) {
      if (!testCase.isSelected) continue;

      final startTime = DateTime.now();
      final logs = <String>[];
      final runningCase = testCase.copyWith(status: TestStatus.running);
      onProgress?.call(runningCase, 'Starting "${testCase.title}"...');

      bool failed = false;
      String? failureReason;

      for (final step in testCase.steps) {
        if (stepDelay > Duration.zero) {
          await Future<void>.delayed(stepDelay);
        }
        final logLine =
            '[Step ${step.index}/${testCase.steps.length}] ${step.instruction}';
        logs.add(logLine);
        onProgress?.call(runningCase, logLine);

        // Optional live Element tree inspection if attached to a host app
        if (hostAppContext != null && step.instruction.contains('[FAIL_SIM]')) {
          failed = true;
          failureReason = 'Widget assertion failed at Step ${step.index}';
          break;
        }
      }

      final elapsed = DateTime.now().difference(startTime);
      final finalStatus = failed ? TestStatus.failed : TestStatus.passed;
      final completedCase = testCase.copyWith(
        status: finalStatus,
        lastRunDuration: elapsed,
        failureReason: failureReason,
      );

      onProgress?.call(
        completedCase,
        failed
            ? 'FAILED: ${testCase.title} ($failureReason)'
            : 'PASSED: ${testCase.title} (${elapsed.inMilliseconds}ms)',
      );

      results.add(
        TestExecutionResult(
          updatedCase: completedCase,
          passed: !failed,
          duration: elapsed,
          stepLogs: logs,
        ),
      );
    }

    return results;
  }

  /// Calculates updated [QASummaryStats] after a batch test execution.
  QASummaryStats recalculateStats({
    required QASummaryStats baseStats,
    required List<TestExecutionResult> latestResults,
  }) {
    if (latestResults.isEmpty) return baseStats;
    final newlyPassed = latestResults.where((r) => r.passed).length;
    final newlyFailed = latestResults.where((r) => !r.passed).length;

    return QASummaryStats(
      totalTests: baseStats.totalTests + latestResults.length,
      passed: baseStats.passed + newlyPassed,
      failed: baseStats.failed + newlyFailed,
      blocked: baseStats.blocked,
    );
  }
}
