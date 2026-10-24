import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../models/qa_models.dart';
import '../services/ai_qa_service.dart';
import '../services/test_execution_engine.dart';
import 'qa_charts.dart';

class OpenFlutterQADashboard extends StatefulWidget {
  final AiQaService? aiService;
  final TestExecutionEngine? executionEngine;
  final BuildContext? hostAppContext;
  final VoidCallback? onCloseOverlay;

  const OpenFlutterQADashboard({
    super.key,
    this.aiService,
    this.executionEngine,
    this.hostAppContext,
    this.onCloseOverlay,
  });

  @override
  State<OpenFlutterQADashboard> createState() => _OpenFlutterQADashboardState();
}

class _OpenFlutterQADashboardState extends State<OpenFlutterQADashboard> {
  late final AiQaService _aiService;
  late final TestExecutionEngine _executionEngine;

  late List<TestSuite> _suites;
  late List<TestCase> _testCases;
  late List<DailyTestRunMetric> _weeklyRuns;
  late QASummaryStats _summaryStats;
  late TestEnvironmentConfig _envConfig;

  String _activeTestCaseId = 'tc-2';
  int _selectedStepIndex = 4; // Step 4 highlighted in blue by default
  String _sidebarTab = 'GENERATE'; // 'GENERATE' or 'EXECUTE'
  bool _isRefining = false;
  bool _isGenerating = false;
  bool _isExecuting = false;
  String? _statusMessage;

  @override
  void initState() {
    super.initState();
    _aiService = widget.aiService ?? AiQaService();
    _executionEngine = widget.executionEngine ?? const TestExecutionEngine();
    _suites = QADefaultData.initialSuites();
    _testCases = QADefaultData.initialTestCases();
    _weeklyRuns = QADefaultData.initialWeeklyRuns();
    _summaryStats = QADefaultData.initialSummaryStats;
    _envConfig = const TestEnvironmentConfig();
  }

  TestCase get _activeTestCase {
    return _testCases.firstWhere(
      (tc) => tc.id == _activeTestCaseId,
      orElse: () => _testCases.first,
    );
  }

  TestStep? get _selectedStep {
    final steps = _activeTestCase.steps;
    if (steps.isEmpty) return null;
    return steps.firstWhere(
      (s) => s.index == _selectedStepIndex,
      orElse: () => steps.first,
    );
  }

  Future<void> _handleRefineWithAi() async {
    final step = _selectedStep;
    if (step == null || _isRefining) return;

    setState(() {
      _isRefining = true;
      _statusMessage = 'Refining Step ${step.index} with AI...';
    });

    final refined = await _aiService.refineTestStep(
      testCase: _activeTestCase,
      step: step,
    );

    if (!mounted) return;
    setState(() {
      _testCases = _testCases.map((tc) {
        if (tc.id != _activeTestCase.id) return tc;
        return tc.copyWith(
          steps: tc.steps
              .map((s) => s.index == refined.index ? refined : s)
              .toList(),
        );
      }).toList();
      _isRefining = false;
      _statusMessage =
          'Step ${refined.index} refined with AI + Flutter Finder assertion.';
    });
  }

  Future<void> _handleEditManually() async {
    final step = _selectedStep;
    if (step == null) return;

    final controller = TextEditingController(text: step.instruction);
    final updatedText = await showDialog<String>(
      context: context,
      builder: (ctx) {
        return AlertDialog(
          backgroundColor: const Color(0xFF1F2229),
          title: Text(
            'Edit Step ${step.index}',
            style: const TextStyle(color: Colors.white, fontSize: 16),
          ),
          content: TextField(
            controller: controller,
            maxLines: 3,
            style: const TextStyle(
              color: Colors.white,
              fontFamily: 'monospace',
              fontSize: 13,
            ),
            decoration: InputDecoration(
              filled: true,
              fillColor: const Color(0xFF14161B),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
              ),
              hintText: 'Enter step instruction...',
              hintStyle: const TextStyle(color: Colors.white38),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(ctx).pop(controller.text.trim()),
              child: const Text('Save Step'),
            ),
          ],
        );
      },
    );

    if (updatedText != null && updatedText.isNotEmpty && mounted) {
      setState(() {
        _testCases = _testCases.map((tc) {
          if (tc.id != _activeTestCase.id) return tc;
          return tc.copyWith(
            steps: tc.steps.map((s) {
              if (s.index != step.index) return s;
              return s.copyWith(instruction: updatedText);
            }).toList(),
          );
        }).toList();
        _statusMessage = 'Updated Step ${step.index} manually.';
      });
    }
  }

  Future<void> _handleGenerateCases() async {
    if (_isGenerating) return;
    setState(() {
      _isGenerating = true;
      _statusMessage =
          'Generating test cases from PRD (${_envConfig.prdFile}) & Figma...';
    });

    final generated = await _aiService.generateTestCasesFromSpec(
      prdDocument: _envConfig.prdFile,
      figmaSpec: _envConfig.figmaFile,
    );

    if (!mounted) return;
    setState(() {
      _testCases = [...generated, ..._testCases];
      _activeTestCaseId = generated.first.id;
      _selectedStepIndex = 1;
      _isGenerating = false;
      _statusMessage =
          'Generated ${generated.length} new AI test cases from PRD & Figma.';
    });
  }

  Future<void> _handleExecuteSelected() async {
    if (_isExecuting) return;
    final selectedCount = _testCases.where((c) => c.isSelected).length;
    if (selectedCount == 0) {
      setState(() {
        _statusMessage = 'Select at least one test case to execute.';
      });
      return;
    }

    setState(() {
      _isExecuting = true;
      _statusMessage =
          'Executing $selectedCount test cases on ${_envConfig.deviceSource} (${_envConfig.devices})...';
    });

    final results = await _executionEngine.runTestCases(
      cases: _testCases,
      hostAppContext: widget.hostAppContext,
      onProgress: (updatedCase, log) {
        if (!mounted) return;
        setState(() {
          _testCases = _testCases
              .map((c) => c.id == updatedCase.id ? updatedCase : c)
              .toList();
          _statusMessage = log;
        });
      },
    );

    if (!mounted) return;
    setState(() {
      _summaryStats = _executionEngine.recalculateStats(
        baseStats: _summaryStats,
        latestResults: results,
      );
      _isExecuting = false;
      final passedCount = results.where((r) => r.passed).length;
      _statusMessage =
          'Run completed: $passedCount/${results.length} passed on ${_envConfig.devices}.';
    });
  }

  void _showExportCodeDialog() {
    final code = _aiService.exportToFlutterTestCode(_activeTestCase);
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: const Color(0xFF1A1D24),
        title: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Expanded(
              child: Text(
                'Flutter Test Script: ${_activeTestCase.title}',
                style: const TextStyle(color: Colors.white, fontSize: 15),
              ),
            ),
            IconButton(
              tooltip: 'Copy Dart code',
              icon: const Icon(Icons.copy, color: Colors.white70, size: 18),
              onPressed: () {
                Clipboard.setData(ClipboardData(text: code));
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(
                    content: Text('Copied flutter_test code to clipboard!'),
                  ),
                );
              },
            ),
          ],
        ),
        content: SingleChildScrollView(
          child: Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: const Color(0xFF111318),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: const Color(0xFF2D323E)),
            ),
            child: SelectableText(
              code,
              style: const TextStyle(
                color: Color(0xFF8BE9FD),
                fontFamily: 'monospace',
                fontSize: 12,
              ),
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Close'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0F1115),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(20),
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 1320),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  _buildTopBar(),
                  const SizedBox(height: 16),
                  LayoutBuilder(
                    builder: (context, constraints) {
                      final isWide = constraints.maxWidth >= 980;
                      if (isWide) {
                        return Column(
                          children: [
                            // Top Row: Test Suites + Test Details + Summary Donut
                            Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Expanded(
                                  flex: 5,
                                  child: _buildTestSuitesCard(),
                                ),
                                const SizedBox(width: 16),
                                Expanded(
                                  flex: 4,
                                  child: _buildTestDetailsCard(),
                                ),
                                const SizedBox(width: 16),
                                Expanded(
                                  flex: 4,
                                  child: TestSummaryDonutCard(
                                    stats: _summaryStats,
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 18),
                            // Bottom Row: Weekly Test Runs Chart + Test Cases & Steps Studio
                            Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                SizedBox(
                                  width: 340,
                                  child: TestRunsWeeklyChartCard(
                                    runs: _weeklyRuns,
                                  ),
                                ),
                                const SizedBox(width: 18),
                                Expanded(
                                  child: _buildTestCasesAndStepsStudio(),
                                ),
                              ],
                            ),
                          ],
                        );
                      }

                      // Responsive stacked layout for mobile / narrow viewports
                      return Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          TestSummaryDonutCard(stats: _summaryStats),
                          const SizedBox(height: 16),
                          _buildTestSuitesCard(),
                          const SizedBox(height: 16),
                          _buildTestDetailsCard(),
                          const SizedBox(height: 16),
                          TestRunsWeeklyChartCard(runs: _weeklyRuns),
                          const SizedBox(height: 16),
                          _buildTestCasesAndStepsStudio(),
                        ],
                      );
                    },
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildTopBar() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
      decoration: BoxDecoration(
        color: const Color(0xFF181A1F),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFF2A2E37)),
      ),
      child: Wrap(
        alignment: WrapAlignment.spaceBetween,
        crossAxisAlignment: WrapCrossAlignment.center,
        spacing: 12,
        runSpacing: 8,
        children: [
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                padding: const EdgeInsets.all(7),
                decoration: BoxDecoration(
                  color: const Color(0xFF52B788).withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Icon(
                  Icons.biotech_rounded,
                  color: Color(0xFF52B788),
                  size: 20,
                ),
              ),
              const SizedBox(width: 10),
              const Text(
                'OpenFlutterQA Automation Studio',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(width: 10),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: _aiService.hasLiveApiKey
                      ? const Color(0xFF52B788).withValues(alpha: 0.2)
                      : const Color(0xFF64B5F6).withValues(alpha: 0.16),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(
                  _aiService.hasLiveApiKey
                      ? 'Gemini AI Active'
                      : 'AI Mock Engine Ready',
                  style: TextStyle(
                    color: _aiService.hasLiveApiKey
                        ? const Color(0xFF52B788)
                        : const Color(0xFF64B5F6),
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ],
          ),
          if (_statusMessage != null)
            Text(
              _statusMessage!,
              style: const TextStyle(
                color: Color(0xFFB0B6C3),
                fontSize: 12.5,
              ),
            ),
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              OutlinedButton.icon(
                style: OutlinedButton.styleFrom(
                  foregroundColor: Colors.white,
                  side: const BorderSide(color: Color(0xFF353B49)),
                ),
                onPressed: _showExportCodeDialog,
                icon: const Icon(Icons.code, size: 16),
                label: const Text('Export Flutter Test'),
              ),
              const SizedBox(width: 8),
              FilledButton.icon(
                style: FilledButton.styleFrom(
                  backgroundColor: const Color(0xFF4CA965),
                  foregroundColor: Colors.white,
                ),
                onPressed: _isExecuting ? null : _handleExecuteSelected,
                icon: _isExecuting
                    ? const SizedBox(
                        width: 14,
                        height: 14,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white,
                        ),
                      )
                    : const Icon(Icons.play_arrow_rounded, size: 18),
                label: Text(_isExecuting ? 'Running...' : 'Run Suite'),
              ),
              if (widget.onCloseOverlay != null) ...[
                const SizedBox(width: 8),
                IconButton(
                  tooltip: 'Minimize QA Studio to Host App',
                  onPressed: widget.onCloseOverlay,
                  icon: const Icon(Icons.close, color: Colors.white70),
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }

  /// Top-left card: "← Test Suites" with 2x2 suite grid.
  Widget _buildTestSuitesCard() {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: const Color(0xFF181A1F),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: const Color(0xFF2A2E37), width: 1.2),
        boxShadow: const [
          BoxShadow(
            color: Color(0x66000000),
            blurRadius: 20,
            offset: Offset(0, 10),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(
                Icons.arrow_back,
                color: Colors.white70,
                size: 18,
              ),
              SizedBox(width: 8),
              Text(
                'Test Suites',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          GridView.builder(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            itemCount: _suites.length,
            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: 2,
              crossAxisSpacing: 12,
              mainAxisSpacing: 12,
              mainAxisExtent: 102,
            ),
            itemBuilder: (context, index) {
              final suite = _suites[index];
              return GestureDetector(
                onTap: () {
                  setState(() {
                    _suites = _suites.asMap().entries.map((e) {
                      if (e.key != index) return e.value;
                      return e.value.copyWith(isSelected: !e.value.isSelected);
                    }).toList();
                  });
                },
                child: Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: const Color(0xFF21242B),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: suite.isSelected
                          ? const Color(0xFF64B5F6)
                          : const Color(0xFF2E323C),
                    ),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              suite.title,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 12.5,
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                          ),
                          SizedBox(
                            width: 20,
                            height: 20,
                            child: Checkbox(
                              value: suite.isSelected,
                              onChanged: (val) {
                                setState(() {
                                  _suites[index] = suite.copyWith(
                                    isSelected: val ?? false,
                                  );
                                });
                              },
                              side: const BorderSide(
                                color: Color(0xFF8A919E),
                                width: 1.4,
                              ),
                              activeColor: const Color(0xFF2E86DE),
                            ),
                          ),
                        ],
                      ),
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            'Test Cases',
                            style: TextStyle(
                              color: Color(0xFF9EA4B0),
                              fontSize: 11,
                            ),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            '${suite.totalCasesCount}',
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 13,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              );
            },
          ),
        ],
      ),
    );
  }

  /// Center-top card: "Test Details" with Host, Build, Device Source, and Devices.
  Widget _buildTestDetailsCard() {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: const Color(0xFF16181D),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: const Color(0xFF2A2E37), width: 1.2),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Test Details',
            style: TextStyle(
              color: Color(0xFF9EA4B0),
              fontSize: 16,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 18),
          Row(
            children: [
              Expanded(
                child: _buildDetailField(
                  icon: Icons.dns_outlined,
                  label: 'Host',
                  value: _envConfig.host,
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: _buildDetailField(
                  icon: Icons.build_outlined,
                  label: 'Build',
                  value: _envConfig.buildFile,
                ),
              ),
            ],
          ),
          const SizedBox(height: 18),
          Row(
            children: [
              Expanded(
                child: _buildDetailField(
                  icon: Icons.hub_outlined,
                  label: 'Device Source',
                  value: _envConfig.deviceSource,
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: _buildDetailField(
                  icon: Icons.smartphone_outlined,
                  label: 'Devices',
                  value: _envConfig.devices,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildDetailField({
    required IconData icon,
    required String label,
    required String value,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Icon(icon, color: const Color(0xFF7D8492), size: 15),
            const SizedBox(width: 6),
            Flexible(
              child: Text(
                label,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  color: Color(0xFF8A919E),
                  fontSize: 13,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 8),
        Container(
          width: double.infinity,
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          decoration: BoxDecoration(
            color: const Color(0xFF1E2128),
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: const Color(0xFF2B2F3A)),
          ),
          child: Text(
            value,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              color: Color(0xFFB8BECA),
              fontSize: 12.5,
            ),
          ),
        ),
      ],
    );
  }

  /// Main bottom-right panel combining TEST CASES list, GENERATE/EXECUTE sidebar,
  /// and the interactive Test Steps inspector + "Refine with AI" context menu.
  Widget _buildTestCasesAndStepsStudio() {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF16181D),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: const Color(0xFF2A2E37), width: 1.2),
        boxShadow: const [
          BoxShadow(
            color: Color(0x66000000),
            blurRadius: 24,
            offset: Offset(0, 12),
          ),
        ],
      ),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final isWide = constraints.maxWidth >= 680;
          if (isWide) {
            return IntrinsicHeight(
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Expanded(
                    flex: 7,
                    child: _buildTestCasesAndStepsColumn(),
                  ),
                  Container(
                    width: 1,
                    color: const Color(0xFF262A34),
                  ),
                  SizedBox(
                    width: 250,
                    child: _buildRightGenerateExecuteSidebar(),
                  ),
                ],
              ),
            );
          }
          return Column(
            children: [
              _buildTestCasesAndStepsColumn(),
              const Divider(color: Color(0xFF262A34), height: 1),
              _buildRightGenerateExecuteSidebar(),
            ],
          );
        },
      ),
    );
  }

  Widget _buildTestCasesAndStepsColumn() {
    final activeCase = _activeTestCase;

    return Padding(
      padding: const EdgeInsets.all(18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header: TEST CASES (24) | Select all | Deselect all
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              RichText(
                text: TextSpan(
                  children: [
                    const TextSpan(
                      text: 'TEST CASES ',
                      style: TextStyle(
                        color: Color(0xFFD4AF37),
                        fontSize: 12,
                        fontWeight: FontWeight.w700,
                        letterSpacing: 0.6,
                      ),
                    ),
                    TextSpan(
                      text: '(${_testCases.length})',
                      style: const TextStyle(
                        color: Color(0xFF8A919E),
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ),
              Row(
                children: [
                  TextButton(
                    onPressed: () {
                      setState(() {
                        _testCases = _testCases
                            .map((c) => c.copyWith(isSelected: true))
                            .toList();
                      });
                    },
                    child: const Text(
                      'Select all',
                      style: TextStyle(color: Color(0xFF8A919E), fontSize: 12),
                    ),
                  ),
                  TextButton(
                    onPressed: () {
                      setState(() {
                        _testCases = _testCases
                            .map((c) => c.copyWith(isSelected: false))
                            .toList();
                      });
                    },
                    child: const Text(
                      'Deselect all',
                      style: TextStyle(color: Color(0xFF8A919E), fontSize: 12),
                    ),
                  ),
                ],
              ),
            ],
          ),
          const SizedBox(height: 8),

          // Compact list of test cases
          ..._testCases.take(5).map((tc) {
            final isCurrent = tc.id == activeCase.id;
            return InkWell(
              onTap: () {
                setState(() {
                  _activeTestCaseId = tc.id;
                  _selectedStepIndex = tc.steps.isNotEmpty
                      ? tc.steps.last.index
                      : 1;
                });
              },
              borderRadius: BorderRadius.circular(8),
              child: Container(
                margin: const EdgeInsets.only(bottom: 6),
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                decoration: BoxDecoration(
                  color: isCurrent
                      ? const Color(0xFF222630)
                      : Colors.transparent,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(
                    color: isCurrent
                        ? const Color(0xFF394152)
                        : const Color(0xFF20232B),
                  ),
                ),
                child: Row(
                  children: [
                    SizedBox(
                      width: 18,
                      height: 18,
                      child: Checkbox(
                        value: tc.isSelected,
                        onChanged: (val) {
                          setState(() {
                            _testCases = _testCases.map((item) {
                              if (item.id != tc.id) return item;
                              return item.copyWith(isSelected: val ?? false);
                            }).toList();
                          });
                        },
                        side: const BorderSide(color: Color(0xFF6C7380)),
                        activeColor: const Color(0xFF4CA965),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: RichText(
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        text: TextSpan(
                          children: [
                            TextSpan(
                              text: tc.title,
                              style: TextStyle(
                                color: isCurrent
                                    ? Colors.white
                                    : const Color(0xFF8A919E),
                                fontSize: 12.5,
                              ),
                            ),
                            const TextSpan(text: '  '),
                            TextSpan(
                              text: tc.status.label,
                              style: TextStyle(
                                color: _statusColor(tc.status),
                                fontSize: 11.5,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                    Icon(
                      isCurrent
                          ? Icons.keyboard_arrow_up
                          : Icons.keyboard_arrow_down,
                      color: const Color(0xFF6C7380),
                      size: 16,
                    ),
                  ],
                ),
              ),
            );
          }),

          const SizedBox(height: 12),

          // Elevated Test Steps Modal Card + Floating AI Action Menu (matching screenshot)
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(18),
            decoration: BoxDecoration(
              color: const Color(0xFF20232A),
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: const Color(0xFF343946), width: 1.2),
              boxShadow: const [
                BoxShadow(
                  color: Color(0x99000000),
                  blurRadius: 22,
                  offset: Offset(0, 8),
                ),
              ],
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text(
                      'Test Steps',
                      style: TextStyle(
                        color: Color(0xFF8A919E),
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Flexible(
                      child: Text(
                        activeCase.title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: Color(0xFF74B9FF),
                          fontSize: 11.5,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),

                // Step Items
                ...activeCase.steps.map((step) {
                  final isHighlighted = step.index == _selectedStepIndex;
                  return GestureDetector(
                    onTap: () {
                      setState(() {
                        _selectedStepIndex = step.index;
                      });
                    },
                    child: Container(
                      width: double.infinity,
                      margin: const EdgeInsets.only(bottom: 8),
                      padding: const EdgeInsets.symmetric(
                        horizontal: 10,
                        vertical: 7,
                      ),
                      decoration: BoxDecoration(
                        color: isHighlighted
                            ? const Color(0xFF1B80C4)
                            : Colors.transparent,
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '${step.index}. ${step.instruction}',
                            style: TextStyle(
                              color: isHighlighted
                                  ? Colors.white
                                  : const Color(0xFFD0D5E0),
                              fontFamily: 'monospace',
                              fontSize: 13,
                              height: 1.4,
                              fontWeight: isHighlighted
                                  ? FontWeight.w600
                                  : FontWeight.w400,
                            ),
                          ),
                          if (step.isRefinedByAi &&
                              step.expectedFinder != null) ...[
                            const SizedBox(height: 4),
                            Text(
                              'Finder: ${step.expectedFinder}',
                              style: TextStyle(
                                color: isHighlighted
                                    ? const Color(0xFFE1F5FE)
                                    : const Color(0xFF52B788),
                                fontFamily: 'monospace',
                                fontSize: 11,
                              ),
                            ),
                          ],
                        ],
                      ),
                    ),
                  );
                }),

                const SizedBox(height: 10),

                // Floating Context Menu ("✨ Refine with AI" & "✏️ Edit Manually")
                Align(
                  alignment: Alignment.centerRight,
                  child: Container(
                    width: 240,
                    decoration: BoxDecoration(
                      color: const Color(0xFF262A33),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(
                        color: const Color(0xFF3B414F),
                        width: 1.2,
                      ),
                      boxShadow: const [
                        BoxShadow(
                          color: Color(0xAA000000),
                          blurRadius: 16,
                          offset: Offset(0, 6),
                        ),
                      ],
                    ),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        InkWell(
                          key: const Key('refine_with_ai_btn'),
                          onTap: _isRefining ? null : _handleRefineWithAi,
                          borderRadius: const BorderRadius.vertical(
                            top: Radius.circular(12),
                          ),
                          child: Padding(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 16,
                              vertical: 12,
                            ),
                            child: Row(
                              children: [
                                const Icon(
                                  Icons.auto_awesome_outlined,
                                  color: Colors.white,
                                  size: 18,
                                ),
                                const SizedBox(width: 10),
                                Expanded(
                                  child: Text(
                                    _isRefining
                                        ? 'Refining...'
                                        : 'Refine with AI',
                                    overflow: TextOverflow.ellipsis,
                                    style: const TextStyle(
                                      color: Colors.white,
                                      fontSize: 14,
                                      fontWeight: FontWeight.w500,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                        const Divider(
                          color: Color(0xFF363B48),
                          height: 1,
                        ),
                        InkWell(
                          key: const Key('edit_manually_btn'),
                          onTap: _handleEditManually,
                          borderRadius: const BorderRadius.vertical(
                            bottom: Radius.circular(12),
                          ),
                          child: const Padding(
                            padding: EdgeInsets.symmetric(
                              horizontal: 16,
                              vertical: 12,
                            ),
                            child: Row(
                              children: [
                                Icon(
                                  Icons.edit_outlined,
                                  color: Colors.white,
                                  size: 18,
                                ),
                                SizedBox(width: 10),
                                Expanded(
                                  child: Text(
                                    'Edit Manually',
                                    overflow: TextOverflow.ellipsis,
                                    style: TextStyle(
                                      color: Colors.white,
                                      fontSize: 14,
                                      fontWeight: FontWeight.w500,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  /// Right sidebar with GENERATE | EXECUTE tabs, PRD attachment, and Figma File attachment.
  Widget _buildRightGenerateExecuteSidebar() {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // GENERATE | EXECUTE tabs
          Wrap(
            spacing: 10,
            runSpacing: 6,
            children: [
              GestureDetector(
                onTap: () => setState(() => _sidebarTab = 'GENERATE'),
                child: Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 10,
                    vertical: 5,
                  ),
                  decoration: BoxDecoration(
                    color: _sidebarTab == 'GENERATE'
                        ? const Color(0xFF332D1A)
                        : Colors.transparent,
                    borderRadius: BorderRadius.circular(5),
                    border: Border.all(
                      color: _sidebarTab == 'GENERATE'
                          ? const Color(0xFFD4AF37)
                          : Colors.transparent,
                    ),
                  ),
                  child: const Text(
                    'GENERATE',
                    style: TextStyle(
                      color: Color(0xFFD4AF37),
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              ),
              GestureDetector(
                onTap: () => setState(() => _sidebarTab = 'EXECUTE'),
                child: Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 10,
                    vertical: 5,
                  ),
                  decoration: BoxDecoration(
                    color: _sidebarTab == 'EXECUTE'
                        ? const Color(0xFF1F2E28)
                        : Colors.transparent,
                    borderRadius: BorderRadius.circular(5),
                  ),
                  child: Text(
                    'EXECUTE',
                    style: TextStyle(
                      color: _sidebarTab == 'EXECUTE'
                          ? const Color(0xFF52B788)
                          : const Color(0xFF7D8492),
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 20),

          // PRD File Box
          const Row(
            children: [
              Icon(
                Icons.description_outlined,
                color: Color(0xFF8A919E),
                size: 15,
              ),
              SizedBox(width: 6),
              Text(
                'PRD',
                style: TextStyle(
                  color: Color(0xFF8A919E),
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 9),
            decoration: BoxDecoration(
              color: const Color(0xFF1E2128),
              borderRadius: BorderRadius.circular(7),
              border: Border.all(color: const Color(0xFF2B2F3A)),
            ),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    _envConfig.prdFile,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: Color(0xFF9EA4B0),
                      fontSize: 11.5,
                    ),
                  ),
                ),
                const Icon(
                  Icons.check,
                  color: Color(0xFF4CA965),
                  size: 15,
                ),
              ],
            ),
          ),
          const SizedBox(height: 18),

          // Figma File Box
          const Row(
            children: [
              Icon(
                Icons.design_services_outlined,
                color: Color(0xFF8A919E),
                size: 15,
              ),
              SizedBox(width: 6),
              Text(
                'Figma File',
                style: TextStyle(
                  color: Color(0xFF8A919E),
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 9),
            decoration: BoxDecoration(
              color: const Color(0xFF1E2128),
              borderRadius: BorderRadius.circular(7),
              border: Border.all(color: const Color(0xFF2B2F3A)),
            ),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    _envConfig.figmaFile,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: Color(0xFF9EA4B0),
                      fontSize: 11.5,
                    ),
                  ),
                ),
                const Icon(
                  Icons.check,
                  color: Color(0xFF4CA965),
                  size: 15,
                ),
              ],
            ),
          ),
          const SizedBox(height: 22),

          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              key: const Key('generate_ai_cases_btn'),
              style: FilledButton.styleFrom(
                backgroundColor: const Color(0xFF2B313E),
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(vertical: 12),
              ),
              onPressed: _isGenerating ? null : _handleGenerateCases,
              icon: const Icon(
                Icons.auto_awesome,
                size: 16,
                color: Color(0xFFD4AF37),
              ),
              label: Text(
                _isGenerating ? 'Generating...' : 'Generate from PRD',
                style: const TextStyle(fontSize: 12.5),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Color _statusColor(TestStatus status) {
    switch (status) {
      case TestStatus.ready:
        return const Color(0xFF52B788);
      case TestStatus.draft:
        return const Color(0xFF9EA4B0);
      case TestStatus.running:
        return const Color(0xFFD4AF37);
      case TestStatus.passed:
        return const Color(0xFF4CA965);
      case TestStatus.failed:
        return const Color(0xFFDF5A49);
      case TestStatus.blocked:
        return const Color(0xFFE0A458);
    }
  }
}
