"""Landing pubblica: richiesta appuntamento senza login."""

from datetime import datetime
from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.models.models import Appuntamento, Patient, RichiestaAppuntamento, db
from app.services.agenda_service import AgendaService
from app.utils.db_schema import ensure_richieste_appuntamento_schema
from app.utils.helpers import normalize_phone

prenota_public_bp = Blueprint("prenota_public", __name__)

TIPI_PUBBLICI = {
    "altro": "Prima consulenza",
    "check": "Check",
    "allenamento_1to1": "Allenamento 1to1",
}


def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Accesso non autorizzato", "danger")
            return redirect(url_for("auth.login"))
        return func(*args, **kwargs)

    return wrapper


@prenota_public_bp.before_request
def _ensure_schema():
    ensure_richieste_appuntamento_schema()


def _trova_paziente_per_telefono(telefono: str):
    """Match paziente esistente confrontando numeri normalizzati."""
    norm = normalize_phone(telefono)
    if not norm:
        return None
    for p in Patient.query.filter(Patient.telefono.isnot(None)).all():
        if normalize_phone(p.telefono) == norm:
            return p
    return None


# ========================
# PUBBLICO: LANDING PRENOTA (root)
# ========================
@prenota_public_bp.route("/", methods=["GET", "POST"])
def prenota_landing():
    """Landing sulla root: richiesta appuntamento senza login."""
    if request.method == "GET" and "role" in session:
        if session["role"] == "admin":
            return redirect(url_for("dashboard.admin_dashboard"))
        if session["role"] == "user":
            return redirect(url_for("dashboard.user_dashboard"))

    if request.method == "POST":
        try:
            nome = (request.form.get("nome") or "").strip()
            cognome = (request.form.get("cognome") or "").strip()
            telefono = (request.form.get("telefono") or "").strip()
            email = (request.form.get("email") or "").strip() or None
            data_str = request.form.get("data_appuntamento") or ""
            tipo = request.form.get("tipo") or "altro"
            note = (request.form.get("note") or "").strip() or None

            if not nome or not cognome or not telefono or not data_str:
                flash("Compila tutti i campi obbligatori", "warning")
                return redirect(url_for("prenota_public.prenota_landing"))

            if tipo not in TIPI_PUBBLICI:
                tipo = "altro"

            if len(normalize_phone(telefono)) < 9:
                flash("Inserisci un numero di telefono valido", "warning")
                return redirect(url_for("prenota_public.prenota_landing"))

            data_appuntamento = datetime.strptime(data_str, "%Y-%m-%d %H:%M:%S")
            if not AgendaService.is_slot_disponibile(data_appuntamento):
                flash("Questo orario non è più disponibile. Scegline un altro.", "warning")
                return redirect(url_for("prenota_public.prenota_landing"))

            paziente = _trova_paziente_per_telefono(telefono)

            if paziente:
                nuovo = Appuntamento(
                    patient_id=paziente.id,
                    created_by="user",
                    data_appuntamento=data_appuntamento,
                    tipo=tipo,
                    stato="in_attesa",
                    note=note,
                )
                db.session.add(nuovo)
                db.session.commit()
                flash(
                    "Richiesta inviata. Il nutrizionista la confermerà a breve.",
                    "success",
                )
            else:
                richiesta = RichiestaAppuntamento(
                    nome=nome,
                    cognome=cognome,
                    telefono=telefono,
                    email=email,
                    data_richiesta=data_appuntamento,
                    tipo=tipo,
                    note=note,
                    stato="in_attesa",
                )
                db.session.add(richiesta)
                db.session.commit()
                flash(
                    "Richiesta inviata. Ti contatteremo per confermare l'appuntamento.",
                    "success",
                )

            return redirect(url_for("prenota_public.prenota_landing", ok=1))

        except ValueError:
            flash("Data o orario non validi", "danger")
            return redirect(url_for("prenota_public.prenota_landing"))
        except Exception as e:
            db.session.rollback()
            flash(f"Errore durante l'invio: {e}", "danger")
            return redirect(url_for("prenota_public.prenota_landing"))

    slot_liberi = AgendaService.slot_liberi_per_select()
    return render_template(
        "public/prenota.html",
        slot_liberi=slot_liberi,
        tipi=TIPI_PUBBLICI,
        inviato=request.args.get("ok") == "1",
    )


@prenota_public_bp.route("/prenota", methods=["GET", "POST"])
def prenota_legacy_redirect():
    """Compatibilità: /prenota → /"""
    if request.method == "POST":
        return prenota_landing()
    qs = request.query_string.decode() if request.query_string else ""
    target = url_for("prenota_public.prenota_landing")
    if qs:
        target = f"{target}?{qs}"
    return redirect(target, code=301)


# ========================
# ADMIN: GESTIONE RICHIESTE
# ========================
@prenota_public_bp.route("/appuntamenti/admin/richieste")
@admin_required
def lista_richieste_admin():
    """Elenco richieste pubbliche in attesa / recenti."""
    richieste = (
        RichiestaAppuntamento.query.order_by(
            RichiestaAppuntamento.stato.asc(),
            RichiestaAppuntamento.data_richiesta.asc(),
        )
        .limit(100)
        .all()
    )
    pazienti = Patient.query.order_by(Patient.cognome.asc(), Patient.nome.asc()).all()
    return render_template(
        "admin/richieste_appuntamento.html",
        richieste=richieste,
        pazienti=pazienti,
        tipi_label=TIPI_PUBBLICI,
    )


@prenota_public_bp.route(
    "/appuntamenti/admin/richieste/<int:id>/accetta", methods=["POST"]
)
@admin_required
def accetta_richiesta(id):
    """Converte una richiesta in appuntamento collegato a un paziente."""
    richiesta = RichiestaAppuntamento.query.get_or_404(id)
    if richiesta.stato != "in_attesa":
        flash("Questa richiesta è già stata gestita", "warning")
        return redirect(url_for("prenota_public.lista_richieste_admin"))

    try:
        patient_id = int(request.form.get("patient_id") or 0)
        paziente = Patient.query.get(patient_id)
        if not paziente:
            flash("Seleziona un paziente in anagrafica", "warning")
            return redirect(url_for("prenota_public.lista_richieste_admin"))

        if not AgendaService.is_slot_disponibile(
            richiesta.data_richiesta, escludi_richiesta_id=richiesta.id
        ):
            flash("Lo slot non è più disponibile", "warning")
            return redirect(url_for("prenota_public.lista_richieste_admin"))

        nuovo = Appuntamento(
            patient_id=paziente.id,
            created_by="Enrico",
            data_appuntamento=richiesta.data_richiesta,
            tipo=richiesta.tipo,
            stato="confermato",
            note=richiesta.note,
        )
        db.session.add(nuovo)
        db.session.flush()

        richiesta.stato = "accettata"
        richiesta.patient_id = paziente.id
        richiesta.appuntamento_id = nuovo.id
        db.session.commit()

        from app.routes.whatsapp.triggers import safe_trigger_appuntamento_stato

        safe_trigger_appuntamento_stato(nuovo, "confermato")

        flash("Richiesta accettata: appuntamento creato ✅", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore: {e}", "danger")

    return redirect(url_for("prenota_public.lista_richieste_admin"))


@prenota_public_bp.route(
    "/appuntamenti/admin/richieste/<int:id>/rifiuta", methods=["POST"]
)
@admin_required
def rifiuta_richiesta(id):
    """Rifiuta una richiesta e libera lo slot."""
    richiesta = RichiestaAppuntamento.query.get_or_404(id)
    if richiesta.stato != "in_attesa":
        flash("Questa richiesta è già stata gestita", "warning")
        return redirect(url_for("prenota_public.lista_richieste_admin"))

    try:
        richiesta.stato = "rifiutata"
        db.session.commit()
        flash("Richiesta rifiutata, slot liberato", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore: {e}", "danger")

    return redirect(url_for("prenota_public.lista_richieste_admin"))
