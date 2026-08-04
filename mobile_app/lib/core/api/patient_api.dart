import 'api_client.dart';

/// Snapshot home area paziente (allineato alle card dashboard user).
class PatientHomeSnapshot {
  const PatientHomeSnapshot({
    this.diet,
    this.workout,
    this.latestProgress,
    this.nextAppointment,
  });

  final Map<String, dynamic>? diet;
  final Map<String, dynamic>? workout;
  final Map<String, dynamic>? latestProgress;
  final Map<String, dynamic>? nextAppointment;
}

class PatientApi {
  PatientApi(this._api);

  final ApiClient _api;

  Future<PatientHomeSnapshot> fetchHome() async {
    final results = await Future.wait([
      _safeGet('/api/v1/diets/active'),
      _safeGet('/api/v1/workouts/active'),
      _safeGet('/api/v1/progress/latest'),
      _safeGet('/api/v1/appointments'),
    ]);

    final dietBody = results[0];
    final workoutBody = results[1];
    final progressBody = results[2];
    final apptBody = results[3];

    Map<String, dynamic>? nextAppt;
    final list = apptBody?['appointments'];
    if (list is List && list.isNotEmpty) {
      final now = DateTime.now();
      final upcoming = list.whereType<Map>().map((e) {
        return Map<String, dynamic>.from(e);
      }).where((a) {
        final raw = a['data_appuntamento'] as String?;
        if (raw == null) return false;
        final dt = DateTime.tryParse(raw);
        return dt != null && !dt.isBefore(now);
      }).toList()
        ..sort((a, b) {
          final da = DateTime.parse(a['data_appuntamento'] as String);
          final db = DateTime.parse(b['data_appuntamento'] as String);
          return da.compareTo(db);
        });
      if (upcoming.isNotEmpty) nextAppt = upcoming.first;
    }

    return PatientHomeSnapshot(
      diet: _asMap(dietBody?['diet']),
      workout: _asMap(workoutBody?['workout']),
      latestProgress: _asMap(progressBody?['progress']),
      nextAppointment: nextAppt,
    );
  }

  Future<List<Map<String, dynamic>>> fetchProgress() async {
    final body = await _safeGet('/api/v1/progress');
    final list = body?['progress'];
    if (list is! List) return const [];
    return list.whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();
  }

  Future<List<Map<String, dynamic>>> fetchAppointments() async {
    final body = await _safeGet('/api/v1/appointments');
    final list = body?['appointments'];
    if (list is! List) return const [];
    return list.whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();
  }

  Future<Map<String, dynamic>?> _safeGet(String path) async {
    try {
      final res = await _api.get<Map<String, dynamic>>(path);
      return res.data;
    } catch (_) {
      return null;
    }
  }

  Map<String, dynamic>? _asMap(Object? value) {
    if (value is Map<String, dynamic>) return value;
    if (value is Map) return Map<String, dynamic>.from(value);
    return null;
  }
}
