from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from models import db, SlotDisponibilita
from datetime import datetime

# ========================
# BLUEPRINT
# ========================
slot_bp = Blueprint('slot', __name__, url_prefix='/admin/slot')


# ========================
# FUNZIONI UTILI
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


# ========================
# ADMIN: LISTA SLOT DISPONIBILI
# ========================
@slot_bp.route('/')
@admin_required
def lista_slot():
    """Redirect alla pagina agenda unificata"""
    return redirect(url_for('agenda.agenda_unificata'))


# ========================
# ADMIN: AGGIUNGI NUOVO SLOT
# ========================
@slot_bp.route('/nuovo', methods=['GET', 'POST'])
@admin_required
def nuovo_slot():
    """Crea un nuovo slot disponibile"""
    now = datetime.now()
    
    if request.method == 'POST':
        try:
            data_ora_str = request.form['data_ora']
            note = request.form.get('note', '').strip()
            
            # Converte stringa in datetime
            data_ora = datetime.strptime(data_ora_str, '%Y-%m-%dT%H:%M')
            
            # Verifica che lo slot non esista già
            esistente = SlotDisponibilita.query.filter_by(data_ora=data_ora).first()
            if esistente:
                flash("Questo slot esiste già!", "warning")
                return redirect(request.url)
            
            # Crea nuovo slot
            nuovo = SlotDisponibilita(
                data_ora=data_ora,
                attivo=True,
                note=note if note else None
            )
            
            db.session.add(nuovo)
            db.session.commit()
            
            flash("Slot aggiunto con successo ✅", "success")
            return redirect(url_for('agenda.agenda_unificata'))
        
        except ValueError:
            flash("Formato data non valido", "danger")
        except Exception as e:
            db.session.rollback()
            flash(f"Errore durante la creazione: {e}", "danger")
    
    return render_template('admin/slot_nuovo.html', now=now)


# ========================
# ADMIN: ATTIVA/DISATTIVA SLOT
# ========================
@slot_bp.route('/toggle/<int:slot_id>', methods=['POST'])
@admin_required
def toggle_slot(slot_id):
    """Attiva o disattiva uno slot"""
    slot = SlotDisponibilita.query.get_or_404(slot_id)
    
    try:
        slot.attivo = not slot.attivo
        db.session.commit()
        
        stato = "attivato" if slot.attivo else "disattivato"
        flash(f"Slot {stato} ✅", "success")
    
    except Exception as e:
        db.session.rollback()
        flash(f"Errore: {e}", "danger")
    
    return redirect(url_for('agenda.agenda_unificata'))


# ========================
# ADMIN: ELIMINA SLOT
# ========================
@slot_bp.route('/elimina/<int:slot_id>', methods=['POST'])
@admin_required
def elimina_slot(slot_id):
    """Elimina uno slot"""
    slot = SlotDisponibilita.query.get_or_404(slot_id)
    
    try:
        db.session.delete(slot)
        db.session.commit()
        flash("Slot eliminato ✅", "success")
    
    except Exception as e:
        db.session.rollback()
        flash(f"Errore durante l'eliminazione: {e}", "danger")
    
    return redirect(url_for('agenda.agenda_unificata'))


# ========================
# ADMIN: AGGIUNGI MULTIPLI SLOT (HELPER)
# ========================
@slot_bp.route('/genera', methods=['GET', 'POST'])
@admin_required
def genera_slot():
    """Genera più slot in batch (es: tutti i lunedì e mercoledì ore 10-12)"""
    if request.method == 'POST':
        try:
            data_inizio = request.form.get('data_inizio')
            data_fine = request.form.get('data_fine')
            giorni_settimana = request.form.getlist('giorni')  # es: ['0', '2'] per lunedì e mercoledì
            orari = request.form.getlist('orari')  # es: ['10:00', '11:00', '12:00']
            note = request.form.get('note', '')
            
            # Validazione
            if not data_inizio or not data_fine:
                flash("Inserisci data inizio e data fine", "danger")
                return render_template('admin/slot_genera.html', now=datetime.now())
            
            if not giorni_settimana:
                flash("Seleziona almeno un giorno della settimana", "danger")
                return render_template('admin/slot_genera.html', now=datetime.now())
            
            if not orari:
                flash("Seleziona almeno un orario", "danger")
                return render_template('admin/slot_genera.html', now=datetime.now())
            
            from datetime import timedelta
            
            data_inizio_dt = datetime.strptime(data_inizio, '%Y-%m-%d')
            data_fine_dt = datetime.strptime(data_fine, '%Y-%m-%d')
            
            slot_creati = 0
            data_corrente = data_inizio_dt
            
            while data_corrente <= data_fine_dt:
                # Controlla se il giorno della settimana è tra quelli selezionati
                if str(data_corrente.weekday()) in giorni_settimana:
                    for orario_str in orari:
                        ora, minuti = map(int, orario_str.split(':'))
                        data_ora = data_corrente.replace(hour=ora, minute=minuti, second=0, microsecond=0)
                        
                        # Verifica che lo slot non esista già
                        esistente = SlotDisponibilita.query.filter_by(data_ora=data_ora).first()
                        if not esistente:
                            nuovo = SlotDisponibilita(
                                data_ora=data_ora,
                                attivo=True,
                                note=note if note else None
                            )
                            db.session.add(nuovo)
                            slot_creati += 1
                
                data_corrente += timedelta(days=1)
            
            db.session.commit()
            flash(f"{slot_creati} slot creati con successo ✅", "success")
            return redirect(url_for('agenda.agenda_unificata'))
        
        except Exception as e:
            db.session.rollback()
            flash(f"Errore durante la generazione: {e}", "danger")
    
    return render_template('admin/slot_genera.html', now=datetime.now())

