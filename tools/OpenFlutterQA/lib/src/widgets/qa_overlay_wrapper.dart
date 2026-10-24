import 'package:flutter/material.dart';
import '../services/ai_qa_service.dart';
import '../services/test_execution_engine.dart';
import 'qa_dashboard.dart';

/// Embeddable Flutter QA Automation plugin wrapper.
///
/// Wrap your root `MaterialApp` or screen with [OpenFlutterQAWrapper] to attach
/// a floating QA Studio toggle button and run AI-refined test suites in-app.
class OpenFlutterQAWrapper extends StatefulWidget {
  final Widget child;
  final bool enabled;
  final bool initiallyOpen;
  final AiQaService? aiService;
  final TestExecutionEngine? executionEngine;

  const OpenFlutterQAWrapper({
    super.key,
    required this.child,
    this.enabled = true,
    this.initiallyOpen = false,
    this.aiService,
    this.executionEngine,
  });

  @override
  State<OpenFlutterQAWrapper> createState() => _OpenFlutterQAWrapperState();
}

class _OpenFlutterQAWrapperState extends State<OpenFlutterQAWrapper> {
  late bool _isStudioOpen;

  @override
  void initState() {
    super.initState();
    _isStudioOpen = widget.initiallyOpen;
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.enabled) return widget.child;

    return Directionality(
      textDirection: TextDirection.ltr,
      child: Stack(
        children: [
          widget.child,
          if (_isStudioOpen)
            Positioned.fill(
              child: Material(
                color: Colors.black87,
                child: OpenFlutterQADashboard(
                  aiService: widget.aiService,
                  executionEngine: widget.executionEngine,
                  hostAppContext: context,
                  onCloseOverlay: () => setState(() => _isStudioOpen = false),
                ),
              ),
            ),
          if (!_isStudioOpen)
            Positioned(
              right: 20,
              bottom: 24,
              child: FloatingActionButton.extended(
                key: const Key('open_qa_studio_fab'),
                backgroundColor: const Color(0xFF181A1F),
                foregroundColor: const Color(0xFF52B788),
                onPressed: () => setState(() => _isStudioOpen = true),
                icon: const Icon(Icons.biotech_rounded),
                label: const Text(
                  'QA Studio',
                  style: TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
