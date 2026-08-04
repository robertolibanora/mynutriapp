import 'package:flutter_test/flutter_test.dart';
import 'package:mynutri_app/core/routing/app_router.dart';

void main() {
  test('parse custom scheme activate-account', () {
    final uri = Uri.parse('mynutriapp://activate-account?token=abc123');
    expect(deepLinkLocation(uri), '/activate-account?token=abc123');
  });

  test('parse custom scheme reset-password', () {
    final uri = Uri.parse('mynutriapp://reset-password?token=xyz');
    expect(deepLinkLocation(uri), '/reset-password?token=xyz');
  });

  test('parse https activate-account', () {
    final uri = Uri.parse(
      'https://stage.mynutriapp.cloud/activate-account?token=tok%2B1',
    );
    expect(
      deepLinkLocation(uri),
      '/activate-account?token=${Uri.encodeQueryComponent('tok+1')}',
    );
  });

  test('ignore unknown paths', () {
    final uri = Uri.parse('https://stage.mynutriapp.cloud/prenota/studio');
    expect(deepLinkLocation(uri), isNull);
  });
}
