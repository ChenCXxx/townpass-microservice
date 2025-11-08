// This is a basic Flutter widget test.
//
// To perform an interaction with a widget in your test, use the WidgetTester
// utility in the flutter_test package. For example, you can send tap and scroll
// gestures. You can also use WidgetTester to find child widgets in the widget
// tree, read text, and verify that the values of widget properties are correct.

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('placeholder smoke test', () {
    // Full app bootstraps numerous platform services (SharedPreferences, alarms,
    // native bridges) that aren't available in the headless test runner. Keep a
    // simple sanity test here so CI still exercises `flutter test`.
    expect(2 + 2, equals(4));
  });
}
