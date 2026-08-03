import 'package:flutter/material.dart';

import '../../core/app_scope.dart';
import '../../core/theme/app_theme.dart';
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
        return Scaffold(
          body: SafeArea(
            child: ListView(
              padding: const EdgeInsets.all(20),
              children: [
                Text(
                  'Profilo',
                  style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                        fontWeight: FontWeight.w800,
                      ),
                ),
                const SizedBox(height: 16),
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: AppColors.surface,
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(color: AppColors.border),
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
                      if (user?.telefono != null) ...[
                        const SizedBox(height: 6),
                        Text(
                          user!.telefono!,
                          style: const TextStyle(color: AppColors.muted),
                        ),
                      ],
                      if (user?.email != null) ...[
                        const SizedBox(height: 4),
                        Text(
                          user!.email!,
                          style: const TextStyle(color: AppColors.muted),
                        ),
                      ],
                    ],
                  ),
                ),
                const SizedBox(height: 20),
                const Text(
                  'Privacy',
                  style: TextStyle(
                    color: AppColors.muted,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 8),
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(Icons.shield_outlined, color: AppColors.accent),
                  title: const Text('Privacy e dati (GDPR)'),
                  subtitle: Text(
                    user?.erasureRequestedAt != null
                        ? 'Cancellazione in elaborazione'
                        : 'Consensi, export e oblio',
                    style: const TextStyle(color: AppColors.muted),
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
                  leading: const Icon(Icons.logout, color: AppColors.muted),
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
