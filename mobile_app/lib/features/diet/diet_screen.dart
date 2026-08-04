import 'package:flutter/material.dart';

import '../../core/api/diets_api.dart';
import '../../core/app_scope.dart';
import '../../core/config/env.dart';
import '../../core/theme/app_theme.dart';
import '../../widgets/empty_placeholder.dart';
import 'diet_detail_screen.dart';

/// Tab Dieta: piani pubblicati dal nutrizionista (`/admin/diet-plans`).
class DietScreen extends StatefulWidget {
  const DietScreen({super.key});

  @override
  State<DietScreen> createState() => _DietScreenState();
}

class _DietScreenState extends State<DietScreen> {
  late final DietsApi _api;
  Future<DietsListResult>? _future;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _api = DietsApi(AppScope.of(context).apiClient);
    _future ??= _load();
  }

  Future<DietsListResult> _load() async {
    final auth = AppScope.of(context).auth;
    if (Env.useMockData || auth.isDemo) {
      return const DietsListResult();
    }
    return _api.listDiets();
  }

  Future<void> _reload() async {
    setState(() => _future = _load());
    await _future;
  }

  void _open(DietSummary diet) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => DietDetailScreen(
          dietId: diet.id,
          title: diet.title,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text(
          'Le mie diete',
          style: TextStyle(fontWeight: FontWeight.w700),
        ),
      ),
      body: FutureBuilder<DietsListResult>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      DietsApi.messageFromError(snap.error!),
                      textAlign: TextAlign.center,
                      style: const TextStyle(color: AppColors.muted),
                    ),
                    const SizedBox(height: 16),
                    FilledButton(
                      onPressed: _reload,
                      child: const Text('Riprova'),
                    ),
                  ],
                ),
              ),
            );
          }

          final diets = snap.data?.diets ?? const <DietSummary>[];
          if (diets.isEmpty) {
            return RefreshIndicator(
              color: AppColors.accent,
              onRefresh: _reload,
              child: ListView(
                physics: const AlwaysScrollableScrollPhysics(),
                children: const [
                  SizedBox(
                    height: 480,
                    child: EmptyPlaceholder(
                      icon: Icons.restaurant_outlined,
                      message: 'Nessuna dieta assegnata ancora',
                    ),
                  ),
                ],
              ),
            );
          }

          // Attive prima, poi le altre.
          final sorted = [...diets]..sort((a, b) {
              if (a.attiva != b.attiva) return a.attiva ? -1 : 1;
              return b.id.compareTo(a.id);
            });

          return RefreshIndicator(
            color: AppColors.accent,
            onRefresh: _reload,
            child: ListView.separated(
              padding: const EdgeInsets.fromLTRB(20, 12, 20, 28),
              itemCount: sorted.length,
              separatorBuilder: (_, _) => const SizedBox(height: 10),
              itemBuilder: (context, i) {
                final diet = sorted[i];
                return _DietCard(
                  diet: diet,
                  onTap: () => _open(diet),
                );
              },
            ),
          );
        },
      ),
    );
  }
}

class _DietCard extends StatelessWidget {
  const _DietCard({required this.diet, required this.onTap});

  final DietSummary diet;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.surface,
      borderRadius: BorderRadius.circular(16),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: diet.attiva
                  ? AppColors.accent.withValues(alpha: 0.45)
                  : AppColors.border,
            ),
          ),
          child: Row(
            children: [
              Container(
                width: 46,
                height: 46,
                decoration: BoxDecoration(
                  color: AppColors.accent.withValues(alpha: 0.14),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(
                  diet.isPlan
                      ? Icons.restaurant_outlined
                      : Icons.picture_as_pdf_outlined,
                  color: AppColors.accent,
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            diet.title,
                            style: const TextStyle(
                              fontWeight: FontWeight.w700,
                              fontSize: 16,
                            ),
                          ),
                        ),
                        if (diet.attiva)
                          Container(
                            margin: const EdgeInsets.only(left: 8),
                            padding: const EdgeInsets.symmetric(
                              horizontal: 8,
                              vertical: 3,
                            ),
                            decoration: BoxDecoration(
                              color: AppColors.accent.withValues(alpha: 0.16),
                              borderRadius: BorderRadius.circular(999),
                            ),
                            child: const Text(
                              'Attiva',
                              style: TextStyle(
                                color: AppColors.accent,
                                fontWeight: FontWeight.w700,
                                fontSize: 11,
                              ),
                            ),
                          ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      diet.subtitle,
                      style: const TextStyle(
                        color: AppColors.muted,
                        fontSize: 13,
                        height: 1.3,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 4),
              const Icon(Icons.chevron_right, color: AppColors.muted),
            ],
          ),
        ),
      ),
    );
  }
}
