enum TestStatus {
  ready,
  draft,
  running,
  passed,
  failed,
  blocked,
}

extension TestStatusExtension on TestStatus {
  String get label {
    switch (this) {
      case TestStatus.ready:
        return 'Ready';
      case TestStatus.draft:
        return 'Draft';
      case TestStatus.running:
        return 'Running';
      case TestStatus.passed:
        return 'Passed';
      case TestStatus.failed:
        return 'Failed';
      case TestStatus.blocked:
        return 'Blocked';
    }
  }
}

class TestStep {
  final int index;
  final String instruction;
  final String? expectedFinder;
  final String? flutterAction;
  final bool isRefinedByAi;

  const TestStep({
    required this.index,
    required this.instruction,
    this.expectedFinder,
    this.flutterAction,
    this.isRefinedByAi = false,
  });

  TestStep copyWith({
    int? index,
    String? instruction,
    String? expectedFinder,
    String? flutterAction,
    bool? isRefinedByAi,
  }) {
    return TestStep(
      index: index ?? this.index,
      instruction: instruction ?? this.instruction,
      expectedFinder: expectedFinder ?? this.expectedFinder,
      flutterAction: flutterAction ?? this.flutterAction,
      isRefinedByAi: isRefinedByAi ?? this.isRefinedByAi,
    );
  }

  Map<String, dynamic> toJson() => {
        'index': index,
        'instruction': instruction,
        'expectedFinder': expectedFinder,
        'flutterAction': flutterAction,
        'isRefinedByAi': isRefinedByAi,
      };
}

class TestCase {
  final String id;
  final String title;
  final TestStatus status;
  final bool isSelected;
  final List<TestStep> steps;
  final Duration? lastRunDuration;
  final String? failureReason;

  const TestCase({
    required this.id,
    required this.title,
    this.status = TestStatus.draft,
    this.isSelected = true,
    this.steps = const [],
    this.lastRunDuration,
    this.failureReason,
  });

  TestCase copyWith({
    String? id,
    String? title,
    TestStatus? status,
    bool? isSelected,
    List<TestStep>? steps,
    Duration? lastRunDuration,
    String? failureReason,
  }) {
    return TestCase(
      id: id ?? this.id,
      title: title ?? this.title,
      status: status ?? this.status,
      isSelected: isSelected ?? this.isSelected,
      steps: steps ?? this.steps,
      lastRunDuration: lastRunDuration ?? this.lastRunDuration,
      failureReason: failureReason ?? this.failureReason,
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'title': title,
        'status': status.label,
        'isSelected': isSelected,
        'steps': steps.map((s) => s.toJson()).toList(),
      };
}

class TestSuite {
  final String id;
  final String title;
  final int totalCasesCount;
  final bool isSelected;
  final List<TestCase> cases;

  const TestSuite({
    required this.id,
    required this.title,
    required this.totalCasesCount,
    this.isSelected = false,
    this.cases = const [],
  });

  TestSuite copyWith({
    String? id,
    String? title,
    int? totalCasesCount,
    bool? isSelected,
    List<TestCase>? cases,
  }) {
    return TestSuite(
      id: id ?? this.id,
      title: title ?? this.title,
      totalCasesCount: totalCasesCount ?? this.totalCasesCount,
      isSelected: isSelected ?? this.isSelected,
      cases: cases ?? this.cases,
    );
  }
}

class DailyTestRunMetric {
  final String dayLabel;
  final String dateLabel;
  final int passed;
  final int failed;

  const DailyTestRunMetric({
    required this.dayLabel,
    required this.dateLabel,
    required this.passed,
    required this.failed,
  });

  int get total => passed + failed;
}

class QASummaryStats {
  final int totalTests;
  final int passed;
  final int failed;
  final int blocked;

  const QASummaryStats({
    required this.totalTests,
    required this.passed,
    required this.failed,
    required this.blocked,
  });

  double get passRate => totalTests == 0 ? 0 : passed / totalTests;
}

class TestEnvironmentConfig {
  final String host;
  final String buildFile;
  final String deviceSource;
  final String devices;
  final String prdFile;
  final String figmaFile;

  const TestEnvironmentConfig({
    this.host = 'Booking_Staging',
    this.buildFile = 'File_name_version_v2.4.apk',
    this.deviceSource = 'LambdaTest',
    this.devices = 'iPhone 14, Pixel 8 Pro',
    this.prdFile = 'very_long_file_name_v3_final.pdf',
    this.figmaFile = 'Filename/Pagename',
  });

  TestEnvironmentConfig copyWith({
    String? host,
    String? buildFile,
    String? deviceSource,
    String? devices,
    String? prdFile,
    String? figmaFile,
  }) {
    return TestEnvironmentConfig(
      host: host ?? this.host,
      buildFile: buildFile ?? this.buildFile,
      deviceSource: deviceSource ?? this.deviceSource,
      devices: devices ?? this.devices,
      prdFile: prdFile ?? this.prdFile,
      figmaFile: figmaFile ?? this.figmaFile,
    );
  }
}

/// Default seed data matching the OpenFlutterQA studio layout.
class QADefaultData {
  static List<TestSuite> initialSuites() {
    return [
      const TestSuite(
        id: 'suite-1',
        title: '1. New Login Feature',
        totalCasesCount: 17,
        isSelected: false,
      ),
      const TestSuite(
        id: 'suite-2',
        title: '2. Cart Offer',
        totalCasesCount: 17,
        isSelected: false,
      ),
      TestSuite(
        id: 'suite-4',
        title: '4. Selection drop test',
        totalCasesCount: 24,
        isSelected: true,
        cases: initialTestCases(),
      ),
      const TestSuite(
        id: 'suite-3',
        title: '1. Selection Group',
        totalCasesCount: 23,
        isSelected: false,
      ),
    ];
  }

  static List<TestCase> initialTestCases() {
    return [
      const TestCase(
        id: 'tc-1',
        title: 'Checkout Icons Functionality',
        status: TestStatus.ready,
        steps: [
          TestStep(
            index: 1,
            instruction: 'Navigate to the home page and verify app bar icons.',
            expectedFinder: "find.byIcon(Icons.shopping_bag_outlined)",
            flutterAction: 'await tester.pumpAndSettle();',
          ),
          TestStep(
            index: 2,
            instruction: 'Tap the checkout icon and confirm cart summary opens.',
            expectedFinder: "find.text('Checkout')",
            flutterAction: "await tester.tap(find.byKey(Key('checkout_btn')));",
          ),
        ],
      ),
      const TestCase(
        id: 'tc-2',
        title: 'Verify Bookmark Status Reflecting Properly',
        status: TestStatus.draft,
        steps: [
          TestStep(
            index: 1,
            instruction: 'Navigate to the home page.',
            expectedFinder: "find.byKey(Key('home_screen'))",
            flutterAction: 'await tester.pumpAndSettle();',
          ),
          TestStep(
            index: 2,
            instruction: 'Select a news article to open its details.',
            expectedFinder: "find.byKey(Key('news_article_card_0'))",
            flutterAction:
                "await tester.tap(find.byKey(Key('news_article_card_0')));",
          ),
          TestStep(
            index: 3,
            instruction:
                'Click the bookmark button on the article detail screen.',
            expectedFinder: "find.byIcon(Icons.bookmark_border)",
            flutterAction:
                "await tester.tap(find.byKey(Key('bookmark_toggle_btn')));",
          ),
          TestStep(
            index: 4,
            instruction:
                'Navigate to the bookmarks tab or page using the navigation menu.',
            expectedFinder: "find.byIcon(Icons.bookmarks_outlined)",
            flutterAction:
                "await tester.tap(find.byKey(Key('nav_bookmarks_tab')));",
          ),
          TestStep(
            index: 5,
            instruction:
                'Verify that the selected article appears on the bookmarks page.',
            expectedFinder: "find.textContaining('Flutter 3.x Release')",
            flutterAction:
                "expect(find.byKey(Key('bookmarked_item_0')), findsOneWidget);",
          ),
        ],
      ),
      const TestCase(
        id: 'tc-3',
        title: 'Bookmark Functionality on Resuming from News Detail Activity',
        status: TestStatus.draft,
        steps: [
          TestStep(
            index: 1,
            instruction: 'Open article details and toggle bookmark state ON.',
          ),
          TestStep(
            index: 2,
            instruction: 'Return to the main feed using the back button.',
          ),
          TestStep(
            index: 3,
            instruction:
                'Verify the feed card displays an active filled bookmark icon.',
          ),
        ],
      ),
      const TestCase(
        id: 'tc-4',
        title: 'Bookmark Icon Changes Based on News Item State',
        status: TestStatus.draft,
        steps: [
          TestStep(
            index: 1,
            instruction: 'Inspect unbookmarked news item icon state.',
          ),
          TestStep(
            index: 2,
            instruction: 'Tap bookmark icon and verify immediate state transition.',
          ),
        ],
      ),
      const TestCase(
        id: 'tc-5',
        title: 'Pagination and Scroll Functionality on News Feed',
        status: TestStatus.ready,
        steps: [
          TestStep(
            index: 1,
            instruction: 'Scroll down 1200px on the primary CustomScrollView.',
          ),
          TestStep(
            index: 2,
            instruction: 'Verify next page indicator loads 10 additional items.',
          ),
        ],
      ),
      const TestCase(
        id: 'tc-6',
        title: 'Pull-to-Refresh and Scroll Functionality',
        status: TestStatus.ready,
        steps: [
          TestStep(
            index: 1,
            instruction: 'Drag down from top of feed to trigger RefreshIndicator.',
          ),
          TestStep(
            index: 2,
            instruction: 'Verify updated timestamp banner is rendered.',
          ),
        ],
      ),
      const TestCase(
        id: 'tc-7',
        title: 'Adding and Removing a Bookmark',
        status: TestStatus.draft,
        steps: [
          TestStep(
            index: 1,
            instruction: 'Bookmark an article from the home feed.',
          ),
          TestStep(
            index: 2,
            instruction: 'Open Bookmarks tab and swipe to remove the article.',
          ),
        ],
      ),
      const TestCase(
        id: 'tc-8',
        title: 'Persisting a Bookmark Across App Restarts',
        status: TestStatus.draft,
        steps: [
          TestStep(
            index: 1,
            instruction: 'Bookmark an item and persist to local storage.',
          ),
          TestStep(
            index: 2,
            instruction: 'Restart widget tree and verify bookmark remains saved.',
          ),
        ],
      ),
    ];
  }

  static List<DailyTestRunMetric> initialWeeklyRuns() {
    return const [
      DailyTestRunMetric(
        dayLabel: 'Mon',
        dateLabel: 'Jun 2',
        passed: 18,
        failed: 6,
      ),
      DailyTestRunMetric(
        dayLabel: 'Tue',
        dateLabel: 'Jun 3',
        passed: 14,
        failed: 8,
      ),
      DailyTestRunMetric(
        dayLabel: 'wed',
        dateLabel: 'Jun 4',
        passed: 20,
        failed: 9,
      ),
      DailyTestRunMetric(
        dayLabel: 'thu',
        dateLabel: 'Jun 5',
        passed: 24,
        failed: 12,
      ),
      DailyTestRunMetric(
        dayLabel: 'Fri',
        dateLabel: '10 june',
        passed: 21,
        failed: 9,
      ),
    ];
  }

  static const QASummaryStats initialSummaryStats = QASummaryStats(
    totalTests: 47,
    blocked: 0,
    passed: 39,
    failed: 8,
  );
}
