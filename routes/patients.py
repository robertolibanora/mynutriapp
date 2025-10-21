from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash
from models import db, Patient, Dieta, Allenamento, Progresso
from datetime import date, timedelta

# ========================
# BLUEPRINT
# ========================
patients_bp = Blueprint('patients', __name__, url_prefix='/admin/pazienti')


# ========================
# DECORATORE DI PROTEZIONE
# ========================
def admin_required(func):
    """Permette l'accesso solo all'admin (Enrico)"""
    from functools import wraps

    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get('role') != 'admin':
            flash("Accesso non autorizzato", "danger")
            return redirect(url_for('auth.login'))
        return func(*args, **kwargs)

    return wrapper


def user_required(func):
    """Permette l'accesso solo agli user (pazienti)"""
    from functools import wraps

    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get('role') != 'user':
            flash("Effettua il login", "warning")
            return redirect(url_for('auth.login'))
        return func(*args, **kwargs)

    return wrapper


# ========================
# LISTA PAZIENTI
# ========================
@patients_bp.route('/')
@admin_required
def lista_pazienti():
    # Ricerca pazienti
    search_query = request.args.get('search', '').strip()
    
    if search_query:
        # Cerca per nome, cognome o telefono
        pazienti = Patient.query.filter(
            db.or_(
                Patient.nome.ilike(f'%{search_query}%'),
                Patient.cognome.ilike(f'%{search_query}%'),
                Patient.telefono.ilike(f'%{search_query}%')
            )
        ).order_by(Patient.data_creazione.desc()).all()
    else:
        pazienti = Patient.query.order_by(Patient.data_creazione.desc()).all()
    
    # Calcola l'età per ogni paziente
    from datetime import date
    oggi = date.today()
    for paziente in pazienti:
        if paziente.data_nascita:
            eta = oggi.year - paziente.data_nascita.year - ((oggi.month, oggi.day) < (paziente.data_nascita.month, paziente.data_nascita.day))
            paziente.eta = eta
        else:
            paziente.eta = None
    
    return render_template('admin/pazienti_lista.html', pazienti=pazienti)


# ========================
# DETTAGLIO SINGOLO PAZIENTE
# ========================
@patients_bp.route('/<int:patient_id>')
@admin_required
def dettaglio_paziente(patient_id):
    from models import Progresso, Documento
    
    paziente = Patient.query.get_or_404(patient_id)
    
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
                    'titolo': '🍽️ Dieta in Scadenza',
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
                    'titolo': '🏋️ Allenamento in Scadenza',
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
                'titolo': '📈 Check Mancante',
                'messaggio': f"Nessun check effettuato da {giorni_dall_ultimo_check} giorni (ultimo: {ultima_data.strftime('%d/%m/%Y')})",
                'urgenza': 'alta' if giorni_dall_ultimo_check > 60 else 'media',
                'colore': '#F44336' if giorni_dall_ultimo_check > 60 else '#FF9800'
            })
    else:
        # Nessun progresso mai registrato
        alerti.append({
            'tipo': 'check_mancante',
            'titolo': '📈 Check Mancante',
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
    if progressi_con_peso:
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
    pesi = [float(p.peso_settimanale) for p in progressi_con_peso]
    aderenze = [p.aderenza if p.aderenza else 5 for p in progressi_con_peso]  # Default 5 se None
    
    return render_template('admin/paziente_dettaglio.html', 
                         paziente=paziente,
                         progressi=progressi,
                         progressi_paziente=progressi_paziente,
                         progressi_nutrizionista=progressi_nutrizionista,
                         documenti=documenti,
                         alerti=alerti,
                         variazione_peso_media=variazione_peso_media,
                         aderenza_media=aderenza_media,
                         check_totali=check_totali,
                         foto_inviate=foto_inviate,
                         date_labels=date_labels,
                         pesi=pesi,
                         aderenze=aderenze)


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

            nuovo = Patient(
                nome=nome,
                cognome=cognome,
                sesso=sesso,
                data_nascita=data_nascita,
                telefono=telefono,
                password_hash=password_hash,
                altezza_cm=altezza,
                peso_iniziale=peso_iniziale
            )

            db.session.add(nuovo)
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
    paziente = Patient.query.get_or_404(patient_id)

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
            
            # Informazioni mediche
            paziente.intolleranze = request.form.get('intolleranze', '').strip() or None
            paziente.cibi_da_ev = request.form.get('cibi_da_ev', '').strip() or None
            paziente.patologie = request.form.get('patologie', '').strip() or None
            paziente.esami_biochimici = request.form.get('esami_biochimici', '').strip() or None
            
            # Attività fisica
            paziente.allenamenti_descr = request.form.get('allenamenti_descr', '').strip() or None

            db.session.commit()
            flash("Dati paziente aggiornati ✅", "success")
            return redirect(url_for('patients.dettaglio_paziente', patient_id=paziente.id))

        except Exception as e:
            db.session.rollback()
            flash(f"Errore durante la modifica: {e}", "danger")

    return render_template('admin/paziente_modifica.html', paziente=paziente)


# ========================
# ELIMINA PAZIENTE
# ========================
@patients_bp.route('/elimina/<int:patient_id>', methods=['POST'])
@admin_required
def elimina_paziente(patient_id):
    paziente = Patient.query.get_or_404(patient_id)

    try:
        db.session.delete(paziente)
        db.session.commit()
        flash(f"Paziente {paziente.nome} eliminato ✅", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore durante l'eliminazione: {e}", "danger")

    return redirect(url_for('patients.lista_pazienti'))


# ========================
# PROFILO USER (i propri dati)
# ========================
@patients_bp.route('/user/profilo')
@user_required
def profilo_user():
    """Mostra il profilo del paziente loggato"""
    user_id = session.get('user_id')
    if not user_id:
        flash("Sessione non valida", "danger")
        return redirect(url_for('auth.login'))
    
    paziente = Patient.query.get_or_404(user_id)
    return render_template('user/profilo.html', paziente=paziente)


# ========================
# ADMIN: SCADENZE
# ========================
@patients_bp.route('/scadenze')
@admin_required
def scadenze():
    """Visualizza tutte le scadenze con filtri"""
    oggi = date.today()
    
    # Filtri dalla query string
    tipo_filtro = request.args.get('tipo', 'tutti')
    giorni_filtro = int(request.args.get('giorni', 30))
    
    # Calcola la data limite
    data_limite = oggi + timedelta(days=giorni_filtro)
    
    scadenze = []
    
    # SCADENZE DIETE
    if tipo_filtro in ['tutti', 'diete']:
        diete_scadenti = db.session.query(Dieta, Patient).join(Patient).filter(
            Dieta.data_fine >= oggi,
            Dieta.data_fine <= data_limite
        ).all()
        
        for dieta, paziente in diete_scadenti:
            giorni_alla_scadenza = (dieta.data_fine - oggi).days
            scadenze.append({
                'tipo': 'dieta',
                'titolo': '🍽️ Dieta',
                'descrizione': (dieta.note[:50] + '...' if dieta.note and len(dieta.note) > 50 else dieta.note) if dieta.note else 'Dieta senza note',
                'paziente': f"{paziente.nome} {paziente.cognome}",
                'data_scadenza': dieta.data_fine,
                'giorni_rimanenti': giorni_alla_scadenza,
                'urgenza': 'alta' if giorni_alla_scadenza <= 7 else 'media' if giorni_alla_scadenza <= 14 else 'bassa',
                'colore': '#F44336' if giorni_alla_scadenza <= 7 else '#FF9800' if giorni_alla_scadenza <= 14 else '#4CAF50',
                'link': url_for('patients.dettaglio_paziente', patient_id=paziente.id)
            })
    
    # SCADENZE ALLENAMENTI
    if tipo_filtro in ['tutti', 'allenamenti']:
        allenamenti_scadenti = db.session.query(Allenamento, Patient).join(Patient).filter(
            Allenamento.data_fine >= oggi,
            Allenamento.data_fine <= data_limite
        ).all()
        
        for allenamento, paziente in allenamenti_scadenti:
            giorni_alla_scadenza = (allenamento.data_fine - oggi).days
            scadenze.append({
                'tipo': 'allenamento',
                'titolo': '🏋️ Allenamento',
                'descrizione': (allenamento.note[:50] + '...' if allenamento.note and len(allenamento.note) > 50 else allenamento.note) if allenamento.note else 'Allenamento senza note',
                'paziente': f"{paziente.nome} {paziente.cognome}",
                'data_scadenza': allenamento.data_fine,
                'giorni_rimanenti': giorni_alla_scadenza,
                'urgenza': 'alta' if giorni_alla_scadenza <= 7 else 'media' if giorni_alla_scadenza <= 14 else 'bassa',
                'colore': '#F44336' if giorni_alla_scadenza <= 7 else '#FF9800' if giorni_alla_scadenza <= 14 else '#4CAF50',
                'link': url_for('patients.dettaglio_paziente', patient_id=paziente.id)
            })
    
    # CHECK MANCANTI
    if tipo_filtro in ['tutti', 'check']:
        # Trova pazienti con ultimo check oltre 30 giorni
        check_mancanti = db.session.query(Patient).outerjoin(Progresso).group_by(Patient.id).having(
            db.func.max(Progresso.data_check) < oggi - timedelta(days=30)
        ).all()
        
        # Trova anche pazienti senza progressi
        pazienti_senza_progressi = db.session.query(Patient).outerjoin(Progresso).filter(
            Progresso.id.is_(None)
        ).all()
        
        for paziente in check_mancanti + pazienti_senza_progressi:
            if paziente in pazienti_senza_progressi:
                giorni_senza_check = 999  # Valore alto per pazienti senza progressi
                ultimo_check = "Mai effettuato"
            else:
                ultimo_progresso = Progresso.query.filter_by(patient_id=paziente.id).order_by(Progresso.data_check.desc()).first()
                giorni_senza_check = (oggi - ultimo_progresso.data_check.date()).days
                ultimo_check = ultimo_progresso.data_check.strftime('%d/%m/%Y')
            
            scadenze.append({
                'tipo': 'check',
                'titolo': '📈 Check Mancante',
                'descrizione': f"Ultimo check: {ultimo_check}",
                'paziente': f"{paziente.nome} {paziente.cognome}",
                'data_scadenza': None,
                'giorni_rimanenti': giorni_senza_check,
                'urgenza': 'alta' if giorni_senza_check > 60 else 'media',
                'colore': '#F44336' if giorni_senza_check > 60 else '#FF9800',
                'link': url_for('patients.dettaglio_paziente', patient_id=paziente.id)
            })
    
    # Ordina per urgenza e giorni rimanenti
    scadenze.sort(key=lambda x: (x['urgenza'] == 'bassa', x['giorni_rimanenti']))
    
    # Statistiche
    stats = {
        'totali': len(scadenze),
        'diete': len([s for s in scadenze if s['tipo'] == 'dieta']),
        'allenamenti': len([s for s in scadenze if s['tipo'] == 'allenamento']),
        'check': len([s for s in scadenze if s['tipo'] == 'check']),
        'urgenti': len([s for s in scadenze if s['urgenza'] == 'alta'])
    }
    
    return render_template('admin/scadenze.html', 
                         scadenze=scadenze, 
                         stats=stats,
                         tipo_filtro=tipo_filtro,
                         giorni_filtro=giorni_filtro)