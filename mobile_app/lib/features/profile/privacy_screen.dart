import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../../core/api/gdpr_api.dart';
import '../../core/app_scope.dart';
import '../../core/config/env.dart';
import '../../core/theme/app_theme.dart';
import '../../widgets/app_ui.dart';

class PrivacyScreen extends StatefulWidget {
  const PrivacyScreen({super.key});

  @override
  State<PrivacyScreen> createState() => _PrivacyScreenState();
}

class _PrivacyScreenState extends State<PrivacyScreen> {
  PrivacyState? _privacy;
  bool _loading = true;
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    final auth = AppScope.of(context).auth;
    try {
      if (auth.isDemo || Env.useMockData) {
        final u = auth.user!;
        _privacy = PrivacyState(
          consensoPrivacy: u.consensoPrivacy,
          consensoMarketing: u.consensoMarketing,
          privacyPolicyVersion: '1.0',
          erasureRequestedAt: u.erasureRequestedAt,
        );
      } else {
        _privacy = await AppScope.of(context).gdprApi.getPrivacy();
      }
    } catch (e) {
      _error = 'Impossibile caricare i consensi';
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _toggleMarketing(bool value) async {
    final deps = AppScope.of(context);
    setState(() => _saving = true);
    try {
      if (deps.auth.isDemo || Env.useMockData) {
        await Future<void>.delayed(const Duration(milliseconds: 200));
        _privacy = PrivacyState(
          consensoPrivacy: _privacy!.consensoPrivacy,
          consensoMarketing: value,
          privacyPolicyVersion: _privacy!.privacyPolicyVersion,
          erasureRequestedAt: _privacy!.erasureRequestedAt,
        );
        deps.auth.updateUser(
          deps.auth.user!.copyWith(consensoMarketing: value),
        );
      } else {
        _privacy = await deps.gdprApi.updateMarketing(value);
        final u = deps.auth.user;
        if (u != null) {
          deps.auth.updateUser(u.copyWith(consensoMarketing: value));
        }
      }
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              value
                  ? 'Consenso marketing attivato'
                  : 'Consenso marketing revocato',
            ),
          ),
        );
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Aggiornamento non riuscito')),
        );
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _export() async {
    final deps = AppScope.of(context);
    try {
      late final List<int> bytes;
      if (deps.auth.isDemo || Env.useMockData) {
        bytes =
            '{"demo":true,"message":"Export disponibile con account reale"}'
                .codeUnits;
      } else {
        bytes = await deps.gdprApi.exportData();
      }

      if (kIsWeb) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Export pronto (salvataggio file non supportato sul web)'),
            ),
          );
        }
        return;
      }

      final file = File(
        '${Directory.systemTemp.path}/miei_dati_${deps.auth.user?.id ?? 0}.json',
      );
      await file.writeAsBytes(bytes, flush: true);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Dati salvati in ${file.path}')),
        );
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Export non riuscito')),
        );
      }
    }
  }

  Future<void> _requestErasure() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.surface,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: const Text(
          'Cancellare i tuoi dati?',
          style: TextStyle(fontWeight: FontWeight.w800),
        ),
        content: const Text(
          'Verrà inviata una richiesta di cancellazione (diritto all’oblio). '
          'Il professionista elaborerà la richiesta. L’accesso all’app potrà essere limitato.',
          style: TextStyle(color: AppColors.muted, height: 1.4),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Annulla'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: FilledButton.styleFrom(
              backgroundColor: AppColors.danger,
              foregroundColor: Colors.white,
              minimumSize: const Size(0, 40),
              padding: const EdgeInsets.symmetric(horizontal: 16),
            ),
            child: const Text('Conferma'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    final deps = AppScope.of(context);
    setState(() => _saving = true);
    try {
      if (deps.auth.isDemo || Env.useMockData) {
        final now = DateTime.now().toUtc().toIso8601String();
        _privacy = PrivacyState(
          consensoPrivacy: _privacy!.consensoPrivacy,
          consensoMarketing: _privacy!.consensoMarketing,
          privacyPolicyVersion: _privacy!.privacyPolicyVersion,
          erasureRequestedAt: now,
        );
        deps.auth.updateUser(
          deps.auth.user!.copyWith(erasureRequestedAt: now),
        );
      } else {
        _privacy = await deps.gdprApi.requestErasure();
        final u = deps.auth.user;
        if (u != null) {
          deps.auth.updateUser(
            u.copyWith(erasureRequestedAt: _privacy!.erasureRequestedAt),
          );
        }
      }
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Richiesta di cancellazione inviata')),
        );
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Richiesta non riuscita')),
        );
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text(
          'Privacy e dati',
          style: TextStyle(fontWeight: FontWeight.w700),
        ),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? AppErrorView(message: _error!, onRetry: _load)
              : ListView(
                  padding: kAppPagePadding,
                  children: [
                    const AppInfoBanner(
                      message:
                          'Gestisci i tuoi consensi e i diritti GDPR (portabilità e oblio).',
                    ),
                    const SizedBox(height: 20),
                    const AppSectionLabel('Consensi'),
                    const SizedBox(height: 10),
                    AppSurfaceCard(
                      child: Column(
                        children: [
                          SwitchListTile(
                            contentPadding: EdgeInsets.zero,
                            title: const Text(
                              'Consenso privacy',
                              style: TextStyle(fontWeight: FontWeight.w700),
                            ),
                            subtitle: const Text(
                              'Necessario per il servizio. Per revocarlo richiedi la cancellazione.',
                              style: TextStyle(
                                color: AppColors.muted,
                                fontSize: 13,
                              ),
                            ),
                            value: _privacy?.consensoPrivacy ?? false,
                            onChanged: null,
                          ),
                          const Divider(color: AppColors.border),
                          SwitchListTile(
                            contentPadding: EdgeInsets.zero,
                            title: const Text(
                              'Consenso marketing',
                              style: TextStyle(fontWeight: FontWeight.w700),
                            ),
                            subtitle: const Text(
                              'Comunicazioni informative o promozionali (WhatsApp/email).',
                              style: TextStyle(
                                color: AppColors.muted,
                                fontSize: 13,
                              ),
                            ),
                            value: _privacy?.consensoMarketing ?? false,
                            onChanged: _saving ? null : _toggleMarketing,
                          ),
                          if (_privacy?.privacyPolicyVersion != null) ...[
                            const SizedBox(height: 8),
                            Align(
                              alignment: Alignment.centerLeft,
                              child: Text(
                                'Policy v${_privacy!.privacyPolicyVersion}',
                                style: const TextStyle(
                                  color: AppColors.muted,
                                  fontSize: 12,
                                ),
                              ),
                            ),
                          ],
                        ],
                      ),
                    ),
                    const SizedBox(height: 22),
                    const AppSectionLabel('I tuoi diritti'),
                    const SizedBox(height: 10),
                    AppSurfaceCard(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          FilledButton.tonal(
                            onPressed: _saving ? null : _export,
                            child: const Text('Scarica i miei dati (JSON)'),
                          ),
                          const SizedBox(height: 10),
                          if (_privacy?.erasurePending == true)
                            const AppInfoBanner(
                              icon: Icons.hourglass_top_rounded,
                              tone: AppBannerTone.accent,
                              message:
                                  'Richiesta di cancellazione già inviata. In attesa di elaborazione.',
                            )
                          else
                            OutlinedButton(
                              onPressed: _saving ? null : _requestErasure,
                              style: OutlinedButton.styleFrom(
                                foregroundColor: AppColors.danger,
                                side: const BorderSide(color: AppColors.danger),
                              ),
                              child: const Text('Richiedi cancellazione dati'),
                            ),
                        ],
                      ),
                    ),
                  ],
                ),
    );
  }
}
