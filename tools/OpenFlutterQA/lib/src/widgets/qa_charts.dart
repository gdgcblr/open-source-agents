import 'dart:math' as math;
import 'package:flutter/material.dart';
import '../models/qa_models.dart';

/// Top-right summary card with the multi-segment Donut Ring and Passed/Failed metrics.
class TestSummaryDonutCard extends StatelessWidget {
  final QASummaryStats stats;

  const TestSummaryDonutCard({
    super.key,
    required this.stats,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 20),
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
      child: FittedBox(
        fit: BoxFit.scaleDown,
        alignment: Alignment.centerLeft,
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            SizedBox(
              width: 118,
              height: 118,
              child: CustomPaint(
                painter: _DonutRingPainter(stats: stats),
              ),
            ),
            const SizedBox(width: 26),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Row(
                  children: [
                    _MetricBlock(
                      value: '${stats.totalTests}',
                      label: 'Total Tests',
                      labelColor: const Color(0xFF9EA4B0),
                    ),
                    const SizedBox(width: 28),
                    _MetricBlock(
                      value: '${stats.blocked}',
                      label: 'Blocked',
                      labelColor: const Color(0xFF9EA4B0),
                    ),
                  ],
                ),
                const SizedBox(height: 18),
                Row(
                  children: [
                    _MetricBlock(
                      value: '${stats.passed}',
                      label: 'Passed',
                      labelColor: const Color(0xFF52B788),
                    ),
                    const SizedBox(width: 28),
                    _MetricBlock(
                      value: '${stats.failed}',
                      label: 'Failed',
                      labelColor: const Color(0xFFE06C58),
                    ),
                  ],
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _MetricBlock extends StatelessWidget {
  final String value;
  final String label;
  final Color labelColor;

  const _MetricBlock({
    required this.value,
    required this.label,
    required this.labelColor,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 78,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            value,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 26,
              fontWeight: FontWeight.w500,
              letterSpacing: -0.5,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            label,
            style: TextStyle(
              color: labelColor,
              fontSize: 13,
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
    );
  }
}

class _DonutRingPainter extends CustomPainter {
  final QASummaryStats stats;

  _DonutRingPainter({required this.stats});

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    const strokeWidth = 15.0;
    final radius = (math.min(size.width, size.height) - strokeWidth) / 2;
    final rect = Rect.fromCircle(center: center, radius: radius);

    final total = math.max(1, stats.totalTests);
    final failedRatio = (stats.failed / total).clamp(0.05, 0.85);
    const blockedVisualRatio = 0.04;
    final passedRatio = (1.0 - failedRatio - blockedVisualRatio).clamp(0.1, 0.91);

    const gapRadians = 0.04;
    const startAngle = 0.12; // Just below right horizontal, matching screenshot

    final passedSweep = (passedRatio * 2 * math.pi) - gapRadians;
    final blockedSweep = (blockedVisualRatio * 2 * math.pi) - gapRadians;
    final failedSweep = (failedRatio * 2 * math.pi) - gapRadians;

    final paint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth
      ..strokeCap = StrokeCap.butt;

    // 1. Passed Arc (Emerald Green)
    paint.color = const Color(0xFF4CA965);
    canvas.drawArc(rect, startAngle, passedSweep, false, paint);

    // 2. Blocked / Neutral Segment (Grey)
    paint.color = const Color(0xFFA0A5B1);
    final blockedStart = startAngle + passedSweep + gapRadians;
    canvas.drawArc(rect, blockedStart, blockedSweep, false, paint);

    // 3. Failed Arc (Coral Red)
    paint.color = const Color(0xFFDF5A49);
    final failedStart = blockedStart + blockedSweep + gapRadians;
    canvas.drawArc(rect, failedStart, failedSweep, false, paint);
  }

  @override
  bool shouldRepaint(covariant _DonutRingPainter oldDelegate) {
    return oldDelegate.stats.totalTests != stats.totalTests ||
        oldDelegate.stats.passed != stats.passed ||
        oldDelegate.stats.failed != stats.failed;
  }
}

/// Bottom-left card showing weekly stacked bar chart and interactive tooltip.
class TestRunsWeeklyChartCard extends StatefulWidget {
  final List<DailyTestRunMetric> runs;

  const TestRunsWeeklyChartCard({
    super.key,
    required this.runs,
  });

  @override
  State<TestRunsWeeklyChartCard> createState() =>
      _TestRunsWeeklyChartCardState();
}

class _TestRunsWeeklyChartCardState extends State<TestRunsWeeklyChartCard> {
  int _selectedIndex = 3; // Defaults to 'thu' (Jun 5) as shown in screenshot
  String _selectedRange = 'Week';

  @override
  Widget build(BuildContext context) {
    final safeIndex = _selectedIndex.clamp(0, widget.runs.length - 1);
    final activeRun = widget.runs[safeIndex];

    return Container(
      padding: const EdgeInsets.fromLTRB(20, 18, 20, 16),
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
          // Header row
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text(
                'Test Runs',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                ),
              ),
              PopupMenuButton<String>(
                initialValue: _selectedRange,
                color: const Color(0xFF242830),
                onSelected: (val) => setState(() => _selectedRange = val),
                itemBuilder: (context) => const [
                  PopupMenuItem(
                    value: 'Week',
                    child: Text('Week', style: TextStyle(color: Colors.white)),
                  ),
                  PopupMenuItem(
                    value: 'Sprint',
                    child: Text('Sprint', style: TextStyle(color: Colors.white)),
                  ),
                ],
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      _selectedRange,
                      style: const TextStyle(
                        color: Color(0xFFB0B6C3),
                        fontSize: 13,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                    const SizedBox(width: 4),
                    const Icon(
                      Icons.keyboard_arrow_down,
                      color: Color(0xFFB0B6C3),
                      size: 18,
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),

          // Tooltip & Bar Chart Stack
          SizedBox(
            height: 215,
            child: Stack(
              clipBehavior: Clip.none,
              children: [
                // Dashed horizontal reference line
                Positioned(
                  top: 84,
                  left: 0,
                  right: 0,
                  child: CustomPaint(
                    size: const Size(double.infinity, 1),
                    painter: _DashedLinePainter(),
                  ),
                ),

                // Bars Row
                Positioned.fill(
                  top: 42,
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                    children: List.generate(widget.runs.length, (index) {
                      final item = widget.runs[index];
                      final isSelected = index == safeIndex;
                      final maxTotal = widget.runs
                          .map((e) => e.total)
                          .fold<int>(1, math.max);
                      final barMaxHeight = 128.0;
                      final passedHeight =
                          (item.passed / maxTotal) * barMaxHeight;
                      final failedHeight =
                          (item.failed / maxTotal) * barMaxHeight;

                      return GestureDetector(
                        onTap: () => setState(() => _selectedIndex = index),
                        child: MouseRegion(
                          cursor: SystemMouseCursors.click,
                          child: Column(
                            mainAxisAlignment: MainAxisAlignment.end,
                            children: [
                              Text(
                                item.dayLabel,
                                style: TextStyle(
                                  color: isSelected
                                      ? Colors.white
                                      : const Color(0xFF9EA4B0),
                                  fontSize: 11.5,
                                  fontWeight: isSelected
                                      ? FontWeight.w600
                                      : FontWeight.w400,
                                ),
                              ),
                              const SizedBox(height: 6),
                              Container(
                                width: 32,
                                decoration: BoxDecoration(
                                  borderRadius: const BorderRadius.vertical(
                                    top: Radius.circular(6),
                                  ),
                                  boxShadow: isSelected
                                      ? [
                                          BoxShadow(
                                            color: const Color(0xFF64B5F6)
                                                .withValues(alpha: 0.25),
                                            blurRadius: 8,
                                          )
                                        ]
                                      : null,
                                ),
                                child: Column(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    // Top portion: Passed (light sky blue)
                                    Container(
                                      height: passedHeight,
                                      decoration: const BoxDecoration(
                                        color: Color(0xFF74B9FF),
                                        borderRadius: BorderRadius.vertical(
                                          top: Radius.circular(5),
                                        ),
                                      ),
                                    ),
                                    // Bottom portion: Failed (darker steel blue)
                                    Container(
                                      height: failedHeight,
                                      color: const Color(0xFF2E86DE),
                                    ),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        ),
                      );
                    }),
                  ),
                ),

                // Floating Tooltip Card (Test cases | Jun 5 | 36 | Passed 24 | Failed 12)
                Positioned(
                  top: 0,
                  left: 34,
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 14,
                      vertical: 10,
                    ),
                    decoration: BoxDecoration(
                      color: const Color(0xFF232730),
                      borderRadius: BorderRadius.circular(10),
                      border: Border.all(
                        color: const Color(0xFF383E4C),
                        width: 1,
                      ),
                      boxShadow: const [
                        BoxShadow(
                          color: Color(0x88000000),
                          blurRadius: 12,
                          offset: Offset(0, 4),
                        ),
                      ],
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Text(
                              'Test cases',
                              style: TextStyle(
                                color: Colors.white,
                                fontSize: 12.5,
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                            const SizedBox(width: 24),
                            Container(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 7,
                                vertical: 2,
                              ),
                              decoration: BoxDecoration(
                                color: const Color(0xFF323744),
                                borderRadius: BorderRadius.circular(4),
                              ),
                              child: Text(
                                activeRun.dateLabel,
                                style: const TextStyle(
                                  color: Color(0xFFD0D5E0),
                                  fontSize: 11,
                                  fontWeight: FontWeight.w500,
                                ),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 2),
                        Text(
                          '${activeRun.total}',
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 15,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Text(
                              'Passed ',
                              style: TextStyle(
                                color: Color(0xFF74B9FF),
                                fontSize: 11.5,
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                            Text(
                              '${activeRun.passed}',
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 11.5,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            const SizedBox(width: 12),
                            const Text(
                              'Failed ',
                              style: TextStyle(
                                color: Color(0xFF2E86DE),
                                fontSize: 11.5,
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                            Text(
                              '${activeRun.failed}',
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 11.5,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 8),
          Align(
            alignment: Alignment.centerRight,
            child: Padding(
              padding: const EdgeInsets.only(right: 12),
              child: Text(
                widget.runs.last.dateLabel,
                style: const TextStyle(
                  color: Color(0xFF9EA4B0),
                  fontSize: 11,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _DashedLinePainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = const Color(0xFF2E86DE).withValues(alpha: 0.45)
      ..strokeWidth = 1.2;
    const dashWidth = 5.0;
    const dashSpace = 4.0;
    double startX = 0;
    while (startX < size.width) {
      canvas.drawLine(
        Offset(startX, 0),
        Offset(math.min(startX + dashWidth, size.width), 0),
        paint,
      );
      startX += dashWidth + dashSpace;
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
