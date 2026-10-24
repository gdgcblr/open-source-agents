import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:open_flutter_qa/open_flutter_qa.dart';

void main() {
  group('OpenFlutterQA Models & AI Service Tests', () {
    test('Default summary stats match expected counts', () {
      const stats = QADefaultData.initialSummaryStats;
      expect(stats.totalTests, 47);
      expect(stats.passed, 39);
      expect(stats.failed, 8);
      expect(stats.blocked, 0);
    });

    test('AiQaService refines step 4 with deterministic Flutter Finder',
        () async {
      final aiService = AiQaService(apiKey: '');
      final testCase = QADefaultData.initialTestCases()[1];
      final step4 = testCase.steps[3];

      expect(
        step4.instruction,
        contains('Navigate to the bookmarks tab or page'),
      );

      final refined = await aiService.refineTestStep(
        testCase: testCase,
        step: step4,
      );

      expect(refined.isRefinedByAi, isTrue);
      expect(refined.expectedFinder, contains('nav_bookmarks_tab'));
      expect(refined.flutterAction, contains('tester.tap'));
    });

    test('AiQaService exports valid flutter_test Dart script', () {
      final aiService = AiQaService(apiKey: '');
      final testCase = QADefaultData.initialTestCases()[1];
      final code = aiService.exportToFlutterTestCode(testCase);

      expect(code, contains("import 'package:flutter_test/flutter_test.dart';"));
      expect(code, contains('testWidgets('));
      expect(code, contains('Verify Bookmark Status Reflecting Properly'));
    });
  });

  group('OpenFlutterQA Studio Dashboard Widget Tests', () {
    testWidgets('Renders Test Suites, Donut Summary, Test Runs, and Test Steps',
        (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1440, 1024);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      await tester.pumpWidget(
        const MaterialApp(
          home: OpenFlutterQADashboard(),
        ),
      );

      // Verify key sections from screenshot
      expect(find.text('Test Suites'), findsOneWidget);
      expect(find.text('1. New Login Feature'), findsOneWidget);
      expect(find.text('4. Selection drop test'), findsOneWidget);

      // Donut Summary Metrics
      expect(find.text('47'), findsOneWidget);
      expect(find.text('Total Tests'), findsOneWidget);
      expect(find.text('39'), findsOneWidget);
      expect(find.text('Passed'), findsOneWidget);
      expect(find.text('8'), findsOneWidget);
      expect(find.text('Failed'), findsOneWidget);

      // Test Details
      expect(find.text('Test Details'), findsOneWidget);
      expect(find.text('LambdaTest'), findsOneWidget);

      // Weekly Test Runs Chart
      expect(find.text('Test Runs'), findsOneWidget);
      expect(find.text('Jun 5'), findsOneWidget);
      expect(find.text('36'), findsOneWidget);

      // Test Steps & Context Menu
      expect(find.text('Test Steps'), findsOneWidget);
      expect(
        find.textContaining(
          '4. Navigate to the bookmarks tab or page using the navigation menu.',
        ),
        findsOneWidget,
      );
      expect(find.text('Refine with AI'), findsOneWidget);
      expect(find.text('Edit Manually'), findsOneWidget);
    });

    testWidgets('Clicking Refine with AI updates selected step',
        (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1440, 1024);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      await tester.pumpWidget(
        const MaterialApp(
          home: OpenFlutterQADashboard(),
        ),
      );

      final refineBtn = find.byKey(const Key('refine_with_ai_btn'));
      expect(refineBtn, findsOneWidget);

      await tester.ensureVisible(refineBtn);
      await tester.pumpAndSettle();
      await tester.tap(refineBtn);
      await tester.pump(const Duration(milliseconds: 500));

      expect(
        find.textContaining("Finder: find.byKey(const Key('nav_bookmarks_tab'))"),
        findsOneWidget,
      );
    });

    testWidgets('OpenFlutterQAWrapper toggles QA Studio overlay on host app',
        (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1280, 900);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      await tester.pumpWidget(
        const MaterialApp(
          home: OpenFlutterQAWrapper(
            child: Scaffold(
              body: Center(child: Text('Host News App')),
            ),
          ),
        ),
      );

      expect(find.text('Host News App'), findsOneWidget);
      expect(find.byKey(const Key('open_qa_studio_fab')), findsOneWidget);

      await tester.tap(find.byKey(const Key('open_qa_studio_fab')));
      await tester.pumpAndSettle();

      expect(find.text('OpenFlutterQA Automation Studio'), findsOneWidget);
    });
  });
}
