import 'dart:typed_data';

import 'package:dio/dio.dart';

import 'api_client.dart';

class PrivacyState {
  PrivacyState({
    required this.consensoPrivacy,
    required this.consensoMarketing,
    this.privacyPolicyVersion,
    this.erasureRequestedAt,
  });

  factory PrivacyState.fromJson(Map<String, dynamic> json) {
    return PrivacyState(
      consensoPrivacy: json['consenso_privacy'] == true,
      consensoMarketing: json['consenso_marketing'] == true,
      privacyPolicyVersion: json['privacy_policy_version'] as String?,
      erasureRequestedAt: json['erasure_requested_at'] as String?,
    );
  }

  final bool consensoPrivacy;
  final bool consensoMarketing;
  final String? privacyPolicyVersion;
  final String? erasureRequestedAt;

  bool get erasurePending =>
      erasureRequestedAt != null && erasureRequestedAt!.isNotEmpty;
}

class GdprApi {
  GdprApi(this._client);

  final ApiClient _client;

  Future<PrivacyState> getPrivacy() async {
    final res = await _client.get<Map<String, dynamic>>('/api/v1/me/privacy');
    return PrivacyState.fromJson(res.data ?? {});
  }

  Future<PrivacyState> updateMarketing(bool enabled) async {
    final res = await _client.patch<Map<String, dynamic>>(
      '/api/v1/me/privacy',
      data: {'consenso_marketing': enabled},
    );
    final privacy = res.data?['privacy'] as Map<String, dynamic>? ?? {};
    return PrivacyState.fromJson(privacy);
  }

  Future<Uint8List> exportData() async {
    final res = await _client.get<List<int>>(
      '/api/v1/me/export',
      options: Options(responseType: ResponseType.bytes),
    );
    return Uint8List.fromList(res.data ?? <int>[]);
  }

  Future<PrivacyState> requestErasure() async {
    final res = await _client.post<Map<String, dynamic>>('/api/v1/me/erasure');
    final privacy = res.data?['privacy'] as Map<String, dynamic>? ?? {};
    return PrivacyState.fromJson(privacy);
  }
}
