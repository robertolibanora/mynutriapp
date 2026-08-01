import 'package:flutter_test/flutter_test.dart';
import 'package:mynutri_app/app.dart';
import 'package:mynutri_app/core/app_scope.dart';
import 'package:mynutri_app/core/auth/token_storage.dart';
import 'package:mynutri_app/core/config/env.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async {
    await Env.load();
  });

  testWidgets('Mostra schermata login con accesso demo', (tester) async {
    final deps = AppDependencies.create(tokenStorage: InMemoryTokenStorage());
    await tester.pumpWidget(MyNutriApp(dependencies: deps));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.text('MyNutriApp'), findsWidgets);
    expect(find.text('Accedi'), findsOneWidget);
    expect(find.text('Entra in demo'), findsOneWidget);
  });

  testWidgets('Demo login apre la home', (tester) async {
    final deps = AppDependencies.create(tokenStorage: InMemoryTokenStorage());
    await tester.pumpWidget(MyNutriApp(dependencies: deps));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    await tester.tap(find.text('Entra in demo'));
    await tester.pump();
    // Completa delay mock repository + navigazione.
    await tester.pump(const Duration(seconds: 1));

    expect(find.textContaining('Ciao'), findsWidgets);
  });
}
