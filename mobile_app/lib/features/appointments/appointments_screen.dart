import 'package:flutter/material.dart';

import '../../core/api/appointments_api.dart';
import '../../core/app_scope.dart';
import '../../core/config/env.dart';
import '../../core/theme/app_theme.dart';
import '../../widgets/empty_placeholder.dart';
import 'book_appointment_screen.dart';

/// Tab Prenota: lista appuntamenti + CTA disponibilità nutrizionista.
class AppointmentsScreen extends StatefulWidget {
  const AppointmentsScreen({super.key});

  @override
  State<AppointmentsScreen> createState() => _AppointmentsScreenState();
}

class _AppointmentsScreenState extends State<AppointmentsScreen> {
  late final AppointmentsApi _api;
  Future<List<AppointmentItem>>? _future;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _api = AppointmentsApi(AppScope.of(context).apiClient);
    _future ??= _load();
  }

  Future<List<AppointmentItem>> _load() async {
    final auth = AppScope.of(context).auth;
    if (Env.useMockData || auth.isDemo) return const [];
    return _api.listAppointments();
  }

  Future<void> _reload() async {
    setState(() => _future = _load());
    await _future;
  }

  Future<void> _openBooking() async {
    final auth = AppScope.of(context).auth;
    if (auth.isDemo || Env.useMockData) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'La prenotazione richiede un account reale collegato al nutrizionista.',
          ),
        ),
      );
      return;
    }
    final ok = await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(
        builder: (_) => const BookAppointmentScreen(),
      ),
    );
    if (ok == true && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Richiesta inviata. Il nutrizionista la confermerà a breve.',
          ),
        ),
      );
      await _reload();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text(
          'Prenota',
          style: TextStyle(fontWeight: FontWeight.w700),
        ),
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 8, 20, 12),
            child: _BookCta(onTap: _openBooking),
          ),
          Expanded(
            child: FutureBuilder<List<AppointmentItem>>(
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

                final items = snap.data ?? const <AppointmentItem>[];
                if (items.isEmpty) {
                  return RefreshIndicator(
                    color: AppColors.accent,
                    onRefresh: _reload,
                    child: ListView(
                      physics: const AlwaysScrollableScrollPhysics(),
                      children: const [
                        SizedBox(
                          height: 360,
                          child: EmptyPlaceholder(
                            icon: Icons.event_busy_outlined,
                            message: 'Nessun appuntamento in programma',
                          ),
                        ),
                      ],
                    ),
                  );
                }

                final sorted = [...items]..sort((a, b) {
                    final da = a.dataAppuntamento ?? a.data ?? '';
                    final db = b.dataAppuntamento ?? b.data ?? '';
                    return da.compareTo(db);
                  });

                return RefreshIndicator(
                  color: AppColors.accent,
                  onRefresh: _reload,
                  child: ListView.separated(
                    padding: const EdgeInsets.fromLTRB(20, 4, 20, 28),
                    itemCount: sorted.length,
                    separatorBuilder: (_, _) => const SizedBox(height: 10),
                    itemBuilder: (context, i) => _ApptCard(item: sorted[i]),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _BookCta extends StatelessWidget {
  const _BookCta({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.accent,
      borderRadius: BorderRadius.circular(16),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 16),
          child: Row(
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  color: Colors.black.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: const Icon(
                  Icons.calendar_month,
                  color: Color(0xFF1A0F08),
                ),
              ),
              const SizedBox(width: 14),
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Prenota un appuntamento',
                      style: TextStyle(
                        color: Color(0xFF1A0F08),
                        fontWeight: FontWeight.w800,
                        fontSize: 16,
                      ),
                    ),
                    SizedBox(height: 2),
                    Text(
                      'Vedi le disponibilità del tuo nutrizionista',
                      style: TextStyle(
                        color: Color(0xFF3A2416),
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
              ),
              const Icon(
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

class _ApptCard extends StatelessWidget {
  const _ApptCard({required this.item});

  final AppointmentItem item;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            item.titolo,
            style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
          ),
          const SizedBox(height: 6),
          Text(
            item.whenLabel,
            style: const TextStyle(color: AppColors.muted, fontSize: 14),
          ),
          if (item.statoLabel != null && item.statoLabel!.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(
              item.statoLabel!,
              style: const TextStyle(
                color: AppColors.accent,
                fontWeight: FontWeight.w600,
                fontSize: 13,
              ),
            ),
          ],
        ],
      ),
    );
  }
}
