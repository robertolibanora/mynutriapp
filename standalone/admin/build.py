#!/usr/bin/env python3
"""Genera le pagine HTML standalone dell'admin MyNutriAPP."""

from pathlib import Path

OUT = Path(__file__).parent

HEAD = """<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — MyNutriAPP</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Playfair+Display:wght@600;700&family=Adam+Script&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="admin.css">
</head>
<body data-nav="{nav}">
  <div id="site-nav"></div>
  <main class="content">
{content}
  </main>
  <div id="site-footer"></div>
  <script src="admin.js"></script>
{extra}
</body>
</html>"""


def wrap(title, nav, content, extra=""):
    indented = "\n".join("    " + line if line else "" for line in content.strip().split("\n"))
    return HEAD.format(title=title, nav=nav, content=indented, extra=extra)


def header(title, subtitle, extra_right="", variant="orange"):
    border = "rgba(255, 117, 31, 0.2)" if variant == "orange" else "rgba(76, 175, 80, 0.2)"
    bg = "rgba(255, 117, 31, 0.1)" if variant == "orange" else "rgba(76, 175, 80, 0.1)"
    hcolor = "#ff751f" if variant == "orange" else "#ffffff"
    return f"""
<header class="page-header" style="background:linear-gradient(135deg,{bg},rgba(13,51,28,0.35));border-color:{border}">
  <div class="page-header-inner">
    <div>
      <h1 style="color:{hcolor}">{title}</h1>
      <p class="subtitle">{subtitle}</p>
    </div>
    {extra_right}
  </div>
</header>"""


def date_block():
    return """<div class="date-block">
      <div class="date live-date"></div>
      <div class="time live-time"></div>
    </div>"""


def breadcrumb(*items):
    parts = []
    for i, (label, href) in enumerate(items):
        if href and i < len(items) - 1:
            parts.append(f'<a href="{href}">{label}</a>')
        else:
            parts.append(f"<span>{label}</span>")
    return '<nav class="breadcrumb">' + " › ".join(parts) + "</nav>"


def stat_cards(items):
    colors = {"green": "stat-card--green", "blue": "stat-card--blue", "purple": "stat-card--purple", "yellow": "stat-card--yellow"}
    cards = []
    for icon, value, label, footer, color in items:
        cls = colors.get(color, "stat-card--green")
        foot = f'<div class="stat-card-footer">{footer}</div>' if footer else ""
        cards.append(f"""
<article class="stat-card {cls}">
  <span class="watermark" aria-hidden="true">{icon}</span>
  <div class="stat-card-top">
    <div><div class="stat-value">{value}</div><div class="stat-label">{label}</div></div>
    <span class="stat-icon">{icon}</span>
  </div>
  {foot}
</article>""")
    return f'<div class="stats-grid">{"".join(cards)}</div>'


def toolbar(actions, search=False):
    btns = "".join(f'<a href="{h}" class="btn {c}">{t}</a>' for h, c, t in actions)
    search_html = ""
    if search:
        search_html = """
<div class="search-group">
  <label for="search">🔍</label>
  <input type="search" id="search" class="search-input" placeholder="Cerca...">
  <button type="button" class="btn btn-white btn-small">Cerca</button>
</div>"""
    return f'<div class="toolbar"><div class="toolbar-actions">{btns}</div>{search_html}</div>'


def form_group(label, name, ftype="text", **kwargs):
    attrs = " ".join(f'{k}="{v}"' for k, v in kwargs.items())
    if ftype == "select":
        options = kwargs.pop("options", [])
        opts = "".join(f'<option value="{v}">{t}</option>' for v, t in options)
        return f'<div class="form-group"><label for="{name}">{label}</label><select id="{name}" name="{name}" class="input-select" {attrs}>{opts}</select></div>'
    if ftype == "textarea":
        return f'<div class="form-group"><label for="{name}">{label}</label><textarea id="{name}" name="{name}" class="input-text" {attrs}></textarea></div>'
    return f'<div class="form-group"><label for="{name}">{label}</label><input type="{ftype}" id="{name}" name="{name}" class="input-text" {attrs}></div>'


def form_actions(submit, cancel_href, submit_label="💾 Salva"):
    return f"""<div class="form-actions">
  <button type="submit" class="btn btn-primary">{submit_label}</button>
  <a href="{cancel_href}" class="btn btn-secondary">↩️ Annulla</a>
</div>"""


def table(headers, rows):
    th = "".join(f"<th>{h}</th>" for h in headers)
    trs = []
    for row in rows:
        tds = "".join(f"<td>{c}</td>" for c in row)
        trs.append(f"<tr>{tds}</tr>")
    return f'<div class="table-wrap"><table class="table"><thead><tr>{th}</tr></thead><tbody>{"".join(trs)}</tbody></table></div>'


PAGES = {}

# ── Dashboard ──
PAGES["index.html"] = wrap(
    "Dashboard Admin",
    "dashboard",
    header("👋 Benvenuto, Enrico!", "Dashboard di controllo del tuo studio nutrizionale", date_block())
    + '<p class="tagline" style="color:var(--orange);font-family:\'Adam Script\',cursive;font-size:1.25rem;margin:-1rem 0 1.5rem">Non Diamo Pillole, Non Diamo Consigli, Diamo Risultati</p>'
    + '<h2 class="section-title">📊 Panoramica Oggi</h2>'
    + stat_cards([
        ("👥", "48", "Pazienti Totali", '<a href="pazienti-lista.html">👁️ Visualizza tutti</a>', "green"),
        ("📅", "5", "Appuntamenti Oggi", "📊 18 questa settimana", "blue"),
        ("💰", "3.240€", "Entrate Mese", '<a href="economia.html">📊 Dettagli vendite</a>', "purple"),
        ("⏰", "12", "Slot Disponibili", '<a href="agenda-unificata.html">⚡ Gestisci slot</a>', "yellow"),
    ])
    + '<div class="grid-2">'
    + """<section class="card"><div class="card-header"><h3>📅 Appuntamenti di oggi</h3><a href="agenda-unificata.html" class="btn btn-ghost btn-small">Vedi agenda</a></div>
<ul class="appointment-list">
<li class="appointment-item appointment-item--done"><span class="appointment-time">08:30</span><div class="appointment-info"><div class="appointment-name">Marco Rossi</div><div class="appointment-type">Controllo mensile</div></div><span class="badge badge-success">Fatto</span></li>
<li class="appointment-item"><span class="appointment-time">10:00</span><div class="appointment-info"><div class="appointment-name">Laura Bianchi</div><div class="appointment-type">Prima visita</div></div><span class="badge badge-info">In arrivo</span></li>
</ul></section>"""
    + """<section class="card"><div class="card-header"><h3>🔔 Attività recente</h3></div>
<ul class="activity-list">
<li class="activity-item"><span class="activity-dot activity-dot--green"></span><div><div class="activity-text"><strong>Marco Rossi</strong> ha caricato un progresso</div><div class="activity-meta">Oggi, 08:15</div></div></li>
<li class="activity-item"><span class="activity-dot activity-dot--orange"></span><div><div class="activity-text">Nuova vendita: Pacchetto 3 mesi — 450€</div><div class="activity-meta">Ieri, 17:42</div></div></li>
</ul></section></div>"""
    + toolbar([("pazienti-lista.html", "btn-primary", "➕ Gestisci Pazienti"), ("economia.html", "btn-white", "💰 Economia")]),
)

# ── Pazienti ──
PAGES["pazienti-lista.html"] = wrap(
    "Gestione Pazienti", "pazienti",
    header("👥 Gestione Pazienti", "Visualizza e gestisci tutti i tuoi pazienti", '<div class="date-block"><div class="date" style="color:var(--green);font-weight:700">48 Pazienti</div></div>')
    + stat_cards([("👥", "48", "Pazienti Totali", "", "green"), ("🥗", "62", "Diete Totali", "", "blue"), ("🏋️", "38", "Allenamenti", "", "yellow"), ("📈", "156", "Progressi", "", "purple")])
    + toolbar([("paziente-nuovo.html", "btn-primary", "➕ Nuovo Paziente"), ("scadenze.html", "btn-white", "⏰ Scadenze")], search=True)
    + """<div class="patients-grid">
<div class="patient-card" data-href="paziente-dettaglio.html"><div class="patient-card-header"><span class="avatar">MR</span><div><strong>Marco Rossi</strong><div class="patient-meta">📱 +39 333 123 4567</div></div></div>
<div class="patient-meta">🥗 3 diete · 🏋️ 2 allenamenti · 📈 8 progressi</div>
<div class="action-buttons" style="margin-top:0.75rem"><a href="paziente-dettaglio.html" class="btn btn-secondary btn-small">Dettaglio</a><a href="paziente-modifica.html" class="btn btn-white btn-small">Modifica</a><button class="btn btn-danger btn-small" data-confirm="Eliminare Marco Rossi?">Elimina</button></div></div>
<div class="patient-card" data-href="paziente-dettaglio.html"><div class="patient-card-header"><span class="avatar">LB</span><div><strong>Laura Bianchi</strong><div class="patient-meta">📱 +39 340 987 6543</div></div></div>
<div class="patient-meta">🥗 1 dieta · 🏋️ 0 allenamenti · 📈 2 progressi</div>
<div class="action-buttons" style="margin-top:0.75rem"><a href="paziente-dettaglio.html" class="btn btn-secondary btn-small">Dettaglio</a><a href="paziente-modifica.html" class="btn btn-white btn-small">Modifica</a></div></div>
<div class="patient-card" data-href="paziente-dettaglio.html"><div class="patient-card-header"><span class="avatar">GV</span><div><strong>Giulia Verdi</strong><div class="patient-meta">📱 +39 328 555 1212</div></div></div>
<div class="patient-meta">🥗 2 diete · 🏋️ 1 allenamento · 📈 5 progressi</div>
<div class="action-buttons" style="margin-top:0.75rem"><a href="paziente-dettaglio.html" class="btn btn-secondary btn-small">Dettaglio</a><a href="paziente-modifica.html" class="btn btn-white btn-small">Modifica</a></div></div>
</div>""",
)

PAGES["paziente-nuovo.html"] = wrap(
    "Nuovo Paziente", "pazienti",
    breadcrumb(("Pazienti", "pazienti-lista.html"), ("Nuovo", None))
    + '<h2 class="page-title">➕ Registra Nuovo Paziente</h2>'
    + """<form class="form-container" data-mock data-success="Paziente registrato (simulazione).">
<h3 class="form-section-title">👤 Dati Personali</h3><div class="form-grid">"""
    + form_group("📝 Nome *", "nome", required="", placeholder="Es: Mario")
    + form_group("📝 Cognome *", "cognome", required="", placeholder="Es: Rossi")
    + form_group("📱 Telefono *", "telefono", "tel", required="", placeholder="3331234567")
    + form_group("🔐 Password *", "password", "password", required="", placeholder="Minimo 6 caratteri")
    + form_group("📅 Data di Nascita *", "data_nascita", "date", required="")
    + form_group("👤 Sesso *", "sesso", "select", required="", options=[("", "Seleziona"), ("M", "Maschio"), ("F", "Femmina"), ("Altro", "Altro")])
    + """</div><h3 class="form-section-title">⚖️ Dati Fisici</h3><div class="form-grid">"""
    + form_group("📏 Altezza (cm) *", "altezza_cm", "number", required="", min="100", max="250", placeholder="175")
    + form_group("⚖️ Peso Iniziale (kg) *", "peso_iniziale", "number", required="", step="0.1", placeholder="75.5")
    + "</div>" + form_actions(True, "pazienti-lista.html", "💾 Registra Paziente") + "</form>",
)

PAGES["paziente-modifica.html"] = wrap(
    "Modifica Paziente", "pazienti",
    breadcrumb(("Pazienti", "pazienti-lista.html"), ("Marco Rossi", "paziente-dettaglio.html"), ("Modifica", None))
    + '<h2 class="page-title">✏️ Modifica Paziente — Marco Rossi</h2>'
    + """<form class="form-container" data-mock data-success="Dati paziente aggiornati (simulazione).">
<h3 class="form-section-title">👤 Dati Anagrafici</h3><div class="form-grid">"""
    + form_group("Nome", "nome", value="Marco")
    + form_group("Cognome", "cognome", value="Rossi")
    + form_group("Telefono", "telefono", "tel", value="+393331234567")
    + form_group("Password", "password", value="marco2024")
    + form_group("Data nascita", "data_nascita", "date", value="1985-03-15")
    + form_group("Sesso", "sesso", "select", options=[("M", "Maschio"), ("F", "Femmina")])
    + form_group("Altezza (cm)", "altezza_cm", "number", value="178")
    + form_group("Peso iniziale (kg)", "peso_iniziale", "number", value="82", step="0.1")
    + """</div><h3 class="form-section-title">🏥 Informazioni Mediche</h3><div class="form-grid">"""
    + form_group("Intolleranze", "intolleranze", "textarea", placeholder="Lattosio...")
    + form_group("Cibi da evitare", "cibi_da_ev", "textarea")
    + form_group("Patologie", "patologie", "textarea")
    + form_group("Esami biochimici", "esami_biochimici", "textarea")
    + """</div><h3 class="form-section-title">🏋️ Attività Fisica</h3>"""
    + form_group("Descrizione allenamenti", "allenamenti_descr", "textarea", placeholder="3x settimana palestra...")
    + form_actions(True, "paziente-dettaglio.html", "💾 Salva Modifiche") + "</form>",
)

PAGES["paziente-dettaglio.html"] = wrap(
    "Dettaglio Paziente", "pazienti",
    """<div class="patient-header"><div class="patient-header-inner">
<div class="patient-identity"><span class="avatar-lg">MR</span><div>
<h1>Marco Rossi</h1><p class="subtitle">📱 +39 333 123 4567</p><p style="color:var(--green);font-size:0.9rem">📅 Registrato il 12/01/2024</p></div></div>
<div class="action-buttons">
<a href="check-completo.html" class="btn btn-primary" style="background:var(--green)">🏥 Check Nutrizionista</a>
<a href="paziente-modifica.html" class="btn btn-primary">✏️ Modifica Dati</a>
<a href="pazienti-lista.html" class="btn btn-secondary">← Torna alla Lista</a>
</div></div></div>"""
    + """<div class="alert-card urgent"><strong>🔥 Scadenza imminente</strong> — Pacchetto nutrizionale scade tra 5 giorni.</div>"""
    + """<div class="content-card" style="margin-bottom:1.25rem"><h3>📊 Stato Profilo</h3><p class="subtitle">Profilo completo con informazioni mediche per piani personalizzati.</p><span class="badge badge-success">✅ Completo</span></div>"""
    + """<div class="quick-links-grid">
<a href="diete-paziente.html" class="quick-link-card"><div class="icon">🥗</div><strong>Diete</strong><div class="patient-meta">3 piani alimentari</div></a>
<a href="allenamenti-paziente.html" class="quick-link-card"><div class="icon">🏋️</div><strong>Allenamenti</strong><div class="patient-meta">2 piani fitness</div></a>
<a href="progressi-paziente.html" class="quick-link-card"><div class="icon">📈</div><strong>Progressi</strong><div class="patient-meta">8 check registrati</div></a>
<a href="documenti-paziente.html" class="quick-link-card"><div class="icon">📄</div><strong>Documenti</strong><div class="patient-meta">4 file caricati</div></a>
<a href="registro-economico-paziente.html" class="quick-link-card"><div class="icon">💰</div><strong>Economia</strong><div class="patient-meta">2 pacchetti acquistati</div></a>
</div>"""
    + """<div class="content-grid-2">
<div class="content-card"><h3>👤 Dati Anagrafici</h3><div class="info-list">
<div class="info-row"><span class="label">Telefono</span><span class="value">+39 333 123 4567</span></div>
<div class="info-row"><span class="label">Password</span><span class="value" style="font-family:monospace">marco2024</span></div>
<div class="info-row"><span class="label">Nascita</span><span class="value">15/03/1985</span></div>
<div class="info-row"><span class="label">Sesso</span><span class="value">M</span></div>
<div class="info-row"><span class="label">Altezza</span><span class="value">178 cm</span></div>
<div class="info-row"><span class="label">Peso iniziale</span><span class="value">82 kg</span></div>
</div></div>
<div class="content-card"><h3>🏥 Informazioni Mediche</h3><div class="info-list">
<div class="info-row"><span class="label">Intolleranze</span><span class="value">Lattosio</span></div>
<div class="info-row"><span class="label">Patologie</span><span class="value">—</span></div>
<div class="info-row"><span class="label">Allenamento</span><span class="value">3x/sett palestra</span></div>
</div></div></div>""",
)

PAGES["scadenze.html"] = wrap(
    "Scadenze Pazienti", "pazienti",
    header("⏰ Scadenze Pazienti", "Monitora pacchetti e controlli in scadenza")
    + toolbar([("pazienti-lista.html", "btn-secondary", "← Pazienti")])
    + table(["Paziente", "Tipo", "Scadenza", "Giorni", "Azioni"], [
        ["Marco Rossi", "Pacchetto 3 mesi", "28/06/2026", '<span class="badge badge-warning">5 gg</span>', '<a href="paziente-dettaglio.html" class="btn btn-small btn-secondary">Dettaglio</a>'],
        ["Giulia Verdi", "Controllo mensile", "25/06/2026", '<span class="badge badge-danger">2 gg</span>', '<a href="paziente-dettaglio.html" class="btn btn-small btn-secondary">Dettaglio</a>'],
        ["Paolo Neri", "Dieta attiva", "15/07/2026", '<span class="badge badge-success">22 gg</span>', '<a href="paziente-dettaglio.html" class="btn btn-small btn-secondary">Dettaglio</a>'],
    ]),
)

# ── Documenti, Diete, Allenamenti, Progressi ──
PAGES["documenti-paziente.html"] = wrap(
    "Documenti Paziente", "pazienti",
    breadcrumb(("Pazienti", "pazienti-lista.html"), ("Marco Rossi", "paziente-dettaglio.html"), ("Documenti", None))
    + header("📄 Documenti — Marco Rossi", "File caricati dal paziente o dallo studio", variant="green")
    + toolbar([("paziente-dettaglio.html", "btn-secondary", "← Torna al paziente")])
    + table(["Nome file", "Data", "Tipo", "Azioni"], [
        ["Referto sangue.pdf", "10/06/2026", "PDF", '<a href="#" class="btn btn-small btn-white">Apri</a> <button class="btn btn-small btn-danger" data-confirm="Eliminare?">Elimina</button>'],
        ["Foto progresso.jpg", "05/06/2026", "Immagine", '<a href="#" class="btn btn-small btn-white">Apri</a> <button class="btn btn-small btn-danger" data-confirm="Eliminare?">Elimina</button>'],
    ]),
)

PAGES["diete-paziente.html"] = wrap(
    "Diete Paziente", "pazienti",
    breadcrumb(("Marco Rossi", "paziente-dettaglio.html"), ("Diete", None))
    + header("🥗 Diete — Marco Rossi", "Storico piani alimentari", variant="green")
    + toolbar([("dieta-nuova.html", "btn-primary", "➕ Nuova Dieta"), ("paziente-dettaglio.html", "btn-secondary", "← Indietro")])
    + table(["Periodo", "Kcal", "Macro", "PDF", "Azioni"], [
        ["01/06 – 30/06/2026", "1800", "C40/P30/G30", "✅", '<a href="#" class="btn btn-small btn-white">Scarica</a>'],
        ["01/05 – 31/05/2026", "1900", "C45/P25/G30", "✅", '<a href="#" class="btn btn-small btn-white">Scarica</a>'],
    ]),
)

PAGES["dieta-nuova.html"] = wrap(
    "Nuova Dieta", "pazienti",
    breadcrumb(("Marco Rossi", "paziente-dettaglio.html"), ("Nuova dieta", None))
    + '<h2 class="page-title">🥗 Nuova Dieta — Marco Rossi</h2>'
    + """<form class="form-container" data-mock data-success="Dieta creata (simulazione)." enctype="multipart/form-data">"""
    + form_group("Data inizio", "data_inizio", "date", required="")
    + form_group("Data fine", "data_fine", "date", required="")
    + form_group("PDF dieta", "pdf", "file", accept=".pdf")
    + """<h3 class="form-section-title">Composizione nutrizionale</h3><div class="form-grid">"""
    + form_group("Kcal", "kcal", "number", placeholder="1800")
    + form_group("Carboidrati %", "carbo", "number", placeholder="40")
    + form_group("Proteine %", "proteine", "number", placeholder="30")
    + form_group("Grassi %", "grassi", "number", placeholder="30")
    + "</div>" + form_group("Note", "note", "textarea") + form_actions(True, "diete-paziente.html", "💾 Salva Dieta") + "</form>",
)

PAGES["allenamenti-paziente.html"] = wrap(
    "Allenamenti Paziente", "pazienti",
    breadcrumb(("Marco Rossi", "paziente-dettaglio.html"), ("Allenamenti", None))
    + header("🏋️ Allenamenti — Marco Rossi", "Piani fitness assegnati", variant="green")
    + toolbar([("allenamento-nuovo.html", "btn-primary", "➕ Nuovo Allenamento"), ("paziente-dettaglio.html", "btn-secondary", "← Indietro")])
    + table(["Periodo", "Note", "File", "Azioni"], [
        ["01/06 – 30/06/2026", "Push/Pull/Legs", "✅ PDF", '<a href="#" class="btn btn-small btn-white">Scarica</a>'],
        ["01/04 – 31/05/2026", "Full body 3x", "✅ PDF", '<a href="#" class="btn btn-small btn-white">Scarica</a>'],
    ]),
)

PAGES["allenamento-nuovo.html"] = wrap(
    "Nuovo Allenamento", "pazienti",
    breadcrumb(("Marco Rossi", "paziente-dettaglio.html"), ("Nuovo allenamento", None))
    + '<h2 class="page-title">🏋️ Nuovo Allenamento — Marco Rossi</h2>'
    + """<form class="form-container" data-mock data-success="Allenamento creato (simulazione).">"""
    + form_group("Data inizio", "data_inizio", "date", required="")
    + form_group("Data fine", "data_fine", "date", required="")
    + form_group("File PDF", "pdf", "file", accept=".pdf")
    + form_group("Note", "note", "textarea", placeholder="Descrizione scheda...")
    + form_actions(True, "allenamenti-paziente.html", "💾 Salva Allenamento") + "</form>",
)

PAGES["progressi-paziente.html"] = wrap(
    "Progressi Paziente", "pazienti",
    breadcrumb(("Marco Rossi", "paziente-dettaglio.html"), ("Progressi", None))
    + header("📈 Progressi — Marco Rossi", "Storico check e misurazioni", variant="green")
    + toolbar([("check-completo.html", "btn-primary", "🏥 Nuovo Check"), ("paziente-dettaglio.html", "btn-secondary", "← Indietro")])
    + table(["Data", "Peso", "Aderenza", "Grasso %", "Azioni"], [
        ["10/06/2026", "78.2 kg", "85%", "18.5%", '<a href="check-dettaglio.html" class="btn btn-small btn-secondary">Dettaglio</a> <a href="check-modifica.html" class="btn btn-small btn-white">Modifica</a>'],
        ["10/05/2026", "79.5 kg", "80%", "19.2%", '<a href="check-dettaglio.html" class="btn btn-small btn-secondary">Dettaglio</a>'],
        ["10/04/2026", "80.8 kg", "75%", "20.1%", '<a href="check-dettaglio.html" class="btn btn-small btn-secondary">Dettaglio</a>'],
    ]),
)

# ── Check nutrizionista ──
check_fields_base = """
<h3 class="form-section-title">📅 Data check</h3>""" + form_group("Data check", "data_check", "date", value="2026-06-10", required="") + """
<h3 class="form-section-title">📊 Dati base</h3><div class="form-grid">""" + (
    form_group("Peso settimanale (kg)", "peso_settimanale", "number", value="78.2", step="0.1")
    + form_group("Aderenza (%)", "aderenza", "number", value="85")
    + form_group("Freq. allenamenti", "frequenza_allenamenti", value="3/sett")
    + form_group("Foto progresso", "foto_progresso", "file", accept="image/*")
    + form_group("Check richiesta", "check_richiesta", "textarea")
) + """</div><h3 class="form-section-title">📏 Misure antropometriche</h3><div class="form-grid">""" + (
    form_group("Circonferenza vita (cm)", "circonferenza_vita", "number", value="82")
    + form_group("Circonferenza fianchi (cm)", "circonferenza_fianchi", "number", value="98")
    + form_group("Plica tricipite (mm)", "plica_tricipite", "number", value="12")
    + form_group("Plica addome (mm)", "plica_addome", "number", value="18")
) + form_group("Note misure", "note_misure", "textarea") + """</div>
<h3 class="form-section-title">🔬 Composizione corporea</h3><div class="form-grid">""" + (
    form_group("Grasso corporeo (%)", "grasso_corporeo", value="18.5")
    + form_group("Massa muscolare (kg)", "massa_muscolare", value="62.3")
    + form_group("Grasso viscerale", "grasso_viscerale", value="8")
    + form_group("TBW (%)", "tbw", value="58")
    + form_group("TMB (kcal)", "tasso_metabolico_basale", value="1680")
    + form_group("Età metabolica", "eta_metabolica", value="32")
    + form_group("BMI", "bmi", value="24.7")
) + form_group("Note composizione", "note_composizione", "textarea") + "</div>"

PAGES["check-completo.html"] = wrap(
    "Check Nutrizionista", "pazienti",
    breadcrumb(("Marco Rossi", "paziente-dettaglio.html"), ("Nuovo check", None))
    + '<h2 class="page-title">🏥 Check Nutrizionista Completo</h2>'
    + f'<form class="form-container" data-mock data-success="Check registrato (simulazione).">{check_fields_base}'
    + form_actions(True, "progressi-paziente.html", "💾 Salva Check") + "</form>",
)

PAGES["check-modifica.html"] = wrap(
    "Modifica Check", "pazienti",
    breadcrumb(("Progressi", "progressi-paziente.html"), ("Modifica check", None))
    + '<h2 class="page-title">✏️ Modifica Check — 10/06/2026</h2>'
    + f'<form class="form-container" data-mock data-success="Check aggiornato (simulazione).">{check_fields_base}'
    + form_actions(True, "check-dettaglio.html", "💾 Aggiorna Check") + "</form>",
)

PAGES["check-dettaglio.html"] = wrap(
    "Dettaglio Check", "pazienti",
    breadcrumb(("Progressi", "progressi-paziente.html"), ("Dettaglio check", None))
    + header("🏥 Check del 10/06/2026", "Marco Rossi", variant="green")
    + toolbar([("check-modifica.html", "btn-primary", "✏️ Modifica"), ("check-completo.html", "btn-white", "➕ Nuovo Check"), ("progressi-paziente.html", "btn-secondary", "← Indietro")])
    + """<div class="content-grid-2">
<div class="content-card"><h3>📊 Dati base</h3><div class="info-list">
<div class="info-row"><span class="label">Peso</span><span class="value">78.2 kg</span></div>
<div class="info-row"><span class="label">Aderenza</span><span class="value">85%</span></div>
<div class="info-row"><span class="label">Allenamenti</span><span class="value">3/sett</span></div>
</div></div>
<div class="content-card"><h3>🔬 Composizione</h3><div class="info-list">
<div class="info-row"><span class="label">Grasso corporeo</span><span class="value">18.5%</span></div>
<div class="info-row"><span class="label">Massa muscolare</span><span class="value">62.3 kg</span></div>
<div class="info-row"><span class="label">BMI</span><span class="value">24.7</span></div>
</div></div></div>
<div class="content-card"><h3>📏 Circonferenze</h3><div class="info-list">
<div class="info-row"><span class="label">Vita</span><span class="value">82 cm</span></div>
<div class="info-row"><span class="label">Fianchi</span><span class="value">98 cm</span></div>
</div></div>""",
)

# ── Agenda ──
PAGES["agenda-unificata.html"] = wrap(
    "Agenda Unificata", "agenda",
    header("📅 Agenda", "Gestisci slot, appuntamenti e calendario", date_block())
    + stat_cards([("📅", "12", "Slot Disponibili", "", "green"), ("📋", "5", "Appuntamenti Oggi", "", "blue"), ("⏳", "2", "In Attesa", "", "yellow"), ("✅", "3", "Confermati", "", "purple")])
    + toolbar([("slot-nuovo.html", "btn-primary", "➕ Nuovo Slot"), ("slot-genera.html", "btn-secondary", "⚡ Genera Multipli"), ("appuntamento-nuovo.html", "btn-white", "📋 Nuovo Appuntamento")])
    + """<div class="tabs">
<button class="tab-btn active" onclick="showTab('calendario',this)">📅 Calendario</button>
<button class="tab-btn" onclick="showTab('slot',this)">🕐 Slot</button>
<button class="tab-btn" onclick="showTab('appuntamenti',this)">📋 Appuntamenti</button>
</div>
<div id="calendario-tab" class="tab-panel active">
<h3 class="section-title">Giugno 2026</h3>
<div class="calendar-grid">
<div class="calendar-day"><div class="calendar-date">Lun 22</div></div>
<div class="calendar-day today"><div class="calendar-date">Mar 23</div><div class="calendar-event confermato">10:00 Laura B.</div><div class="calendar-event in_attesa">15:00 Paolo N.</div></div>
<div class="calendar-day"><div class="calendar-date">Mer 24</div><div class="calendar-event">09:00 Slot libero</div></div>
<div class="calendar-day"><div class="calendar-date">Gio 25</div></div>
<div class="calendar-day"><div class="calendar-date">Ven 26</div><div class="calendar-event confermato">11:30 Giulia V.</div></div>
</div></div>
<div id="slot-tab" class="tab-panel">
<div class="slot-row"><div><strong>24/06/2026 09:00</strong><div class="patient-meta">Disponibile</div></div><div class="action-buttons"><button class="btn btn-small btn-white">Toggle</button><button class="btn btn-small btn-danger" data-confirm="Eliminare slot?">Elimina</button></div></div>
<div class="slot-row"><div><strong>25/06/2026 10:30</strong><div class="patient-meta">Disponibile</div></div><div class="action-buttons"><button class="btn btn-small btn-white">Toggle</button><button class="btn btn-small btn-danger" data-confirm="Eliminare slot?">Elimina</button></div></div>
<p style="margin-top:1rem"><a href="slot-lista.html" class="btn btn-ghost btn-small">Vedi tutti gli slot →</a></p>
</div>
<div id="appuntamenti-tab" class="tab-panel">
<div class="appointment-row slot-row"><div><strong>10:00 — Laura Bianchi</strong><div class="patient-meta">Prima visita · In attesa</div></div><div class="action-buttons"><button class="btn btn-small btn-primary">Conferma</button><button class="btn btn-small btn-danger" data-confirm="Annullare?">Annulla</button></div></div>
<div class="appointment-row slot-row"><div><strong>15:00 — Paolo Neri</strong><div class="patient-meta">Check · Confermato</div></div><div class="action-buttons"><a href="paziente-dettaglio.html" class="btn btn-small btn-secondary">Paziente</a></div></div>
<p style="margin-top:1rem"><a href="appuntamenti-lista.html" class="btn btn-ghost btn-small">Lista completa →</a></p>
</div>""",
)

PAGES["appuntamenti-lista.html"] = wrap(
    "Appuntamenti", "agenda",
    header("📋 Appuntamenti", "Gestione appuntamenti dello studio")
    + toolbar([("appuntamento-nuovo.html", "btn-primary", "➕ Nuovo"), ("agenda-unificata.html", "btn-white", "📅 Calendario")])
    + table(["Data/Ora", "Paziente", "Tipo", "Stato", "Azioni"], [
        ["23/06 10:00", "Laura Bianchi", "Prima visita", '<span class="badge badge-warning">In attesa</span>', '<button class="btn btn-small btn-primary">Conferma</button> <button class="btn btn-small btn-danger" data-confirm="Eliminare?">Elimina</button>'],
        ["23/06 15:00", "Paolo Neri", "Check", '<span class="badge badge-success">Confermato</span>', '<a href="paziente-dettaglio.html" class="btn btn-small btn-secondary">Paziente</a>'],
        ["26/06 11:30", "Giulia Verdi", "Follow-up", '<span class="badge badge-success">Confermato</span>', '<a href="paziente-dettaglio.html" class="btn btn-small btn-secondary">Paziente</a>'],
    ]),
)

PAGES["appuntamento-nuovo.html"] = wrap(
    "Nuovo Appuntamento", "agenda",
    breadcrumb(("Agenda", "agenda-unificata.html"), ("Nuovo appuntamento", None))
    + '<h2 class="page-title">📋 Nuovo Appuntamento</h2>'
    + """<form class="form-container" data-mock data-success="Appuntamento creato (simulazione).">"""
    + form_group("Paziente", "patient_id", "select", required="", options=[("", "Seleziona"), ("1", "Marco Rossi"), ("2", "Laura Bianchi")])
    + form_group("Data e ora", "data_appuntamento", "datetime-local", required="")
    + form_group("Tipo", "tipo", "select", options=[("visita", "Visita"), ("check", "Check"), ("followup", "Follow-up")])
    + form_group("Note", "note", "textarea")
    + form_actions(True, "agenda-unificata.html", "💾 Crea Appuntamento") + "</form>",
)

PAGES["slot-lista.html"] = wrap(
    "Slot Disponibili", "agenda",
    header("🕐 Slot Disponibili", "Gestione slot futuri")
    + toolbar([("slot-nuovo.html", "btn-primary", "➕ Nuovo Slot"), ("slot-genera.html", "btn-secondary", "⚡ Genera Multipli"), ("agenda-unificata.html", "btn-white", "📅 Agenda")])
    + table(["Data/Ora", "Stato", "Note", "Azioni"], [
        ["24/06/2026 09:00", '<span class="badge badge-success">Attivo</span>', "—", '<button class="btn btn-small btn-white">Toggle</button> <button class="btn btn-small btn-danger" data-confirm="Eliminare?">Elimina</button>'],
        ["25/06/2026 10:30", '<span class="badge badge-success">Attivo</span>', "Mattina", '<button class="btn btn-small btn-white">Toggle</button> <button class="btn btn-small btn-danger" data-confirm="Eliminare?">Elimina</button>'],
        ["26/06/2026 14:00", '<span class="badge badge-warning">Disattivo</span>', "—", '<button class="btn btn-small btn-white">Toggle</button> <button class="btn btn-small btn-danger" data-confirm="Eliminare?">Elimina</button>'],
    ]),
)

PAGES["slot-nuovo.html"] = wrap(
    "Nuovo Slot", "agenda",
    breadcrumb(("Agenda", "agenda-unificata.html"), ("Nuovo slot", None))
    + '<h2 class="page-title">➕ Nuovo Slot</h2>'
    + """<form class="form-container" data-mock data-success="Slot creato (simulazione).">"""
    + form_group("Data e ora", "data_ora", "datetime-local", required="")
    + form_group("Note", "note", "textarea", placeholder="Opzionale...")
    + form_actions(True, "agenda-unificata.html", "💾 Crea Slot") + "</form>",
)

PAGES["slot-genera.html"] = wrap(
    "Genera Slot", "agenda",
    breadcrumb(("Agenda", "agenda-unificata.html"), ("Genera slot", None))
    + '<h2 class="page-title">⚡ Genera Slot Multipli</h2>'
    + """<form class="form-container" data-mock data-success="Slot generati (simulazione).">"""
    + form_group("Data inizio", "data_inizio", "date", required="")
    + form_group("Data fine", "data_fine", "date", required="")
    + """<div class="form-group"><label>Giorni settimana</label><div class="checkbox-group">
<label><input type="checkbox" name="giorni" value="1" checked> Lun</label>
<label><input type="checkbox" name="giorni" value="2" checked> Mar</label>
<label><input type="checkbox" name="giorni" value="3" checked> Mer</label>
<label><input type="checkbox" name="giorni" value="4"> Gio</label>
<label><input type="checkbox" name="giorni" value="5" checked> Ven</label>
</div></div>"""
    + form_group("Orari (es. 09:00,10:30,15:00)", "orari", value="09:00,10:30,15:00")
    + form_group("Note", "note", "textarea")
    + form_actions(True, "agenda-unificata.html", "⚡ Genera Slot") + "</form>",
)

# ── Economia ──
PAGES["economia.html"] = wrap(
    "Dashboard Economia", "economia",
    header("💰 Dashboard Economia", "Gestisci vendite, entrate e listino prezzi", '<div class="date-block"><div class="date" style="color:var(--green);font-weight:700">12.450€</div><div class="time">Totale incassato</div></div>')
    + stat_cards([("🥗", "Nutrizione", "Piani alimentari", "", "green"), ("🏋️", "Allenamento", "Piani fitness", "", "blue"), ("🎯", "Completo", "Pacchetti", "", "yellow"), ("👤", "1-to-1", "Sessioni", "", "purple")])
    + """<section class="card" style="margin:1.5rem 0"><h3 class="section-title">📊 Entrate ultimi 30 giorni</h3>
<div class="chart-placeholder"><div class="chart-bar" style="height:45%"></div><div class="chart-bar" style="height:60%"></div><div class="chart-bar" style="height:35%"></div><div class="chart-bar" style="height:80%"></div><div class="chart-bar" style="height:55%"></div><div class="chart-bar" style="height:70%"></div></div>
<p style="text-align:right;color:var(--orange);font-weight:600;margin-top:0.75rem">Totale periodo: 3.240€</p></section>"""
    + toolbar([("vendita-nuova.html", "btn-primary", "➕ Nuova Vendita"), ("listino-gestione.html", "btn-white", "📋 Listino"), ("vendite-lista.html", "btn-secondary", "📄 Tutte le vendite")], search=True)
    + table(["Data", "Paziente", "Prodotto", "Importo", "Stato", "Azioni"], [
        ["20/06/2026", "Marco Rossi", "Pacchetto 3 mesi", "450€", '<span class="badge badge-success">Pagato</span>', '<a href="vendita-dettaglio.html" class="btn btn-small btn-secondary">Dettaglio</a> <a href="vendita-modifica.html" class="btn btn-small btn-white">Modifica</a>'],
        ["15/06/2026", "Laura Bianchi", "Prima visita", "120€", '<span class="badge badge-success">Pagato</span>', '<a href="vendita-dettaglio.html" class="btn btn-small btn-secondary">Dettaglio</a>'],
        ["10/06/2026", "Giulia Verdi", "Controllo", "60€", '<span class="badge badge-warning">In attesa</span>', '<a href="vendita-modifica.html" class="btn btn-small btn-white">Modifica</a>'],
    ]),
)

PAGES["vendite-lista.html"] = wrap(
    "Lista Vendite", "economia",
    header("📄 Lista Vendite", "Tutte le vendite registrate")
    + toolbar([("vendita-nuova.html", "btn-primary", "➕ Nuova Vendita"), ("economia.html", "btn-secondary", "← Economia")])
    + table(["ID", "Data", "Paziente", "Importo", "Stato", "Azioni"], [
        ["#142", "20/06/2026", "Marco Rossi", "450€", "Pagato", '<a href="vendita-dettaglio.html" class="btn btn-small btn-secondary">Dettaglio</a> <button class="btn btn-small btn-danger" data-confirm="Eliminare vendita?">Elimina</button>'],
        ["#141", "15/06/2026", "Laura Bianchi", "120€", "Pagato", '<a href="vendita-dettaglio.html" class="btn btn-small btn-secondary">Dettaglio</a>'],
    ]),
)

PAGES["vendita-nuova.html"] = wrap(
    "Nuova Vendita", "economia",
    breadcrumb(("Economia", "economia.html"), ("Nuova vendita", None))
    + '<h2 class="page-title">➕ Nuova Vendita</h2>'
    + """<form class="form-container" data-mock data-success="Vendita registrata (simulazione)."><div class="form-grid">"""
    + form_group("Paziente", "patient_id", "select", required="", options=[("", "Seleziona"), ("1", "Marco Rossi"), ("2", "Laura Bianchi")])
    + form_group("Prodotto listino", "listino_id", "select", options=[("1", "Pacchetto 3 mesi — 450€"), ("2", "Prima visita — 120€")])
    + form_group("Data inizio", "data_inizio", "date", required="")
    + form_group("Metodo pagamento", "metodo_pagamento", "select", options=[("contanti", "Contanti"), ("bonifico", "Bonifico"), ("carta", "Carta")])
    + form_group("Sconto (€)", "sconto", "number", value="0")
    + "</div>" + form_group("Note", "note", "textarea") + form_actions(True, "economia.html", "💾 Registra Vendita") + "</form>",
)

PAGES["vendita-modifica.html"] = wrap(
    "Modifica Vendita", "economia",
    breadcrumb(("Economia", "economia.html"), ("Modifica vendita", None))
    + '<h2 class="page-title">✏️ Modifica Vendita #142</h2>'
    + """<form class="form-container" data-mock data-success="Vendita aggiornata (simulazione)."><div class="form-grid">"""
    + form_group("Prodotto", "listino_id", "select", options=[("1", "Pacchetto 3 mesi — 450€")])
    + form_group("Data inizio", "data_inizio", "date", value="2026-06-20")
    + form_group("Metodo pagamento", "metodo_pagamento", "select", options=[("bonifico", "Bonifico"), ("contanti", "Contanti")])
    + form_group("Sconto (€)", "sconto", value="0")
    + form_group("Stato", "stato", "select", options=[("pagato", "Pagato"), ("attesa", "In attesa"), ("annullato", "Annullato")])
    + "</div>" + form_group("Note", "note", "textarea") + form_actions(True, "vendita-dettaglio.html", "💾 Salva") + "</form>",
)

PAGES["vendita-notifica.html"] = wrap(
    "Modifica Vendita (Notifica)", "economia",
    breadcrumb(("Vendita", "vendita-dettaglio.html"), ("Da notifica", None))
    + '<h2 class="page-title">🔔 Modifica Vendita — Notifica</h2>'
    + """<form class="form-container" data-mock data-success="Vendita aggiornata (simulazione)."><div class="form-grid">"""
    + form_group("Prodotto", "listino_id", "select", options=[("1", "Pacchetto 3 mesi")])
    + form_group("Data inizio", "data_inizio", "date", value="2026-06-20")
    + form_group("Metodo pagamento", "metodo_pagamento", "select", options=[("bonifico", "Bonifico")])
    + form_group("Sconto (€)", "sconto", value="0")
    + form_group("Importo finale (€)", "importo_finale", value="450")
    + form_group("Stato", "stato", "select", options=[("pagato", "Pagato"), ("attesa", "In attesa")])
    + "</div>" + form_group("Note", "note", "textarea") + form_actions(True, "vendita-dettaglio.html", "💾 Conferma") + "</form>",
)

PAGES["vendita-dettaglio.html"] = wrap(
    "Dettaglio Vendita", "economia",
    breadcrumb(("Economia", "economia.html"), ("Vendita #142", None))
    + header("💰 Vendita #142", "Marco Rossi — Pacchetto 3 mesi", variant="green")
    + toolbar([("vendita-modifica.html", "btn-primary", "✏️ Modifica"), ("registro-economico-paziente.html", "btn-white", "📊 Registro paziente"), ("vendite-lista.html", "btn-secondary", "← Lista")])
    + """<div class="content-grid-2">
<div class="content-card"><h3>Dettagli vendita</h3><div class="info-list">
<div class="info-row"><span class="label">Data</span><span class="value">20/06/2026</span></div>
<div class="info-row"><span class="label">Importo</span><span class="value">450€</span></div>
<div class="info-row"><span class="label">Sconto</span><span class="value">0€</span></div>
<div class="info-row"><span class="label">Stato</span><span class="value"><span class="badge badge-success">Pagato</span></span></div>
</div></div>
<div class="content-card"><h3>Pagamento</h3><div class="info-list">
<div class="info-row"><span class="label">Metodo</span><span class="value">Bonifico</span></div>
<div class="info-row"><span class="label">Paziente</span><span class="value"><a href="paziente-dettaglio.html" style="color:var(--orange)">Marco Rossi</a></span></div>
</div></div></div>""",
)

PAGES["registro-economico-paziente.html"] = wrap(
    "Registro Economico Paziente", "economia",
    breadcrumb(("Marco Rossi", "paziente-dettaglio.html"), ("Registro economico", None))
    + header("💰 Registro Economico — Marco Rossi", "Storico acquisti e spese", variant="green")
    + stat_cards([("💰", "870€", "Totale speso", "", "purple"), ("📦", "2", "Pacchetti", "", "green"), ("📅", "20/06", "Ultimo acquisto", "", "blue")])
    + toolbar([("vendita-nuova.html", "btn-primary", "➕ Nuova Vendita"), ("paziente-dettaglio.html", "btn-secondary", "← Paziente"), ("economia.html", "btn-white", "Dashboard")])
    + table(["Data", "Prodotto", "Importo", "Stato", "Azioni"], [
        ["20/06/2026", "Pacchetto 3 mesi", "450€", "Pagato", '<a href="vendita-dettaglio.html" class="btn btn-small btn-secondary">Dettaglio</a>'],
        ["15/03/2026", "Prima visita + dieta", "420€", "Pagato", '<a href="vendita-dettaglio.html" class="btn btn-small btn-secondary">Dettaglio</a>'],
    ]),
)

PAGES["listino-gestione.html"] = wrap(
    "Gestione Listino", "economia",
    header("📋 Gestione Listino Prezzi", "Prodotti e pacchetti per categoria")
    + toolbar([("listino-nuovo.html", "btn-primary", "➕ Nuovo Prodotto"), ("economia.html", "btn-secondary", "← Economia")])
    + """<h3 class="section-title">🥗 Nutrizione</h3>"""
    + table(["Prodotto", "Durata", "Prezzo", "Check", "Azioni"], [
        ["Pacchetto 3 mesi", "3 mesi", "450€", "6", '<a href="listino-modifica.html" class="btn btn-small btn-white">Modifica</a> <button class="btn btn-small btn-danger" data-confirm="Eliminare?">Elimina</button>'],
        ["Prima visita + dieta", "1 mese", "120€", "1", '<a href="listino-modifica.html" class="btn btn-small btn-white">Modifica</a>'],
    ])
    + """<h3 class="section-title">🏋️ Allenamento</h3>"""
    + table(["Prodotto", "Durata", "Prezzo", "Check", "Azioni"], [
        ["Scheda 3 mesi", "3 mesi", "200€", "—", '<a href="listino-modifica.html" class="btn btn-small btn-white">Modifica</a>'],
    ]),
)

PAGES["listino-nuovo.html"] = wrap(
    "Nuovo Prodotto Listino", "economia",
    breadcrumb(("Listino", "listino-gestione.html"), ("Nuovo prodotto", None))
    + '<h2 class="page-title">➕ Nuovo Prodotto</h2>'
    + """<form class="form-container" data-mock data-success="Prodotto aggiunto al listino (simulazione)."><div class="form-grid">"""
    + form_group("Nome prodotto", "nome_prodotto", required="", placeholder="Es: Pacchetto 6 mesi")
    + form_group("Categoria", "categoria", "select", options=[("nutrizione", "Nutrizione"), ("allenamento", "Allenamento"), ("completo", "Completo"), ("1to1", "1-to-1")])
    + form_group("Durata (mesi)", "durata_mesi", "number", value="3")
    + form_group("Prezzo (€)", "prezzo", "number", required="", step="0.01")
    + form_group("Check inclusi", "check_inclusi", "number", value="6")
    + "</div>" + form_group("Note", "note", "textarea") + form_actions(True, "listino-gestione.html", "💾 Salva Prodotto") + "</form>",
)

PAGES["listino-modifica.html"] = wrap(
    "Modifica Listino", "economia",
    breadcrumb(("Listino", "listino-gestione.html"), ("Modifica prodotto", None))
    + '<h2 class="page-title">✏️ Modifica — Pacchetto 3 mesi</h2>'
    + """<form class="form-container" data-mock data-success="Prodotto aggiornato (simulazione)."><div class="form-grid">"""
    + form_group("Nome prodotto", "nome_prodotto", value="Pacchetto 3 mesi")
    + form_group("Prezzo (€)", "prezzo", value="450")
    + form_group("Check inclusi", "check_inclusi", value="6")
    + """<div class="form-group"><label><input type="checkbox" name="attivo" checked> Prodotto attivo</label></div>"""
    + "</div>" + form_group("Note", "note", "textarea") + form_actions(True, "listino-gestione.html", "💾 Salva") + "</form>",
)

# ── Broadcast ──
PAGES["broadcast-dashboard.html"] = wrap(
    "Messaggi WhatsApp", "messaggi",
    header("📱 Dashboard Messaggi", "Trigger automatici e broadcast WhatsApp")
    + toolbar([("broadcast-nuovo.html", "btn-primary", "📤 Invia Broadcast"), ("broadcast-config.html", "btn-white", "⚙️ Configura Template")])
    + """<div class="trigger-grid">
<div class="trigger-card"><h4>📅 Promemoria appuntamenti</h4><p class="subtitle">Invio automatico 24h prima</p><button type="button" class="btn-toggle btn-on" onclick="toggleTrigger(this)">● ON</button></div>
<div class="trigger-card"><h4>🥗 Nuove diete</h4><p class="subtitle">Notifica quando carichi una dieta</p><button type="button" class="btn-toggle btn-on" onclick="toggleTrigger(this)">● ON</button></div>
<div class="trigger-card"><h4>🏋️ Nuovi allenamenti</h4><p class="subtitle">Notifica scheda allenamento</p><button type="button" class="btn-toggle btn-off" onclick="toggleTrigger(this)">● OFF</button></div>
<div class="trigger-card"><h4>⏰ Scadenze pacchetti</h4><p class="subtitle">Avviso 7 giorni prima</p><button type="button" class="btn-toggle btn-on" onclick="toggleTrigger(this)">● ON</button></div>
</div>
<div class="content-card"><h3>📝 Variabili disponibili</h3>
<p class="subtitle"><code>{nome}</code> <code>{cognome}</code> <code>{telefono}</code> <code>{data_appuntamento}</code> <code>{tipo}</code></p></div>""",
)

PAGES["broadcast-nuovo.html"] = wrap(
    "Nuovo Broadcast", "messaggi",
    breadcrumb(("Messaggi", "broadcast-dashboard.html"), ("Nuovo broadcast", None))
    + '<h2 class="page-title">📤 Invia Broadcast WhatsApp</h2>'
    + """<form class="form-container" data-mock data-success="Broadcast inviato a 48 pazienti (simulazione).">"""
    + form_group("Messaggio", "messaggio", "textarea", placeholder="Ciao {nome}, ...", rows="8")
    + """<p class="subtitle">Variabili: {nome} {cognome} {telefono}</p>"""
    + form_actions(True, "broadcast-dashboard.html", "📤 Invia a tutti") + "</form>",
)

PAGES["broadcast-config.html"] = wrap(
    "Config Template", "messaggi",
    breadcrumb(("Messaggi", "broadcast-dashboard.html"), ("Configurazione", None))
    + '<h2 class="page-title">⚙️ Configurazione Template</h2>'
    + """<form class="form-container" data-mock data-success="Template salvati (simulazione).">"""
    + form_group("Template appuntamenti", "tpl_appuntamenti", "textarea", placeholder="Promemoria: domani alle {ora}...")
    + form_group("Template diete", "tpl_diete", "textarea", placeholder="Ciao {nome}, la tua nuova dieta...")
    + form_group("Template allenamenti", "tpl_allenamenti", "textarea")
    + form_group("Template scadenze", "tpl_scadenze", "textarea")
    + form_actions(True, "broadcast-dashboard.html", "💾 Salva Template") + "</form>",
)


def main():
    import sys
    sys.path.insert(0, str(OUT.parent))
    from spa_builder import build_spa_html

    css = (OUT / "admin.css").read_text(encoding="utf-8")
    js = (OUT / "admin.js").read_text(encoding="utf-8")
    fonts = (
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Playfair+Display:wght@600;700&family=Adam+Script&display=swap" rel="stylesheet">'
    )
    html = build_spa_html(
        pages=PAGES,
        css=css,
        js=js,
        fonts_link=fonts,
        app_title="MyNutriAPP",
        main_class="content",
        home_id="dashboard",
        shell_before_main='  <div id="site-nav"></div>',
        shell_after_main='  <div id="site-footer"></div>',
    )
    out = OUT.parent / "mynutriapp-admin.html"
    out.write_text(html, encoding="utf-8")
    print(f"  ✓ {out.name} ({len(PAGES)} schermate)")
    print(f"\nFile unico generato: {out}")


if __name__ == "__main__":
    main()
