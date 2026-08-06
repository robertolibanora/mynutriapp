import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/app_scope.dart';
import '../../widgets/app_ui.dart';

class ForgotPasswordScreen extends StatefulWidget {
  const ForgotPasswordScreen({super.key});

  @override
  State<ForgotPasswordScreen> createState() => _ForgotPasswordScreenState();
}

class _ForgotPasswordScreenState extends State<ForgotPasswordScreen> {
  final _email = TextEditingController();
  String? _info;
  String? _error;
  bool _busy = false;

  @override
  void dispose() {
    _email.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() {
      _busy = true;
      _error = null;
      _info = null;
    });
    try {
      final msg = await AppScope.of(context).auth.forgotPassword(
            email: _email.text,
          );
      if (!mounted) return;
      setState(() => _info = msg);
    } catch (_) {
      if (!mounted) return;
      setState(() => _error = 'Richiesta non riuscita. Riprova.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text(
          'Password dimenticata',
          style: TextStyle(fontWeight: FontWeight.w700),
        ),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.go('/login'),
        ),
      ),
      body: SafeArea(
        child: ListView(
          padding: kAppPagePadding.copyWith(left: 24, right: 24),
          children: [
            const AppInfoBanner(
              message:
                  'Inserisci l\'email del tuo account paziente. '
                  'Se è registrata, riceverai le istruzioni per il reset.',
            ),
            const SizedBox(height: 20),
            TextField(
              controller: _email,
              keyboardType: TextInputType.emailAddress,
              autofillHints: const [AutofillHints.email],
              decoration: const InputDecoration(
                labelText: 'Email',
                prefixIcon: Icon(Icons.mail_outline),
              ),
            ),
            if (_info != null) ...[
              const SizedBox(height: 16),
              AppInfoBanner(
                message: _info!,
                tone: AppBannerTone.accent,
                icon: Icons.check_circle_outline_rounded,
              ),
            ],
            if (_error != null) ...[
              const SizedBox(height: 16),
              AppInfoBanner(
                message: _error!,
                tone: AppBannerTone.danger,
                icon: Icons.error_outline_rounded,
              ),
            ],
            const SizedBox(height: 24),
            FilledButton(
              onPressed: _busy ? null : _submit,
              child: Text(_busy ? 'Invio…' : 'Invia link di reset'),
            ),
          ],
        ),
      ),
    );
  }
}
