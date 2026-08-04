import 'package:flutter_test/flutter_test.dart';
import 'package:mynutri_app/app.dart';
import 'package:mynutri_app/core/app_scope.dart';
import 'package:mynutri_app/core/auth/token_storage.dart';
import 'package:mynutri_app/core/config/env.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async {
    await Env.load();
    Env.useMockData = true;
  });

  testWidgets('Mostra schermata login con accesso demo', (tester) async {
    final deps = AppDependencies.create(tokenStorage: InMemoryTokenStorage());
    await tester.pumpWidget(
      MyNutriApp(dependencies: deps, enableDeepLinks: false),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.text('MyNutriApp'), findsWidgets);
    expect(find.text('Accedi'), findsOneWidget);
    expect(find.text('Entra in demo'), findsOneWidget);
  });

  testWidgets('Demo login autentica e mostra shell', (tester) async {
    final deps = AppDependencies.create(tokenStorage: InMemoryTokenStorage());
    await tester.pumpWidget(
      MyNutriApp(dependencies: deps, enableDeepLinks: false),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    await tester.tap(find.text('Entra in demo'));
    await tester.pump();
    // loginDemo ha delay 500ms
    await tester.pump(const Duration(milliseconds: 600));
    await tester.pump(); // rebuild post-auth / redirect

    expect(deps.auth.isAuthenticated, isTrue);
    expect(find.textContaining('Ciao'), findsWidgets);
  });
}
