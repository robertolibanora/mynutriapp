from flask import Blueprint, render_template, request, redirect, url_for, flash, session, Response, jsonify
from werkzeug.security import generate_password_hash
from app.models.models import db, Patient, Dieta, Allenamento, Progresso, PatientNote, Appuntamento, DietPlan, Documento
from app.services.paziente_service import (
    LABEL_STATO_CLIENTE,
    STATI_CLIENTE,
    approva_paziente,
    rifiuta_paziente,
)
from app.services.gdpr_service import (
    GdprError,
    apply_consents,
    export_as_json_bytes,
    purge_patient,
    request_erasure,
)
from app.services.patient_search_service import search_patients
from app.services.patient_list_service import list_patients_enriched
from app.services.patient_timeline_service import get_patient_timeline
from app.utils.db_schema import ensure_gdpr_schema, ensure_patient_stato_schema, ensure_activity_notes_schema
from app.utils.tenant import (
    assert_patient_tenant,
    patients_query_for_tenant,
    require_tenant,
    tenant_filter_enabled,
)
from datetime import date, datetime, timedelta
from sqlalchemy import case
from sqlalchemy.orm import joinedload

# ========================
# BLUEPRINT
# ========================
patients_bp = Blueprint('patients', __name__, url_prefix='/admin/pazienti')


@patients_bp.before_request
def _ensure_patient_schema():
    ensure_patient_stato_schema()
    ensure_gdpr_schema()
    ensure_activity_notes_schema()


# ========================
# DECORATORE DI PROTEZIONE
# ========================
def admin_required(func):
    """Permette l'accesso solo all'admin (Enrico)"""
    from functools import wraps

    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get('role') not in ('admin', 'nutrizionista'):
            flash("Accesso non autorizzato", "danger")
            return redirect(url_for('auth.login'))
        return func(*args, **kwargs)

    return wrapper


def _get_tenant_patient(patient_id: int) -> Patient:
    paziente = Patient.query.get_or_404(patient_id)
    assert_patient_tenant(paziente)
    return paziente


# ========================
# LISTA PAZIENTI
# ========================
@patients_bp.route('/')
@admin_required
def lista_pazienti():
    search_query = request.args.get('search', '').strip()
    stato_filtro = request.args.get('stato', '').strip()
    filtro = request.args.get('filtro', '').strip() or stato_filtro or 'tutti'
    sort = request.args.get('sort', 'nome').strip() or 'nome'

    rows = list_patients_enriched(search=search_query, filtro=filtro, sort=sort)

    base_counts = patients_query_for_tenant()
    return render_template(
        'admin/pazienti_lista.html',
        rows=rows,
        search_query=search_query,
        filtro=filtro,
        sort=sort,
        label_stato=LABEL_STATO_CLIENTE,
        n_provvisori=base_counts.filter_by(stato_cliente='provvisorio').count(),
        n_attivi=base_counts.filter_by(stato_cliente='attivo').count(),
        n_non_attivi=base_counts.filter_by(stato_cliente='non_attivo').count(),
        n_totali=base_counts.count(),
    )


# ========================
# API RICERCA GLOBALE
# ========================
@patients_bp.route('/api/search')
@admin_required
def api_search_pazienti():
    q = request.args.get('q', '')
    try:
        limit = int(request.args.get('limit', 8))
    except ValueError:
        limit = 8
    results = search_patients(q, limit=limit)
    return jsonify({"results": results, "q": q})


# ========================
# APPROVA / RIFIUTA CLIENTE PROVVISORIO
# ========================
@patients_bp.route('/<int:patient_id>/approva', methods=['POST'])
@admin_required
def approva_cliente(patient_id):
    """Approva cliente provvisorio → attivo + conferma appuntamento in attesa."""
    paziente = _get_tenant_patient(patient_id)
    if paziente.stato_cliente != 'provvisorio':
        flash("Questo paziente non è in stato provvisorio", "warning")
        return redirect(url_for('patients.lista_pazienti'))

    try:
        appuntamento = approva_paziente(paziente)
        db.session.commit()
        if appuntamento:
            from app.routes.whatsapp.triggers import safe_trigger_appuntamento_stato
            safe_trigger_appuntamento_stato(appuntamento, 'confermato')
        flash(f"{paziente.nome} {paziente.cognome} approvato: ora è attivo ✅", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore durante l'approvazione: {e}", "danger")

    return redirect(url_for('patients.lista_pazienti', stato='provvisorio'))


@patients_bp.route('/<int:patient_id>/rifiuta', methods=['POST'])
@admin_required
def rifiuta_cliente(patient_id):
    """Rifiuta cliente provvisorio → non attivo + annulla appuntamenti in attesa."""
    paziente = _get_tenant_patient(patient_id)
    if paziente.stato_cliente != 'provvisorio':
        flash("Questo paziente non è in stato provvisorio", "warning")
        return redirect(url_for('patients.lista_pazienti'))

    try:
        rifiuta_paziente(paziente)
        db.session.commit()
        flash(f"{paziente.nome} {paziente.cognome} rifiutato: impostato come non attivo", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore durante il rifiuto: {e}", "danger")

    return redirect(url_for('patients.lista_pazienti', stato='provvisorio'))


# ========================
# DETTAGLIO SINGOLO PAZIENTE
# ========================
@patients_bp.route('/<int:patient_id>')
@admin_required
def dettaglio_paziente(patient_id):
    from app.models.models import Progresso, Documento
    from app.utils.audit import log_audit_event
    
    paziente = _get_tenant_patient(patient_id)
    
    # Audit log per visualizzazione dati paziente
    log_audit_event('VIEW', 'patient', patient_id)
    db.session.commit()
    
    # Recupera progressi ordinati per data
    progressi = Progresso.query.filter_by(patient_id=patient_id).order_by(Progresso.data_check.asc()).all()
    
    # Recupera documenti ordinati per data upload (più recenti prima)
    documenti = Documento.query.filter_by(patient_id=patient_id).order_by(Documento.data_upload.desc()).all()
    
    # CALCOLA ALERT
    from datetime import date, timedelta
    oggi = date.today()
    alerti = []
    
    # Alert per diete in scadenza (14 giorni)
    for dieta in paziente.diete:
        if dieta.data_fine >= oggi:  # Solo diete ancora attive
            giorni_alla_scadenza = (dieta.data_fine - oggi).days
            if giorni_alla_scadenza <= 14:
                alerti.append({
                    'tipo': 'dieta_scadenza',
                    'titolo': 'Dieta in scadenza',
                    'messaggio': f"La dieta scade tra {giorni_alla_scadenza} giorni ({dieta.data_fine.strftime('%d/%m/%Y')})",
                    'urgenza': 'alta' if giorni_alla_scadenza <= 7 else 'media',
                    'colore': '#F44336' if giorni_alla_scadenza <= 7 else '#FF9800'
                })
    
    # Alert per allenamenti in scadenza (14 giorni)
    for allenamento in paziente.allenamenti:
        if allenamento.data_fine >= oggi:  # Solo allenamenti ancora attivi
            giorni_alla_scadenza = (allenamento.data_fine - oggi).days
            if giorni_alla_scadenza <= 14:
                alerti.append({
                    'tipo': 'allenamento_scadenza',
                    'titolo': 'Allenamento in scadenza',
                    'messaggio': f"L'allenamento scade tra {giorni_alla_scadenza} giorni ({allenamento.data_fine.strftime('%d/%m/%Y')})",
                    'urgenza': 'alta' if giorni_alla_scadenza <= 7 else 'media',
                    'colore': '#F44336' if giorni_alla_scadenza <= 7 else '#FF9800'
                })
    
    # Alert per check non effettuati da più di un mese
    if progressi:
        ultimo_check = max(progressi, key=lambda p: p.data_check)
        # Se data_check è datetime, converti in date, altrimenti usa direttamente
        ultima_data = ultimo_check.data_check.date() if hasattr(ultimo_check.data_check, 'date') else ultimo_check.data_check
        giorni_dall_ultimo_check = (oggi - ultima_data).days
        if giorni_dall_ultimo_check > 30:
            alerti.append({
                'tipo': 'check_mancante',
                'titolo': 'Check mancante',
                'messaggio': f"Nessun check effettuato da {giorni_dall_ultimo_check} giorni (ultimo: {ultima_data.strftime('%d/%m/%Y')})",
                'urgenza': 'alta' if giorni_dall_ultimo_check > 60 else 'media',
                'colore': '#F44336' if giorni_dall_ultimo_check > 60 else '#FF9800'
            })
    else:
        # Nessun progresso mai registrato
        alerti.append({
            'tipo': 'check_mancante',
            'titolo': 'Check mancante',
            'messaggio': "Nessun check mai effettuato - inizia il monitoraggio!",
            'urgenza': 'media',
            'colore': '#FF9800'
        })
    
    # CALCOLA STATISTICHE
    # Separare progressi del paziente da quelli del nutrizionista
    progressi_paziente = [p for p in progressi if p.tipo_check == 'paziente']
    progressi_nutrizionista = [p for p in progressi if p.tipo_check == 'nutrizionista']
    
    # Statistiche peso - include tutti i progressi con peso (paziente + nutrizionista)
    variazioni_peso = []
    progressi_con_peso = [p for p in progressi if p.peso_settimanale]
    if progressi_con_peso and paziente.peso_iniziale is not None:
        peso_iniziale = float(paziente.peso_iniziale)
        for p in progressi_con_peso:
            variazioni_peso.append(float(p.peso_settimanale) - peso_iniziale)
    
    variazione_peso_media = sum(variazioni_peso) / len(variazioni_peso) if variazioni_peso else 0
    
    # Statistiche aderenza - include tutti i progressi con aderenza (paziente + nutrizionista)
    aderenze_tutte = [p.aderenza for p in progressi if p.aderenza is not None]
    aderenza_media = sum(aderenze_tutte) / len(aderenze_tutte) if aderenze_tutte else 0
    
    # Statistiche check totali
    check_totali = len(progressi)
    
    # Statistiche foto
    foto_inviate = len([p for p in progressi if p.foto_path])
    
    # Prepara dati per il grafico - include tutti i progressi con peso (paziente + nutrizionista)
    progressi_con_peso = [p for p in progressi if p.peso_settimanale]
    date_labels = [p.data_check.strftime('%d/%m/%Y') for p in progressi_con_peso]
    pesi = [round(float(p.peso_settimanale), 1) for p in progressi_con_peso]
    aderenze = [p.aderenza if p.aderenza else 5 for p in progressi_con_peso]  # Default 5 se None
    
    # Decrittografa campi sensibili per visualizzazione
    # Le template accedono direttamente ai campi, quindi decrittiamo qui
    paziente.patologie = paziente.patologie_decrypted
    paziente.intolleranze = paziente.intolleranze_decrypted
    paziente.esami_biochimici = paziente.esami_biochimici_decrypted

    # Diario colloqui (tab dedicato)
    from app.services.diario_review_service import list_patient_diaries

    diary_items = []
    da_revisionare = []
    confermati = []
    altri = []
    utente_id = session.get("utente_id")
    if utente_id:
        diary_items = list_patient_diaries(
            patient_id=patient_id,
            utente_id=int(utente_id),
        )
        da_revisionare = [i for i in diary_items if i["da_revisionare"]]
        confermati = [i for i in diary_items if i["valido_storico"]]
        altri = [
            i for i in diary_items
            if not i["da_revisionare"] and not i["valido_storico"]
        ]

    now = datetime.now()
    eta = None
    if paziente.data_nascita:
        eta = oggi.year - paziente.data_nascita.year - (
            (oggi.month, oggi.day) < (paziente.data_nascita.month, paziente.data_nascita.day)
        )

    peso_attuale = None
    if progressi_con_peso:
        ultimo_peso = max(progressi_con_peso, key=lambda p: p.data_check)
        peso_attuale = float(ultimo_peso.peso_settimanale)

    delta_peso = None
    if peso_attuale is not None and paziente.peso_iniziale is not None:
        delta_peso = round(peso_attuale - float(paziente.peso_iniziale), 1)

    app_q = Appuntamento.query.filter_by(patient_id=patient_id)
    if tenant_filter_enabled():
        app_q = app_q.filter(Appuntamento.utente_id == require_tenant())
    appuntamenti = app_q.order_by(Appuntamento.data_appuntamento.desc()).limit(50).all()
    prossimo_app = (
        app_q.filter(
            Appuntamento.data_appuntamento >= now,
            Appuntamento.stato.in_(("in_attesa", "confermato")),
        )
        .order_by(Appuntamento.data_appuntamento.asc())
        .first()
    )
    ultima_visita = (
        app_q.filter(
            Appuntamento.data_appuntamento < now,
            Appuntamento.stato != "annullato",
        )
        .order_by(Appuntamento.data_appuntamento.desc())
        .first()
    )

    diet_plans = (
        DietPlan.query.filter_by(patient_id=patient_id)
        .order_by(DietPlan.updated_at.desc())
        .all()
    )
    dieta_attiva = next((d for d in diet_plans if d.status == "published"), None)
    diete_bozza = [d for d in diet_plans if d.status == "draft"]
    diete_pdf = (
        Dieta.query.filter_by(patient_id=patient_id)
        .order_by(Dieta.data_inizio.desc())
        .all()
    )

    allenamenti = (
        Allenamento.query.filter_by(patient_id=patient_id)
        .order_by(Allenamento.created_at.desc())
        .all()
    )
    allenamento_attivo = None
    for a in allenamenti:
        if a.data_fine and a.data_fine >= oggi:
            allenamento_attivo = a
            break
    if allenamento_attivo is None and allenamenti:
        allenamento_attivo = allenamenti[0]

    notes = (
        PatientNote.query.filter_by(patient_id=patient_id)
        .order_by(PatientNote.created_at.desc())
        .all()
    )

    timeline = get_patient_timeline(patient=paziente, page=1, per_page=40)

    pending = []
    for d in diete_bozza:
        pending.append({"title": f"Dieta in bozza: {d.title}", "url": url_for("diete_plans.diet_plan_detail", diet_plan_id=d.id)})
    for a in appuntamenti:
        if a.stato == "in_attesa" and a.data_appuntamento >= now:
            pending.append({"title": "Appuntamento da confermare", "url": url_for("patients.dettaglio_paziente", patient_id=patient_id, tab="appuntamenti")})
            break
    if paziente.stato_cliente == "attivo" and not prossimo_app:
        pending.append({"title": "Senza appuntamento futuro", "url": f"/appuntamenti/admin/nuovo?patient_id={patient_id}"})
    pending.extend({"title": al["titolo"], "url": None} for al in alerti[:3])

    active_tab = (request.args.get("tab") or "panoramica").strip()
    allowed_tabs = {
        "panoramica", "timeline", "diete", "allenamenti", "progressi",
        "appuntamenti", "documenti", "note", "diario", "messaggi", "mediche", "percorsi",
    }
    if active_tab == "percorsi":
        active_tab = "diete"
    if active_tab not in allowed_tabs:
        active_tab = "panoramica"

    return render_template(
        "admin/paziente_dettaglio.html",
        paziente=paziente,
        eta=eta,
        progressi=list(reversed(progressi)),
        progressi_paziente=progressi_paziente,
        progressi_nutrizionista=progressi_nutrizionista,
        documenti=documenti,
        alerti=alerti,
        pending=pending,
        variazione_peso_media=variazione_peso_media,
        aderenza_media=aderenza_media,
        check_totali=check_totali,
        foto_inviate=foto_inviate,
        date_labels=date_labels,
        pesi=pesi,
        aderenze=aderenze,
        diary_items=diary_items,
        da_revisionare=da_revisionare,
        confermati=confermati,
        altri=altri,
        peso_attuale=peso_attuale,
        delta_peso=delta_peso,
        prossimo_app=prossimo_app,
        ultima_visita=ultima_visita,
        diet_plans=diet_plans,
        dieta_attiva=dieta_attiva,
        diete_bozza=diete_bozza,
        diete_pdf=diete_pdf,
        allenamenti=allenamenti,
        allenamento_attivo=allenamento_attivo,
        appuntamenti=appuntamenti,
        notes=notes,
        timeline=timeline,
        active_tab=active_tab,
        label_stato=LABEL_STATO_CLIENTE,
    )


@patients_bp.route('/<int:patient_id>/note', methods=['POST'])
@admin_required
def aggiungi_nota(patient_id):
    paziente = _get_tenant_patient(patient_id)
    body = (request.form.get("body") or "").strip()
    if not body:
        flash("La nota non può essere vuota", "warning")
        return redirect(url_for("patients.dettaglio_paziente", patient_id=patient_id, tab="note"))
    note = PatientNote(
        patient_id=paziente.id,
        utente_id=require_tenant(),
        body=body,
    )
    db.session.add(note)
    db.session.commit()
    flash("Nota salvata", "success")
    return redirect(url_for("patients.dettaglio_paziente", patient_id=patient_id, tab="note"))


@patients_bp.route('/<int:patient_id>/note/<int:note_id>/elimina', methods=['POST'])
@admin_required
def elimina_nota(patient_id, note_id):
    _get_tenant_patient(patient_id)
    note = PatientNote.query.get_or_404(note_id)
    if note.patient_id != patient_id or note.utente_id != require_tenant():
        flash("Nota non trovata", "danger")
        return redirect(url_for("patients.dettaglio_paziente", patient_id=patient_id, tab="note"))
    db.session.delete(note)
    db.session.commit()
    flash("Nota eliminata", "success")
    return redirect(url_for("patients.dettaglio_paziente", patient_id=patient_id, tab="note"))


@patients_bp.route('/<int:patient_id>/percorsi')
@admin_required
def percorsi_paziente(patient_id):
    """Redirect alla scheda paziente, tab Diete."""
    _get_tenant_patient(patient_id)
    return redirect(
        url_for('patients.dettaglio_paziente', patient_id=patient_id, tab='diete')
    )


# ========================
# CREA NUOVO PAZIENTE
# ========================
@patients_bp.route('/nuovo', methods=['GET', 'POST'])
@admin_required
def nuovo_paziente():
    if request.method == 'POST':
        try:
            nome = request.form['nome']
            cognome = request.form['cognome']
            sesso = request.form['sesso']
            data_nascita = request.form['data_nascita']
            telefono = request.form['telefono']
            password = request.form['password']
            altezza = request.form['altezza_cm']
            peso_iniziale = request.form['peso_iniziale']

            # 🔐 Cripta password
            password_hash = generate_password_hash(password)

            if not request.form.get('consenso_privacy'):
                flash("Il consenso privacy è obbligatorio", "danger")
                return render_template('admin/paziente_nuovo.html')

            nuovo = Patient(
                nome=nome,
                cognome=cognome,
                sesso=sesso,
                data_nascita=data_nascita,
                telefono=telefono,
                password_hash=password_hash,
                altezza_cm=altezza,
                peso_iniziale=peso_iniziale,
                stato_cliente='attivo',
                nutrizionista_id=require_tenant(),
            )
            apply_consents(
                nuovo,
                consenso_privacy=True,
                consenso_marketing=bool(request.form.get('consenso_marketing')),
            )

            db.session.add(nuovo)
            db.session.commit()
            
            # Audit log
            from app.utils.audit import log_audit_event
            log_audit_event('CREATE', 'patient', nuovo.id)
            db.session.commit()
            
            flash("Paziente aggiunto con successo ✅", "success")
            return redirect(url_for('patients.lista_pazienti'))

        except Exception as e:
            db.session.rollback()
            flash(f"Errore durante l'aggiunta del paziente: {e}", "danger")

    return render_template('admin/paziente_nuovo.html')


# ========================
# MODIFICA PAZIENTE
# ========================
@patients_bp.route('/modifica/<int:patient_id>', methods=['GET', 'POST'])
@admin_required
def modifica_paziente(patient_id):
    paziente = _get_tenant_patient(patient_id)

    if request.method == 'POST':
        try:
            # Dati anagrafici
            paziente.nome = request.form['nome']
            paziente.cognome = request.form['cognome']
            paziente.sesso = request.form['sesso']
            paziente.data_nascita = request.form['data_nascita']
            paziente.telefono = request.form['telefono']
            paziente.altezza_cm = request.form['altezza_cm']
            paziente.peso_iniziale = request.form['peso_iniziale']
            
            # 🔐 Gestione password (solo se fornita)
            nuova_password = request.form.get('password', '').strip()
            if nuova_password:
                paziente.password_hash = generate_password_hash(nuova_password)
                flash("Password aggiornata con successo 🔐", "success")
            
            # Informazioni mediche (campi sensibili crittografati)
            intolleranze_val = request.form.get('intolleranze', '').strip() or None
            paziente.intolleranze_decrypted = intolleranze_val
            
            paziente.cibi_da_ev = request.form.get('cibi_da_ev', '').strip() or None
            
            patologie_val = request.form.get('patologie', '').strip() or None
            paziente.patologie_decrypted = patologie_val
            
            esami_val = request.form.get('esami_biochimici', '').strip() or None
            paziente.esami_biochimici_decrypted = esami_val
            
            # Attività fisica
            paziente.allenamenti_descr = request.form.get('allenamenti_descr', '').strip() or None
            paziente.email = request.form.get('email', '').strip() or None
            apply_consents(
                paziente,
                consenso_privacy=bool(request.form.get('consenso_privacy')),
                consenso_marketing=bool(request.form.get('consenso_marketing')),
            )

            db.session.commit()
            
            # Audit log
            from app.utils.audit import log_audit_event
            log_audit_event('UPDATE', 'patient', paziente.id)
            db.session.commit()
            
            flash("Dati paziente aggiornati ✅", "success")
            return redirect(url_for('patients.dettaglio_paziente', patient_id=paziente.id))

        except Exception as e:
            db.session.rollback()
            flash(f"Errore durante la modifica: {e}", "danger")

    # Decrittografa campi sensibili per modifica
    paziente.patologie = paziente.patologie_decrypted
    paziente.intolleranze = paziente.intolleranze_decrypted
    paziente.esami_biochimici = paziente.esami_biochimici_decrypted
    
    return render_template('admin/paziente_modifica.html', paziente=paziente)


# ========================
# ELIMINA / OBLIO PAZIENTE
# ========================
@patients_bp.route('/elimina/<int:patient_id>', methods=['POST'])
@admin_required
def elimina_paziente(patient_id):
    paziente = _get_tenant_patient(patient_id)
    nome = f"{paziente.nome} {paziente.cognome}"

    try:
        mode = purge_patient(paziente)
        if mode == "anonymized":
            flash(f"Paziente {nome}: dati anonimizzati (hold legale attivo) ✅", "success")
        else:
            flash(f"Paziente {nome} eliminato ✅", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore durante l'eliminazione: {e}", "danger")

    return redirect(url_for('patients.lista_pazienti'))


@patients_bp.route('/<int:patient_id>/export')
@admin_required
def export_paziente(patient_id):
    """Download JSON portabilità dati (GDPR Art. 20)."""
    paziente = _get_tenant_patient(patient_id)
    from app.utils.audit import log_audit_event

    payload = export_as_json_bytes(paziente)
    log_audit_event('EXPORT', 'patient', paziente.id)
    db.session.commit()
    filename = f"paziente_{paziente.id}_export.json"
    return Response(
        payload,
        mimetype='application/json',
        headers={'Content-Disposition': f'attachment; filename={filename}'},
    )


@patients_bp.route('/<int:patient_id>/erasure', methods=['POST'])
@admin_required
def erasure_paziente(patient_id):
    """Richiesta + esecuzione immediata oblio (staff)."""
    paziente = _get_tenant_patient(patient_id)
    try:
        request_erasure(paziente)
        db.session.commit()
        mode = purge_patient(paziente)
        flash(
            "Oblio completato (anonimizzato)" if mode == "anonymized" else "Oblio completato (eliminato)",
            "success",
        )
    except GdprError as e:
        db.session.rollback()
        flash(str(e), "warning")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore oblio: {e}", "danger")
    return redirect(url_for('patients.lista_pazienti'))


# ========================
# ADMIN: SCADENZE → Attività
# ========================
@patients_bp.route('/scadenze')
@admin_required
def scadenze():
    """Compatibilità: le scadenze sono confluite nella sezione Attività."""
    return redirect(url_for('attivita.lista_attivita', bucket='prossime'))