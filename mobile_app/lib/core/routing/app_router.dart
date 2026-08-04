import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../features/auth/activate_account_screen.dart';
import '../../features/auth/forgot_password_screen.dart';
import '../../features/auth/login_screen.dart';
import '../../features/auth/reset_password_screen.dart';
import '../../features/shell/main_shell.dart';
import '../auth/auth_controller.dart';
import '../theme/app_theme.dart';

/// Router app: login, shell, activate/reset (deep link).
GoRouter createAppRouter(AuthController auth) {
  return GoRouter(
    initialLocation: '/',
    refreshListenable: auth,
    redirect: (context, state) {
      final loc = state.matchedLocation;
      final loggingIn = loc == '/login' || loc == '/';
      final publicAuth = loc == '/forgot-password' ||
          loc == '/activate-account' ||
          loc == '/reset-password';

      if (auth.bootstrapping) return null;

      if (!auth.isAuthenticated && !loggingIn && !publicAuth) {
        return '/login';
      }
      if (auth.isAuthenticated && (loggingIn || loc == '/forgot-password')) {
        return '/home';
      }
      return null;
    },
    routes: [
      GoRoute(
        path: '/',
        builder: (context, state) {
          if (auth.bootstrapping) {
            return const Scaffold(
              backgroundColor: Color(0xFF000000),
              body: Center(
                child: CircularProgressIndicator(color: AppColors.accent),
              ),
            );
          }
          if (auth.isAuthenticated) {
            return const MainShell();
          }
          return const LoginScreen();
        },
      ),
      GoRoute(
        path: '/login',
        builder: (context, state) => const LoginScreen(),
      ),
      GoRoute(
        path: '/home',
        builder: (context, state) => const MainShell(),
      ),
      GoRoute(
        path: '/forgot-password',
        builder: (context, state) => const ForgotPasswordScreen(),
      ),
      GoRoute(
        path: '/activate-account',
        builder: (context, state) {
          final token = state.uri.queryParameters['token'] ?? '';
          return ActivateAccountScreen(token: token);
        },
      ),
      GoRoute(
        path: '/reset-password',
        builder: (context, state) {
          final token = state.uri.queryParameters['token'] ?? '';
          return ResetPasswordScreen(token: token);
        },
      ),
    ],
  );
}

/// Estrae path interno da URI deep link (custom scheme o https).
String? deepLinkLocation(Uri uri) {
  // mynutriapp://activate-account?token=...
  // https://stage.mynutriapp.cloud/activate-account?token=...
  final hostPath = uri.host.isNotEmpty &&
          (uri.path.isEmpty || uri.path == '/')
      ? '/${uri.host}'
      : uri.path.startsWith('/')
          ? uri.path
          : '/${uri.path}';

  String path = hostPath;
  if (uri.scheme == 'mynutriapp') {
    // host = activate-account | reset-password
    if (uri.host.isNotEmpty) {
      path = '/${uri.host}';
    }
  }

  if (path == '/activate-account' || path == '/reset-password') {
    final token = uri.queryParameters['token'];
    if (token == null || token.isEmpty) return path;
    return '$path?token=${Uri.encodeQueryComponent(token)}';
  }
  return null;
}
