"""Icone SVG per l'interfaccia admin."""

from markupsafe import Markup

# path / inner SVG per icona (stile sidebar: stroke 1.7)
_ICONS = {
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    "x": '<path d="M18 6 6 18M6 6l12 12"/>',
    "eye": '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/>',
    "edit": '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
    "trash": '<path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M10 11v6M14 11v6"/>',
    "users": '<path d="M16 19v-1a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v1"/><circle cx="9.5" cy="7.5" r="3.2"/><path d="M21 19v-1a4 4 0 0 0-3-3.85"/>',
    "user": '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    "calendar": '<rect x="3.5" y="4.5" width="17" height="16" rx="2.5"/><path d="M3.5 9h17M8 3v4M16 3v4"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "wallet": '<rect x="3" y="6" width="18" height="13" rx="2.5"/><path d="M3 10h18M16 14.5h2.5"/>',
    "chart": '<path d="M4 19V5"/><path d="M4 19h16"/><path d="M8 17V9M12 17V7M16 17v-4"/>',
    "diet": '<path d="M11 20A7 7 0 0 1 4 13c0-5 5-9 16-9 0 11-4 16-9 16z"/><path d="M4 20c4-4 6-6 9-7"/>',
    "dumbbell": '<path d="m6.5 6.5 11 11"/><path d="m8 8-2-2"/><path d="m16 16 2 2"/><path d="m18 6-2 2"/><path d="m6 18 2-2"/>',
    "target": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5"/>',
    "phone": '<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.8 19.8 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.08 4.18 2 2 0 0 1 4.06 2h3a2 2 0 0 1 2 1.72c.12.86.3 1.7.54 2.5a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.58-1.06a2 2 0 0 1 2.11-.45c.8.24 1.64.42 2.5.54A2 2 0 0 1 22 16.92z"/>',
    "mail": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "check-circle": '<circle cx="12" cy="12" r="9"/><path d="m9 12 2 2 4-4"/>',
    "x-circle": '<circle cx="12" cy="12" r="9"/><path d="m15 9-6 6M9 9l6 6"/>',
    "pause": '<rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/>',
    "play": '<polygon points="8,5 19,12 8,19"/>',
    "list": '<path d="M8 6h13M8 12h13M8 18h13"/><path d="M3 6h.01M3 12h.01M3 18h.01"/>',
    "clipboard": '<rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h1a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h1"/>',
    "message": '<path d="M21 11.5a7.5 7.5 0 0 1-11 6.6L4 20l1.4-5.3A7.5 7.5 0 1 1 21 11.5z"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>',
    "package": '<path d="M21 8l-9-5-9 5v8l9 5 9-5V8z"/><path d="M3.5 8.5 12 13l8.5-4.5M12 22V13"/>',
    "card": '<rect x="3" y="6" width="18" height="13" rx="2.5"/><path d="M3 10h18M7 15h.01M11 15h2"/>',
    "flame": '<path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.5-1.5-3-1.5-5.5 0-2 2-3.5 2.5-3.5S14 4.5 14 6.5C14 10 11 11.5 11 12a2.5 2.5 0 0 0 2.5 2.5c1.5 0 2.5-1.5 2.5-3.5 0-2-1-3-1-4.5 2 1.5 3 3.5 3 6a6 6 0 1 1-12 0c0-2 .5-3.5 1.5-4.5z"/>',
    "scale": '<path d="M12 3v17"/><path d="M5 8h14"/><path d="M7 8l-2 5h4l-2-5zM17 8l-2 5h4l-2-5z"/>',
    "trending": '<path d="m3 17 6-6 4 4 7-9"/><path d="M14 6h7v7"/>',
    "file": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>',
    "medical": '<path d="M12 6v12"/><path d="M6 12h12"/><path d="M18 8a6 6 0 1 0-12 0v10a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V8z"/>',
    "tag": '<path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><circle cx="7.5" cy="7.5" r="1.5"/>',
    "filter": '<polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>',
    "folder": '<path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7l-2-2H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2z"/>',
    "arrow-left": '<path d="m15 18-6-6 6-6"/>',
    "arrow-right": '<path d="m9 6 6 6-6 6"/>',
    "undo": '<path d="M3 7v6h6"/><path d="M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13"/>',
    "refresh": '<path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 16h5v5"/>',
    "bank": '<rect x="3" y="10" width="18" height="10"/><path d="M12 2 3 7v3h18V7l-9-5z"/><path d="M7 14h.01M12 14h.01M17 14h.01"/>',
    "cash": '<rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="2"/><path d="M6 10h.01M18 14h.01"/>',
    "lock": '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    "camera": '<path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h3l2-3h8l2 3h3a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/>',
    "ruler": '<path d="M21.3 8.7 8.7 21.3c-1 1-2.5 1-3.4 0l-2.6-2.6c-1-1-1-2.5 0-3.4L15.3 2.7c1-1 2.5-1 3.4 0l2.6 2.6c1 1 1 2.5 0 3.4z"/><path d="m7.5 10.5 2 2M11.5 14.5l2 2M15.5 6.5l2 2"/>',
    "calculator": '<rect x="4" y="2" width="16" height="20" rx="2"/><path d="M8 6h8M8 10h.01M12 10h.01M16 10h.01M8 14h.01M12 14h.01M16 14h.01M8 18h.01M12 18h.01M16 18h.01"/>',
    "flask": '<path d="M9 3h6v7.5l5.5 9.5a2 2 0 0 1-1.7 3H5.2a2 2 0 0 1-1.7-3L9 10.5V3z"/><path d="M9 3h6"/>',
    "ban": '<circle cx="12" cy="12" r="9"/><path d="m4.9 4.9 14.2 14.2"/>',
    "bell": '<path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/>',
    "hourglass": '<path d="M6 2h12"/><path d="M6 22h12"/><path d="M6 2v6a6 6 0 0 0 6 6 6 6 0 0 0-6 6v6"/><path d="M18 2v6a6 6 0 0 1-6 6 6 6 0 0 1 6 6v6"/>',
    "activity": '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
    "link": '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
    "cake": '<path d="M20 21V8a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v13"/><path d="M4 15h16"/><path d="M8 21v-4M12 21v-4M16 21v-4"/><path d="M12 3v2M8 5h8"/>',
    "save": '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><path d="M17 21v-8H7v8M7 3v5h8"/>',
    "zap": '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
    "alert": '<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><path d="M12 9v4M12 17h.01"/>',
    "star": '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>',
    "image": '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-5-5L5 21"/>',
    "pin": '<path d="M12 2v8"/><path d="m8 6 4-4 4 4"/><path d="M8 10H5a2 2 0 0 0-2 2v1a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-1a2 2 0 0 0-2-2h-3"/>',
    "heart-pulse": '<path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/><path d="M3.22 12H9.5l.5-1 2 4.5 2-7 1.5 3.5h5.27"/>',
    "droplet": '<path d="M12 22a7 7 0 0 0 7-7c0-2-1-3.9-3-5.5S12 2 12 2 6 7.5 6 10a7 7 0 0 0 7 12z"/>',
    "bone": '<path d="M15 3a3 3 0 0 0-2.12.88L9.5 7.26a3 3 0 0 0 0 4.24l1.38 1.38a3 3 0 0 0 4.24 0l3.38-3.38A3 3 0 0 0 21 6.12 3 3 0 0 0 15 3z"/><path d="M9 21a3 3 0 0 0 2.12-.88l3.38-3.38a3 3 0 0 0 0-4.24l-1.38-1.38a3 3 0 0 0-4.24 0L5.5 14.74A3 3 0 0 0 3 17.88 3 3 0 0 0 9 21z"/>',
    "help": '<circle cx="12" cy="12" r="9"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3M12 17h.01"/>',
}


def admin_icon(name, size=18, css_class="adm-icon", title=None):
    """Renderizza un'icona SVG inline per le template Jinja."""
    inner = _ICONS.get(name)
    if not inner:
        return Markup("")
    label = f' aria-label="{title}" role="img"' if title else ' aria-hidden="true"'
    return Markup(
        f'<span class="{css_class}{label}">'
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        f'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
        f"{inner}</svg></span>"
    )
