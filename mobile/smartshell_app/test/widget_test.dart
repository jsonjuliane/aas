// This is a basic Flutter widget test.
//
// To perform an interaction with a widget in your test, use the WidgetTester
// utility in the flutter_test package. For example, you can send tap and scroll
// gestures. You can also use WidgetTester to find child widgets in the widget
// tree, read text, and verify that the values of widget properties are correct.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:smartshell_app/main.dart';

void main() {
  testWidgets('shows SmartShell link screen', (WidgetTester tester) async {
    await tester.pumpWidget(const SmartShellApp());

    expect(find.text('SmartShell Link'), findsOneWidget);
    expect(find.text('Connect to Helmet'), findsOneWidget);
    expect(find.text('Mock'), findsNothing);
    expect(find.text('Open Mock Helmet'), findsNothing);
  });

  testWidgets('starts with empty PIN and validates before connecting', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const SmartShellApp());

    final pinField = tester.widget<TextField>(find.byType(TextField));
    expect(pinField.controller?.text, isEmpty);

    await tester.tap(find.text('Connect to Helmet'));
    await tester.pump();

    expect(
      find.text('Enter the helmet PIN before connecting.'),
      findsOneWidget,
    );
  });

  testWidgets('saves contact sheet without crashing', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: ConfigHomeScreen(
          transport: TestConfigTransport(
            HelmetConfig(
              riderName: 'Test Rider',
              homeBarangay: 'Zapote',
              contacts: [
                EmergencyContact(
                  name: 'Mom',
                  phone: '+639201234567',
                  priority: 1,
                ),
              ],
              messageTemplate: 'Alert {name}',
            ),
          ),
          initialConfig: HelmetConfig(
            riderName: 'Test Rider',
            homeBarangay: 'Zapote',
            contacts: [
              EmergencyContact(
                name: 'Mom',
                phone: '+639201234567',
                priority: 1,
              ),
            ],
            messageTemplate: 'Alert {name}',
          ),
          pin: '000000',
        ),
      ),
    );

    expect(find.byIcon(Icons.delete_outline), findsNothing);

    await tester.ensureVisible(find.text('Add Contact'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Add Contact'));
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, 'Name'), 'Dad');
    await tester.enterText(
      find.widgetWithText(TextField, 'Phone'),
      '+639209876543',
    );
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(find.text('Dad'), findsOneWidget);
    expect(find.byIcon(Icons.delete_outline), findsWidgets);
  });
}

class TestConfigTransport implements ConfigTransport {
  TestConfigTransport(this.config);

  HelmetConfig config;

  @override
  String get label => 'Test helmet';

  @override
  Future<void> close() async {}

  @override
  Future<ConfigResponse> send(Map<String, dynamic> command) async {
    final op = '${command['op'] ?? ''}';
    if (op == 'add_contact') {
      final contacts = [
        ...config.contacts,
        EmergencyContact(
          name: '${command['name'] ?? ''}',
          phone: '${command['phone'] ?? ''}',
          priority: config.contacts.length + 1,
        ),
      ];
      config = HelmetConfig(
        riderName: config.riderName,
        homeBarangay: config.homeBarangay,
        contacts: contacts,
        messageTemplate: config.messageTemplate,
      );
      return ConfigResponse({'ok': true, 'data': _configJson(config)});
    }
    return ConfigResponse({'ok': false, 'error': 'Unsupported op: $op'});
  }

  Map<String, dynamic> _configJson(HelmetConfig config) {
    return {
      'rider_name': config.riderName,
      'subject_home_barangay': config.homeBarangay,
      'contacts': config.contacts.map((contact) => contact.toJson()).toList(),
      'message_template': config.messageTemplate,
    };
  }
}
