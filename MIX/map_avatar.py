"""Avatar emoji + sfondo (palette progetto) per posizione sulla mappa live."""
from __future__ import annotations

# Natura e bicicletta
MAP_AVATAR_EMOJIS: tuple[str, ...] = (
    '🚴',
    '🌿',
    '🌳',
    '🌻',
    '🐸',
    '🍃',
    '🌼',
    '🦋',
    '🌲',
    '⛰️',
    '🌺',
    '🍄',
)

# Chiavi allineate a :root in base.css
MAP_AVATAR_BACKGROUNDS: dict[str, str] = {
    'peach': '#f1bf98',
    'mint': '#e1f4cb',
    'sage': '#bacba9',
    'lino': '#f7f8f3',
    'forest': '#3f4739',
}

MAP_AVATAR_BG_ORDER: tuple[str, ...] = (
    'peach',
    'mint',
    'sage',
    'lino',
    'forest',
)

DEFAULT_MAP_AVATAR_EMOJI = MAP_AVATAR_EMOJIS[0]
DEFAULT_MAP_AVATAR_BG = 'peach'


def map_avatar_bg_choices_ordered():
    return [(k, MAP_AVATAR_BACKGROUNDS[k]) for k in MAP_AVATAR_BG_ORDER]


def normalize_map_avatar(emoji: str | None, bg_key: str | None) -> tuple[str, str]:
    e = (emoji or '').strip()
    if e not in MAP_AVATAR_EMOJIS:
        e = DEFAULT_MAP_AVATAR_EMOJI
    k = (bg_key or '').strip().lower()
    if k not in MAP_AVATAR_BACKGROUNDS:
        k = DEFAULT_MAP_AVATAR_BG
    return e, k


def map_avatar_bg_hex(bg_key: str) -> str:
    return MAP_AVATAR_BACKGROUNDS.get(bg_key, MAP_AVATAR_BACKGROUNDS[DEFAULT_MAP_AVATAR_BG])
