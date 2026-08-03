import 'package:flutter/widgets.dart';

import 'api/api_client.dart';
import 'api/gdpr_api.dart';
import 'auth/auth_controller.dart';
import 'auth/token_storage.dart';

class AppDependencies {
  AppDependencies({
    required this.tokenStorage,
    required this.apiClient,
    required this.auth,
    required this.gdprApi,
  });

  factory AppDependencies.create({TokenStorage? tokenStorage}) {
    final tokens = tokenStorage ?? SecureTokenStorage();
    final api = ApiClient(tokenStorage: tokens);
    return AppDependencies(
      tokenStorage: tokens,
      apiClient: api,
      auth: AuthController(apiClient: api, tokenStorage: tokens),
      gdprApi: GdprApi(api),
    );
  }

  final TokenStorage tokenStorage;
  final ApiClient apiClient;
  final AuthController auth;
  final GdprApi gdprApi;
}

class AppScope extends InheritedWidget {
  const AppScope({
    super.key,
    required this.dependencies,
    required super.child,
  });

  final AppDependencies dependencies;

  static AppDependencies of(BuildContext context) {
    final scope = context.dependOnInheritedWidgetOfExactType<AppScope>();
    assert(scope != null, 'AppScope non trovato');
    return scope!.dependencies;
  }

  @override
  bool updateShouldNotify(AppScope oldWidget) =>
      dependencies != oldWidget.dependencies;
}
