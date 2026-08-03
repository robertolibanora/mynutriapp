import 'package:flutter/material.dart';

import '../core/branding.dart';

/// Logo ufficiale MyNutriApp.
class AppLogo extends StatelessWidget {
  const AppLogo({
    super.key,
    this.size = 72,
    this.borderRadius = 18,
    this.semanticLabel = kAppName,
  });

  final double size;
  final double borderRadius;
  final String? semanticLabel;

  @override
  Widget build(BuildContext context) {
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
        AppLogo(size: logoSize, borderRadius: logoSize * 0.28),
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
                    color: theme.colorScheme.onSurface.withValues(alpha: 0.65),
                  ),
                ),
            ],
          ),
        ],
      ],
    );
  }
}
