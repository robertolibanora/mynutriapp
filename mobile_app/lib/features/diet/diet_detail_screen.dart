import 'package:flutter/material.dart';

import '../../core/api/diets_api.dart';
import '../../core/app_scope.dart';
import '../../core/config/env.dart';
import '../../core/theme/app_theme.dart';
import '../../widgets/app_ui.dart';

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
    _future ??= _load();
  }

  Future<DietDetail> _load() async {
    final auth = AppScope.of(context).auth;
    if (Env.useMockData || auth.isDemo) {
      return _demoDetail(widget.dietId, widget.title);
    }
    return _api.getDiet(widget.dietId);
  }

  DietDetail _demoDetail(int id, String? title) {
    final summary = DietSummary(
      kind: 'diet_plan',
      id: id,
      title: title ?? (id == 2 ? 'Piano mantenimento' : 'Piano equilibrato'),
      goal: id == 2 ? 'Stabilità peso' : 'Ricompposizione',
      attiva: id == 1,
      targetKcal: id == 2 ? 2000 : 1800,
      mealsCount: id == 2 ? 4 : 5,
      notes: 'Esempio demo — i pasti sotto sono illustrativi.',
    );
    return DietDetail(
      summary: summary,
      totalKcal: summary.targetKcal,
      totalProtein: 120,
      totalCarbs: 180,
      totalFat: 60,
      targetProteinPct: 30,
      targetCarbsPct: 40,
      targetFatPct: 30,
      meals: [
        DietMeal(
          id: 1,
          dayLabel: 'Giorno tipo',
          mealName: 'Colazione',
          mealTime: '08:00',
          kcal: 380,
          items: const [
            DietMealItem(id: 1, foodName: 'Yogurt greco', quantityG: 150, kcal: 140),
            DietMealItem(id: 2, foodName: 'Fiocchi d’avena', quantityG: 40, kcal: 150),
            DietMealItem(id: 3, foodName: 'Mirtilli', quantityG: 80, kcal: 45),
          ],
        ),
        DietMeal(
          id: 2,
          dayLabel: 'Giorno tipo',
          mealName: 'Pranzo',
          mealTime: '13:00',
          kcal: 520,
          items: const [
            DietMealItem(id: 4, foodName: 'Petto di pollo', quantityG: 140, kcal: 230),
            DietMealItem(id: 5, foodName: 'Riso integrale', quantityG: 80, kcal: 280),
          ],
        ),
        DietMeal(
          id: 3,
          dayLabel: 'Giorno tipo',
          mealName: 'Cena',
          mealTime: '20:00',
          kcal: 480,
          items: const [
            DietMealItem(id: 6, foodName: 'Salmone', quantityG: 150, kcal: 280),
            DietMealItem(id: 7, foodName: 'Verdure al vapore', quantityG: 200, kcal: 60),
          ],
        ),
      ],
    );
  }

  Future<void> _reload() async {
    setState(() => _future = _load());
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
            return AppErrorView(
              message: DietsApi.messageFromError(snap.error!),
              onRetry: _reload,
            );
          }

          final detail = snap.data!;
          final s = detail.summary;
          final byDay = detail.mealsByDay;

          return RefreshIndicator(
            color: AppColors.accent,
            onRefresh: _reload,
            child: ListView(
              padding: kAppPagePadding,
              children: [
                AppSurfaceCard(
                  highlighted: s.attiva,
                  padding: const EdgeInsets.all(18),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              s.title,
                              style: Theme.of(context)
                                  .textTheme
                                  .titleLarge
                                  ?.copyWith(fontWeight: FontWeight.w800),
                            ),
                          ),
                          if (s.attiva) const AppStatusChip(label: 'Attiva'),
                        ],
                      ),
                      if (s.goal != null && s.goal!.trim().isNotEmpty) ...[
                        const SizedBox(height: 8),
                        Text(
                          s.goal!,
                          style: const TextStyle(
                            color: AppColors.muted,
                            height: 1.35,
                          ),
                        ),
                      ],
                      if (s.notes != null && s.notes!.trim().isNotEmpty) ...[
                        const SizedBox(height: 8),
                        Text(
                          s.notes!,
                          style: const TextStyle(
                            color: AppColors.muted,
                            height: 1.35,
                            fontSize: 13.5,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                const SizedBox(height: 14),
                _MacrosCard(detail: detail),
                if (!s.isPlan) ...[
                  const SizedBox(height: 14),
                  AppSurfaceCard(
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
                  AppSectionLabel(entry.key),
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

class _MacrosCard extends StatelessWidget {
  const _MacrosCard({required this.detail});

  final DietDetail detail;

  @override
  Widget build(BuildContext context) {
    final kcal =
        detail.totalKcal ?? detail.summary.targetKcal ?? detail.summary.kcal;
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

    return AppSurfaceCard(
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
    return AppSurfaceCard(
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
