// This is a basic Flutter widget test.
//
// To perform an interaction with a widget in your test, use the WidgetTester
// utility in the flutter_test package. For example, you can send tap and scroll
// gestures. You can also use WidgetTester to find child widgets in the widget
// tree, read text, and verify that the values of widget properties are correct.

import 'package:flutter_test/flutter_test.dart';

import 'package:smartshell_app/main.dart';

void main() {
  testWidgets('shows SmartShell link screen', (WidgetTester tester) async {
    await tester.pumpWidget(const SmartShellApp());

    expect(find.text('SmartShell Link'), findsOneWidget);
    expect(find.text('Open Mock Helmet'), findsOneWidget);
  });

  testWidgets('opens mock helmet config with default PIN', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const SmartShellApp());

    await tester.tap(find.text('Open Mock Helmet'));
    await tester.pumpAndSettle(const Duration(seconds: 1));

    expect(find.text('SmartShell Setup'), findsOneWidget);
    expect(find.text('Rider Info'), findsOneWidget);
    expect(find.text('Emergency Contacts'), findsOneWidget);
  });
}
