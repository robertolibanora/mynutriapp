import 'package:flutter/material.dart';

import '../../core/api/patient_api.dart';
import '../../core/app_scope.dart';
import '../../core/config/env.dart';
import '../../core/theme/app_theme.dart';
import '../../widgets/empty_placeholder.dart';

class ProgressScreen extends StatefulWidget {
  const ProgressScreen({super.key});

  @override
  State<ProgressScreen> createState() => _ProgressScreenState();
}

class _ProgressScreenState extends State<ProgressScreen> {
  Future<List<Map<String, dynamic>>>? _future;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _future ??= _load();
  }

  Future<List<Map<String, dynamic>>> _load() async {
    final auth = AppScope.of(context).auth;
    if (Env.useMockData || auth.isDemo) return const [];
    return PatientApi(AppScope.of(context).apiClient).fetchProgress();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text(
          'Progressi',
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
              icon: Icons.show_chart_outlined,
              message: 'Nessun progresso da mostrare ancora',
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
                final p = items[i];
                final peso = p['peso_settimanale'];
                final data = p['data_check']?.toString() ?? '—';
                final aderenza = p['aderenza']?.toString();
                return Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.05),
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(color: AppColors.border),
                  ),
                  child: Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              data,
                              style: const TextStyle(
                                fontWeight: FontWeight.w700,
                                fontSize: 15.5,
                              ),
                            ),
                            if (aderenza != null && aderenza.isNotEmpty) ...[
                              const SizedBox(height: 4),
                              Text(
                                'Aderenza: $aderenza',
                                style: const TextStyle(
                                  color: AppColors.muted2,
                                  fontSize: 13.5,
                                ),
                              ),
                            ],
                          ],
                        ),
                      ),
                      Text(
                        peso != null ? '$peso kg' : '—',
                        style: const TextStyle(
                          color: AppColors.accent,
                          fontWeight: FontWeight.w800,
                          fontSize: 18,
                        ),
                      ),
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
