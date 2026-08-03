import 'package:flutter/material.dart';

import 'core/app_scope.dart';
import 'core/theme/app_theme.dart';
import 'features/auth/login_screen.dart';
import 'features/shell/main_shell.dart';

class MyNutriApp extends StatefulWidget {
  const MyNutriApp({super.key, required this.dependencies});

  final AppDependencies dependencies;

  @override
  State<MyNutriApp> createState() => _MyNutriAppState();
}

class _MyNutriAppState extends State<MyNutriApp> {
  @override
  void initState() {
    super.initState();
    widget.dependencies.auth.bootstrap();
  }

  @override
  Widget build(BuildContext context) {
    return AppScope(
      dependencies: widget.dependencies,
      child: MaterialApp(
        title: 'MyNutriApp',
        debugShowCheckedModeBanner: false,
        theme: buildAppTheme(),
        home: AnimatedBuilder(
          animation: widget.dependencies.auth,
          builder: (context, _) {
            final auth = widget.dependencies.auth;
            if (auth.bootstrapping) {
              return const Scaffold(
                body: Center(child: CircularProgressIndicator()),
              );
            }
            if (auth.isAuthenticated) {
              return const MainShell();
            }
            return const LoginScreen();
          },
        ),
      ),
    );
  }
}
