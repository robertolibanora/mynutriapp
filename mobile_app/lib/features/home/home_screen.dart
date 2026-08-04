import 'package:flutter/material.dart';

import '../../core/api/patient_api.dart';
import '../../core/app_scope.dart';
import '../../core/config/env.dart';
import '../../core/theme/app_theme.dart';
import '../../widgets/summary_card.dart';
import '../../widgets/user_header.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, this.onOpenProfile});

  final VoidCallback? onOpenProfile;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  late final PatientApi _api;
  Future<PatientHomeSnapshot>? _future;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _api = PatientApi(AppScope.of(context).apiClient);
    _future ??= _load();
  }

  Future<PatientHomeSnapshot> _load() async {
    if (Env.useMockData || AppScope.of(context).auth.isDemo) {
      return const PatientHomeSnapshot();
    }
    return _api.fetchHome();
  }

  Future<void> _refresh() async {
    setState(() => _future = _load());
    await _future;
  }

  @override
  Widget build(BuildContext context) {
    final auth = AppScope.of(context).auth;
    return AnimatedBuilder(
      animation: auth,
      builder: (context, _) {
        final user = auth.user;
        final parts = user?.displayName.trim().split(RegExp(r'\s+')) ?? const [];
        final first = (user?.nome.isNotEmpty == true)
            ? user!.nome
            : (parts.isNotEmpty ? parts.first : 'utente');

        return Scaffold(
          body: SafeArea(
            bottom: false,
            child: Column(
              children: [
                UserHeader(
                  firstName: first,
                  onAvatarTap: widget.onOpenProfile,
                ),
                Expanded(
                  child: RefreshIndicator(
                    color: AppColors.accent,
                    onRefresh: _refresh,
                    child: FutureBuilder<PatientHomeSnapshot>(
                      future: _future,
                      builder: (context, snap) {
                        final data = snap.data ?? const PatientHomeSnapshot();
                        return ListView(
                          physics: const AlwaysScrollableScrollPhysics(),
                          padding: const EdgeInsets.fromLTRB(18, 8, 18, 28),
                          children: [
                            const _HeroMotto(),
                            const SizedBox(height: 8),
                            if (data.latestProgress != null)
                              _WeightFeature(progress: data.latestProgress!),
                            _DietCard(diet: data.diet),
                            _WorkoutCard(workout: data.workout),
                            if (data.latestProgress == null)
                              const SummaryCard(
                                icon: Icons.monitor_weight_outlined,
                                title: 'Peso attuale',
                                child: CardEmptyState(
                                  icon: Icons.show_chart_outlined,
                                  message: 'Nessun progresso registrato ancora',
                                ),
                              ),
                            _AppointmentCard(appt: data.nextAppointment),
                            const SizedBox(height: 8),
                            const Text(
                              'Powered by Roberto Libanora',
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                color: AppColors.muted2,
                                fontSize: 12,
                              ),
                            ),
                          ],
                        );
                      },
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

class _HeroMotto extends StatelessWidget {
  const _HeroMotto();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(8, 18, 8, 18),
      child: Column(
        children: [
          const Text(
            'MYNUTRIAPP',
            style: TextStyle(
              color: AppColors.accent,
              fontSize: 11.5,
              fontWeight: FontWeight.w700,
              letterSpacing: 2.2,
            ),
          ),
          const SizedBox(height: 10),
          const Text(
            'Non diamo pillole, non diamo consigli: diamo risultati.',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: AppColors.primary,
              fontSize: 21,
              fontWeight: FontWeight.w700,
              height: 1.35,
              letterSpacing: -0.4,
            ),
          ),
          const SizedBox(height: 16),
          Container(
            height: 1,
            margin: const EdgeInsets.symmetric(horizontal: 40),
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [
                  Colors.transparent,
                  AppColors.accent.withValues(alpha: 0.35),
                  Colors.transparent,
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _WeightFeature extends StatelessWidget {
  const _WeightFeature({required this.progress});

  final Map<String, dynamic> progress;

  @override
  Widget build(BuildContext context) {
    final peso = progress['peso_settimanale'];
    final dataCheck = progress['data_check']?.toString() ?? '—';
    final aderenza = progress['aderenza']?.toString();

    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 14),
      padding: const EdgeInsets.fromLTRB(18, 18, 18, 16),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            AppColors.accent.withValues(alpha: 0.16),
            Colors.white.withValues(alpha: 0.06),
          ],
        ),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: AppColors.accent.withValues(alpha: 0.22)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'PESO ATTUALE',
            style: TextStyle(
              color: AppColors.muted2,
              fontSize: 12.5,
              fontWeight: FontWeight.w700,
              letterSpacing: 1.1,
            ),
          ),
          const SizedBox(height: 10),
          RichText(
            text: TextSpan(
              children: [
                TextSpan(
                  text: peso?.toString() ?? '—',
                  style: const TextStyle(
                    color: AppColors.text,
                    fontSize: 38,
                    fontWeight: FontWeight.w800,
                    letterSpacing: -1,
                    height: 1,
                  ),
                ),
                const TextSpan(
                  text: ' kg',
                  style: TextStyle(
                    color: AppColors.muted2,
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 16,
            runSpacing: 6,
            children: [
              Text(
                'Check: $dataCheck',
                style: const TextStyle(color: AppColors.muted2, fontSize: 13.5),
              ),
              if (aderenza != null && aderenza.isNotEmpty)
                Text(
                  'Aderenza: $aderenza',
                  style: const TextStyle(color: AppColors.muted2, fontSize: 13.5),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

class _DietCard extends StatelessWidget {
  const _DietCard({this.diet});

  final Map<String, dynamic>? diet;

  @override
  Widget build(BuildContext context) {
    if (diet == null) {
      return const SummaryCard(
        icon: Icons.restaurant_outlined,
        title: 'Dieta attuale',
        child: CardEmptyState(
          icon: Icons.restaurant_outlined,
          message: 'Nessuna dieta assegnata ancora',
        ),
      );
    }

    final title = (diet!['title'] as String?) ??
        (diet!['kind'] == 'dieta_pdf' ? 'Dieta PDF' : 'Piano alimentare');
    final goal = diet!['goal'] as String?;
    final totals = diet!['totals'];
    final kcal = diet!['target_kcal'] ??
        (totals is Map ? totals['kcal'] : null) ??
        diet!['kcal'];
    final inizio = diet!['data_inizio']?.toString();
    final fine = diet!['data_fine']?.toString();

    return SummaryCard(
      icon: Icons.restaurant_outlined,
      title: 'Dieta attuale',
      child: Column(
        children: [
          SummaryRow(label: 'Piano', value: title),
          if (goal != null && goal.isNotEmpty)
            SummaryRow(label: 'Obiettivo', value: goal),
          if (kcal != null) SummaryRow(label: 'Calorie', value: '$kcal kcal/giorno'),
          if (inizio != null && fine != null)
            SummaryRow(label: 'Periodo', value: '$inizio – $fine'),
        ],
      ),
    );
  }
}

class _WorkoutCard extends StatelessWidget {
  const _WorkoutCard({this.workout});

  final Map<String, dynamic>? workout;

  @override
  Widget build(BuildContext context) {
    if (workout == null) {
      return const SummaryCard(
        icon: Icons.fitness_center_outlined,
        title: 'Allenamento attuale',
        child: CardEmptyState(
          icon: Icons.fitness_center_outlined,
          message: 'Nessun allenamento assegnato ancora',
        ),
      );
    }

    final inizio = workout!['data_inizio']?.toString() ?? '—';
    final fine = workout!['data_fine']?.toString() ?? '—';
    final note = workout!['note'] as String?;

    return SummaryCard(
      icon: Icons.fitness_center_outlined,
      title: 'Allenamento attuale',
      child: Column(
        children: [
          SummaryRow(label: 'Periodo', value: '$inizio – $fine'),
          if (note != null && note.isNotEmpty)
            SummaryRow(label: 'Note', value: note),
        ],
      ),
    );
  }
}

class _AppointmentCard extends StatelessWidget {
  const _AppointmentCard({this.appt});

  final Map<String, dynamic>? appt;

  @override
  Widget build(BuildContext context) {
    if (appt == null) {
      return const SummaryCard(
        icon: Icons.calendar_month_outlined,
        title: 'Prossimo appuntamento',
        child: CardEmptyState(
          icon: Icons.event_busy_outlined,
          message: 'Nessun appuntamento in programma',
        ),
      );
    }

    final data = appt!['data']?.toString() ?? '—';
    final ora = appt!['ora']?.toString() ?? '';
    final tipo = (appt!['tipo_label'] as String?) ??
        (appt!['tipo'] as String?) ??
        '—';
    final note = appt!['note'] as String?;

    return SummaryCard(
      icon: Icons.calendar_month_outlined,
      title: 'Prossimo appuntamento',
      child: Column(
        children: [
          SummaryRow(
            label: 'Data',
            value: ora.isEmpty ? data : '$data alle $ora',
          ),
          SummaryRow(label: 'Tipo', value: tipo),
          if (note != null && note.isNotEmpty)
            SummaryRow(label: 'Note', value: note),
        ],
      ),
    );
  }
}
