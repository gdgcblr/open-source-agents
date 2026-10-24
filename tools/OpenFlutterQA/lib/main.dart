import 'package:flutter/material.dart';
import 'open_flutter_qa.dart';

void main() {
  runApp(const OpenFlutterQAStudioApp());
}

class OpenFlutterQAStudioApp extends StatelessWidget {
  const OpenFlutterQAStudioApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'OpenFlutterQA Automation Studio',
      debugShowCheckedModeBanner: false,
      theme: ThemeData.dark(useMaterial3: true).copyWith(
        scaffoldBackgroundColor: const Color(0xFF0F1115),
        colorScheme: const ColorScheme.dark(
          primary: Color(0xFF52B788),
          secondary: Color(0xFF64B5F6),
          surface: Color(0xFF181A1F),
        ),
      ),
      home: const OpenFlutterQADashboard(),
    );
  }
}
