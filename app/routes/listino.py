from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.models.models import db, Listino

# ========================
# BLUEPRINT
# ========================
listino_bp = Blueprint('listino', __name__)


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
# ADMIN: GESTIONE LISTINO
# ========================
@listino_bp.route('/admin/listino')
@admin_required
def lista_listino_admin():
    """Mostra tutto il listino prezzi per modifica"""
    # Raggruppa per categoria
    nutrizione = Listino.query.filter_by(categoria='nutrizione').order_by(Listino.durata_mesi).all()
    allenamento = Listino.query.filter_by(categoria='allenamento').order_by(Listino.durata_mesi).all()
    completo = Listino.query.filter_by(categoria='completo').order_by(Listino.durata_mesi).all()
    uno_a_uno = Listino.query.filter_by(categoria='1to1').order_by(Listino.durata_mesi).all()
    
    return render_template('admin/listino_gestione.html',
                         nutrizione=nutrizione,
                         allenamento=allenamento,
                         completo=completo,
                         uno_a_uno=uno_a_uno)


# ========================
# ADMIN: MODIFICA PREZZO
# ========================
@listino_bp.route('/admin/listino/modifica/<int:listino_id>', methods=['GET', 'POST'])
@admin_required
def modifica_listino(listino_id):
    """Modifica un elemento del listino"""
    prodotto = Listino.query.get_or_404(listino_id)
    
    if request.method == 'POST':
        try:
            prodotto.nome_prodotto = request.form['nome_prodotto']
            prodotto.prezzo = request.form['prezzo']
            prodotto.check_inclusi = request.form.get('check_inclusi', 0)
            prodotto.note = request.form.get('note', '').strip() or None
            prodotto.attivo = 'attivo' in request.form
            
            db.session.commit()
            flash("Prodotto aggiornato ✅", "success")
            return redirect(url_for('listino.lista_listino_admin'))
        
        except Exception as e:
            db.session.rollback()
            flash(f"Errore durante l'aggiornamento: {e}", "danger")
    
    return render_template('admin/listino_modifica.html', prodotto=prodotto)


# ========================
# ADMIN: NUOVO PRODOTTO
# ========================
@listino_bp.route('/admin/listino/nuovo', methods=['GET', 'POST'])
@admin_required
def nuovo_listino():
    """Crea un nuovo prodotto nel listino"""
    if request.method == 'POST':
        try:
            nuovo = Listino(
                nome_prodotto=request.form['nome_prodotto'],
                categoria=request.form['categoria'],
                durata_mesi=request.form['durata_mesi'],
                prezzo=request.form['prezzo'],
                check_inclusi=request.form.get('check_inclusi', 0),
                note=request.form.get('note', '').strip() or None,
                attivo=True
            )
            
            db.session.add(nuovo)
            db.session.commit()
            flash("Prodotto aggiunto ✅", "success")
            return redirect(url_for('listino.lista_listino_admin'))
        
        except Exception as e:
            db.session.rollback()
            flash(f"Errore durante la creazione: {e}", "danger")
    
    return render_template('admin/listino_nuovo.html')


# ========================
# ADMIN: ELIMINA PRODOTTO
# ========================
@listino_bp.route('/admin/listino/elimina/<int:listino_id>', methods=['POST'])
@admin_required
def elimina_listino(listino_id):
    """Elimina un prodotto dal listino"""
    prodotto = Listino.query.get_or_404(listino_id)
    
    try:
        db.session.delete(prodotto)
        db.session.commit()
        flash("Prodotto eliminato ✅", "success")
    
    except Exception as e:
        db.session.rollback()
        flash(f"Errore durante l'eliminazione: {e}", "danger")
    
    return redirect(url_for('listino.lista_listino_admin'))


# ========================
# USER: VISUALIZZA LISTINO
# ========================
@listino_bp.route('/user/listino')
@user_required
def lista_listino_user():
    """Mostra il listino prezzi agli utenti"""
    # Solo prodotti attivi
    nutrizione = Listino.query.filter_by(categoria='nutrizione', attivo=True).order_by(Listino.durata_mesi).all()
    allenamento = Listino.query.filter_by(categoria='allenamento', attivo=True).order_by(Listino.durata_mesi).all()
    completo = Listino.query.filter_by(categoria='completo', attivo=True).order_by(Listino.durata_mesi).all()
    uno_a_uno = Listino.query.filter_by(categoria='1to1', attivo=True).order_by(Listino.durata_mesi).all()
    
    return render_template('user/listino.html',
                         nutrizione=nutrizione,
                         allenamento=allenamento,
                         completo=completo,
                         uno_a_uno=uno_a_uno)


# ========================
# PUBLIC: VISUALIZZA LISTINO (SENZA LOGIN)
# ========================
@listino_bp.route('/listino')
def lista_listino_public():
    """Mostra il listino prezzi pubblicamente"""
    # Solo prodotti attivi
    nutrizione = Listino.query.filter_by(categoria='nutrizione', attivo=True).order_by(Listino.durata_mesi).all()
    allenamento = Listino.query.filter_by(categoria='allenamento', attivo=True).order_by(Listino.durata_mesi).all()
    completo = Listino.query.filter_by(categoria='completo', attivo=True).order_by(Listino.durata_mesi).all()
    uno_a_uno = Listino.query.filter_by(categoria='1to1', attivo=True).order_by(Listino.durata_mesi).all()
    
    return render_template('public/listino.html',
                         nutrizione=nutrizione,
                         allenamento=allenamento,
                         completo=completo,
                         uno_a_uno=uno_a_uno)

