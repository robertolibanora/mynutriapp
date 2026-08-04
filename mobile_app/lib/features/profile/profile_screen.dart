import 'package:flutter/material.dart';

import '../../core/app_scope.dart';
import '../../core/theme/app_theme.dart';
import '../../widgets/app_logo.dart';
import 'privacy_screen.dart';

class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final auth = AppScope.of(context).auth;
    return AnimatedBuilder(
      animation: auth,
      builder: (context, _) {
        final user = auth.user;
        final initial = (user?.nome.isNotEmpty == true)
            ? user!.nome[0].toUpperCase()
            : (user?.displayName.isNotEmpty == true
                ? user!.displayName[0].toUpperCase()
                : '?');

        return Scaffold(
          body: SafeArea(
            child: ListView(
              padding: const EdgeInsets.fromLTRB(20, 20, 20, 28),
              children: [
                Row(
                  children: [
                    const AppLogo(size: 40),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        'Profilo',
                        style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                              fontWeight: FontWeight.w800,
                            ),
                      ),
                    ),
                    Container(
                      width: 44,
                      height: 44,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: AppColors.accentSoft,
                        border: Border.all(
                          color: AppColors.accent.withValues(alpha: 0.35),
                        ),
                      ),
                      child: Text(
                        initial,
                        style: const TextStyle(
                          color: AppColors.accent,
                          fontWeight: FontWeight.w700,
                          fontSize: 17,
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 20),
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                      colors: [
                        Colors.white.withValues(alpha: 0.08),
                        AppColors.accent.withValues(alpha: 0.12),
                      ],
                    ),
                    borderRadius: BorderRadius.circular(18),
                    border: Border.all(color: AppColors.borderStrong),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        user?.displayName ?? '—',
                        style: const TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      if (auth.isDemo) ...[
                        const SizedBox(height: 6),
                        const Text(
                          'Account demo',
                          style: TextStyle(
                            color: AppColors.accent,
                            fontWeight: FontWeight.w600,
                            fontSize: 13,
                          ),
                        ),
                      ],
                      if (user?.telefono != null) ...[
                        const SizedBox(height: 8),
                        Text(
                          user!.telefono!,
                          style: const TextStyle(color: AppColors.muted2),
                        ),
                      ],
                      if (user?.email != null) ...[
                        const SizedBox(height: 4),
                        Text(
                          user!.email!,
                          style: const TextStyle(color: AppColors.muted2),
                        ),
                      ],
                    ],
                  ),
                ),
                const SizedBox(height: 20),
                const Text(
                  'Privacy',
                  style: TextStyle(
                    color: AppColors.muted2,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 8),
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(
                    Icons.shield_outlined,
                    color: AppColors.accent,
                  ),
                  title: const Text('Privacy e dati (GDPR)'),
                  subtitle: Text(
                    user?.erasureRequestedAt != null
                        ? 'Cancellazione in elaborazione'
                        : 'Consensi, export e oblio',
                    style: const TextStyle(color: AppColors.muted2),
                  ),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () {
                    Navigator.of(context).push(
                      MaterialPageRoute<void>(
                        builder: (_) => const PrivacyScreen(),
                      ),
                    );
                  },
                ),
                const Divider(color: AppColors.border),
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(Icons.logout, color: AppColors.muted2),
                  title: const Text('Esci'),
                  onTap: () => auth.logout(),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}
