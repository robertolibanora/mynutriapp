import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

import '../api/api_client.dart';
import '../config/env.dart';
import 'token_storage.dart';

class PatientUser {
  PatientUser({
    required this.id,
    required this.nome,
    required this.cognome,
    this.telefono,
    this.email,
    this.consensoPrivacy = false,
    this.consensoMarketing = false,
    this.erasureRequestedAt,
  });

  factory PatientUser.fromJson(Map<String, dynamic> json) {
    return PatientUser(
      id: json['id'] as int,
      nome: (json['nome'] as String?) ?? '',
      cognome: (json['cognome'] as String?) ?? '',
      telefono: json['telefono'] as String?,
      email: json['email'] as String?,
      consensoPrivacy: json['consenso_privacy'] == true,
      consensoMarketing: json['consenso_marketing'] == true,
      erasureRequestedAt: json['erasure_requested_at'] as String?,
    );
  }

  factory PatientUser.demo() => PatientUser(
        id: 0,
        nome: 'Demo',
        cognome: 'Paziente',
        telefono: '3330000000',
        email: 'demo@mynutriapp.local',
        consensoPrivacy: true,
        consensoMarketing: false,
      );

  final int id;
  final String nome;
  final String cognome;
  final String? telefono;
  final String? email;
  final bool consensoPrivacy;
  final bool consensoMarketing;
  final String? erasureRequestedAt;

  String get displayName => '$nome $cognome'.trim();

  PatientUser copyWith({
    bool? consensoPrivacy,
    bool? consensoMarketing,
    String? erasureRequestedAt,
  }) {
    return PatientUser(
      id: id,
      nome: nome,
      cognome: cognome,
      telefono: telefono,
      email: email,
      consensoPrivacy: consensoPrivacy ?? this.consensoPrivacy,
      consensoMarketing: consensoMarketing ?? this.consensoMarketing,
      erasureRequestedAt: erasureRequestedAt ?? this.erasureRequestedAt,
    );
  }
}

class AuthController extends ChangeNotifier {
  AuthController({
    required ApiClient apiClient,
    required TokenStorage tokenStorage,
  })  : _api = apiClient,
        _tokens = tokenStorage;

  final ApiClient _api;
  final TokenStorage _tokens;

  PatientUser? user;
  bool bootstrapping = true;
  bool busy = false;
  String? error;
  bool isDemo = false;

  bool get isAuthenticated => user != null;

  Future<void> bootstrap() async {
    bootstrapping = true;
    notifyListeners();
    try {
      await _bootstrapBody().timeout(const Duration(seconds: 12));
    } catch (_) {
      try {
        await _tokens.clear();
      } catch (_) {}
      user = null;
    } finally {
      bootstrapping = false;
      notifyListeners();
    }
  }

  Future<void> _bootstrapBody() async {
    if (Env.useMockData) {
      // Nessun auto-login in mock.
      return;
    }
    final access = await _tokens.readAccessToken();
    if (access == null || access.isEmpty) return;
    final res = await _api.get<Map<String, dynamic>>('/api/v1/me');
    user = PatientUser.fromJson(res.data ?? {});
    isDemo = false;
  }

  Future<bool> login({
    required String telefono,
    required String password,
    String? email,
  }) async {
    busy = true;
    error = null;
    notifyListeners();
    try {
      if (Env.useMockData) {
        await Future<void>.delayed(const Duration(milliseconds: 400));
        user = PatientUser.demo();
        isDemo = true;
        return true;
      }
      final body = <String, dynamic>{
        'telefono': telefono.trim(),
        'password': password,
      };
      if (email != null && email.trim().isNotEmpty) {
        body['email'] = email.trim();
      }
      final res = await _api.post<Map<String, dynamic>>(
        '/api/v1/auth/login',
        data: body,
      );
      final data = res.data ?? {};
      final access = data['access_token'] as String?;
      final refresh = data['refresh_token'] as String?;
      if (access == null || refresh == null) {
        error = 'Risposta login non valida';
        return false;
      }
      await _tokens.saveTokens(accessToken: access, refreshToken: refresh);
      final me = await _api.get<Map<String, dynamic>>('/api/v1/me');
      user = PatientUser.fromJson(me.data ?? {});
      isDemo = false;
      return true;
    } on DioException catch (e) {
      if (kDebugMode) {
        debugPrint(
          'login DioException type=${e.type} message=${e.message} '
          'uri=${e.requestOptions.uri} status=${e.response?.statusCode}',
        );
        if (e.error != null) debugPrint('login Dio error=${e.error}');
      }
      // Nessuna risposta HTTP = rete/TLS/ATS, non credenziali.
      final noResponse = e.response == null ||
          e.type == DioExceptionType.connectionTimeout ||
          e.type == DioExceptionType.sendTimeout ||
          e.type == DioExceptionType.receiveTimeout ||
          e.type == DioExceptionType.connectionError;
      if (noResponse) {
        final detail = (e.message ?? e.error?.toString() ?? e.type.name).trim();
        error =
            'Impossibile contattare il server (${Env.apiBaseUrl}).'
            '${detail.isEmpty ? '' : ' $detail'}';
        return false;
      }
      final code = e.response?.data is Map
          ? (e.response!.data as Map)['code'] as String?
          : null;
      if (code == 'phone_ambiguous') {
        error = 'Telefono su più professionisti: inserisci anche l\'email.';
      } else if (code == 'account_inactive') {
        error = 'Account non ancora attivo.';
      } else {
        error = 'Credenziali non valide';
      }
      return false;
    } catch (e, st) {
      if (kDebugMode) {
        debugPrint('login unexpected error: $e\n$st');
      }
      error = 'Errore di connessione';
      return false;
    } finally {
      busy = false;
      notifyListeners();
    }
  }

  Future<void> loginDemo() async {
    busy = true;
    error = null;
    notifyListeners();
    await Future<void>.delayed(const Duration(milliseconds: 500));
    user = PatientUser.demo();
    isDemo = true;
    busy = false;
    notifyListeners();
  }

  /// Richiede reset password. Messaggio sempre generico lato server.
  Future<String> forgotPassword({required String email}) async {
    if (Env.useMockData) {
      await Future<void>.delayed(const Duration(milliseconds: 300));
      return 'Se l\'indirizzo è registrato, riceverai a breve un\'email con le istruzioni.';
    }
    final res = await _api.post<Map<String, dynamic>>(
      '/api/v1/auth/forgot-password',
      data: {'email': email.trim()},
    );
    final data = res.data ?? {};
    return (data['message'] as String?) ??
        'Se l\'indirizzo è registrato, riceverai a breve un\'email con le istruzioni.';
  }

  Future<String> activateAccount({
    required String token,
    required String password,
    required String passwordConfirm,
  }) async {
    if (Env.useMockData) {
      await Future<void>.delayed(const Duration(milliseconds: 300));
      return 'Account attivato (demo). Accedi con le nuove credenziali.';
    }
    final res = await _api.post<Map<String, dynamic>>(
      '/api/v1/auth/activate-account',
      data: {
        'token': token.trim(),
        'password': password,
        'password_confirm': passwordConfirm,
      },
    );
    final data = res.data ?? {};
    return (data['message'] as String?) ??
        'Account attivato. Puoi accedere dall\'app.';
  }

  Future<String> resetPassword({
    required String token,
    required String password,
    required String passwordConfirm,
  }) async {
    if (Env.useMockData) {
      await Future<void>.delayed(const Duration(milliseconds: 300));
      return 'Password aggiornata (demo). Accedi con la nuova password.';
    }
    // Invalida subito eventuali token locali
    await _tokens.clear();
    user = null;
    isDemo = false;
    notifyListeners();

    final res = await _api.post<Map<String, dynamic>>(
      '/api/v1/auth/reset-password',
      data: {
        'token': token.trim(),
        'password': password,
        'password_confirm': passwordConfirm,
      },
    );
    final data = res.data ?? {};
    return (data['message'] as String?) ??
        'Password aggiornata. Accedi con la nuova password.';
  }

  Future<void> logout() async {
    await _tokens.clear();
    user = null;
    isDemo = false;
    notifyListeners();
  }

  void updateUser(PatientUser next) {
    user = next;
    notifyListeners();
  }
}
