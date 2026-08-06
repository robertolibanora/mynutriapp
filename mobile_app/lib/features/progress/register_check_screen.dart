import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/api/progress_api.dart';
import '../../core/app_scope.dart';
import '../../core/config/env.dart';
import '../../core/theme/app_theme.dart';
import '../../widgets/app_ui.dart';

/// Form per registrare un check settimanale (peso + aderenza).
class RegisterCheckScreen extends StatefulWidget {
  const RegisterCheckScreen({super.key, this.initialWeight});

  final double? initialWeight;

  @override
  State<RegisterCheckScreen> createState() => _RegisterCheckScreenState();
}

class _RegisterCheckScreenState extends State<RegisterCheckScreen> {
  final _formKey = GlobalKey<FormState>();
  final _peso = TextEditingController();
  final _freq = TextEditingController();
  int? _aderenza;
  bool _submitting = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    final w = widget.initialWeight;
    if (w != null) {
      _peso.text = w.toStringAsFixed(1);
    }
  }

  @override
  void dispose() {
    _peso.dispose();
    _freq.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_submitting) return;
    if (!_formKey.currentState!.validate()) return;

    final peso = double.parse(_peso.text.trim().replaceAll(',', '.'));
    final freq = _freq.text.trim();
    final auth = AppScope.of(context).auth;

    setState(() {
      _submitting = true;
      _error = null;
    });

    try {
      if (Env.useMockData || auth.isDemo) {
        await Future<void>.delayed(const Duration(milliseconds: 250));
        if (!mounted) return;
        Navigator.of(context).pop(
          ProgressPoint(
            id: DateTime.now().millisecondsSinceEpoch,
            date: DateTime.now(),
            weight: peso,
            aderenza: _aderenza?.toString(),
          ),
        );
        return;
      }

      final api = ProgressApi(AppScope.of(context).apiClient);
      final created = await api.createCheck(
        pesoSettimanale: peso,
        aderenza: _aderenza,
        frequenzaAllenamenti: freq.isEmpty ? null : freq,
      );
      if (!mounted) return;
      Navigator.of(context).pop(created);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = ProgressApi.messageFromError(e);
        _submitting = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text(
          'Registra check',
          style: TextStyle(fontWeight: FontWeight.w700),
        ),
      ),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: kAppPagePadding,
          children: [
            const AppInfoBanner(
              icon: Icons.add_chart_rounded,
              tone: AppBannerTone.accent,
              message:
                  'Inserisci il peso di oggi. Il nutrizionista riceverà il check.',
            ),
            const SizedBox(height: 20),
            TextFormField(
              controller: _peso,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              textInputAction: TextInputAction.next,
              inputFormatters: [
                FilteringTextInputFormatter.allow(RegExp(r'[0-9.,]')),
              ],
              decoration: const InputDecoration(
                labelText: 'Peso (kg)',
                prefixIcon: Icon(Icons.monitor_weight_outlined),
                suffixText: 'kg',
              ),
              validator: (raw) {
                final v = (raw ?? '').trim().replaceAll(',', '.');
                if (v.isEmpty) return 'Inserisci il peso';
                final n = double.tryParse(v);
                if (n == null || n <= 0 || n > 400) {
                  return 'Peso non valido';
                }
                return null;
              },
            ),
            const SizedBox(height: 14),
            TextFormField(
              controller: _freq,
              keyboardType: TextInputType.number,
              textInputAction: TextInputAction.done,
              inputFormatters: [FilteringTextInputFormatter.digitsOnly],
              decoration: const InputDecoration(
                labelText: 'Allenamenti (opzionale)',
                hintText: 'es. 3 volte a settimana',
                prefixIcon: Icon(Icons.fitness_center_outlined),
              ),
            ),
            const SizedBox(height: 22),
            const AppSectionLabel('Aderenza alla dieta'),
            const SizedBox(height: 6),
            const Text(
              'Da 1 (bassa) a 10 (ottima) — opzionale',
              style: TextStyle(color: AppColors.muted, fontSize: 13),
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (var i = 1; i <= 10; i++)
                  ChoiceChip(
                    label: Text('$i'),
                    selected: _aderenza == i,
                    onSelected: (sel) {
                      setState(() => _aderenza = sel ? i : null);
                    },
                    selectedColor: AppColors.accent.withValues(alpha: 0.35),
                    labelStyle: TextStyle(
                      fontWeight: FontWeight.w700,
                      color:
                          _aderenza == i ? AppColors.text : AppColors.muted,
                    ),
                    side: BorderSide(
                      color: _aderenza == i
                          ? AppColors.accent
                          : AppColors.border,
                    ),
                    backgroundColor: AppColors.surface,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(10),
                    ),
                  ),
              ],
            ),
            if (_error != null) ...[
              const SizedBox(height: 18),
              AppInfoBanner(
                message: _error!,
                icon: Icons.error_outline_rounded,
                tone: AppBannerTone.danger,
              ),
            ],
            const SizedBox(height: 28),
            SizedBox(
              width: double.infinity,
              height: 52,
              child: FilledButton(
                onPressed: _submitting ? null : _submit,
                child: _submitting
                    ? const SizedBox(
                        width: 22,
                        height: 22,
                        child: CircularProgressIndicator(
                          strokeWidth: 2.4,
                          color: Color(0xFF1A0F08),
                        ),
                      )
                    : const Text('Salva check'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
