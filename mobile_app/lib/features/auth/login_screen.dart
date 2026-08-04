import 'package:flutter/material.dart';

import '../../core/app_scope.dart';
import '../../core/theme/app_theme.dart';
import '../../widgets/app_logo.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _telefono = TextEditingController();
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _obscure = true;
  bool _showEmail = false;

  @override
  void dispose() {
    _telefono.dispose();
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final auth = AppScope.of(context).auth;
    final ok = await auth.login(
      telefono: _telefono.text,
      password: _password.text,
      email: _showEmail ? _email.text : null,
    );
    if (!mounted) return;
    if (!ok && auth.error != null) {
      final needsEmail = auth.error!.toLowerCase().contains('email');
      if (needsEmail && !_showEmail) {
        setState(() => _showEmail = true);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = AppScope.of(context).auth;
    return AnimatedBuilder(
      animation: auth,
      builder: (context, _) {
        return Scaffold(
          body: SafeArea(
            child: ListView(
              padding: const EdgeInsets.fromLTRB(24, 56, 24, 32),
              children: [
                const Center(child: AppLogo(size: 72, borderRadius: 16)),
                const SizedBox(height: 20),
                Text(
                  'MyNutriApp',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                        fontWeight: FontWeight.w800,
                        letterSpacing: -0.4,
                      ),
                ),
                const SizedBox(height: 8),
                const Text(
                  'Accedi all\'area paziente',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: AppColors.muted2,
                    fontSize: 15,
                    height: 1.3,
                  ),
                ),
                const SizedBox(height: 40),
                TextField(
                  controller: _telefono,
                  keyboardType: TextInputType.phone,
                  textInputAction: TextInputAction.next,
                  decoration: const InputDecoration(
                    labelText: 'Telefono',
                    prefixIcon: Icon(Icons.phone_outlined),
                  ),
                ),
                if (_showEmail) ...[
                  const SizedBox(height: 12),
                  TextField(
                    controller: _email,
                    keyboardType: TextInputType.emailAddress,
                    textInputAction: TextInputAction.next,
                    decoration: const InputDecoration(
                      labelText: 'Email',
                      prefixIcon: Icon(Icons.mail_outline),
                    ),
                  ),
                ],
                const SizedBox(height: 12),
                TextField(
                  controller: _password,
                  obscureText: _obscure,
                  textInputAction: TextInputAction.done,
                  onSubmitted: (_) {
                    if (!auth.busy) _submit();
                  },
                  decoration: InputDecoration(
                    labelText: 'Password',
                    prefixIcon: const Icon(Icons.lock_outline),
                    suffixIcon: IconButton(
                      onPressed: () => setState(() => _obscure = !_obscure),
                      icon: Icon(
                        _obscure
                            ? Icons.visibility_outlined
                            : Icons.visibility_off_outlined,
                      ),
                    ),
                  ),
                ),
                if (auth.error != null) ...[
                  const SizedBox(height: 16),
                  _LoginErrorBanner(message: auth.error!),
                ],
                const SizedBox(height: 20),
                FilledButton(
                  onPressed: auth.busy ? null : _submit,
                  child: Text(auth.busy ? 'Accesso…' : 'Accedi'),
                ),
                const SizedBox(height: 12),
                OutlinedButton.icon(
                  onPressed: auth.busy
                      ? null
                      : () => AppScope.of(context).auth.loginDemo(),
                  icon: const Icon(Icons.play_circle_outline, size: 20),
                  label: const Text('Entra in demo'),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _LoginErrorBanner extends StatelessWidget {
  const _LoginErrorBanner({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: const Color(0xFF3A1515),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.danger.withValues(alpha: 0.55)),
      ),
      child: Text(
        message,
        style: const TextStyle(
          color: Color(0xFFFFC9C9),
          fontSize: 13.5,
          height: 1.35,
        ),
      ),
    );
  }
}
