import 'package:flutter/material.dart';

import '../../core/api/diets_api.dart';
import '../../core/app_scope.dart';
import '../../core/config/env.dart';
import '../../core/theme/app_theme.dart';
import '../../widgets/app_ui.dart';
import '../../widgets/empty_placeholder.dart';
import 'diet_detail_screen.dart';

/// Tab Dieta: piani pubblicati dal nutrizionista.
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
      return DietsListResult(
        activeKind: 'diet_plan',
        activeId: 1,
        diets: [
          DietSummary(
            kind: 'diet_plan',
            id: 1,
            title: 'Piano equilibrato',
            goal: 'Ricompposizione',
            attiva: true,
            targetKcal: 1800,
            mealsCount: 5,
          ),
          DietSummary(
            kind: 'diet_plan',
            id: 2,
            title: 'Piano mantenimento',
            goal: 'Stabilità peso',
            attiva: false,
            targetKcal: 2000,
            mealsCount: 4,
          ),
        ],
      );
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
      body: SafeArea(
        child: FutureBuilder<DietsListResult>(
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

            final diets = snap.data?.diets ?? const <DietSummary>[];
            final sorted = [...diets]..sort((a, b) {
                if (a.attiva != b.attiva) return a.attiva ? -1 : 1;
                return b.id.compareTo(a.id);
              });

            return RefreshIndicator(
              color: AppColors.accent,
              onRefresh: _reload,
              child: ListView(
                physics: const AlwaysScrollableScrollPhysics(),
                padding: kAppPagePadding,
                children: [
                  const AppPageHeader(
                    title: 'Dieta',
                    subtitle: 'Piani alimentari assegnati dal nutrizionista',
                  ),
                  const SizedBox(height: 20),
                  if (diets.isEmpty)
                    const SizedBox(
                      height: 360,
                      child: EmptyPlaceholder(
                        icon: Icons.restaurant_outlined,
                        message: 'Nessuna dieta assegnata ancora',
                        hint: 'Quando il nutrizionista pubblicherà un piano lo vedrai qui',
                      ),
                    )
                  else ...[
                    AppSectionLabel(
                      diets.length == 1
                          ? '1 piano'
                          : '${diets.length} piani',
                    ),
                    const SizedBox(height: 10),
                    for (var i = 0; i < sorted.length; i++) ...[
                      if (i > 0) const SizedBox(height: 10),
                      _DietCard(
                        diet: sorted[i],
                        onTap: () => _open(sorted[i]),
                      ),
                    ],
                  ],
                ],
              ),
            );
          },
        ),
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
    return AppSurfaceCard(
      highlighted: diet.attiva,
      onTap: onTap,
      child: Row(
        children: [
          AppIconBox(
            icon: diet.isPlan
                ? Icons.restaurant_outlined
                : Icons.picture_as_pdf_outlined,
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
                    if (diet.attiva) ...[
                      const SizedBox(width: 8),
                      const AppStatusChip(label: 'Attiva'),
                    ],
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
          const Icon(Icons.chevron_right_rounded, color: AppColors.muted),
        ],
      ),
    );
  }
}
