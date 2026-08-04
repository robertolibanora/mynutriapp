import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import '../../core/api/progress_api.dart';
import '../../core/app_scope.dart';
import '../../core/config/env.dart';
import '../../core/theme/app_theme.dart';
import '../../widgets/empty_placeholder.dart';
import 'register_check_screen.dart';

class ProgressScreen extends StatefulWidget {
  const ProgressScreen({super.key});

  @override
  State<ProgressScreen> createState() => _ProgressScreenState();
}

class _ProgressScreenState extends State<ProgressScreen> {
  late final ProgressApi _api;
  Future<List<ProgressPoint>>? _future;
  List<ProgressPoint>? _demoPoints;
  int? _touchedIndex;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _api = ProgressApi(AppScope.of(context).apiClient);
    _future ??= _load();
  }

  List<ProgressPoint> _seedDemo() {
    final now = DateTime.now();
    return [
      ProgressPoint(
        id: 1,
        date: now.subtract(const Duration(days: 21)),
        weight: 72.5,
        aderenza: '7',
      ),
      ProgressPoint(
        id: 2,
        date: now.subtract(const Duration(days: 14)),
        weight: 71.9,
        aderenza: '8',
      ),
      ProgressPoint(
        id: 3,
        date: now.subtract(const Duration(days: 7)),
        weight: 71.3,
        aderenza: '9',
      ),
      ProgressPoint(
        id: 4,
        date: now,
        weight: 70.7,
        aderenza: '10',
      ),
    ];
  }

  Future<List<ProgressPoint>> _load() async {
    final auth = AppScope.of(context).auth;
    if (Env.useMockData || auth.isDemo) {
      return List<ProgressPoint>.from(_demoPoints ??= _seedDemo());
    }
    return _api.listProgress();
  }

  Future<void> _reload() async {
    setState(() {
      _touchedIndex = null;
      _future = _load();
    });
    await _future;
  }

  Future<void> _openRegister(List<ProgressPoint> points) async {
    final initial = points.isNotEmpty ? points.last.weight : null;
    final created = await Navigator.of(context).push<ProgressPoint>(
      MaterialPageRoute<ProgressPoint>(
        builder: (_) => RegisterCheckScreen(initialWeight: initial),
      ),
    );
    if (created == null || !mounted) return;

    final auth = AppScope.of(context).auth;
    if (Env.useMockData || auth.isDemo) {
      final base = List<ProgressPoint>.from(_demoPoints ??= _seedDemo());
      // Sostituisci check dello stesso giorno se presente.
      final day = DateTime(created.date.year, created.date.month, created.date.day);
      base.removeWhere((p) {
        final d = DateTime(p.date.year, p.date.month, p.date.day);
        return d == day;
      });
      base.add(created);
      base.sort((a, b) => a.date.compareTo(b.date));
      _demoPoints = base;
    }

    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Check registrato.')),
    );
    await _reload();
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
      body: FutureBuilder<List<ProgressPoint>>(
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
                      ProgressApi.messageFromError(snap.error!),
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

          final points = snap.data ?? const <ProgressPoint>[];
          return Column(
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 8, 20, 12),
                child: _RegisterCta(onTap: () => _openRegister(points)),
              ),
              Expanded(
                child: points.isEmpty
                    ? RefreshIndicator(
                        color: AppColors.accent,
                        onRefresh: _reload,
                        child: ListView(
                          physics: const AlwaysScrollableScrollPhysics(),
                          children: const [
                            SizedBox(
                              height: 420,
                              child: EmptyPlaceholder(
                                icon: Icons.show_chart_outlined,
                                message:
                                    'Nessun progresso ancora.\nRegistra il primo check.',
                              ),
                            ),
                          ],
                        ),
                      )
                    : RefreshIndicator(
                        color: AppColors.accent,
                        onRefresh: _reload,
                        child: ListView(
                          physics: const AlwaysScrollableScrollPhysics(),
                          padding: const EdgeInsets.fromLTRB(20, 0, 20, 28),
                          children: [
                            _SummaryHeader(points: points),
                            const SizedBox(height: 18),
                            _WeightChart(
                              points: points,
                              touchedIndex: _touchedIndex,
                              onTouched: (i) =>
                                  setState(() => _touchedIndex = i),
                            ),
                            const SizedBox(height: 20),
                            if (_touchedIndex != null &&
                                _touchedIndex! >= 0 &&
                                _touchedIndex! < points.length)
                              _TouchedCard(point: points[_touchedIndex!])
                            else
                              _TouchedCard(
                                point: points.last,
                                label: 'Ultimo check',
                              ),
                          ],
                        ),
                      ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _RegisterCta extends StatelessWidget {
  const _RegisterCta({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.accent,
      borderRadius: BorderRadius.circular(16),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: const Padding(
          padding: EdgeInsets.symmetric(horizontal: 18, vertical: 16),
          child: Row(
            children: [
              Icon(Icons.add_chart_rounded, color: Color(0xFF1A0F08), size: 26),
              SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Registra check',
                      style: TextStyle(
                        color: Color(0xFF1A0F08),
                        fontWeight: FontWeight.w800,
                        fontSize: 16,
                      ),
                    ),
                    SizedBox(height: 2),
                    Text(
                      'Aggiorna peso e aderenza di questa settimana',
                      style: TextStyle(
                        color: Color(0xFF3A2416),
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
              ),
              Icon(
                Icons.arrow_forward_ios_rounded,
                size: 16,
                color: Color(0xFF1A0F08),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SummaryHeader extends StatelessWidget {
  const _SummaryHeader({required this.points});

  final List<ProgressPoint> points;

  @override
  Widget build(BuildContext context) {
    final first = points.first.weight!;
    final last = points.last.weight!;
    final delta = last - first;
    final deltaLabel = '${delta >= 0 ? '+' : ''}${delta.toStringAsFixed(1)} kg';

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.border),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Peso attuale',
                  style: TextStyle(
                    color: AppColors.muted,
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  '${last.toStringAsFixed(1)} kg',
                  style: const TextStyle(
                    fontSize: 28,
                    fontWeight: FontWeight.w800,
                    letterSpacing: -0.5,
                  ),
                ),
              ],
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              const Text(
                'Variazione',
                style: TextStyle(
                  color: AppColors.muted,
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                deltaLabel,
                style: TextStyle(
                  fontSize: 20,
                  fontWeight: FontWeight.w800,
                  color: delta <= 0 ? AppColors.accent : AppColors.danger,
                ),
              ),
              Text(
                'su ${points.length} check',
                style: const TextStyle(color: AppColors.muted, fontSize: 12),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _TouchedCard extends StatelessWidget {
  const _TouchedCard({required this.point, this.label});

  final ProgressPoint point;
  final String? label;

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
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label ?? 'Check selezionato',
                  style: const TextStyle(
                    color: AppColors.muted,
                    fontSize: 12.5,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  _fmtDate(point.date),
                  style: const TextStyle(
                    fontWeight: FontWeight.w700,
                    fontSize: 16,
                  ),
                ),
                if (point.aderenza != null && point.aderenza!.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(
                    'Aderenza: ${point.aderenza}',
                    style: const TextStyle(color: AppColors.muted, fontSize: 13.5),
                  ),
                ],
              ],
            ),
          ),
          Text(
            '${point.weight!.toStringAsFixed(1)} kg',
            style: const TextStyle(
              color: AppColors.accent,
              fontWeight: FontWeight.w800,
              fontSize: 22,
            ),
          ),
        ],
      ),
    );
  }
}

class _WeightChart extends StatelessWidget {
  const _WeightChart({
    required this.points,
    required this.touchedIndex,
    required this.onTouched,
  });

  final List<ProgressPoint> points;
  final int? touchedIndex;
  final ValueChanged<int?> onTouched;

  @override
  Widget build(BuildContext context) {
    final weights = points.map((p) => p.weight!).toList();
    final minW = weights.reduce((a, b) => a < b ? a : b);
    final maxW = weights.reduce((a, b) => a > b ? a : b);
    final pad = ((maxW - minW).abs() < 0.5 ? 1.0 : (maxW - minW) * 0.25)
        .clamp(0.5, 5.0);
    final minY = (minW - pad);
    final maxY = (maxW + pad);

    final spots = <FlSpot>[
      for (var i = 0; i < points.length; i++)
        FlSpot(i.toDouble(), points[i].weight!),
    ];

    return Container(
      height: 280,
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(8, 20, 16, 12),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.border),
      ),
      child: LineChart(
        LineChartData(
          minX: 0,
          maxX: (points.length - 1).toDouble(),
          minY: minY,
          maxY: maxY,
          gridData: FlGridData(
            show: true,
            drawVerticalLine: false,
            horizontalInterval: _niceInterval(minY, maxY),
            getDrawingHorizontalLine: (value) => FlLine(
              color: AppColors.border,
              strokeWidth: 1,
            ),
          ),
          borderData: FlBorderData(show: false),
          titlesData: FlTitlesData(
            topTitles: const AxisTitles(
              sideTitles: SideTitles(showTitles: false),
            ),
            rightTitles: const AxisTitles(
              sideTitles: SideTitles(showTitles: false),
            ),
            leftTitles: AxisTitles(
              sideTitles: SideTitles(
                showTitles: true,
                reservedSize: 44,
                interval: _niceInterval(minY, maxY),
                getTitlesWidget: (value, meta) {
                  if (value < minY || value > maxY) {
                    return const SizedBox.shrink();
                  }
                  return Text(
                    value.toStringAsFixed(1),
                    style: const TextStyle(
                      color: AppColors.muted,
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                    ),
                  );
                },
              ),
            ),
            bottomTitles: AxisTitles(
              sideTitles: SideTitles(
                showTitles: true,
                reservedSize: 28,
                interval: 1,
                getTitlesWidget: (value, meta) {
                  final i = value.round();
                  if (i < 0 || i >= points.length) {
                    return const SizedBox.shrink();
                  }
                  // Mostra prima, ultima e qualche intermedia.
                  final show = points.length <= 5 ||
                      i == 0 ||
                      i == points.length - 1 ||
                      i == (points.length / 2).floor();
                  if (!show) return const SizedBox.shrink();
                  final d = points[i].date;
                  return Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Text(
                      '${d.day.toString().padLeft(2, '0')}/${d.month.toString().padLeft(2, '0')}',
                      style: const TextStyle(
                        color: AppColors.muted,
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  );
                },
              ),
            ),
          ),
          lineTouchData: LineTouchData(
            handleBuiltInTouches: true,
            touchCallback: (event, response) {
              if (!event.isInterestedForInteractions ||
                  response?.lineBarSpots == null ||
                  response!.lineBarSpots!.isEmpty) {
                // tieni ultimo tocco finché non ne arriva un altro
                return;
              }
              onTouched(response.lineBarSpots!.first.x.round());
            },
            touchTooltipData: LineTouchTooltipData(
              getTooltipColor: (_) => const Color(0xFF2A2A2A),
              getTooltipItems: (spots) {
                return spots.map((s) {
                  final i = s.x.round();
                  final p = points[i];
                  return LineTooltipItem(
                    '${_fmtDate(p.date)}\n${p.weight!.toStringAsFixed(1)} kg',
                    const TextStyle(
                      color: AppColors.text,
                      fontWeight: FontWeight.w700,
                      fontSize: 13,
                      height: 1.35,
                    ),
                  );
                }).toList();
              },
            ),
            getTouchedSpotIndicator: (bar, indexes) {
              return indexes.map((i) {
                return TouchedSpotIndicatorData(
                  FlLine(
                    color: AppColors.accent.withValues(alpha: 0.45),
                    strokeWidth: 1.5,
                  ),
                  FlDotData(
                    show: true,
                    getDotPainter: (spot, percent, barData, index) {
                      return FlDotCirclePainter(
                        radius: 6,
                        color: AppColors.accent,
                        strokeWidth: 2,
                        strokeColor: AppColors.bg,
                      );
                    },
                  ),
                );
              }).toList();
            },
          ),
          lineBarsData: [
            LineChartBarData(
              spots: spots,
              isCurved: true,
              curveSmoothness: 0.28,
              color: AppColors.accent,
              barWidth: 3,
              isStrokeCapRound: true,
              dotData: FlDotData(
                show: true,
                getDotPainter: (spot, percent, bar, index) {
                  final selected = touchedIndex == index;
                  return FlDotCirclePainter(
                    radius: selected ? 5.5 : 3.5,
                    color: AppColors.accent,
                    strokeWidth: selected ? 2 : 0,
                    strokeColor: AppColors.bg,
                  );
                },
              ),
              belowBarData: BarAreaData(
                show: true,
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    AppColors.accent.withValues(alpha: 0.28),
                    AppColors.accent.withValues(alpha: 0.02),
                  ],
                ),
              ),
            ),
          ],
        ),
        duration: const Duration(milliseconds: 250),
      ),
    );
  }

  static double _niceInterval(double minY, double maxY) {
    final range = (maxY - minY).abs();
    if (range <= 1) return 0.5;
    if (range <= 2) return 0.5;
    if (range <= 5) return 1;
    return (range / 4).ceilToDouble();
  }
}

String _fmtDate(DateTime d) {
  final dd = d.day.toString().padLeft(2, '0');
  final mm = d.month.toString().padLeft(2, '0');
  return '$dd/$mm/${d.year}';
}
