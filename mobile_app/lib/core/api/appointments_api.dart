import 'package:dio/dio.dart';

import 'api_client.dart';

class AppointmentItem {
  const AppointmentItem({
    required this.id,
    required this.titolo,
    this.data,
    this.ora,
    this.stato,
    this.statoLabel,
    this.tipo,
    this.tipoLabel,
    this.note,
    this.professionista,
    this.dataAppuntamento,
  });

  factory AppointmentItem.fromJson(Map<String, dynamic> json) {
    return AppointmentItem(
      id: json['id'] as int? ?? 0,
      titolo: (json['titolo'] as String?) ??
          (json['tipo_label'] as String?) ??
          'Appuntamento',
      data: json['data'] as String?,
      ora: json['ora'] as String?,
      stato: json['stato'] as String?,
      statoLabel: json['stato_label'] as String?,
      tipo: json['tipo'] as String?,
      tipoLabel: json['tipo_label'] as String?,
      note: json['note'] as String?,
      professionista: json['professionista'] as String?,
      dataAppuntamento: json['data_appuntamento'] as String?,
    );
  }

  final int id;
  final String titolo;
  final String? data;
  final String? ora;
  final String? stato;
  final String? statoLabel;
  final String? tipo;
  final String? tipoLabel;
  final String? note;
  final String? professionista;
  final String? dataAppuntamento;

  String get whenLabel {
    if (data == null) return '—';
    final d = DateTime.tryParse(data!);
    final dateStr = d == null
        ? data!
        : '${d.day.toString().padLeft(2, '0')}/'
            '${d.month.toString().padLeft(2, '0')}/'
            '${d.year}';
    if (ora == null || ora!.isEmpty) return dateStr;
    return '$dateStr · $ora';
  }
}

class AvailabilitySlot {
  const AvailabilitySlot({
    required this.dataAppuntamento,
    required this.data,
    required this.ora,
    required this.label,
    this.note,
  });

  factory AvailabilitySlot.fromJson(Map<String, dynamic> json) {
    return AvailabilitySlot(
      dataAppuntamento: json['data_appuntamento'] as String? ?? '',
      data: json['data'] as String? ?? '',
      ora: json['ora'] as String? ?? '',
      label: json['label'] as String? ?? '',
      note: json['note'] as String?,
    );
  }

  final String dataAppuntamento;
  final String data;
  final String ora;
  final String label;
  final String? note;
}

class AppointmentTipo {
  const AppointmentTipo({required this.value, required this.label});

  factory AppointmentTipo.fromJson(Map<String, dynamic> json) {
    return AppointmentTipo(
      value: json['value'] as String? ?? 'check',
      label: json['label'] as String? ?? 'Check',
    );
  }

  final String value;
  final String label;
}

class AvailabilityResult {
  const AvailabilityResult({
    required this.slots,
    required this.tipi,
    this.professionista,
    this.error,
  });

  final List<AvailabilitySlot> slots;
  final List<AppointmentTipo> tipi;
  final String? professionista;
  final String? error;
}

class AppointmentsApi {
  AppointmentsApi(this._client);

  final ApiClient _client;

  Future<List<AppointmentItem>> listAppointments() async {
    final res = await _client.get<Map<String, dynamic>>('/api/v1/appointments');
    final raw = res.data?['appointments'];
    if (raw is! List) return const [];
    return raw
        .whereType<Map>()
        .map((e) => AppointmentItem.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Future<AvailabilityResult> fetchAvailability({int limit = 100}) async {
    final res = await _client.get<Map<String, dynamic>>(
      '/api/v1/appointments/availability',
      queryParameters: {'limit': limit},
    );
    final data = res.data ?? {};
    final slotsRaw = data['slots'];
    final tipiRaw = data['tipi'];
    return AvailabilityResult(
      professionista: data['professionista'] as String?,
      error: data['error'] as String?,
      slots: slotsRaw is List
          ? slotsRaw
              .whereType<Map>()
              .map(
                (e) => AvailabilitySlot.fromJson(Map<String, dynamic>.from(e)),
              )
              .toList()
          : const [],
      tipi: tipiRaw is List
          ? tipiRaw
              .whereType<Map>()
              .map((e) => AppointmentTipo.fromJson(Map<String, dynamic>.from(e)))
              .toList()
          : const [
              AppointmentTipo(value: 'check', label: 'Check'),
              AppointmentTipo(value: 'altro', label: 'Prima consulenza'),
            ],
    );
  }

  Future<AppointmentItem> book({
    required String dataAppuntamento,
    required String tipo,
    String? note,
  }) async {
    final res = await _client.post<Map<String, dynamic>>(
      '/api/v1/appointments',
      data: {
        'data_appuntamento': dataAppuntamento,
        'tipo': tipo,
        if (note != null && note.trim().isNotEmpty) 'note': note.trim(),
      },
    );
    return AppointmentItem.fromJson(res.data ?? {});
  }

  static String messageFromError(Object error) {
    if (error is DioException) {
      final data = error.response?.data;
      if (data is Map) {
        final err = data['error'];
        if (err is String && err.isNotEmpty) return err;
        final msg = data['message'];
        if (msg is String && msg.isNotEmpty) return msg;
      }
      if (error.type == DioExceptionType.connectionError ||
          error.type == DioExceptionType.connectionTimeout) {
        return 'Impossibile contattare il server.';
      }
      return 'Errore di rete (${error.response?.statusCode ?? '—'}).';
    }
    return 'Qualcosa è andato storto.';
  }
}
