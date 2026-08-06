import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/app_scope.dart';
import '../../core/theme/app_theme.dart';
import '../../widgets/app_logo.dart';
import '../../widgets/app_ui.dart';

class ResetPasswordScreen extends StatefulWidget {
  const ResetPasswordScreen({super.key, required this.token});

  final String token;

  @override
  State<ResetPasswordScreen> createState() => _ResetPasswordScreenState();
}

class _ResetPasswordScreenState extends State<ResetPasswordScreen> {
  final _password = TextEditingController();
  final _confirm = TextEditingController();
  bool _obscure = true;
  bool _busy = false;
  String? _error;
  String? _success;

  @override
  void dispose() {
    _password.dispose();
    _confirm.dispose();
    super.dispose();
  }

  String? _validate() {
    final p = _password.text;
    final c = _confirm.text;
    if (widget.token.trim().isEmpty) {
      return 'Link non valido. Richiedi un nuovo reset password.';
    }
    if (p.length < 8) {
      return 'La password deve avere almeno 8 caratteri.';
    }
    if (p != c) {
      return 'Le password non coincidono.';
    }
    return null;
  }

  Future<void> _submit() async {
    final validation = _validate();
    if (validation != null) {
      setState(() {
        _error = validation;
        _success = null;
      });
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
      _success = null;
    });
    try {
      final msg = await AppScope.of(context).auth.resetPassword(
            token: widget.token,
            password: _password.text,
            passwordConfirm: _confirm.text,
          );
      if (!mounted) return;
      setState(() => _success = msg);
    } on DioException catch (e) {
      if (!mounted) return;
      final data = e.response?.data;
      final code = data is Map ? data['code'] as String? : null;
      final message = data is Map
          ? (data['error'] as String? ?? data['message'] as String?)
          : null;
      if (code == 'invalid_token') {
        setState(
          () => _error =
              'Link non valido, scaduto o già usato. Richiedi un nuovo reset dall\'app.',
        );
      } else if (code == 'weak_password' || code == 'password_mismatch') {
        setState(() => _error = message ?? 'Password non valida.');
      } else {
        setState(() => _error = message ?? 'Reset non riuscito. Riprova.');
      }
    } catch (_) {
      if (!mounted) return;
      setState(() => _error = 'Errore di connessione. Riprova.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final missingToken = widget.token.trim().isEmpty;
    return Scaffold(
      appBar: AppBar(
        title: const Text(
          'Nuova password',
          style: TextStyle(fontWeight: FontWeight.w700),
        ),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.go('/login'),
        ),
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(24, 24, 24, 32),
          children: [
            const Center(child: AppLogo(size: 64, borderRadius: 14)),
            const SizedBox(height: 16),
            Text(
              'Imposta nuova password',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                    fontWeight: FontWeight.w800,
                  ),
            ),
            const SizedBox(height: 8),
            const Text(
              'Dopo il salvataggio le sessioni precedenti verranno invalidate.',
              textAlign: TextAlign.center,
              style: TextStyle(color: AppColors.muted, height: 1.35),
            ),
            const SizedBox(height: 28),
            if (missingToken)
              const AppInfoBanner(
                tone: AppBannerTone.danger,
                icon: Icons.link_off_rounded,
                message:
                    'Link non valido. Usa “Password dimenticata?” dal login.',
              )
            else if (_success != null) ...[
              AppInfoBanner(
                message: _success!,
                tone: AppBannerTone.accent,
                icon: Icons.check_circle_outline_rounded,
              ),
              const SizedBox(height: 20),
              FilledButton(
                onPressed: () => context.go('/login'),
                child: const Text('Vai al login'),
              ),
            ] else ...[
              TextField(
                controller: _password,
                obscureText: _obscure,
                autofillHints: const [AutofillHints.newPassword],
                decoration: InputDecoration(
                  labelText: 'Nuova password',
                  prefixIcon: const Icon(Icons.lock_outline),
                  suffixIcon: IconButton(
                    onPressed: () => setState(() => _obscure = !_obscure),
                    icon: Icon(
                      _obscure
                          ? Icons.visibility_outlined
                          : Icons.visibility_off_outlined,
                    ),
                  ),
                  helperText: 'Minimo 8 caratteri',
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _confirm,
                obscureText: _obscure,
                onSubmitted: (_) {
                  if (!_busy) _submit();
                },
                decoration: const InputDecoration(
                  labelText: 'Conferma password',
                  prefixIcon: Icon(Icons.lock_outline),
                ),
              ),
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
                child: Text(_busy ? 'Salvataggio…' : 'Salva password'),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
