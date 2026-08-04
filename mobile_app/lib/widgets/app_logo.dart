import 'package:flutter/material.dart';

import '../core/branding.dart';
import '../core/theme/app_theme.dart';

/// Brand mark area paziente: forchetta/coltello in riquadro nero (come `user-brand-mark`).
class AppLogo extends StatelessWidget {
  const AppLogo({
    super.key,
    this.size = 40,
    this.borderRadius = 12,
    this.semanticLabel = kAppName,
    this.useAsset = false,
  });

  final double size;
  final double borderRadius;
  final String? semanticLabel;

  /// Se true usa `logo.png` (foglia). Default: icona dieta come design originale.
  final bool useAsset;

  @override
  Widget build(BuildContext context) {
    if (useAsset) {
      return ClipRRect(
        borderRadius: BorderRadius.circular(borderRadius),
        child: Image.asset(
          kAppLogoAsset,
          width: size,
          height: size,
          fit: BoxFit.cover,
          semanticLabel: semanticLabel,
          filterQuality: FilterQuality.high,
        ),
      );
    }

    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: Colors.black,
        borderRadius: BorderRadius.circular(borderRadius),
        border: Border.all(color: AppColors.accent.withValues(alpha: 0.35)),
      ),
      alignment: Alignment.center,
      child: Icon(
        Icons.restaurant,
        size: size * 0.48,
        color: AppColors.text,
        semanticLabel: semanticLabel,
      ),
    );
  }
}

/// Logo + nome app (tipico header / login).
class AppBrandHeader extends StatelessWidget {
  const AppBrandHeader({
    super.key,
    this.logoSize = 40,
    this.showName = true,
    this.subtitle,
  });

  final double logoSize;
  final bool showName;
  final String? subtitle;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        AppLogo(size: logoSize, borderRadius: logoSize * 0.3),
        if (showName) ...[
          const SizedBox(width: 12),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                kAppName,
                style: theme.textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w800,
                  letterSpacing: -0.3,
                ),
              ),
              if (subtitle != null)
                Text(
                  subtitle!,
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: AppColors.muted2,
                  ),
                ),
            ],
          ),
        ],
      ],
    );
  }
}
