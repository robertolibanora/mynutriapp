import 'package:flutter/material.dart';

import '../../core/app_scope.dart';
import '../../core/auth/auth_controller.dart';
import '../../core/branding.dart';
import '../../core/theme/app_theme.dart';
import '../../widgets/app_ui.dart';
import 'privacy_screen.dart';

class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});

  static String _initials(String? name) {
    final parts = (name ?? '')
        .trim()
        .split(RegExp(r'\s+'))
        .where((p) => p.isNotEmpty)
        .toList();
    if (parts.isEmpty) return '?';
    if (parts.length == 1) {
      return parts.first.substring(0, 1).toUpperCase();
    }
    return (parts[0].substring(0, 1) + parts[1].substring(0, 1)).toUpperCase();
  }

  Future<void> _confirmLogout(BuildContext context, AuthController auth) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.surface,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: const Text(
          'Esci dall’account?',
          style: TextStyle(fontWeight: FontWeight.w800),
        ),
        content: const Text(
          'Potrai accedere di nuovo con telefono e password.',
          style: TextStyle(color: AppColors.muted, height: 1.4),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Annulla'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            style: FilledButton.styleFrom(
              backgroundColor: AppColors.danger,
              foregroundColor: Colors.white,
              minimumSize: const Size(0, 40),
              padding: const EdgeInsets.symmetric(horizontal: 16),
            ),
            child: const Text('Esci'),
          ),
        ],
      ),
    );
    if (ok == true) await auth.logout();
  }

  void _openPrivacy(BuildContext context) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => const PrivacyScreen(),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final auth = AppScope.of(context).auth;
    return AnimatedBuilder(
      animation: auth,
      builder: (context, _) {
        final user = auth.user;
        final erasurePending = user?.erasureRequestedAt != null;

        return Scaffold(
          body: SafeArea(
            child: ListView(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 28),
              children: [
                const AppPageHeader(
                  title: 'Profilo',
                  subtitle: 'Account e preferenze',
                ),
                const SizedBox(height: 20),
                _IdentityCard(
                  initials: _initials(user?.displayName),
                  name: user?.displayName ?? '—',
                  isDemo: auth.isDemo,
                  telefono: user?.telefono,
                  email: user?.email,
                ),
                if (erasurePending) ...[
                  const SizedBox(height: 12),
                  const AppInfoBanner(
                    icon: Icons.hourglass_top_rounded,
                    tone: AppBannerTone.danger,
                    message:
                        'Cancellazione in elaborazione. La richiesta di oblio è stata ricevuta.',
                  ),
                ],
                const SizedBox(height: 24),
                const AppSectionLabel('Privacy e dati'),
                const SizedBox(height: 10),
                _SettingsCard(
                  children: [
                    _SettingsTile(
                      icon: Icons.shield_outlined,
                      title: 'Privacy e dati (GDPR)',
                      subtitle: erasurePending
                          ? 'Cancellazione in elaborazione'
                          : 'Consensi, export e richiesta di cancellazione',
                      onTap: () => _openPrivacy(context),
                    ),
                  ],
                ),
                const SizedBox(height: 22),
                const AppSectionLabel('Account'),
                const SizedBox(height: 10),
                _SettingsCard(
                  children: [
                    _SettingsTile(
                      icon: Icons.logout_rounded,
                      title: 'Esci',
                      subtitle: 'Disconnetti questo dispositivo',
                      destructive: true,
                      onTap: () => _confirmLogout(context, auth),
                    ),
                  ],
                ),
                const SizedBox(height: 32),
                Center(
                  child: Text(
                    '$kAppName · v1.0.0',
                    style: TextStyle(
                      color: AppColors.muted.withValues(alpha: 0.85),
                      fontSize: 12.5,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _IdentityCard extends StatelessWidget {
  const _IdentityCard({
    required this.initials,
    required this.name,
    required this.isDemo,
    this.telefono,
    this.email,
  });

  final String initials;
  final String name;
  final bool isDemo;
  final String? telefono;
  final String? email;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: AppColors.accent.withValues(alpha: 0.28),
        ),
      ),
      child: Column(
        children: [
          CircleAvatar(
            radius: 36,
            backgroundColor: AppColors.accent.withValues(alpha: 0.16),
            child: Text(
              initials,
              style: const TextStyle(
                color: AppColors.accent,
                fontWeight: FontWeight.w800,
                fontSize: 22,
              ),
            ),
          ),
          const SizedBox(height: 14),
          Text(
            name,
            textAlign: TextAlign.center,
            style: const TextStyle(
              fontSize: 20,
              fontWeight: FontWeight.w800,
            ),
          ),
          if (isDemo) ...[
            const SizedBox(height: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(
                color: AppColors.accent.withValues(alpha: 0.14),
                borderRadius: BorderRadius.circular(8),
              ),
              child: const Text(
                'Account demo',
                style: TextStyle(
                  color: AppColors.accent,
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
          ],
          if ((telefono != null && telefono!.isNotEmpty) ||
              (email != null && email!.isNotEmpty)) ...[
            const SizedBox(height: 16),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              decoration: BoxDecoration(
                color: AppColors.bg.withValues(alpha: 0.55),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: AppColors.border),
              ),
              child: Column(
                children: [
                  if (telefono != null && telefono!.isNotEmpty)
                    _ContactRow(
                      icon: Icons.phone_outlined,
                      value: telefono!,
                    ),
                  if (telefono != null &&
                      telefono!.isNotEmpty &&
                      email != null &&
                      email!.isNotEmpty)
                    const SizedBox(height: 10),
                  if (email != null && email!.isNotEmpty)
                    _ContactRow(
                      icon: Icons.mail_outline_rounded,
                      value: email!,
                    ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _ContactRow extends StatelessWidget {
  const _ContactRow({required this.icon, required this.value});

  final IconData icon;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, size: 18, color: AppColors.accent),
        const SizedBox(width: 10),
        Expanded(
          child: Text(
            value,
            style: const TextStyle(
              color: AppColors.muted,
              fontSize: 13.5,
              height: 1.3,
            ),
          ),
        ),
      ],
    );
  }
}

class _SettingsCard extends StatelessWidget {
  const _SettingsCard({required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.border),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(children: children),
    );
  }
}

class _SettingsTile extends StatelessWidget {
  const _SettingsTile({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
    this.destructive = false,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;
  final bool destructive;

  @override
  Widget build(BuildContext context) {
    final accent = destructive ? AppColors.danger : AppColors.accent;
    final titleColor = destructive ? AppColors.danger : AppColors.text;

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
          child: Row(
            children: [
              Container(
                width: 42,
                height: 42,
                decoration: BoxDecoration(
                  color: accent.withValues(alpha: 0.14),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(icon, color: accent, size: 22),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: TextStyle(
                        fontWeight: FontWeight.w700,
                        fontSize: 15.5,
                        color: titleColor,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      subtitle,
                      style: const TextStyle(
                        color: AppColors.muted,
                        fontSize: 12.5,
                        height: 1.3,
                      ),
                    ),
                  ],
                ),
              ),
              if (!destructive)
                const Icon(
                  Icons.chevron_right_rounded,
                  color: AppColors.muted,
                ),
            ],
          ),
        ),
      ),
    );
  }
}
