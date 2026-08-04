import 'dart:async';

import 'package:app_links/app_links.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import 'core/app_scope.dart';
import 'core/routing/app_router.dart';
import 'core/theme/app_theme.dart';

const _bootBg = Color(0xFF000000);

class MyNutriApp extends StatefulWidget {
  const MyNutriApp({
    super.key,
    required this.dependencies,
    this.enableDeepLinks = true,
  });

  final AppDependencies dependencies;
  final bool enableDeepLinks;

  @override
  State<MyNutriApp> createState() => _MyNutriAppState();
}

class _MyNutriAppState extends State<MyNutriApp> {
  late final GoRouter _router;
  StreamSubscription<Uri>? _linkSub;

  @override
  void initState() {
    super.initState();
    _router = createAppRouter(widget.dependencies.auth);
    widget.dependencies.auth.bootstrap();
    if (widget.enableDeepLinks) {
      unawaited(_initDeepLinks());
    }
  }

  Future<void> _initDeepLinks() async {
    try {
      final appLinks = AppLinks();
      final initial = await appLinks.getInitialLink();
      if (initial != null) {
        _handleUri(initial);
      }
      _linkSub = appLinks.uriLinkStream.listen(
        _handleUri,
        onError: (Object e) {
          if (kDebugMode) debugPrint('deep link stream error: $e');
        },
      );
    } catch (e) {
      if (kDebugMode) debugPrint('deep link init error: $e');
    }
  }

  void _handleUri(Uri uri) {
    final loc = deepLinkLocation(uri);
    if (loc == null) return;
    if (kDebugMode) debugPrint('deep link → $loc');
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _router.go(loc);
    });
  }

  @override
  void dispose() {
    _linkSub?.cancel();
    _router.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AppScope(
      dependencies: widget.dependencies,
      child: MaterialApp.router(
        title: 'MyNutriApp',
        debugShowCheckedModeBanner: false,
        theme: buildAppTheme(),
        color: _bootBg,
        routerConfig: _router,
      ),
    );
  }
}
