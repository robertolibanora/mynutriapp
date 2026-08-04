import 'package:flutter/material.dart';

import '../../core/api/patient_api.dart';
import '../../core/app_scope.dart';
import '../../core/config/env.dart';
import '../../core/theme/app_theme.dart';
import '../../widgets/empty_placeholder.dart';

class AppointmentsScreen extends StatefulWidget {
  const AppointmentsScreen({super.key});

  @override
  State<AppointmentsScreen> createState() => _AppointmentsScreenState();
}

class _AppointmentsScreenState extends State<AppointmentsScreen> {
  Future<List<Map<String, dynamic>>>? _future;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _future ??= _load();
  }

  Future<List<Map<String, dynamic>>> _load() async {
    final auth = AppScope.of(context).auth;
    if (Env.useMockData || auth.isDemo) return const [];
    return PatientApi(AppScope.of(context).apiClient).fetchAppointments();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text(
          'Prenota',
          style: TextStyle(fontWeight: FontWeight.w700),
        ),
      ),
      body: FutureBuilder<List<Map<String, dynamic>>>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          final items = snap.data ?? const [];
          if (items.isEmpty) {
            return const EmptyPlaceholder(
              icon: Icons.event_busy_outlined,
              message: 'Nessun appuntamento',
            );
          }
          return RefreshIndicator(
            color: AppColors.accent,
            onRefresh: () async {
              setState(() => _future = _load());
              await _future;
            },
            child: ListView.separated(
              padding: const EdgeInsets.fromLTRB(18, 12, 18, 28),
              itemCount: items.length,
              separatorBuilder: (_, _) => const SizedBox(height: 10),
              itemBuilder: (context, i) {
                final a = items[i];
                final data = a['data']?.toString() ?? '—';
                final ora = a['ora']?.toString() ?? '';
                final tipo = (a['tipo_label'] as String?) ??
                    (a['tipo'] as String?) ??
                    'Appuntamento';
                final stato = (a['stato_label'] as String?) ??
                    (a['stato'] as String?) ??
                    '';
                return Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.05),
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(color: AppColors.border),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        tipo,
                        style: const TextStyle(
                          fontWeight: FontWeight.w700,
                          fontSize: 15.5,
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        ora.isEmpty ? data : '$data · $ora',
                        style: const TextStyle(
                          color: AppColors.muted2,
                          fontSize: 14,
                        ),
                      ),
                      if (stato.isNotEmpty) ...[
                        const SizedBox(height: 8),
                        Text(
                          stato,
                          style: const TextStyle(
                            color: AppColors.accent,
                            fontWeight: FontWeight.w600,
                            fontSize: 13,
                          ),
                        ),
                      ],
                    ],
                  ),
                );
              },
            ),
          );
        },
      ),
    );
  }
}
