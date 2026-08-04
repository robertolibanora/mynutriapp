import 'package:dio/dio.dart';

import 'api_client.dart';

class ProgressPoint {
  const ProgressPoint({
    required this.id,
    required this.date,
    this.weight,
    this.aderenza,
  });

  factory ProgressPoint.fromJson(Map<String, dynamic> json) {
    final rawDate = json['data_check']?.toString();
    final parsed = rawDate != null ? DateTime.tryParse(rawDate) : null;
    return ProgressPoint(
      id: json['id'] as int? ?? 0,
      date: parsed ?? DateTime.fromMillisecondsSinceEpoch(0),
      weight: _num(json['peso_settimanale']),
      aderenza: json['aderenza']?.toString(),
    );
  }

  final int id;
  final DateTime date;
  final double? weight;
  final String? aderenza;

  static double? _num(Object? v) {
    if (v == null) return null;
    if (v is num) return v.toDouble();
    return double.tryParse(v.toString());
  }
}

class ProgressApi {
  ProgressApi(this._client);

  final ApiClient _client;

  /// Punti ordinati dal più vecchio al più recente (per il grafico).
  Future<List<ProgressPoint>> listProgress() async {
    final res = await _client.get<Map<String, dynamic>>('/api/v1/progress');
    final raw = res.data?['progress'];
    if (raw is! List) return const [];
    final points = raw
        .whereType<Map>()
        .map((e) => ProgressPoint.fromJson(Map<String, dynamic>.from(e)))
        .where((p) => p.weight != null)
        .toList()
      ..sort((a, b) => a.date.compareTo(b.date));
    return points;
  }

  /// Registra un check paziente (peso obbligatorio).
  Future<ProgressPoint> createCheck({
    required double pesoSettimanale,
    int? aderenza,
    String? frequenzaAllenamenti,
  }) async {
    final body = <String, dynamic>{
      'peso_settimanale': pesoSettimanale,
      'aderenza': ?aderenza,
      if (frequenzaAllenamenti != null && frequenzaAllenamenti.isNotEmpty)
        'frequenza_allenamenti': frequenzaAllenamenti,
    };
    final res = await _client.post<Map<String, dynamic>>(
      '/api/v1/progress',
      data: body,
    );
    final data = res.data;
    if (data == null) {
      throw StateError('Risposta create progress vuota');
    }
    return ProgressPoint.fromJson(data);
  }

  static String messageFromError(Object error) {
    if (error is DioException) {
      final data = error.response?.data;
      if (data is Map && data['error'] is String) return data['error'] as String;
      if (error.type == DioExceptionType.connectionError ||
          error.type == DioExceptionType.connectionTimeout) {
        return 'Impossibile contattare il server.';
      }
      return 'Errore di rete (${error.response?.statusCode ?? '—'}).';
    }
    return 'Qualcosa è andato storto.';
  }
}
