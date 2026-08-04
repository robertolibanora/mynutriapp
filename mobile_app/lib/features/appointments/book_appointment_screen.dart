import 'package:flutter/material.dart';

import '../../core/api/appointments_api.dart';
import '../../core/app_scope.dart';
import '../../core/theme/app_theme.dart';

/// Selezione disponibilità del nutrizionista + conferma prenotazione.
class BookAppointmentScreen extends StatefulWidget {
  const BookAppointmentScreen({super.key});

  @override
  State<BookAppointmentScreen> createState() => _BookAppointmentScreenState();
}

class _BookAppointmentScreenState extends State<BookAppointmentScreen> {
  late final AppointmentsApi _api;
  Future<AvailabilityResult>? _future;
  String _tipo = 'check';
  AvailabilitySlot? _selected;
  bool _submitting = false;
  String? _submitError;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _api = AppointmentsApi(AppScope.of(context).apiClient);
    _future ??= _api.fetchAvailability();
  }

  Future<void> _reload() async {
    setState(() {
      _selected = null;
      _submitError = null;
      _future = _api.fetchAvailability();
    });
    await _future;
  }

  Future<void> _confirm() async {
    final slot = _selected;
    if (slot == null || _submitting) return;
    setState(() {
      _submitting = true;
      _submitError = null;
    });
    try {
      await _api.book(
        dataAppuntamento: slot.dataAppuntamento,
        tipo: _tipo,
      );
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _submitError = AppointmentsApi.messageFromError(e);
        _submitting = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text(
          'Disponibilità',
          style: TextStyle(fontWeight: FontWeight.w700),
        ),
      ),
      body: FutureBuilder<AvailabilityResult>(
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
                      AppointmentsApi.messageFromError(snap.error!),
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

          final result = snap.data!;
          final tipi = result.tipi;
          if (tipi.isNotEmpty && !tipi.any((t) => t.value == _tipo)) {
            _tipo = tipi.first.value;
          }

          if (result.error == 'no_nutritionist') {
            return const Center(
              child: Padding(
                padding: EdgeInsets.all(24),
                child: Text(
                  'Nessun nutrizionista collegato al tuo account.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: AppColors.muted),
                ),
              ),
            );
          }

          if (result.slots.isEmpty) {
            return RefreshIndicator(
              color: AppColors.accent,
              onRefresh: _reload,
              child: ListView(
                physics: const AlwaysScrollableScrollPhysics(),
                padding: const EdgeInsets.all(24),
                children: [
                  const SizedBox(height: 80),
                  const Icon(
                    Icons.event_busy_outlined,
                    size: 48,
                    color: AppColors.muted,
                  ),
                  const SizedBox(height: 14),
                  Text(
                    result.professionista != null
                        ? 'Nessuno slot libero con ${result.professionista} nei prossimi giorni.'
                        : 'Nessuno slot libero nei prossimi giorni.',
                    textAlign: TextAlign.center,
                    style: const TextStyle(color: AppColors.muted, height: 1.4),
                  ),
                ],
              ),
            );
          }

          final byDay = <String, List<AvailabilitySlot>>{};
          for (final s in result.slots) {
            byDay.putIfAbsent(s.data, () => []).add(s);
          }

          return Column(
            children: [
              Expanded(
                child: RefreshIndicator(
                  color: AppColors.accent,
                  onRefresh: _reload,
                  child: ListView(
                    padding: const EdgeInsets.fromLTRB(20, 12, 20, 16),
                    children: [
                      if (result.professionista != null) ...[
                        Text(
                          'Slot di ${result.professionista}',
                          style: const TextStyle(
                            color: AppColors.muted,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const SizedBox(height: 14),
                      ],
                      const Text(
                        'Tipo di appuntamento',
                        style: TextStyle(
                          fontWeight: FontWeight.w700,
                          fontSize: 15,
                        ),
                      ),
                      const SizedBox(height: 10),
                      Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: [
                          for (final t in tipi)
                            ChoiceChip(
                              label: Text(t.label),
                              selected: _tipo == t.value,
                              onSelected: (_) => setState(() => _tipo = t.value),
                              selectedColor:
                                  AppColors.accent.withValues(alpha: 0.22),
                              labelStyle: TextStyle(
                                color: _tipo == t.value
                                    ? AppColors.accent
                                    : AppColors.text,
                                fontWeight: FontWeight.w600,
                              ),
                              side: BorderSide(
                                color: _tipo == t.value
                                    ? AppColors.accent.withValues(alpha: 0.5)
                                    : AppColors.border,
                              ),
                              backgroundColor: AppColors.surface,
                            ),
                        ],
                      ),
                      const SizedBox(height: 22),
                      const Text(
                        'Scegli uno slot',
                        style: TextStyle(
                          fontWeight: FontWeight.w700,
                          fontSize: 15,
                        ),
                      ),
                      const SizedBox(height: 10),
                      for (final entry in byDay.entries) ...[
                        Padding(
                          padding: const EdgeInsets.only(top: 8, bottom: 8),
                          child: Text(
                            _dayHeading(entry.key),
                            style: const TextStyle(
                              color: AppColors.accent,
                              fontWeight: FontWeight.w700,
                              fontSize: 13,
                            ),
                          ),
                        ),
                        Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: [
                            for (final slot in entry.value)
                              _SlotChip(
                                slot: slot,
                                selected: _selected?.dataAppuntamento ==
                                    slot.dataAppuntamento,
                                onTap: () => setState(() {
                                  _selected = slot;
                                  _submitError = null;
                                }),
                              ),
                          ],
                        ),
                      ],
                      if (_submitError != null) ...[
                        const SizedBox(height: 16),
                        Text(
                          _submitError!,
                          style: const TextStyle(color: AppColors.danger),
                        ),
                      ],
                      const SizedBox(height: 24),
                    ],
                  ),
                ),
              ),
              SafeArea(
                top: false,
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(20, 8, 20, 16),
                  child: FilledButton(
                    onPressed:
                        _selected == null || _submitting ? null : _confirm,
                    child: Text(
                      _submitting ? 'Invio…' : 'Conferma richiesta',
                    ),
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  String _dayHeading(String isoDate) {
    final d = DateTime.tryParse(isoDate);
    if (d == null) return isoDate;
    const weekdays = [
      'lunedì',
      'martedì',
      'mercoledì',
      'giovedì',
      'venerdì',
      'sabato',
      'domenica',
    ];
    final wd = weekdays[d.weekday - 1];
    return '$wd ${d.day.toString().padLeft(2, '0')}/'
        '${d.month.toString().padLeft(2, '0')}/${d.year}';
  }
}

class _SlotChip extends StatelessWidget {
  const _SlotChip({
    required this.slot,
    required this.selected,
    required this.onTap,
  });

  final AvailabilitySlot slot;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: selected
          ? AppColors.accent.withValues(alpha: 0.18)
          : AppColors.surface,
      borderRadius: BorderRadius.circular(12),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: selected
                  ? AppColors.accent.withValues(alpha: 0.55)
                  : AppColors.border,
            ),
          ),
          child: Text(
            slot.ora,
            style: TextStyle(
              fontWeight: FontWeight.w700,
              color: selected ? AppColors.accent : AppColors.text,
            ),
          ),
        ),
      ),
    );
  }
}
