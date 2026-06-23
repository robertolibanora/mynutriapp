#!/usr/bin/env python3
"""Genera le pagine HTML standalone user (paziente) MyNutriAPP."""

from pathlib import Path

OUT = Path(__file__).parent

HEAD = """<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
  <meta name="theme-color" content="#ff751f">
  <title>{title} — NutriApp</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Adam+Script&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="user.css">
</head>
<body data-nav="{nav}">
  <div id="site-header"></div>
  <div class="content-wrapper">
    <main class="user-content content-main">
{content}
    </main>
  </div>
  <div id="site-bottom-nav"></div>
  <script src="user.js"></script>
</body>
</html>"""


def wrap(title, nav, content):
    indented = "\n".join("      " + line if line else "" for line in content.strip().split("\n"))
    return HEAD.format(title=title, nav=nav, content=indented)


def title(text):
    return f'<h1 class="page-title-user">{text}</h1>'


def card_info(label, value):
    return f'<div class="card-info-row"><span class="card-label">{label}</span><span class="card-value">{value}</span></div>'


def summary_card(icon, name, rows, footer=""):
    rows_html = "".join(
        f'<div class="summary-row"><span class="summary-label">{l}</span><span class="summary-value">{v}</span></div>'
        for l, v in rows
    )
    foot = footer or ""
    return f"""<div class="summary-card">
  <div class="summary-header"><span class="summary-icon">{icon}</span><span class="summary-title">{name}</span></div>
  <div class="summary-content">{rows_html}{foot}</div>
</div>"""


def card_user(icon, card_title, body, badge="", extra_class="", footer=""):
    badge_html = f'<span class="status-badge {badge}">{badge}</span>' if badge and badge.startswith("status-") else (f'<span class="card-badge">{badge}</span>' if badge else "")
    if badge and not badge.startswith("status-") and "status-" in badge:
        badge_html = f'<span class="status-badge {badge.split()[0] if " " in badge else badge}">{badge.split()[-1] if " " in badge else badge}</span>'
    # simplify badge
    badge_html = ""
    if badge:
        if badge in ("Attiva", "Attivo"):
            badge_html = '<span class="status-badge status-active">Attiva</span>'
        elif badge in ("Scaduta", "Scaduto"):
            badge_html = '<span class="status-badge status-expired">Scaduta</span>'
        elif badge == "confirmed":
            badge_html = '<span class="status-badge status-confirmed">✅ Confermato</span>'
        elif badge == "pending":
            badge_html = '<span class="status-badge status-pending">⏳ In Attesa</span>'
        elif badge == "completed":
            badge_html = '<span class="status-badge status-completed">✔️ Completato</span>'
        elif badge == "cancelled":
            badge_html = '<span class="status-badge status-cancelled">❌ Annullato</span>'
        elif badge == "past":
            badge_html = '<span class="status-badge status-past">📅 Passato</span>'
        else:
            badge_html = f'<span class="card-badge">{badge}</span>'

    return f"""<div class="card-user {extra_class}">
  <div class="card-header">
    <div style="display:flex;align-items:center"><span class="card-icon">{icon}</span><span class="card-title">{card_title}</span></div>
    {badge_html}
  </div>
  <div class="card-body">{body}</div>
  {footer}
</div>"""


def section_divider(text):
    return f'<div class="section-divider"><div class="divider-line"></div><h2 class="section-title">{text}</h2><div class="divider-line"></div></div>'


def form_select(name, label, options, required=False):
    req = " required" if required else ""
    opts = "".join(f'<option value="{v}">{t}</option>' for v, t in options)
    return f"""<div class="form-group">
  <label for="{name}" class="card-label" style="display:block;margin-bottom:0.5rem">{label}</label>
  <select id="{name}" name="{name}" class="btn-user" style="width:100%;text-align:left"{req}>{opts}</select>
</div>"""


PAGES = {}

# ── Dashboard ──
PAGES["index.html"] = wrap(
    "Dashboard",
    "home",
    title("📊 La Tua Dashboard")
    + '<p class="motto">Non Diamo Pillole, Non Diamo Consigli, Diamo Risultati</p>'
    + '<div class="quick-links-user">'
    + '<a href="diete-lista.html" class="quick-link-btn"><span>🥗</span>Diete</a>'
    + '<a href="allenamenti-lista.html" class="quick-link-btn"><span>🏋️</span>Allenamenti</a>'
    + '<a href="documenti-lista.html" class="quick-link-btn"><span>📄</span>Documenti</a>'
    + '<a href="listino.html" class="quick-link-btn"><span>💰</span>Listino</a>'
    + "</div>"
    + summary_card("🥗", "Dieta Attuale", [
        ("Periodo:", "01/06/2026 - 30/06/2026"),
        ("Calorie:", "1800 kcal/giorno"),
    ], '<a href="diete-lista.html" class="btn-user btn-user-small mt-2">📄 Apri PDF Dieta</a>')
    + summary_card("🏋️", "Allenamento Attuale", [
        ("Periodo:", "01/06/2026 - 30/06/2026"),
        ("Note:", "Push/Pull/Legs 3x"),
    ], '<a href="allenamenti-lista.html" class="btn-user btn-user-small mt-2">📄 Apri PDF Allenamento</a>')
    + summary_card("⚖️", "Peso Attuale", [
        ("Data Check:", "10/06/2026"),
        ("Peso:", "78.2 kg"),
        ("Aderenza:", "85%"),
        ("Peso Iniziale:", "82 kg"),
        ("Differenza:", '<span style="color:#4caf50">-3.8 kg</span>'),
    ], '<a href="progressi-lista.html" class="btn-user btn-user-small mt-2">📈 Vedi progressi</a>')
    + summary_card("📅", "Prossimo Appuntamento", [
        ("Data:", "28/06/2026 alle 10:00"),
        ("Tipo:", "Check"),
    ], '<a href="appuntamenti-lista.html" class="btn-user btn-user-small mt-2">📅 I miei appuntamenti</a>'),
)

# ── Profilo ──
PAGES["profilo.html"] = wrap(
    "Profilo",
    "profilo",
    title("👤 Il Mio Profilo")
    + card_user("📋", "Dati Anagrafici", card_info("Nome", "Marco Rossi") + card_info("Data di Nascita", "15/03/1985") + card_info("Sesso", "M") + card_info("Telefono", "+39 333 123 4567"))
    + card_user("📏", "Dati Fisici", card_info("Altezza", "178 cm") + card_info("Peso Iniziale", "82 kg"))
    + card_user("🩺", "Informazioni Mediche", card_info("Intolleranze", "Lattosio") + card_info("Cibi da Evitare", "—") + card_info("Patologie", "—"))
    + card_user("🏃", "Attività Fisica", card_info("Descrizione", "3x/sett palestra"))
    + '<div class="quick-links-user">'
    + '<a href="documenti-lista.html" class="quick-link-btn"><span>📄</span>Documenti</a>'
    + '<a href="listino.html" class="quick-link-btn"><span>💰</span>Listino</a>'
    + "</div>"
    + '<div class="divider"></div>'
    + '<a href="#" class="btn-user btn-user-secondary" data-logout>🚪 Esci</a>',
)

# ── Progressi ──
PAGES["progressi-lista.html"] = wrap(
    "Progressi",
    "progressi",
    title("📈 I Miei Progressi")
    + '<div class="mb-2 text-center"><a href="progresso-nuovo.html" class="btn-nuovo-check">➕ Inserisci Nuovo Check</a></div>'
    + section_divider("🏥 Check del Dottor MyNutriApp")
    + card_user("🏥", "Check Nutrizionista 10/06/2026", '<div class="text-center"><a href="dettaglio-check-nutrizionista.html" class="btn-dettaglio">Visualizza Dettagli</a></div>', extra_class="card-nutrizionista")
    + card_user("🏥", "Check Nutrizionista 10/04/2026", '<div class="text-center"><a href="dettaglio-check-nutrizionista.html" class="btn-dettaglio">Visualizza Dettagli</a></div>', extra_class="card-nutrizionista")
    + section_divider("👤 I Miei Check")
    + card_user("⚖️", "Il Mio Check 05/06/2026", '<div class="text-center"><a href="dettaglio-check-paziente.html" class="btn-dettaglio">Visualizza Dettagli</a></div>')
    + card_user("⚖️", "Il Mio Check 22/05/2026", '<div class="text-center"><a href="dettaglio-check-paziente.html" class="btn-dettaglio">Visualizza Dettagli</a></div>'),
)

PAGES["progresso-nuovo.html"] = wrap(
    "Nuovo Check",
    "progressi",
    title("📊 Nuovo Check Progresso")
    + """<form class="card-user" data-mock data-success="Check salvato (simulazione)." data-redirect="progressi-lista.html">
  <div class="card-body">"""
    + """<div class="form-group">
  <label for="peso_settimanale" class="card-label" style="display:block;margin-bottom:0.5rem">Peso Attuale (kg) *</label>
  <input type="number" step="0.1" id="peso_settimanale" name="peso_settimanale" class="btn-user" style="width:100%;text-align:center;font-size:1.5rem;font-weight:700;color:#ff751f" placeholder="Es: 75.5" required>
</div>"""
    + form_select("aderenza", "Aderenza alla Dieta (1-10, opzionale)", [("", "Seleziona..."), ("10", "10 - Perfetta"), ("8", "8 - Molto Buona"), ("6", "6 - Discreta"), ("4", "4 - Mediocre")])
    + form_select("frequenza_allenamenti", "Allenamenti questa Settimana", [("", "Seleziona..."), ("0", "0 volte"), ("2", "2 volte"), ("3", "3 volte"), ("5+", "5+ volte")])
    + """</div>
  <div style="display:flex;gap:0.5rem;margin-top:1rem">
    <button type="submit" class="btn-user" style="flex:1">💾 Salva Check</button>
    <a href="progressi-lista.html" class="btn-user btn-user-secondary" style="flex:1">↩️ Annulla</a>
  </div>
</form>""",
)

def check_detail_page(kind):
    if kind == "paziente":
        nav_title = "Il Mio Check"
        sections = """<div class="check-section"><h2 class="section-title">I Tuoi Dati</h2><div class="data-grid">
<div class="data-card"><span class="data-icon">⚖️</span><div><div class="data-label">Peso</div><div class="data-value">77.8 kg</div></div></div>
<div class="data-card"><span class="data-icon">📊</span><div><div class="data-label">Aderenza</div><div class="data-value">8/10</div></div></div>
<div class="data-card"><span class="data-icon">🏋️</span><div><div class="data-label">Allenamenti</div><div class="data-value">3 volte</div></div></div>
</div></div>"""
    else:
        nav_title = "Check Nutrizionista"
        sections = """<div class="check-section"><h2 class="section-title">Dati Base del Check</h2><div class="data-grid">
<div class="data-card"><span class="data-icon">⚖️</span><div><div class="data-label">Peso</div><div class="data-value">78.2 kg</div></div></div>
<div class="data-card"><span class="data-icon">📊</span><div><div class="data-label">Aderenza</div><div class="data-value">85%</div></div></div>
<div class="data-card"><span class="data-icon">🏋️</span><div><div class="data-label">Allenamenti</div><div class="data-value">3/sett</div></div></div>
</div></div>
<div class="check-section"><h2 class="section-title">Misure Antropometriche</h2><div class="data-grid">
<div class="data-card"><span class="data-icon">🩲</span><div><div class="data-label">Vita</div><div class="data-value">82 cm</div></div></div>
<div class="data-card"><span class="data-icon">🦵</span><div><div class="data-label">Fianchi</div><div class="data-value">98 cm</div></div></div>
<div class="data-card"><span class="data-icon">📏</span><div><div class="data-label">Plica addome</div><div class="data-value">18 mm</div></div></div>
</div></div>
<div class="check-section"><h2 class="section-title">Composizione Corporea</h2><div class="data-grid">
<div class="data-card"><span class="data-icon">🩸</span><div><div class="data-label">Grasso corporeo</div><div class="data-value">18.5%</div></div></div>
<div class="data-card"><span class="data-icon">💪</span><div><div class="data-label">Massa muscolare</div><div class="data-value">62.3 kg</div></div></div>
<div class="data-card"><span class="data-icon">📊</span><div><div class="data-label">BMI</div><div class="data-value">24.7</div></div></div>
</div><div class="note-section"><h3 class="note-title">Note</h3><p class="note-text">Ottimi progressi, continua così!</p></div></div>"""

    return wrap(
        "Dettaglio Check",
        "progressi",
        f"""<div class="check-header">
  <h1>{nav_title}</h1>
  <p class="text-muted" style="margin-top:0.35rem">05/06/2026</p>
</div>
<a href="progressi-lista.html" class="btn-user btn-user-secondary mb-2">← Torna ai Progressi</a>
{sections}""",
    )

PAGES["dettaglio-check-paziente.html"] = check_detail_page("paziente")
PAGES["dettaglio-check-nutrizionista.html"] = check_detail_page("nutrizionista")

# ── Appuntamenti ──
def appointment_card(tipo, date, time, note, status):
    body = card_info("📅 Data", date) + card_info("🕐 Ora", time)
    if note:
        body += card_info("💬 Note", note)
    extra = ""
    if status == "completed":
        extra = "card-completato"
    elif status == "past":
        extra = "card-passato"
    return card_user("🗓️", tipo, body, badge=status, extra_class=extra)

PAGES["appuntamenti-lista.html"] = wrap(
    "Appuntamenti",
    "prenota",
    title("📅 I Miei Appuntamenti")
    + '<div class="mb-2 text-center"><a href="appuntamento-prenota.html" class="btn-nuovo-appuntamento">➕ Prenota Nuovo Appuntamento</a></div>'
    + section_divider("🕐 Prossimi Appuntamenti")
    + appointment_card("Check", "28/06/2026", "10:00", "Porta referto recente", "pending")
    + appointment_card("Rinnovo Dieta", "15/07/2026", "11:30", "", "confirmed")
    + section_divider("✅ Appuntamenti Completati")
    + appointment_card("Prima Visita", "10/01/2024", "09:00", "", "completed")
    + section_divider("📜 Altri Appuntamenti Passati")
    + appointment_card("Check", "10/03/2026", "14:00", "", "past"),
)

PAGES["appuntamento-prenota.html"] = wrap(
    "Prenota Appuntamento",
    "prenota",
    title("📅 Prenota Appuntamento")
    + """<form class="card-user" data-mock data-success="Appuntamento prenotato (simulazione)." data-redirect="appuntamenti-lista.html">
  <div class="card-body">"""
    + form_select("data_appuntamento", "Scegli Data e Ora *", [("", "Seleziona uno slot..."), ("2026-06-28T10:00", "📅 28/06/2026 — 10:00"), ("2026-07-02T15:00", "📅 02/07/2026 — 15:00"), ("2026-07-05T09:30", "📅 05/07/2026 — 09:30")], required=True)
    + form_select("tipo", "Tipo Appuntamento *", [("", "Seleziona tipo..."), ("allenamento_1to1", "💪 Allenamento 1to1"), ("rinnovo_dieta", "🍽️ Rinnovo Dieta"), ("check", "✅ Check"), ("altro", "📌 Altro")], required=True)
    + """<div class="form-group">
  <label for="note" class="card-label" style="display:block;margin-bottom:0.5rem">Note (opzionale)</label>
  <textarea id="note" name="note" class="btn-user" style="width:100%;min-height:80px;text-align:left;font-size:0.9rem;padding:0.75rem" placeholder="Es: Ho bisogno di aggiornare la dieta..."></textarea>
</div></div>
  <div style="display:flex;gap:0.5rem;margin-top:1rem">
    <button type="submit" class="btn-user" style="flex:1">✅ Prenota Appuntamento</button>
    <a href="appuntamenti-lista.html" class="btn-user btn-user-secondary" style="flex:1">↩️ Annulla</a>
  </div>
</form>""",
)

# ── Diete & Allenamenti ──
PAGES["diete-lista.html"] = wrap(
    "Le Mie Diete",
    "home",
    title("🥗 Le Mie Diete")
    + card_user("🍽️", "Dieta 1", card_info("Data Inizio", "01/06/2026") + card_info("Data Fine", "30/06/2026") + card_info("Calorie", "1800 kcal/giorno") + card_info("Carboidrati", "40%") + card_info("Proteine", "30%") + card_info("Grassi", "30%"), badge="Attiva", footer='<a href="#" class="btn-user mt-2">📄 Apri PDF Dieta</a>')
    + card_user("🍽️", "Dieta 2", card_info("Data Inizio", "01/05/2026") + card_info("Data Fine", "31/05/2026") + card_info("Calorie", "1900 kcal/giorno"), badge="Scaduta", footer='<a href="#" class="btn-user mt-2">📄 Apri PDF Dieta</a>'),
)

PAGES["allenamenti-lista.html"] = wrap(
    "I Miei Allenamenti",
    "home",
    title("🏋️ I Miei Allenamenti")
    + card_user("💪", "Allenamento 1", card_info("Data Inizio", "01/06/2026") + card_info("Data Fine", "30/06/2026") + card_info("Note", "Push/Pull/Legs"), badge="Attivo", footer='<a href="#" class="btn-user mt-2">📄 Apri PDF Allenamento</a>')
    + card_user("💪", "Allenamento 2", card_info("Data Inizio", "01/04/2026") + card_info("Data Fine", "31/05/2026") + card_info("Note", "Full body 3x"), badge="Scaduto", footer='<a href="#" class="btn-user mt-2">📄 Apri PDF Allenamento</a>'),
)

# ── Documenti ──
PAGES["documenti-lista.html"] = wrap(
    "Documenti",
    "profilo",
    title("📄 I Miei Documenti")
    + '<div class="mb-2"><a href="documento-nuovo.html" class="btn-user">➕ Carica Nuovo Documento</a></div>'
    + card_user("🩸", "Analisi", card_info("Descrizione", "Analisi sangue giugno 2026") + card_info("Caricato il", "05/06/2026 alle 14:30"), badge="05/06/2026", footer="""<div style="display:flex;gap:0.5rem;margin-top:1rem">
  <a href="#" class="btn-user btn-user-small" style="flex:1">👁️ Visualizza</a>
  <button type="button" class="btn-user btn-user-secondary btn-user-small" style="flex:1" data-confirm="Eliminare questo documento?">🗑️ Elimina</button>
</div>""")
    + card_user("📋", "Referto", card_info("Descrizione", "Certificato intolleranza lattosio") + card_info("Caricato il", "12/01/2024 alle 10:00"), badge="12/01/2024", footer="""<div style="display:flex;gap:0.5rem;margin-top:1rem">
  <a href="#" class="btn-user btn-user-small" style="flex:1">👁️ Visualizza</a>
  <button type="button" class="btn-user btn-user-secondary btn-user-small" style="flex:1" data-confirm="Eliminare questo documento?">🗑️ Elimina</button>
</div>"""),
)

PAGES["documento-nuovo.html"] = wrap(
    "Carica Documento",
    "profilo",
    title("📤 Carica Documento")
    + """<form class="card-user" data-mock data-success="Documento caricato (simulazione)." data-redirect="documenti-lista.html">
  <div class="card-body">"""
    + form_select("tipo", "Tipo Documento", [("", "Seleziona tipo..."), ("analisi", "🩸 Analisi del Sangue"), ("referto", "📋 Referto Medico"), ("pdf_altro", "📄 Altro Documento")], required=True)
    + """<div class="form-group">
  <label for="descrizione" class="card-label" style="display:block;margin-bottom:0.5rem">Descrizione (opzionale)</label>
  <textarea id="descrizione" name="descrizione" class="btn-user" style="width:100%;min-height:80px;text-align:left;font-size:0.9rem;padding:0.75rem" placeholder="Es: Analisi del sangue giugno 2026"></textarea>
</div>
<div class="form-group">
  <label for="file" class="card-label" style="display:block;margin-bottom:0.5rem">File (PDF, JPG, PNG)</label>
  <input type="file" id="file" name="file" accept=".pdf,.jpg,.jpeg,.png" class="btn-user" style="width:100%;padding:0.75rem;font-size:0.85rem" required>
</div></div>
  <div style="display:flex;gap:0.5rem;margin-top:1rem">
    <button type="submit" class="btn-user" style="flex:1">💾 Carica Documento</button>
    <a href="documenti-lista.html" class="btn-user btn-user-secondary" style="flex:1">↩️ Annulla</a>
  </div>
</form>
<div class="card-user card-highlight" style="margin-top:1rem">
  <div class="card-body">
    <p class="card-label" style="margin-bottom:0.5rem">💡 Suggerimento</p>
    <p class="card-value" style="font-size:0.85rem;line-height:1.5">Carica esami del sangue, certificati di intolleranze o altri documenti medici. Il tuo nutrizionista potrà visualizzarli.</p>
  </div>
</div>""",
)

# ── Listino ──
def listino_product(icon, name, duration, checks, note, price, featured=False):
    extra = " card-featured" if featured else ""
    body = card_info("Durata", duration)
    if checks:
        body += card_info("Check Inclusi", checks)
    if note:
        body += card_info("Dettagli", note)
    body += f'<div class="price-display">{price}</div>'
    badge = "⭐ PIÙ SCELTO" if "PIÙ SCELTO" in name.upper() or featured else ""
    return card_user(icon, name, body, badge=badge, extra_class=extra)

PAGES["listino.html"] = wrap(
    "Listino Prezzi",
    "profilo",
    title("💰 Listino Prezzi")
    + '<h2 class="section-title">🥗 Piano Nutrizionale</h2>'
    + listino_product("🥗", "Pacchetto 3 Mesi — IL PIÙ SCELTO", "3 mesi", "6 check", "Dieta personalizzata + follow-up", "450€", featured=True)
    + listino_product("🥗", "Prima Visita + Dieta", "1 mese", "1 check", "Prima consulenza completa", "120€")
    + '<div class="divider"></div><h2 class="section-title">🏋️ Piano di Allenamento</h2>'
    + listino_product("💪", "Scheda 3 Mesi", "3 mesi", "", "Piano fitness personalizzato", "200€")
    + '<div class="divider"></div><h2 class="section-title">🌟 Piano Completo</h2>'
    + listino_product("🌟", "Nutrizione + Allenamento", "3 mesi", "8 check", "Pacchetto totale", "580€", featured=True)
    + '<div class="divider"></div><h2 class="section-title">💪 Allenamento 1 to 1</h2>'
    + listino_product("💪", "Sessione singola", "1 allenamento", "", "Con il nutrizionista", "60€")
    + """<div class="card-user card-highlight" style="margin-top:1.5rem">
  <div class="card-body">
    <p class="card-label" style="margin-bottom:0.75rem;font-size:1rem;color:#ff751f">✨ Tutti i piani includono:</p>
    <div style="display:flex;flex-direction:column;gap:0.5rem;font-size:0.9rem">
      <div>💬 Follow up via WhatsApp</div>
      <div>🎯 Supporto e motivazione continua</div>
      <div>📹 Possibilità di video-call di aggiornamento</div>
    </div>
  </div>
</div>
<p class="text-center text-muted mt-2" style="font-size:0.9rem">Per maggiori informazioni contatta il tuo nutrizionista!</p>""",
)


def main():
    import sys
    sys.path.insert(0, str(OUT.parent))
    from spa_builder import build_spa_html

    css = (OUT / "user.css").read_text(encoding="utf-8")
    js = (OUT / "user.js").read_text(encoding="utf-8")
    fonts = (
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Adam+Script&display=swap" rel="stylesheet">'
    )
    html = build_spa_html(
        pages=PAGES,
        css=css,
        js=js,
        fonts_link=fonts,
        app_title="NutriApp",
        main_class="user-content content-main",
        home_id="home",
        viewport="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover",
        extra_head='<meta name="theme-color" content="#ff751f">',
        shell_before_main='  <div id="site-header"></div>\n  <div class="content-wrapper">',
        shell_after_main="  </div>\n  <div id=\"site-bottom-nav\"></div>",
        inner_main_footer='    <div id="site-powered"></div>',
    )
    out = OUT.parent / "mynutriapp-user.html"
    out.write_text(html, encoding="utf-8")
    print(f"  ✓ {out.name} ({len(PAGES)} schermate)")
    print(f"\nFile unico generato: {out}")


if __name__ == "__main__":
    main()
