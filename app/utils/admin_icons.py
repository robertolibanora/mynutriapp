"""Icone SVG per l'interfaccia admin.

Le icone sono disabilitate: l'helper resta disponibile per non rompere
i template, ma non renderizza più nulla.
"""

from markupsafe import Markup

_ICONS = {}


def admin_icon(name, size=18, css_class="adm-icon", title=None, stroke=1.7):
    """Le icone UI sono disabilitate (ritorna sempre stringa vuota)."""
    return Markup("")
