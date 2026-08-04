from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.models.models import db, Progresso, Patient
from datetime import datetime
import json
from app.utils.tenant import assert_resource_patient_tenant, get_tenant_patient_or_404


# ========================
# BLUEPRINT
# ========================
progressi_bp = Blueprint('progressi', __name__, url_prefix='/progressi')

# ========================
# FUNZIONI UTILI
# ========================
def admin_required(func):
    """Accesso solo per Enrico (admin)"""
    from functools import wraps
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get('role') not in ('admin', 'nutrizionista'):
            flash("Accesso riservato all’amministratore", "danger")
            return redirect(url_for('auth.login'))
        return func(*args, **kwargs)
    return wrapper


# ========================
# ADMIN: PROGRESSI DI UN PAZIENTE
# ========================
@progressi_bp.route('/admin/paziente/<int:patient_id>')
@admin_required
def progressi_paziente_admin(patient_id):
    paziente = get_tenant_patient_or_404(patient_id)
    # Ordina progressi per data check (più recenti prima)
    progressi = Progresso.query.filter_by(patient_id=patient_id).order_by(Progresso.data_check.desc()).all()
    return render_template(
        'admin/progressi_paziente.html',
        paziente=paziente,
        progressi=progressi
    )


# ========================
# ADMIN: CHECK NUTRIZIONISTA COMPLETO
# ========================
@progressi_bp.route('/admin/check_nutrizionista/<int:patient_id>', methods=['GET', 'POST'])
@admin_required
def check_nutrizionista_completo(patient_id):
    """Check completo del nutrizionista con tutte le misure per un paziente specifico"""
    paziente = get_tenant_patient_or_404(patient_id)

    if request.method == 'POST':
        try:
            data_check = request.form['data_check']
            
            # Gestione upload foto
            foto_path = None
            if 'foto_progresso' in request.files:
                foto_file = request.files['foto_progresso']
                if foto_file and foto_file.filename:
                    # Genera nome file sicuro
                    import os
                    import uuid
                    from werkzeug.utils import secure_filename
                    
                    filename = secure_filename(foto_file.filename)
                    unique_filename = f"{uuid.uuid4()}_{filename}"
                    foto_path = f"uploads/progressi/{unique_filename}"
                    
                    # Crea directory se non esiste
                    upload_dir = os.path.join('static', 'uploads', 'progressi')
                    os.makedirs(upload_dir, exist_ok=True)
                    
                    # Salva il file
                    foto_file.save(os.path.join('static', foto_path))
            
            # Crea il record Progresso per il check nutrizionista
            nuovo_progresso = Progresso(
                patient_id=patient_id,
                data_check=data_check,
                tipo_check='nutrizionista',
                peso_settimanale=float(request.form.get('peso_settimanale')) if request.form.get('peso_settimanale') else None,
                frequenza_allenamenti=request.form.get('frequenza_allenamenti'),
                foto_path=foto_path,
                aderenza=int(request.form.get('aderenza')) if request.form.get('aderenza') else None,
                check_richiesta=bool(request.form.get('check_richiesta'))
            )
            
            db.session.add(nuovo_progresso)
            db.session.flush()  # Per ottenere l'ID del progresso
            
            # MISURE ANTROPOMETRICHE
            misure_data = {
                'circonferenza_braccio': request.form.get('circonferenza_braccio'),
                'circonferenza_spalle': request.form.get('circonferenza_spalle'),
                'circonferenza_torace': request.form.get('circonferenza_torace'),
                'circonferenza_vita': request.form.get('circonferenza_vita'),
                'circonferenza_fianchi': request.form.get('circonferenza_fianchi'),
                'circonferenza_coscia': request.form.get('circonferenza_coscia'),
                'circonferenza_polpaccio': request.form.get('circonferenza_polpaccio'),
                'plica_addominale': request.form.get('plica_addominale'),
                'plica_tricipitale': request.form.get('plica_tricipitale'),
                'plica_soprailiaca': request.form.get('plica_soprailiaca'),
                'plica_sottoscapolare': request.form.get('plica_sottoscapolare'),
                'plica_cutanea_coscia': request.form.get('plica_cutanea_coscia'),
                'note_misure': request.form.get('note_misure', '').strip()
            }
            
            # Crea misure antropometriche solo se almeno un campo è compilato
            if any(misure_data.values()):
                from app.models.models import MisureAntropometriche
                misure = MisureAntropometriche(
                    patient_id=patient_id,
                    progresso_id=nuovo_progresso.id,
                    data_misurazione=data_check,
                    circonferenza_braccio=float(misure_data['circonferenza_braccio']) if misure_data['circonferenza_braccio'] else None,
                    circonferenza_spalle=float(misure_data['circonferenza_spalle']) if misure_data['circonferenza_spalle'] else None,
                    circonferenza_torace=float(misure_data['circonferenza_torace']) if misure_data['circonferenza_torace'] else None,
                    circonferenza_vita=float(misure_data['circonferenza_vita']) if misure_data['circonferenza_vita'] else None,
                    circonferenza_fianchi=float(misure_data['circonferenza_fianchi']) if misure_data['circonferenza_fianchi'] else None,
                    circonferenza_coscia=float(misure_data['circonferenza_coscia']) if misure_data['circonferenza_coscia'] else None,
                    circonferenza_polpaccio=float(misure_data['circonferenza_polpaccio']) if misure_data['circonferenza_polpaccio'] else None,
                    plica_addominale=float(misure_data['plica_addominale']) if misure_data['plica_addominale'] else None,
                    plica_tricipitale=float(misure_data['plica_tricipitale']) if misure_data['plica_tricipitale'] else None,
                    plica_soprailiaca=float(misure_data['plica_soprailiaca']) if misure_data['plica_soprailiaca'] else None,
                    plica_sottoscapolare=float(misure_data['plica_sottoscapolare']) if misure_data['plica_sottoscapolare'] else None,
                    plica_cutanea_coscia=float(misure_data['plica_cutanea_coscia']) if misure_data['plica_cutanea_coscia'] else None,
                    note=misure_data['note_misure'] if misure_data['note_misure'] else None
                )
                db.session.add(misure)
            
            # COMPOSIZIONE CORPOREA
            composizione_data = {
                'grasso_corporeo': request.form.get('grasso_corporeo'),
                'massa_muscolare': request.form.get('massa_muscolare'),
                'grasso_viscerale': request.form.get('grasso_viscerale'),
                'tbw': request.form.get('tbw'),
                'tasso_metabolico_basale': request.form.get('tasso_metabolico_basale'),
                'eta_metabolica': request.form.get('eta_metabolica'),
                'punteggio_postura': request.form.get('punteggio_postura'),
                'massa_ossea': request.form.get('massa_ossea'),
                'bmi': request.form.get('bmi'),
                'note_composizione': request.form.get('note_composizione', '').strip()
            }
            
            # Crea composizione corporea solo se almeno un campo è compilato
            if any(composizione_data.values()):
                from app.models.models import ComposizioneCorporea
                composizione = ComposizioneCorporea(
                    patient_id=patient_id,
                    progresso_id=nuovo_progresso.id,
                    data_misurazione=data_check,
                    grasso_corporeo=float(composizione_data['grasso_corporeo']) if composizione_data['grasso_corporeo'] else None,
                    massa_muscolare=float(composizione_data['massa_muscolare']) if composizione_data['massa_muscolare'] else None,
                    grasso_viscerale=float(composizione_data['grasso_viscerale']) if composizione_data['grasso_viscerale'] else None,
                    tbw=float(composizione_data['tbw']) if composizione_data['tbw'] else None,
                    tasso_metabolico_basale=int(composizione_data['tasso_metabolico_basale']) if composizione_data['tasso_metabolico_basale'] else None,
                    eta_metabolica=int(composizione_data['eta_metabolica']) if composizione_data['eta_metabolica'] else None,
                    punteggio_postura=int(composizione_data['punteggio_postura']) if composizione_data['punteggio_postura'] else None,
                    massa_ossea=float(composizione_data['massa_ossea']) if composizione_data['massa_ossea'] else None,
                    bmi=float(composizione_data['bmi']) if composizione_data['bmi'] else None,
                    note=composizione_data['note_composizione'] if composizione_data['note_composizione'] else None
                )
                db.session.add(composizione)
            
            db.session.commit()
            flash("Check nutrizionista completo aggiunto ✅", "success")
            return redirect(url_for('patients.dettaglio_paziente', patient_id=patient_id))

        except Exception as e:
            db.session.rollback()
            flash(f"Errore durante il salvataggio: {e}", "danger")

    return render_template('admin/check_nutrizionista_completo.html', paziente=paziente)


# ========================
# ADMIN: DETTAGLIO CHECK
# ========================
@progressi_bp.route('/admin/dettaglio/<int:progresso_id>')
@admin_required
def dettaglio_check(progresso_id):
    """Visualizza i dettagli completi di un check"""
    progresso = Progresso.query.get_or_404(progresso_id)
    assert_resource_patient_tenant(progresso)
    paziente = progresso.patient
    
    # Carica le misure associate se esistono
    misure_antropometriche = None
    composizione_corporea = None
    
    if progresso.tipo_check == 'nutrizionista':
        # Prendi il primo elemento se esiste (dovrebbe essere sempre uno per check)
        misure_antropometriche = progresso.misure_antropometriche_rel[0] if progresso.misure_antropometriche_rel else None
        composizione_corporea = progresso.composizione_corporea_rel[0] if progresso.composizione_corporea_rel else None
    
    return render_template('admin/dettaglio_check.html', 
                         progresso=progresso, 
                         paziente=paziente,
                         misure_antropometriche=misure_antropometriche,
                         composizione_corporea=composizione_corporea)


# ========================
# ADMIN: MODIFICA CHECK NUTRIZIONISTA ESISTENTE
# ========================
@progressi_bp.route('/admin/modifica_check/<int:progresso_id>', methods=['GET', 'POST'])
@admin_required
def modifica_check_nutrizionista(progresso_id):
    """Modifica un check nutrizionista esistente"""
    progresso = Progresso.query.get_or_404(progresso_id)
    assert_resource_patient_tenant(progresso)
    paziente = progresso.patient
    
    # Verifica che sia un check nutrizionista
    if progresso.tipo_check != 'nutrizionista':
        flash("Puoi modificare solo i check del nutrizionista", "danger")
        return redirect(url_for('progressi.progressi_paziente_admin', patient_id=paziente.id))
    
    if request.method == 'POST':
        try:
            # Aggiorna i dati base del progresso
            progresso.data_check = request.form['data_check']
            progresso.peso_settimanale = float(request.form.get('peso_settimanale')) if request.form.get('peso_settimanale') else None
            progresso.frequenza_allenamenti = request.form.get('frequenza_allenamenti')
            progresso.aderenza = int(request.form.get('aderenza')) if request.form.get('aderenza') else None
            progresso.check_richiesta = bool(request.form.get('check_richiesta'))
            
            # Gestione upload foto
            if 'foto_progresso' in request.files:
                foto_file = request.files['foto_progresso']
                if foto_file and foto_file.filename:
                    import os
                    import uuid
                    from werkzeug.utils import secure_filename
                    
                    filename = secure_filename(foto_file.filename)
                    unique_filename = f"{uuid.uuid4()}_{filename}"
                    foto_path = f"uploads/progressi/{unique_filename}"
                    
                    # Crea directory se non esiste
                    upload_dir = os.path.join('static', 'uploads', 'progressi')
                    os.makedirs(upload_dir, exist_ok=True)
                    
                    # Salva il file
                    foto_file.save(os.path.join('static', foto_path))
                    progresso.foto_path = foto_path
            
            # Aggiorna o crea misure antropometriche
            misure_data = {
                'circonferenza_braccio': request.form.get('circonferenza_braccio'),
                'circonferenza_spalle': request.form.get('circonferenza_spalle'),
                'circonferenza_torace': request.form.get('circonferenza_torace'),
                'circonferenza_vita': request.form.get('circonferenza_vita'),
                'circonferenza_fianchi': request.form.get('circonferenza_fianchi'),
                'circonferenza_coscia': request.form.get('circonferenza_coscia'),
                'circonferenza_polpaccio': request.form.get('circonferenza_polpaccio'),
                'plica_addominale': request.form.get('plica_addominale'),
                'plica_tricipitale': request.form.get('plica_tricipitale'),
                'plica_soprailiaca': request.form.get('plica_soprailiaca'),
                'plica_sottoscapolare': request.form.get('plica_sottoscapolare'),
                'plica_cutanea_coscia': request.form.get('plica_cutanea_coscia'),
                'note_misure': request.form.get('note_misure', '').strip()
            }
            
            # Elimina misure esistenti
            if progresso.misure_antropometriche_rel:
                for misura in progresso.misure_antropometriche_rel:
                    db.session.delete(misura)
            
            # Crea nuove misure se almeno un campo è compilato
            if any(misure_data.values()):
                from app.models.models import MisureAntropometriche
                misure = MisureAntropometriche(
                    patient_id=paziente.id,
                    progresso_id=progresso.id,
                    data_misurazione=progresso.data_check,
                    circonferenza_braccio=float(misure_data['circonferenza_braccio']) if misure_data['circonferenza_braccio'] else None,
                    circonferenza_spalle=float(misure_data['circonferenza_spalle']) if misure_data['circonferenza_spalle'] else None,
                    circonferenza_torace=float(misure_data['circonferenza_torace']) if misure_data['circonferenza_torace'] else None,
                    circonferenza_vita=float(misure_data['circonferenza_vita']) if misure_data['circonferenza_vita'] else None,
                    circonferenza_fianchi=float(misure_data['circonferenza_fianchi']) if misure_data['circonferenza_fianchi'] else None,
                    circonferenza_coscia=float(misure_data['circonferenza_coscia']) if misure_data['circonferenza_coscia'] else None,
                    circonferenza_polpaccio=float(misure_data['circonferenza_polpaccio']) if misure_data['circonferenza_polpaccio'] else None,
                    plica_addominale=float(misure_data['plica_addominale']) if misure_data['plica_addominale'] else None,
                    plica_tricipitale=float(misure_data['plica_tricipitale']) if misure_data['plica_tricipitale'] else None,
                    plica_soprailiaca=float(misure_data['plica_soprailiaca']) if misure_data['plica_soprailiaca'] else None,
                    plica_sottoscapolare=float(misure_data['plica_sottoscapolare']) if misure_data['plica_sottoscapolare'] else None,
                    plica_cutanea_coscia=float(misure_data['plica_cutanea_coscia']) if misure_data['plica_cutanea_coscia'] else None,
                    note=misure_data['note_misure'] if misure_data['note_misure'] else None
                )
                db.session.add(misure)
            
            # Aggiorna o crea composizione corporea
            composizione_data = {
                'grasso_corporeo': request.form.get('grasso_corporeo'),
                'massa_muscolare': request.form.get('massa_muscolare'),
                'grasso_viscerale': request.form.get('grasso_viscerale'),
                'tbw': request.form.get('tbw'),
                'tasso_metabolico_basale': request.form.get('tasso_metabolico_basale'),
                'eta_metabolica': request.form.get('eta_metabolica'),
                'punteggio_postura': request.form.get('punteggio_postura'),
                'massa_ossea': request.form.get('massa_ossea'),
                'bmi': request.form.get('bmi'),
                'note_composizione': request.form.get('note_composizione', '').strip()
            }
            
            # Elimina composizione esistente
            if progresso.composizione_corporea_rel:
                for comp in progresso.composizione_corporea_rel:
                    db.session.delete(comp)
            
            # Crea nuova composizione se almeno un campo è compilato
            if any(composizione_data.values()):
                from app.models.models import ComposizioneCorporea
                composizione = ComposizioneCorporea(
                    patient_id=paziente.id,
                    progresso_id=progresso.id,
                    data_misurazione=progresso.data_check,
                    grasso_corporeo=float(composizione_data['grasso_corporeo']) if composizione_data['grasso_corporeo'] else None,
                    massa_muscolare=float(composizione_data['massa_muscolare']) if composizione_data['massa_muscolare'] else None,
                    grasso_viscerale=float(composizione_data['grasso_viscerale']) if composizione_data['grasso_viscerale'] else None,
                    tbw=float(composizione_data['tbw']) if composizione_data['tbw'] else None,
                    tasso_metabolico_basale=int(composizione_data['tasso_metabolico_basale']) if composizione_data['tasso_metabolico_basale'] else None,
                    eta_metabolica=int(composizione_data['eta_metabolica']) if composizione_data['eta_metabolica'] else None,
                    punteggio_postura=int(composizione_data['punteggio_postura']) if composizione_data['punteggio_postura'] else None,
                    massa_ossea=float(composizione_data['massa_ossea']) if composizione_data['massa_ossea'] else None,
                    bmi=float(composizione_data['bmi']) if composizione_data['bmi'] else None,
                    note=composizione_data['note_composizione'] if composizione_data['note_composizione'] else None
                )
                db.session.add(composizione)
            
            db.session.commit()
            flash("Check nutrizionista aggiornato ✅", "success")
            return redirect(url_for('progressi.dettaglio_check', progresso_id=progresso_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f"Errore durante l'aggiornamento: {e}", "danger")
    
    # Carica i dati esistenti per la modifica
    misure_antropometriche = progresso.misure_antropometriche_rel[0] if progresso.misure_antropometriche_rel else None
    composizione_corporea = progresso.composizione_corporea_rel[0] if progresso.composizione_corporea_rel else None
    
    return render_template('admin/modifica_check_nutrizionista.html', 
                         progresso=progresso, 
                         paziente=paziente,
                         misure_antropometriche=misure_antropometriche,
                         composizione_corporea=composizione_corporea)