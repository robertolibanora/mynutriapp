from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.models.models import db, Vendita, Patient, Listino
from app.utils.helpers import admin_required, safe_float
from datetime import datetime

# ========================
# BLUEPRINT
# ========================
vendite_bp = Blueprint('vendite', __name__, url_prefix='/admin/vendite')

# ========================
# DECORATORI
# ========================
def admin_required(func):
    """Accesso riservato all'admin"""
    from functools import wraps
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get('role') != 'admin':
            flash("Accesso non autorizzato", "danger")
            return redirect(url_for('auth.login'))
        return func(*args, **kwargs)
    return wrapper


# ========================
# LISTA TUTTE LE VENDITE
# ========================
@vendite_bp.route('/')
@admin_required
def lista_vendite():
    """Mostra tutte le vendite registrate"""
    vendite = Vendita.query.order_by(Vendita.data_acquisto.desc()).all()
    totale = sum(v.importo_finale for v in vendite)
    return render_template('admin/vendite_lista.html', vendite=vendite, totale=totale)


# ========================
# DETTAGLIO DI UNA VENDITA
# ========================
@vendite_bp.route('/dettaglio/<int:id>')
@admin_required
def dettaglio_vendita(id):
    """Mostra i dettagli di una vendita specifica"""
    vendita = Vendita.query.get_or_404(id)
    return render_template('admin/vendita_dettaglio.html', vendita=vendita)


# ========================
# CREA NUOVA VENDITA
# ========================
@vendite_bp.route('/nuova', methods=['GET', 'POST'])
@admin_required
def nuova_vendita():
    """Crea una nuova vendita (collegata a un paziente e un piano listino)"""
    pazienti = Patient.query.order_by(Patient.nome.asc()).all()
    piani = Listino.query.filter_by(attivo=True).order_by(Listino.nome_prodotto.asc()).all()
    
    # Crea dizionario per JavaScript (sempre disponibile)
    piani_dict = {piano.id: {'prezzo': safe_float(piano.prezzo)} for piano in piani}

    if request.method == 'POST':
        try:
            patient_id = request.form['patient_id']
            listino_id = request.form['listino_id']
            data_inizio = request.form['data_inizio']
            metodo_pagamento = request.form['metodo_pagamento']
            sconto = safe_float(request.form.get('sconto'), 0)
            note = request.form.get('note')

            piano = Listino.query.get_or_404(listino_id)
            importo_finale = safe_float(piano.prezzo) - sconto

            nuova = Vendita(
                patient_id=patient_id,
                listino_id=listino_id,
                data_inizio=data_inizio,
                metodo_pagamento=metodo_pagamento,
                sconto=sconto,
                importo_finale=importo_finale,
                stato='pagato',
                note=note
            )

            db.session.add(nuova)
            db.session.commit()
            flash("Vendita registrata ✅", "success")
            return redirect(url_for('vendite.lista_vendite'))

        except Exception as e:
            db.session.rollback()
            flash(f"Errore durante la registrazione: {e}", "danger")
    
    return render_template('admin/vendita_nuova.html', pazienti=pazienti, piani=piani, piani_dict=piani_dict)


# ========================
# MODIFICA UNA VENDITA
# ========================
@vendite_bp.route('/modifica/<int:id>', methods=['GET', 'POST'])
@admin_required
def modifica_vendita(id):
    """Permette di modificare una vendita esistente"""
    vendita = Vendita.query.get_or_404(id)
    piani = Listino.query.filter_by(attivo=True).all()

    if request.method == 'POST':
        try:
            vendita.listino_id = request.form['listino_id']
            vendita.data_inizio = request.form['data_inizio']
            vendita.metodo_pagamento = request.form['metodo_pagamento']
            vendita.sconto = safe_float(request.form.get('sconto'), 0)
            vendita.stato = request.form['stato']
            vendita.note = request.form.get('note')
            
            # Ricalcola importo finale (prezzo - sconto)
            listino = Listino.query.get(vendita.listino_id)
            if listino:
                vendita.importo_finale = safe_float(listino.prezzo) - vendita.sconto
            
            db.session.commit()
            flash("Vendita aggiornata ✅", "success")
            return redirect(url_for('vendite.dashboard_economia'))
        except Exception as e:
            db.session.rollback()
            flash(f"Errore durante la modifica: {e}", "danger")

    return render_template('admin/vendita_modifica.html', vendita=vendita, piani=piani)


# ========================
# ELIMINA VENDITA
# ========================
@vendite_bp.route('/elimina/<int:id>', methods=['POST'])
@admin_required
def elimina_vendita(id):
    """Elimina una vendita"""
    vendita = Vendita.query.get_or_404(id)
    try:
        db.session.delete(vendita)
        db.session.commit()
        flash("Vendita eliminata ✅", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore durante eliminazione: {e}", "danger")

    return redirect(url_for('vendite.lista_vendite'))

# ========================
# DASHBOARD ECONOMIA
# ========================
@vendite_bp.route('/dashboard')
@admin_required
def dashboard_economia():
    """
    Vista generale delle vendite e contabilità.
    Mostra le vendite filtrabili per cliente o stato e il totale incassato.
    """
    nome = request.args.get('cliente')
    stato = request.args.get('stato')
    periodo = int(request.args.get('periodo', 30))  # Default 30 giorni

    # Query base
    query = Vendita.query.join(Patient).join(Listino)

    if nome:
        nome = f"%{nome.lower()}%"
        query = query.filter(
            db.func.lower(db.func.concat(Patient.nome, ' ', Patient.cognome)).like(nome)
        )

    if stato:
        query = query.filter(Vendita.stato == stato)

    vendite = query.order_by(Vendita.data_acquisto.desc()).all()
    totale_incassato = sum(v.importo_finale for v in vendite if v.stato == 'pagato')
    
    
    # Prepara dati per il grafico (periodo selezionato)
    from datetime import date, timedelta
    from collections import defaultdict
    
    oggi = date.today()
    giorni_fa = oggi - timedelta(days=periodo)
    
    # Raggruppa vendite per data e categoria
    vendite_per_data_categoria = {
        'nutrizione': defaultdict(float),
        'allenamento': defaultdict(float),
        'completo': defaultdict(float),
        '1to1': defaultdict(float)
    }
    
    for v in vendite:
        if v.stato == 'pagato' and v.data_acquisto:
            data = v.data_acquisto.date()
            if data >= giorni_fa:
                categoria = v.listino.categoria
                if categoria in vendite_per_data_categoria:
                    vendite_per_data_categoria[categoria][data] += safe_float(v.importo_finale)
    
    # Crea array per il grafico (tutti i giorni del periodo selezionato)
    date_labels = []
    importi_nutrizione = []
    importi_allenamento = []
    importi_completo = []
    importi_1to1 = []
    
    for i in range(periodo):
        data = oggi - timedelta(days=periodo-1-i)
        date_labels.append(data.strftime('%d/%m'))
        importi_nutrizione.append(vendite_per_data_categoria['nutrizione'].get(data, 0))
        importi_allenamento.append(vendite_per_data_categoria['allenamento'].get(data, 0))
        importi_completo.append(vendite_per_data_categoria['completo'].get(data, 0))
        importi_1to1.append(vendite_per_data_categoria['1to1'].get(data, 0))

    return render_template(
        'admin/economia.html',
        vendite=vendite,
        totale_incassato=totale_incassato,
        date_labels=date_labels,
        importi_nutrizione=importi_nutrizione,
        importi_allenamento=importi_allenamento,
        importi_completo=importi_completo,
        importi_1to1=importi_1to1,
        periodo=periodo
    )


# ========================
# REGISTRO ECONOMICO PAZIENTE
# ========================
@vendite_bp.route('/paziente/<int:patient_id>')
@admin_required
def registro_economico_paziente(patient_id):
    """
    Mostra il registro economico completo di un paziente specifico
    con tutti i pacchetti acquistati e grafico delle spese
    """
    paziente = Patient.query.get_or_404(patient_id)
    
    # Recupera tutte le vendite del paziente
    vendite_paziente = Vendita.query.filter_by(patient_id=patient_id).order_by(Vendita.data_acquisto.desc()).all()
    
    # Calcola statistiche
    totale_speso = sum(safe_float(v.importo_finale) for v in vendite_paziente if v.stato == 'pagato')
    totale_vendite = len(vendite_paziente)
    vendite_pagate = len([v for v in vendite_paziente if v.stato == 'pagato'])
    
    
    # Prepara dati per il grafico (ultimi 12 mesi)
    from datetime import date, timedelta
    from collections import defaultdict
    
    oggi = date.today()
    mesi_fa = oggi - timedelta(days=365)
    
    # Raggruppa vendite per mese e categoria
    vendite_per_mese_categoria = {
        'nutrizione': defaultdict(float),
        'allenamento': defaultdict(float),
        'completo': defaultdict(float),
        '1to1': defaultdict(float)
    }
    
    for v in vendite_paziente:
        if v.stato == 'pagato' and v.data_acquisto:
            data = v.data_acquisto.date()
            if data >= mesi_fa:
                categoria = v.listino.categoria
                mese_key = data.strftime('%Y-%m')
                if categoria in vendite_per_mese_categoria:
                    vendite_per_mese_categoria[categoria][mese_key] += safe_float(v.importo_finale)
    
    # Crea array per il grafico (ultimi 12 mesi, calendario)
    date_labels = []
    importi_nutrizione = []
    importi_allenamento = []
    importi_completo = []
    importi_1to1 = []

    y, m = oggi.year, oggi.month
    for i in range(11, -1, -1):
        mm = m - i
        yy = y
        while mm <= 0:
            mm += 12
            yy -= 1
        mese_key = f'{yy:04d}-{mm:02d}'
        date_labels.append(date(yy, mm, 1).strftime('%b %Y'))
        importi_nutrizione.append(vendite_per_mese_categoria['nutrizione'].get(mese_key, 0))
        importi_allenamento.append(vendite_per_mese_categoria['allenamento'].get(mese_key, 0))
        importi_completo.append(vendite_per_mese_categoria['completo'].get(mese_key, 0))
        importi_1to1.append(vendite_per_mese_categoria['1to1'].get(mese_key, 0))
    
    return render_template(
        'admin/registro_economico_paziente.html',
        paziente=paziente,
        vendite_paziente=vendite_paziente,
        totale_speso=totale_speso,
        totale_vendite=totale_vendite,
        vendite_pagate=vendite_pagate,
        date_labels=date_labels,
        importi_nutrizione=importi_nutrizione,
        importi_allenamento=importi_allenamento,
        importi_completo=importi_completo,
        importi_1to1=importi_1to1
    )