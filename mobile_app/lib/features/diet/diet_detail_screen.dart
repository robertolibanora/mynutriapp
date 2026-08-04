import 'package:flutter/material.dart';

import '../../core/api/diets_api.dart';
import '../../core/app_scope.dart';
import '../../core/theme/app_theme.dart';

class DietDetailScreen extends StatefulWidget {
  const DietDetailScreen({super.key, required this.dietId, this.title});

  final int dietId;
  final String? title;

  @override
  State<DietDetailScreen> createState() => _DietDetailScreenState();
}

class _DietDetailScreenState extends State<DietDetailScreen> {
  late final DietsApi _api;
  Future<DietDetail>? _future;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _api = DietsApi(AppScope.of(context).apiClient);
    _future ??= _api.getDiet(widget.dietId);
  }

  Future<void> _reload() async {
    setState(() => _future = _api.getDiet(widget.dietId));
    await _future;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(
          widget.title ?? 'Dettaglio dieta',
          style: const TextStyle(fontWeight: FontWeight.w700),
        ),
      ),
      body: FutureBuilder<DietDetail>(
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

          final detail = snap.data!;
          final s = detail.summary;
          final byDay = detail.mealsByDay;

          return RefreshIndicator(
            color: AppColors.accent,
            onRefresh: _reload,
            child: ListView(
              padding: const EdgeInsets.fromLTRB(20, 12, 20, 32),
              children: [
                Text(
                  s.title,
                  style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                        fontWeight: FontWeight.w800,
                      ),
                ),
                if (s.attiva) ...[
                  const SizedBox(height: 8),
                  const _Badge(label: 'Attiva', accent: true),
                ],
                if (s.goal != null && s.goal!.trim().isNotEmpty) ...[
                  const SizedBox(height: 10),
                  Text(
                    s.goal!,
                    style: const TextStyle(color: AppColors.muted, height: 1.35),
                  ),
                ],
                if (s.notes != null && s.notes!.trim().isNotEmpty) ...[
                  const SizedBox(height: 8),
                  Text(
                    s.notes!,
                    style: const TextStyle(color: AppColors.muted, height: 1.35),
                  ),
                ],
                const SizedBox(height: 18),
                _MacrosCard(detail: detail),
                if (!s.isPlan) ...[
                  const SizedBox(height: 16),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: AppColors.surface,
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(color: AppColors.border),
                    ),
                    child: Text(
                      s.dataInizio != null && s.dataFine != null
                          ? 'Periodo: ${formatDietDate(s.dataInizio!)} – ${formatDietDate(s.dataFine!)}'
                          : 'Dieta in formato PDF assegnata dal nutrizionista.',
                      style: const TextStyle(height: 1.4),
                    ),
                  ),
                ],
                if (byDay.isEmpty && s.isPlan) ...[
                  const SizedBox(height: 28),
                  const Text(
                    'Nessun pasto nel piano ancora.',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: AppColors.muted),
                  ),
                ],
                for (final entry in byDay.entries) ...[
                  const SizedBox(height: 22),
                  Text(
                    entry.key,
                    style: const TextStyle(
                      color: AppColors.accent,
                      fontWeight: FontWeight.w700,
                      fontSize: 13,
                      letterSpacing: 0.4,
                    ),
                  ),
                  const SizedBox(height: 10),
                  for (final meal in entry.value) ...[
                    _MealCard(meal: meal),
                    const SizedBox(height: 10),
                  ],
                ],
              ],
            ),
          );
        },
      ),
    );
  }
}

class _Badge extends StatelessWidget {
  const _Badge({required this.label, this.accent = false});

  final String label;
  final bool accent;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(
          color: accent
              ? AppColors.accent.withValues(alpha: 0.16)
              : AppColors.surface,
          borderRadius: BorderRadius.circular(999),
          border: Border.all(
            color: accent
                ? AppColors.accent.withValues(alpha: 0.4)
                : AppColors.border,
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: accent ? AppColors.accent : AppColors.muted,
            fontWeight: FontWeight.w700,
            fontSize: 12,
          ),
        ),
      ),
    );
  }
}

class _MacrosCard extends StatelessWidget {
  const _MacrosCard({required this.detail});

  final DietDetail detail;

  @override
  Widget build(BuildContext context) {
    final kcal = detail.totalKcal ?? detail.summary.targetKcal ?? detail.summary.kcal;
    final rows = <(String, String)>[
      if (kcal != null) ('Calorie', '${kcal.round()} kcal'),
      if (detail.totalProtein != null)
        ('Proteine', '${detail.totalProtein!.round()} g'),
      if (detail.totalCarbs != null)
        ('Carboidrati', '${detail.totalCarbs!.round()} g'),
      if (detail.totalFat != null) ('Grassi', '${detail.totalFat!.round()} g'),
      if (detail.targetProteinPct != null)
        ('Target P', '${detail.targetProteinPct!.round()}%'),
      if (detail.targetCarbsPct != null)
        ('Target C', '${detail.targetCarbsPct!.round()}%'),
      if (detail.targetFatPct != null)
        ('Target F', '${detail.targetFatPct!.round()}%'),
    ];
    if (rows.isEmpty) return const SizedBox.shrink();

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.border),
      ),
      child: Wrap(
        spacing: 16,
        runSpacing: 12,
        children: [
          for (final row in rows)
            SizedBox(
              width: 140,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    row.$1,
                    style: const TextStyle(
                      color: AppColors.muted,
                      fontSize: 12.5,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    row.$2,
                    style: const TextStyle(
                      fontWeight: FontWeight.w700,
                      fontSize: 16,
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class _MealCard extends StatelessWidget {
  const _MealCard({required this.meal});

  final DietMeal meal;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  meal.heading,
                  style: const TextStyle(
                    fontWeight: FontWeight.w700,
                    fontSize: 15.5,
                  ),
                ),
              ),
              if (meal.kcal != null)
                Text(
                  '${meal.kcal!.round()} kcal',
                  style: const TextStyle(
                    color: AppColors.accent,
                    fontWeight: FontWeight.w700,
                    fontSize: 13,
                  ),
                ),
            ],
          ),
          if (meal.notes != null && meal.notes!.trim().isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(
              meal.notes!,
              style: const TextStyle(color: AppColors.muted, fontSize: 13),
            ),
          ],
          if (meal.items.isNotEmpty) ...[
            const SizedBox(height: 12),
            for (final item in meal.items) ...[
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Padding(
                      padding: EdgeInsets.only(top: 6),
                      child: Icon(
                        Icons.circle,
                        size: 6,
                        color: AppColors.muted,
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            item.foodName ?? 'Alimento',
                            style: const TextStyle(fontWeight: FontWeight.w600),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            [
                              if (item.quantityG != null)
                                '${item.quantityG!.round()} g',
                              if (item.kcal != null)
                                '${item.kcal!.round()} kcal',
                            ].join(' · '),
                            style: const TextStyle(
                              color: AppColors.muted,
                              fontSize: 13,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ],
        ],
      ),
    );
  }
}
