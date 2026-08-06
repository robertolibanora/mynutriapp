import 'package:dio/dio.dart';

import 'api_client.dart';

/// Piano / dieta assegnata al paziente (`GET /api/v1/diets`).
class DietSummary {
  const DietSummary({
    required this.kind,
    required this.id,
    required this.title,
    this.goal,
    this.notes,
    this.status,
    this.attiva = false,
    this.dataInizio,
    this.dataFine,
    this.hasPdf = false,
    this.targetKcal,
    this.mealsCount = 0,
    this.kcal,
  });

  factory DietSummary.fromJson(Map<String, dynamic> json) {
    return DietSummary(
      kind: json['kind'] as String? ?? 'diet_plan',
      id: json['id'] as int,
      title: (json['title'] as String?)?.trim().isNotEmpty == true
          ? json['title'] as String
          : 'Dieta #${json['id']}',
      goal: json['goal'] as String?,
      notes: json['notes'] as String?,
      status: json['status'] as String?,
      attiva: json['attiva'] == true,
      dataInizio: json['data_inizio'] as String?,
      dataFine: json['data_fine'] as String?,
      hasPdf: json['has_pdf'] == true,
      targetKcal: _num(json['target_kcal']),
      mealsCount: (json['meals_count'] as num?)?.toInt() ?? 0,
      kcal: _num(json['kcal']),
    );
  }

  final String kind;
  final int id;
  final String title;
  final String? goal;
  final String? notes;
  final String? status;
  final bool attiva;
  final String? dataInizio;
  final String? dataFine;
  final bool hasPdf;
  final double? targetKcal;
  final int mealsCount;
  final double? kcal;

  bool get isPlan => kind == 'diet_plan';

  String get subtitle {
    if (isPlan) {
      final parts = <String>[];
      if (goal != null && goal!.trim().isNotEmpty) parts.add(goal!.trim());
      if (targetKcal != null) parts.add('${targetKcal!.round()} kcal');
      if (mealsCount > 0) {
        parts.add('$mealsCount past${mealsCount == 1 ? 'o' : 'i'}');
      }
      return parts.isEmpty ? 'Piano alimentare' : parts.join(' · ');
    }
    final parts = <String>[];
    if (dataInizio != null && dataFine != null) {
      parts.add('${formatDietDate(dataInizio!)} – ${formatDietDate(dataFine!)}');
    }
    if (kcal != null) parts.add('${kcal!.round()} kcal');
    return parts.isEmpty ? 'Dieta PDF' : parts.join(' · ');
  }

  static double? _num(Object? v) {
    if (v == null) return null;
    if (v is num) return v.toDouble();
    return double.tryParse(v.toString());
  }
}

String formatDietDate(String iso) {
  final d = DateTime.tryParse(iso);
  if (d == null) return iso;
  final dd = d.day.toString().padLeft(2, '0');
  final mm = d.month.toString().padLeft(2, '0');
  return '$dd/$mm/${d.year}';
}

class DietMealItem {
  const DietMealItem({
    required this.id,
    this.foodName,
    this.quantityG,
    this.kcal,
    this.notes,
  });

  factory DietMealItem.fromJson(Map<String, dynamic> json) {
    final food = json['food'];
    String? name;
    if (food is Map) {
      name = food['name'] as String?;
      final brand = food['brand'] as String?;
      if (name != null && brand != null && brand.trim().isNotEmpty) {
        name = '$name ($brand)';
      }
    }
    final computed = json['computed'];
    double? kcal;
    if (computed is Map && computed['kcal'] != null) {
      kcal = (computed['kcal'] as num?)?.toDouble();
    }
    return DietMealItem(
      id: json['id'] as int? ?? 0,
      foodName: name ?? 'Alimento',
      quantityG: (json['quantity_g'] as num?)?.toDouble(),
      kcal: kcal,
      notes: json['notes'] as String?,
    );
  }

  final int id;
  final String? foodName;
  final double? quantityG;
  final double? kcal;
  final String? notes;
}

class DietMeal {
  const DietMeal({
    required this.id,
    this.dayIndex,
    this.dayIndexTo,
    this.dayLabel,
    this.mealName,
    this.mealTime,
    this.notes,
    this.items = const [],
    this.kcal,
  });

  factory DietMeal.fromJson(Map<String, dynamic> json) {
    final itemsRaw = json['items'];
    final items = itemsRaw is List
        ? itemsRaw
            .whereType<Map>()
            .map((e) => DietMealItem.fromJson(Map<String, dynamic>.from(e)))
            .toList()
        : <DietMealItem>[];
    final totals = json['totals'];
    final dayFrom = (json['day_index'] as num?)?.toInt();
    final dayToRaw = (json['day_index_to'] as num?)?.toInt();
    return DietMeal(
      id: json['id'] as int? ?? 0,
      dayIndex: dayFrom,
      dayIndexTo: dayToRaw ?? dayFrom,
      dayLabel: json['day_label'] as String?,
      mealName: json['meal_name'] as String?,
      mealTime: json['meal_time'] as String?,
      notes: json['notes'] as String?,
      items: items,
      kcal: totals is Map ? (totals['kcal'] as num?)?.toDouble() : null,
    );
  }

  final int id;
  final int? dayIndex;
  /// Inclusivo; se assente vale [dayIndex].
  final int? dayIndexTo;
  final String? dayLabel;
  final String? mealName;
  final String? mealTime;
  final String? notes;
  final List<DietMealItem> items;
  final double? kcal;

  int get dayFrom => dayIndex ?? 0;
  int get dayTo => dayIndexTo ?? dayFrom;

  bool coversDay(int dayIdx) => dayIdx >= dayFrom && dayIdx <= dayTo;

  String get heading {
    final name = (mealName?.trim().isNotEmpty == true) ? mealName!.trim() : 'Pasto';
    if (mealTime != null && mealTime!.isNotEmpty) return '$name · $mealTime';
    return name;
  }
}

class DietDetail {
  const DietDetail({
    required this.summary,
    this.meals = const [],
    this.totalKcal,
    this.totalProtein,
    this.totalCarbs,
    this.totalFat,
    this.targetProteinPct,
    this.targetCarbsPct,
    this.targetFatPct,
  });

  factory DietDetail.fromJson(Map<String, dynamic> json) {
    final mealsRaw = json['meals'];
    final meals = mealsRaw is List
        ? mealsRaw
            .whereType<Map>()
            .map((e) => DietMeal.fromJson(Map<String, dynamic>.from(e)))
            .toList()
        : <DietMeal>[];
    final totals = json['totals'];
    return DietDetail(
      summary: DietSummary.fromJson(json),
      meals: meals,
      totalKcal: totals is Map ? (totals['kcal'] as num?)?.toDouble() : null,
      totalProtein:
          totals is Map ? (totals['protein'] as num?)?.toDouble() : null,
      totalCarbs: totals is Map ? (totals['carbs'] as num?)?.toDouble() : null,
      totalFat: totals is Map ? (totals['fat'] as num?)?.toDouble() : null,
      targetProteinPct: (json['target_protein_pct'] as num?)?.toDouble(),
      targetCarbsPct: (json['target_carbs_pct'] as num?)?.toDouble(),
      targetFatPct: (json['target_fat_pct'] as num?)?.toDouble(),
    );
  }

  final DietSummary summary;
  final List<DietMeal> meals;
  final double? totalKcal;
  final double? totalProtein;
  final double? totalCarbs;
  final double? totalFat;
  final double? targetProteinPct;
  final double? targetCarbsPct;
  final double? targetFatPct;

  /// Indici giorno 0-based presenti nel piano (espande gli intervalli).
  List<int> get dayIndexes {
    if (meals.isEmpty) return const [];
    var minD = meals.first.dayFrom;
    var maxD = meals.first.dayTo;
    for (final m in meals) {
      if (m.dayFrom < minD) minD = m.dayFrom;
      if (m.dayTo > maxD) maxD = m.dayTo;
    }
    // Piano tipico a 7 giorni (builder admin).
    if (maxD < 6) maxD = 6;
    if (minD > 0) minD = 0;
    return [for (var i = minD; i <= maxD; i++) i];
  }

  List<DietMeal> mealsForDay(int dayIdx) {
    final list = meals.where((m) => m.coversDay(dayIdx)).toList()
      ..sort((a, b) {
        final ta = a.mealTime ?? '';
        final tb = b.mealTime ?? '';
        final c = ta.compareTo(tb);
        if (c != 0) return c;
        return a.id.compareTo(b.id);
      });
    return list;
  }

  /// Pasti raggruppati per giorno 0-based (intervalli espansi).
  Map<int, List<DietMeal>> get mealsByDayIndex {
    final map = <int, List<DietMeal>>{};
    for (final day in dayIndexes) {
      map[day] = mealsForDay(day);
    }
    return map;
  }
}

class DietsListResult {
  const DietsListResult({this.activeKind, this.activeId, this.diets = const []});

  final String? activeKind;
  final int? activeId;
  final List<DietSummary> diets;
}

class DietsApi {
  DietsApi(this._client);

  final ApiClient _client;

  Future<DietsListResult> listDiets() async {
    final res = await _client.get<Map<String, dynamic>>('/api/v1/diets');
    final data = res.data ?? {};
    final active = data['active'];
    String? activeKind;
    int? activeId;
    if (active is Map) {
      activeKind = active['kind'] as String?;
      activeId = active['id'] as int?;
    }
    final raw = data['diets'];
    final diets = raw is List
        ? raw
            .whereType<Map>()
            .map((e) => DietSummary.fromJson(Map<String, dynamic>.from(e)))
            .toList()
        : <DietSummary>[];
    return DietsListResult(
      activeKind: activeKind,
      activeId: activeId,
      diets: diets,
    );
  }

  Future<DietDetail> getDiet(int id) async {
    final res = await _client.get<Map<String, dynamic>>('/api/v1/diets/$id');
    return DietDetail.fromJson(res.data ?? {});
  }

  Future<DietDetail?> getActive() async {
    final res = await _client.get<Map<String, dynamic>>('/api/v1/diets/active');
    final diet = res.data?['diet'];
    if (diet is! Map) return null;
    return DietDetail.fromJson(Map<String, dynamic>.from(diet));
  }

  static String messageFromError(Object error) {
    if (error is DioException) {
      final data = error.response?.data;
      if (data is Map && data['error'] is String) return data['error'] as String;
      if (data is Map && data['message'] is String) {
        return data['message'] as String;
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
