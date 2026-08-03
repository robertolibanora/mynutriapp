import 'package:flutter/foundation.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';

/// Configurazione runtime (dart-define > .env > default).
class Env {
  Env._();

  static String apiBaseUrl = 'https://stage.mynutriapp.cloud';
  static bool useMockData = false;

  static Future<void> load() async {
    try {
      await dotenv.load(fileName: '.env.example');
    } catch (_) {
      // Asset opzionale in test/CI.
    }

    const defineUrl = String.fromEnvironment('API_BASE_URL');
    const defineMock = String.fromEnvironment('USE_MOCK_DATA');

    apiBaseUrl = defineUrl.isNotEmpty
        ? defineUrl
        : (dotenv.maybeGet('API_BASE_URL') ?? apiBaseUrl);
    apiBaseUrl = apiBaseUrl.replaceAll(RegExp(r'/$'), '');

    if (defineMock.isNotEmpty) {
      useMockData = defineMock.toLowerCase() == 'true';
    } else {
      useMockData =
          (dotenv.maybeGet('USE_MOCK_DATA') ?? 'false').toLowerCase() == 'true';
    }

    if (kDebugMode) {
      debugPrint('Env apiBaseUrl=$apiBaseUrl useMockData=$useMockData');
    }
  }
}
