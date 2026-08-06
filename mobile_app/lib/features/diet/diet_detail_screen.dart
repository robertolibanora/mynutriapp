import 'package:flutter/material.dart';

import '../../core/api/diets_api.dart';
import '../../core/app_scope.dart';
import '../../core/config/env.dart';
import '../../core/theme/app_theme.dart';
import '../../widgets/app_ui.dart';

const _weekdayShort = [
  'Lun',
  'Mar',
  'Mer',
  'Gio',
  'Ven',
  'Sab',
  'Dom',
];
const _weekdayLong = [
  'Lunedì',
  'Martedì',
  'Mercoledì',
  'Giovedì',
  'Venerdì',
  'Sabato',
  'Domenica',
];

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
  int? _selectedDay;
  bool _showAll = false;

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
      mealsCount: 21,
      notes: 'Esempio demo — piano settimanale illustrativo.',
    );

    DietMeal meal({
      required int id,
      required int day,
      required String name,
      required String time,
      required double kcal,
      required List<DietMealItem> items,
    }) {
      return DietMeal(
        id: id,
        dayIndex: day,
        dayIndexTo: day,
        dayLabel: 'Giorno ${day + 1}',
        mealName: name,
        mealTime: time,
        kcal: kcal,
        items: items,
      );
    }

    final meals = <DietMeal>[];
    var mid = 1;
    for (var day = 0; day < 7; day++) {
      meals.add(
        meal(
          id: mid++,
          day: day,
          name: 'Colazione',
          time: '08:00',
          kcal: 380,
          items: const [
            DietMealItem(
              id: 1,
              foodName: 'Yogurt greco',
              quantityG: 150,
              kcal: 140,
            ),
            DietMealItem(
              id: 2,
              foodName: 'Fiocchi d’avena',
              quantityG: 40,
              kcal: 150,
            ),
          ],
        ),
      );
      meals.add(
        meal(
          id: mid++,
          day: day,
          name: 'Pranzo',
          time: '13:00',
          kcal: 520,
          items: const [
            DietMealItem(
              id: 3,
              foodName: 'Petto di pollo',
              quantityG: 140,
              kcal: 230,
            ),
            DietMealItem(
              id: 4,
              foodName: 'Riso integrale',
              quantityG: 80,
              kcal: 280,
            ),
          ],
        ),
      );
      meals.add(
        meal(
          id: mid++,
          day: day,
          name: 'Cena',
          time: '20:00',
          kcal: 480,
          items: const [
            DietMealItem(
              id: 5,
              foodName: 'Salmone',
              quantityG: 150,
              kcal: 280,
            ),
            DietMealItem(
              id: 6,
              foodName: 'Verdure al vapore',
              quantityG: 200,
              kcal: 60,
            ),
          ],
        ),
      );
    }

    return DietDetail(
      summary: summary,
      totalKcal: summary.targetKcal,
      totalProtein: 120,
      totalCarbs: 180,
      totalFat: 60,
      targetProteinPct: 30,
      targetCarbsPct: 40,
      targetFatPct: 30,
      meals: meals,
    );
  }

  Future<void> _reload() async {
    setState(() => _future = _load());
    await _future;
  }

  /// Default: giorno della settimana corrente (Lun=0 … Dom=6).
  int _resolveSelectedDay(DietDetail detail) {
    final days = detail.dayIndexes;
    if (days.isEmpty) return 0;
    if (_selectedDay != null && days.contains(_selectedDay)) {
      return _selectedDay!;
    }
    final todayIdx = DateTime.now().weekday - 1;
    if (days.contains(todayIdx)) return todayIdx;
    return days.reduce(
      (a, b) => (a - todayIdx).abs() <= (b - todayIdx).abs() ? a : b,
    );
  }

  String _dayTitle(int dayIdx, {required bool isToday}) {
    final n = dayIdx + 1;
    if (dayIdx >= 0 && dayIdx < 7) {
      final wd = _weekdayLong[dayIdx];
      if (isToday) return 'Oggi · $wd';
      return 'Giorno $n · $wd';
    }
    return isToday ? 'Oggi · Giorno $n' : 'Giorno $n';
  }

  double? _dayKcal(List<DietMeal> meals) {
    var sum = 0.0;
    var any = false;
    for (final m in meals) {
      if (m.kcal != null) {
        sum += m.kcal!;
        any = true;
      }
    }
    return any ? sum : null;
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
          final days = detail.dayIndexes;
          final todayIdx = DateTime.now().weekday - 1;
          final selected = _resolveSelectedDay(detail);
          final dayMeals = detail.mealsForDay(selected);
          final dayKcal = _dayKcal(dayMeals);

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
                if (s.isPlan && days.isEmpty) ...[
                  const SizedBox(height: 28),
                  const Text(
                    'Nessun pasto nel piano ancora.',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: AppColors.muted),
                  ),
                ],
                if (s.isPlan && days.isNotEmpty) ...[
                  const SizedBox(height: 22),
                  Row(
                    children: [
                      const Expanded(
                        child: AppSectionLabel('I tuoi pasti'),
                      ),
                      TextButton(
                        onPressed: () => setState(() => _showAll = !_showAll),
                        style: TextButton.styleFrom(
                          foregroundColor: AppColors.accent,
                          padding: const EdgeInsets.symmetric(horizontal: 8),
                          minimumSize: Size.zero,
                          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                        ),
                        child: Text(
                          _showAll ? 'Solo un giorno' : 'Vedi tutto',
                          style: const TextStyle(
                            fontWeight: FontWeight.w700,
                            fontSize: 13,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  if (!_showAll) ...[
                    _DaySelector(
                      days: days,
                      selected: selected,
                      todayIdx: todayIdx,
                      onSelect: (d) => setState(() {
                        _selectedDay = d;
                        _showAll = false;
                      }),
                    ),
                    const SizedBox(height: 14),
                    _TodayHero(
                      title: _dayTitle(selected, isToday: selected == todayIdx),
                      mealCount: dayMeals.length,
                      kcal: dayKcal,
                    ),
                    const SizedBox(height: 12),
                    if (dayMeals.isEmpty)
                      const AppSurfaceCard(
                        child: Text(
                          'Nessun pasto previsto per questo giorno.',
                          style: TextStyle(color: AppColors.muted, height: 1.4),
                        ),
                      )
                    else
                      for (final meal in dayMeals) ...[
                        _MealCard(meal: meal),
                        const SizedBox(height: 10),
                      ],
                  ] else ...[
                    for (final day in days) ...[
                      const SizedBox(height: 8),
                      _DaySectionHeader(
                        title: _dayTitle(day, isToday: day == todayIdx),
                        isToday: day == todayIdx,
                        kcal: _dayKcal(detail.mealsForDay(day)),
                        onFocus: () => setState(() {
                          _selectedDay = day;
                          _showAll = false;
                        }),
                      ),
                      const SizedBox(height: 10),
                      if (detail.mealsForDay(day).isEmpty)
                        const Padding(
                          padding: EdgeInsets.only(bottom: 8),
                          child: Text(
                            'Nessun pasto',
                            style: TextStyle(
                              color: AppColors.muted,
                              fontSize: 13,
                            ),
                          ),
                        )
                      else
                        for (final meal in detail.mealsForDay(day)) ...[
                          _MealCard(
                            meal: meal,
                            highlighted: day == todayIdx,
                          ),
                          const SizedBox(height: 10),
                        ],
                    ],
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

class _DaySelector extends StatelessWidget {
  const _DaySelector({
    required this.days,
    required this.selected,
    required this.todayIdx,
    required this.onSelect,
  });

  final List<int> days;
  final int selected;
  final int todayIdx;
  final ValueChanged<int> onSelect;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 72,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: days.length,
        separatorBuilder: (_, _) => const SizedBox(width: 8),
        itemBuilder: (context, i) {
          final day = days[i];
          final isSelected = day == selected;
          final isToday = day == todayIdx;
          final short = day >= 0 && day < 7 ? _weekdayShort[day] : 'G${day + 1}';

          return Material(
            color: isSelected
                ? AppColors.accent
                : AppColors.surface,
            borderRadius: BorderRadius.circular(14),
            child: InkWell(
              onTap: () => onSelect(day),
              borderRadius: BorderRadius.circular(14),
              child: Container(
                width: 58,
                padding: const EdgeInsets.symmetric(vertical: 10),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(
                    color: isSelected
                        ? AppColors.accent
                        : isToday
                            ? AppColors.accent.withValues(alpha: 0.45)
                            : AppColors.border,
                  ),
                ),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(
                      short,
                      style: TextStyle(
                        fontWeight: FontWeight.w800,
                        fontSize: 13,
                        color: isSelected
                            ? const Color(0xFF1A0F08)
                            : AppColors.text,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      isToday ? 'Oggi' : '${day + 1}',
                      style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                        color: isSelected
                            ? const Color(0xFF3A2416)
                            : isToday
                                ? AppColors.accent
                                : AppColors.muted,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}

class _TodayHero extends StatelessWidget {
  const _TodayHero({
    required this.title,
    required this.mealCount,
    this.kcal,
  });

  final String title;
  final int mealCount;
  final double? kcal;

  @override
  Widget build(BuildContext context) {
    return AppSurfaceCard(
      highlighted: true,
      padding: const EdgeInsets.all(16),
      child: Row(
        children: [
          const AppIconBox(icon: Icons.today_outlined, size: 44),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    fontWeight: FontWeight.w800,
                    fontSize: 16,
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  [
                    if (mealCount > 0)
                      '$mealCount past${mealCount == 1 ? 'o' : 'i'}'
                    else
                      'Nessun pasto',
                    if (kcal != null) '${kcal!.round()} kcal',
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
    );
  }
}

class _DaySectionHeader extends StatelessWidget {
  const _DaySectionHeader({
    required this.title,
    required this.isToday,
    required this.onFocus,
    this.kcal,
  });

  final String title;
  final bool isToday;
  final VoidCallback onFocus;
  final double? kcal;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: TextStyle(
                  color: isToday ? AppColors.accent : AppColors.muted,
                  fontWeight: FontWeight.w700,
                  fontSize: 13,
                ),
              ),
              if (kcal != null)
                Text(
                  '${kcal!.round()} kcal',
                  style: const TextStyle(
                    color: AppColors.muted,
                    fontSize: 12,
                  ),
                ),
            ],
          ),
        ),
        if (isToday)
          const AppStatusChip(label: 'Oggi')
        else
          TextButton(
            onPressed: onFocus,
            style: TextButton.styleFrom(
              foregroundColor: AppColors.muted,
              padding: const EdgeInsets.symmetric(horizontal: 6),
              minimumSize: Size.zero,
              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
            ),
            child: const Text(
              'Apri',
              style: TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600),
            ),
          ),
      ],
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
  const _MealCard({required this.meal, this.highlighted = false});

  final DietMeal meal;
  final bool highlighted;

  @override
  Widget build(BuildContext context) {
    return AppSurfaceCard(
      highlighted: highlighted,
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
