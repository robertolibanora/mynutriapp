import 'package:flutter/material.dart';

import '../../core/api/appointments_api.dart';
import '../../core/api/diets_api.dart';
import '../../core/api/progress_api.dart';
import '../../core/app_scope.dart';
import '../../core/config/env.dart';
import '../../core/theme/app_theme.dart';
import '../../widgets/app_logo.dart';
import '../../widgets/app_ui.dart';
import '../progress/register_check_screen.dart';

/// Snapshot aggregato per la dashboard Home.
class _HomeSnapshot {
  const _HomeSnapshot({
    this.activeDiet,
    this.nextAppointment,
    this.progress = const [],
  });

  final DietSummary? activeDiet;
  final AppointmentItem? nextAppointment;
  final List<ProgressPoint> progress;
}

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.onOpenTab});

  /// Indici tab: 0 Home, 1 Dieta, 2 Prenota, 3 Progressi, 4 Profilo.
  final ValueChanged<int> onOpenTab;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  late final DietsApi _dietsApi;
  late final AppointmentsApi _appointmentsApi;
  late final ProgressApi _progressApi;
  Future<_HomeSnapshot>? _future;
  List<ProgressPoint>? _demoProgress;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final client = AppScope.of(context).apiClient;
    _dietsApi = DietsApi(client);
    _appointmentsApi = AppointmentsApi(client);
    _progressApi = ProgressApi(client);
    _future ??= _load();
  }

  Future<_HomeSnapshot> _load() async {
    final auth = AppScope.of(context).auth;
    if (Env.useMockData || auth.isDemo) {
      return _demoSnapshot();
    }

    final dietsFuture = _dietsApi.listDiets();
    final apptsFuture = _appointmentsApi.listAppointments();
    final progressFuture = _progressApi.listProgress();

    final diets = await dietsFuture;
    final appts = await apptsFuture;
    final progress = await progressFuture;

    DietSummary? active;
    if (diets.activeId != null) {
      for (final d in diets.diets) {
        if (d.id == diets.activeId &&
            (diets.activeKind == null || d.kind == diets.activeKind)) {
          active = d;
          break;
        }
      }
    }
    if (active == null) {
      for (final d in diets.diets) {
        if (d.attiva) {
          active = d;
          break;
        }
      }
    }
    active ??= diets.diets.isNotEmpty ? diets.diets.first : null;

    return _HomeSnapshot(
      activeDiet: active,
      nextAppointment: _pickNextAppointment(appts),
      progress: progress,
    );
  }

  List<ProgressPoint> _seedDemoProgress() {
    final now = DateTime.now();
    return [
      ProgressPoint(
        id: 1,
        date: now.subtract(const Duration(days: 21)),
        weight: 72.5,
      ),
      ProgressPoint(
        id: 2,
        date: now.subtract(const Duration(days: 14)),
        weight: 71.9,
      ),
      ProgressPoint(
        id: 3,
        date: now.subtract(const Duration(days: 7)),
        weight: 71.3,
      ),
      ProgressPoint(
        id: 4,
        date: now,
        weight: 70.7,
      ),
    ];
  }

  _HomeSnapshot _demoSnapshot() {
    final now = DateTime.now();
    final next = now.add(const Duration(days: 5));
    _demoProgress ??= _seedDemoProgress();
    return _HomeSnapshot(
      activeDiet: DietSummary(
        kind: 'diet_plan',
        id: 1,
        title: 'Piano equilibrato',
        goal: 'Ricompposizione',
        attiva: true,
        targetKcal: 1800,
        mealsCount: 5,
      ),
      nextAppointment: AppointmentItem(
        id: 1,
        titolo: 'Controllo nutrizionale',
        data: next.toIso8601String().split('T').first,
        ora: '10:30',
        statoLabel: 'Confermato',
        professionista: 'Dott.ssa Rossi',
      ),
      progress: List<ProgressPoint>.from(_demoProgress!),
    );
  }

  AppointmentItem? _pickNextAppointment(List<AppointmentItem> items) {
    final today = DateTime.now();
    final startOfToday = DateTime(today.year, today.month, today.day);
    AppointmentItem? best;
    DateTime? bestDt;
    for (final a in items) {
      if (a.data == null) continue;
      final d = DateTime.tryParse(a.data!);
      if (d == null) continue;
      final day = DateTime(d.year, d.month, d.day);
      if (day.isBefore(startOfToday)) continue;
      if (bestDt == null || day.isBefore(bestDt) || day.isAtSameMomentAs(bestDt)) {
        // A parità di data preferisci l'ora più vicina se presente.
        if (bestDt != null && day.isAtSameMomentAs(bestDt) && a.ora != null) {
          final bestOra = best?.ora;
          if (bestOra != null && a.ora!.compareTo(bestOra) >= 0) continue;
        }
        best = a;
        bestDt = day;
      }
    }
    return best;
  }

  Future<void> _reload() async {
    setState(() => _future = _load());
    await _future;
  }

  Future<void> _openRegisterCheck(List<ProgressPoint> points) async {
    final initial = points.isNotEmpty ? points.last.weight : null;
    final created = await Navigator.of(context).push<ProgressPoint>(
      MaterialPageRoute<ProgressPoint>(
        builder: (_) => RegisterCheckScreen(initialWeight: initial),
      ),
    );
    if (created == null || !mounted) return;

    final auth = AppScope.of(context).auth;
    if (Env.useMockData || auth.isDemo) {
      final base = List<ProgressPoint>.from(_demoProgress ??= _seedDemoProgress());
      final day = DateTime(
        created.date.year,
        created.date.month,
        created.date.day,
      );
      base.removeWhere((p) {
        final d = DateTime(p.date.year, p.date.month, p.date.day);
        return d == day;
      });
      base.add(created);
      base.sort((a, b) => a.date.compareTo(b.date));
      _demoProgress = base;
    }

    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Check registrato.')),
    );
    await _reload();
  }

  String _timeGreeting() {
    final h = DateTime.now().hour;
    if (h < 12) return 'Buongiorno';
    if (h < 18) return 'Buon pomeriggio';
    return 'Buonasera';
  }

  @override
  Widget build(BuildContext context) {
    final auth = AppScope.of(context).auth;
    return AnimatedBuilder(
      animation: auth,
      builder: (context, _) {
        final user = auth.user;
        final name = (user?.nome.isNotEmpty == true) ? user!.nome : 'paziente';
        final isDemo = auth.isDemo;

        return Scaffold(
          body: SafeArea(
            child: FutureBuilder<_HomeSnapshot>(
              future: _future,
              builder: (context, snap) {
                final loading =
                    snap.connectionState == ConnectionState.waiting &&
                        !snap.hasData;
                final data = snap.data ?? const _HomeSnapshot();

                return RefreshIndicator(
                  color: AppColors.accent,
                  onRefresh: _reload,
                  child: ListView(
                    physics: const AlwaysScrollableScrollPhysics(),
                    padding: const EdgeInsets.fromLTRB(20, 16, 20, 28),
                    children: [
                      _Header(
                        greeting: '${_timeGreeting()}, $name',
                        subtitle: isDemo
                            ? 'Modalità demo — dati di esempio'
                            : 'Il tuo percorso nutrizionale',
                      ),
                      const SizedBox(height: 20),
                      if (loading)
                        const Padding(
                          padding: EdgeInsets.symmetric(vertical: 48),
                          child: Center(child: CircularProgressIndicator()),
                        )
                      else if (snap.hasError)
                        AppErrorView(
                          message: 'Non riesco a caricare la panoramica.',
                          onRetry: _reload,
                        )
                      else ...[
                        _DietHeroCard(
                          diet: data.activeDiet,
                          onTap: () => widget.onOpenTab(1),
                        ),
                        const SizedBox(height: 12),
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Expanded(
                              child: _MetricCard(
                                icon: Icons.calendar_month_outlined,
                                label: 'Prossimo appuntamento',
                                value: data.nextAppointment?.whenLabel ??
                                    'Nessuno in agenda',
                                detail: data.nextAppointment?.titolo ??
                                    'Prenota dalla tab Prenota',
                                onTap: () => widget.onOpenTab(2),
                              ),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: _WeightMetricCard(
                                points: data.progress,
                                onTap: () => widget.onOpenTab(3),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 22),
                        const AppSectionLabel('Azioni rapide'),
                        const SizedBox(height: 10),
                        AppAccentCta(
                          icon: Icons.add_chart_rounded,
                          title: 'Registra check',
                          subtitle: 'Aggiorna peso e aderenza',
                          onTap: () => _openRegisterCheck(data.progress),
                        ),
                        const SizedBox(height: 10),
                        AppSurfaceCta(
                          icon: Icons.event_available_outlined,
                          title: 'Prenota visita',
                          subtitle: 'Scegli uno slot disponibile',
                          onTap: () => widget.onOpenTab(2),
                        ),
                        const SizedBox(height: 28),
                        TextButton(
                          onPressed: () => widget.onOpenTab(4),
                          style: TextButton.styleFrom(
                            foregroundColor: AppColors.muted,
                            padding: EdgeInsets.zero,
                            alignment: Alignment.centerLeft,
                          ),
                          child: const Text(
                            'Privacy e dati (GDPR) → Profilo',
                            style: TextStyle(fontSize: 13, height: 1.4),
                          ),
                        ),
                      ],
                    ],
                  ),
                );
              },
            ),
          ),
        );
      },
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.greeting, required this.subtitle});

  final String greeting;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        const AppLogo(size: 40, borderRadius: 10),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                greeting,
                style: Theme.of(context)
                    .textTheme
                    .headlineSmall
                    ?.copyWith(fontWeight: FontWeight.w800),
              ),
              const SizedBox(height: 2),
              Text(
                subtitle,
                style: const TextStyle(
                  color: AppColors.muted,
                  fontSize: 13.5,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _DietHeroCard extends StatelessWidget {
  const _DietHeroCard({required this.diet, required this.onTap});

  final DietSummary? diet;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final hasDiet = diet != null;
    return Material(
      color: AppColors.surface,
      borderRadius: BorderRadius.circular(16),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.all(18),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: hasDiet
                  ? AppColors.accent.withValues(alpha: 0.35)
                  : AppColors.border,
            ),
          ),
          child: Row(
            children: [
              Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  color: AppColors.accent.withValues(alpha: 0.14),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: const Icon(
                  Icons.restaurant_outlined,
                  color: AppColors.accent,
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      hasDiet ? 'Dieta attiva' : 'Dieta',
                      style: const TextStyle(
                        color: AppColors.muted,
                        fontSize: 12.5,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      hasDiet ? diet!.title : 'Nessun piano assegnato',
                      style: const TextStyle(
                        fontWeight: FontWeight.w800,
                        fontSize: 17,
                      ),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      hasDiet
                          ? diet!.subtitle
                          : 'Quando il nutrizionista pubblicherà un piano lo vedrai qui',
                      style: const TextStyle(
                        color: AppColors.muted,
                        fontSize: 13,
                        height: 1.3,
                      ),
                    ),
                  ],
                ),
              ),
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

class _MetricCard extends StatelessWidget {
  const _MetricCard({
    required this.icon,
    required this.label,
    required this.value,
    required this.detail,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final String value;
  final String detail;
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
          constraints: const BoxConstraints(minHeight: 132),
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: AppColors.border),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(icon, color: AppColors.accent, size: 22),
              const SizedBox(height: 10),
              Text(
                label,
                style: const TextStyle(
                  color: AppColors.muted,
                  fontSize: 11.5,
                  fontWeight: FontWeight.w600,
                  height: 1.2,
                ),
              ),
              const SizedBox(height: 6),
              Text(
                value,
                style: const TextStyle(
                  fontWeight: FontWeight.w800,
                  fontSize: 14.5,
                  height: 1.25,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                detail,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  color: AppColors.muted,
                  fontSize: 12,
                  height: 1.25,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _WeightMetricCard extends StatelessWidget {
  const _WeightMetricCard({required this.points, required this.onTap});

  final List<ProgressPoint> points;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final has = points.isNotEmpty && points.last.weight != null;
    String value;
    String detail;
    if (!has) {
      value = '—';
      detail = 'Registra il primo check';
    } else {
      final last = points.last.weight!;
      value = '${last.toStringAsFixed(1)} kg';
      if (points.length >= 2 && points.first.weight != null) {
        final delta = last - points.first.weight!;
        final sign = delta >= 0 ? '+' : '';
        detail = '$sign${delta.toStringAsFixed(1)} kg dal primo check';
      } else {
        detail = 'Ultimo check';
      }
    }

    return _MetricCard(
      icon: Icons.show_chart_outlined,
      label: 'Peso attuale',
      value: value,
      detail: detail,
      onTap: onTap,
    );
  }
}

