import 'package:flutter/material.dart';

import '../../core/api/appointments_api.dart';
import '../../core/app_scope.dart';
import '../../core/config/env.dart';
import '../../core/theme/app_theme.dart';
import '../../widgets/app_ui.dart';
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
    if (Env.useMockData || auth.isDemo) {
      final next = DateTime.now().add(const Duration(days: 5));
      return [
        AppointmentItem(
          id: 1,
          titolo: 'Controllo nutrizionale',
          data: next.toIso8601String().split('T').first,
          ora: '10:30',
          statoLabel: 'Confermato',
          professionista: 'Dott.ssa Rossi',
        ),
      ];
    }
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
      body: SafeArea(
        child: FutureBuilder<List<AppointmentItem>>(
          future: _future,
          builder: (context, snap) {
            if (snap.connectionState == ConnectionState.waiting) {
              return const Center(child: CircularProgressIndicator());
            }
            if (snap.hasError) {
              return AppErrorView(
                message: AppointmentsApi.messageFromError(snap.error!),
                onRetry: _reload,
              );
            }

            final items = snap.data ?? const <AppointmentItem>[];
            final sorted = [...items]..sort((a, b) {
                final da = a.dataAppuntamento ?? a.data ?? '';
                final db = b.dataAppuntamento ?? b.data ?? '';
                return da.compareTo(db);
              });

            return RefreshIndicator(
              color: AppColors.accent,
              onRefresh: _reload,
              child: ListView(
                physics: const AlwaysScrollableScrollPhysics(),
                padding: kAppPagePadding,
                children: [
                  const AppPageHeader(
                    title: 'Prenota',
                    subtitle: 'Visite e recall in agenda',
                  ),
                  const SizedBox(height: 20),
                  AppAccentCta(
                    icon: Icons.event_available_outlined,
                    title: 'Prenota un appuntamento',
                    subtitle: 'Vedi le disponibilità del nutrizionista',
                    onTap: _openBooking,
                  ),
                  const SizedBox(height: 22),
                  const AppSectionLabel('In agenda'),
                  const SizedBox(height: 10),
                  if (items.isEmpty)
                    const SizedBox(
                      height: 280,
                      child: EmptyPlaceholder(
                        icon: Icons.event_busy_outlined,
                        message: 'Nessun appuntamento in programma',
                        hint: 'Usa il pulsante sopra per richiedere uno slot',
                      ),
                    )
                  else
                    for (var i = 0; i < sorted.length; i++) ...[
                      if (i > 0) const SizedBox(height: 10),
                      _ApptCard(item: sorted[i]),
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

class _ApptCard extends StatelessWidget {
  const _ApptCard({required this.item});

  final AppointmentItem item;

  @override
  Widget build(BuildContext context) {
    return AppSurfaceCard(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const AppIconBox(icon: Icons.calendar_month_outlined),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  item.titolo,
                  style: const TextStyle(
                    fontWeight: FontWeight.w700,
                    fontSize: 16,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  item.whenLabel,
                  style: const TextStyle(
                    color: AppColors.muted,
                    fontSize: 13.5,
                  ),
                ),
                if (item.professionista != null &&
                    item.professionista!.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(
                    item.professionista!,
                    style: const TextStyle(
                      color: AppColors.muted,
                      fontSize: 13,
                    ),
                  ),
                ],
                if (item.statoLabel != null && item.statoLabel!.isNotEmpty) ...[
                  const SizedBox(height: 10),
                  AppStatusChip(label: item.statoLabel!),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}
