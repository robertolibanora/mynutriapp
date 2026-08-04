"""Landing pubblica: richiesta appuntamento senza login (fuori dalla root).

Il tenant è identificato esclusivamente da ``studio_slug`` nell'URL
``/prenota/<studio_slug>``. ``/prenota`` senza slug è neutro e non crea prenotazioni.
"""

from datetime import datetime
from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.models.diario import Utente
from app.models.enums import UtenteRuolo
from app.models.models import Appuntamento, Patient, RichiestaAppuntamento, db
from app.services.agenda_service import AgendaService
from app.services.licensing_service import PlanLimitError
from app.services.gdpr_service import apply_consents
from app.services.paziente_service import crea_paziente_provvisorio
from app.utils.db_schema import (
    ensure_gdpr_schema,
    ensure_patient_stato_schema,
    ensure_richieste_appuntamento_schema,
)
from app.utils.helpers import normalize_phone, slugify_studio_name
from app.utils.tenant import assert_patient_tenant, require_tenant, tenant_filter_enabled

prenota_public_bp = Blueprint("prenota_public", __name__)

TIPI_PUBBLICI = {
    "altro": "Prima consulenza",
    "check": "Check",
    "allenamento_1to1": "Allenamento 1to1",
}


@prenota_public_bp.before_request
def _ensure_schema():
    ensure_patient_stato_schema()
    ensure_gdpr_schema()
    ensure_richieste_appuntamento_schema()


def _utente_by_slug(slug: str) -> Utente | None:
    slug = slugify_studio_name(slug)
    if not slug:
        return None
    return Utente.query.filter_by(
        public_slug=slug, ruolo=UtenteRuolo.NUTRIZIONISTA.value, attivo=True
    ).first()


def _prenota_redirect(utente: Utente, **kwargs):
    """Redirect verso /prenota/<studio_slug> (tenant obbligatorio)."""
    slug = utente.studio_slug or utente.public_slug
    if not slug:
        flash("Link di prenotazione non configurato per questo studio.", "warning")
        return redirect(url_for("prenota_public.prenota_landing"))
    return redirect(
        url_for("prenota_public.prenota_by_slug", slug=slug, **kwargs)
    )


def _trova_paziente_per_telefono(telefono: str, nutrizionista_id: int | None = None):
    """Match paziente esistente confrontando numeri normalizzati (scoped al tenant)."""
    norm = normalize_phone(telefono)
    if not norm:
        return None
    q = Patient.query.filter(Patient.telefono.isnot(None))
    if nutrizionista_id is not None:
        q = q.filter_by(nutrizionista_id=nutrizionista_id)
    for p in q.all():
        if normalize_phone(p.telefono) == norm:
            return p
    return None


def _studio_display_name(utente: Utente) -> str:
    return (
        (getattr(utente, "studio_nome", None) or "").strip()
        or (utente.studio_slug or utente.public_slug or "").replace("-", " ").title()
        or f"{utente.nome} {utente.cognome}".strip()
    )


def _render_prenota(utente: Utente | None, *, inviato: bool = False, status: int = 200):
    if utente is None:
        return (
            render_template(
                "public/prenota_neutra.html",
                message="Link di prenotazione non valido o non più disponibile.",
            ),
            status,
        )

    tenant_id = int(utente.id)
    slot_liberi = AgendaService.slot_liberi_per_select(utente_id=tenant_id)
    studio_slug = utente.studio_slug or utente.public_slug
    return render_template(
        "public/prenota.html",
        slot_liberi=slot_liberi,
        tipi=TIPI_PUBBLICI,
        inviato=inviato,
        nutrizionista=utente,
        studio_nome=_studio_display_name(utente),
        studio_slug=studio_slug,
        public_slug=studio_slug,  # compat template legacy
    )


def _handle_prenota_post(utente: Utente):
    tenant_id = int(utente.id)
    try:
        nome = (request.form.get("nome") or "").strip()
        cognome = (request.form.get("cognome") or "").strip()
        telefono = (request.form.get("telefono") or "").strip()
        email = (request.form.get("email") or "").strip() or None
        altezza_raw = (request.form.get("altezza_cm") or "").strip()
        peso_raw = (request.form.get("peso_iniziale") or "").strip()
        data_str = request.form.get("data_appuntamento") or ""
        tipo = request.form.get("tipo") or "altro"
        note = (request.form.get("note") or "").strip() or None

        if not nome or not cognome or not telefono or not data_str or not altezza_raw or not peso_raw:
            flash("Compila tutti i campi obbligatori", "warning")
            return _prenota_redirect(utente)

        if not request.form.get("consenso_privacy"):
            flash("Il consenso privacy è obbligatorio", "warning")
            return _prenota_redirect(utente)

        try:
            altezza_cm = int(float(altezza_raw.replace(",", ".")))
            peso_iniziale = float(peso_raw.replace(",", "."))
        except ValueError:
            flash("Altezza e peso devono essere numerici", "warning")
            return _prenota_redirect(utente)

        if not (100 <= altezza_cm <= 250):
            flash("Inserisci un'altezza valida (100–250 cm)", "warning")
            return _prenota_redirect(utente)
        if not (30 <= peso_iniziale <= 300):
            flash("Inserisci un peso valido (30–300 kg)", "warning")
            return _prenota_redirect(utente)

        if tipo not in TIPI_PUBBLICI:
            tipo = "altro"

        if len(normalize_phone(telefono)) < 9:
            flash("Inserisci un numero di telefono valido", "warning")
            return _prenota_redirect(utente)

        data_appuntamento = datetime.strptime(data_str, "%Y-%m-%d %H:%M:%S")
        if not AgendaService.is_slot_disponibile(data_appuntamento, utente_id=tenant_id):
            flash("Questo orario non è più disponibile. Scegline un altro.", "warning")
            return _prenota_redirect(utente)

        note_finale = note
        if email:
            note_finale = f"Email: {email}" + (f"\n{note}" if note else "")

        paziente = _trova_paziente_per_telefono(telefono, nutrizionista_id=tenant_id)

        if not paziente:
            paziente = crea_paziente_provvisorio(
                nome,
                cognome,
                telefono,
                altezza_cm=altezza_cm,
                peso_iniziale=peso_iniziale,
                nutrizionista_id=tenant_id,
            )
            # Pubblico: non può accedere finché non approvato / invitato
            paziente.account_status = "disabled"
            db.session.add(paziente)
            db.session.flush()
        else:
            if paziente.stato_cliente == "non_attivo":
                paziente.stato_cliente = "provvisorio"
            if nome and paziente.nome != nome:
                paziente.nome = nome
            if cognome and paziente.cognome != cognome:
                paziente.cognome = cognome
            if paziente.stato_cliente == "provvisorio" or paziente.altezza_cm is None:
                paziente.altezza_cm = altezza_cm
            if paziente.stato_cliente == "provvisorio" or paziente.peso_iniziale is None:
                paziente.peso_iniziale = peso_iniziale

        if email:
            paziente.email = email
        apply_consents(
            paziente,
            consenso_privacy=True,
            consenso_marketing=bool(request.form.get("consenso_marketing")),
        )

        nuovo = Appuntamento(
            patient_id=paziente.id,
            utente_id=tenant_id,
            created_by="user",
            data_appuntamento=data_appuntamento,
            tipo=tipo,
            stato="in_attesa",
            note=note_finale,
        )
        db.session.add(nuovo)
        db.session.commit()
        flash(
            "Richiesta inviata. Il nutrizionista la confermerà a breve.",
            "success",
        )

        return _prenota_redirect(utente, ok=1)

    except PlanLimitError as exc:
        db.session.rollback()
        flash(exc.message, "danger")
        return _prenota_redirect(utente)
    except ValueError:
        flash("Data o orario non validi", "danger")
        return _prenota_redirect(utente)
    except Exception as e:
        db.session.rollback()
        flash(f"Errore durante l'invio: {e}", "danger")
        return _prenota_redirect(utente)


# ========================
# PUBBLICO: PRENOTA (/prenota e /prenota/<studio_slug>)
# ========================
@prenota_public_bp.route("/prenota", methods=["GET", "POST"])
def prenota_landing():
    """Pagina neutra: senza studio_slug non si prenota e non si espone alcun tenant."""
    if request.method == "GET" and session.get("role") == "user":
        session.clear()

    if request.method == "POST":
        flash("Per prenotare usa il link completo fornito dal tuo nutrizionista.", "warning")
        return (
            render_template(
                "public/prenota_neutra.html",
                message="Prenotazione non disponibile senza link dello studio.",
            ),
            404,
        )

    return (
        render_template(
            "public/prenota_neutra.html",
            message=(
                "Per prenotare un appuntamento apri il link personale "
                "del tuo nutrizionista (/prenota/nome-studio)."
            ),
        ),
        404,
    )


@prenota_public_bp.route("/prenota/<slug>", methods=["GET", "POST"])
def prenota_by_slug(slug: str):
    """Prenotazione pubblica per studio_slug (tenant risolto solo lato server)."""
    if request.method == "GET" and session.get("role") == "user":
        session.clear()

    utente = _utente_by_slug(slug)
    if utente is None or not (utente.studio_slug or utente.public_slug):
        flash("Link di prenotazione non valido o non più disponibile.", "warning")
        return _render_prenota(None, status=404)

    if request.method == "POST":
        return _handle_prenota_post(utente)

    return _render_prenota(utente, inviato=request.args.get("ok") == "1")


def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get("role") not in ("admin", "nutrizionista"):
            flash("Accesso non autorizzato", "danger")
            return redirect(url_for("auth.login"))
        return func(*args, **kwargs)

    return wrapper


@prenota_public_bp.route("/appuntamenti/admin/richieste")
@admin_required
def lista_richieste_admin():
    """Elenco richieste pubbliche in attesa / recenti (tenant)."""
    uid = require_tenant()
    q = RichiestaAppuntamento.query
    if tenant_filter_enabled():
        q = q.filter(RichiestaAppuntamento.utente_id == uid)
    richieste = q.order_by(
        RichiestaAppuntamento.stato.asc(),
        RichiestaAppuntamento.data_richiesta.asc(),
    ).limit(100).all()

    pq = Patient.query
    if tenant_filter_enabled():
        pq = pq.filter(Patient.nutrizionista_id == uid)
    pazienti = pq.order_by(Patient.cognome.asc(), Patient.nome.asc()).all()
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
    """Converte una richiesta in appuntamento e attiva il paziente collegato."""
    uid = require_tenant()
    richiesta = RichiestaAppuntamento.query.get_or_404(id)
    if tenant_filter_enabled() and richiesta.utente_id != uid:
        flash("Richiesta non trovata", "danger")
        return redirect(url_for("prenota_public.lista_richieste_admin"))
    if richiesta.stato != "in_attesa":
        flash("Questa richiesta è già stata gestita", "warning")
        return redirect(url_for("prenota_public.lista_richieste_admin"))

    try:
        patient_id = int(request.form.get("patient_id") or 0)
        paziente = Patient.query.get(patient_id)
        if not paziente:
            flash("Seleziona un paziente in anagrafica", "warning")
            return redirect(url_for("prenota_public.lista_richieste_admin"))
        assert_patient_tenant(paziente)

        if not AgendaService.is_slot_disponibile(
            richiesta.data_richiesta,
            escludi_richiesta_id=richiesta.id,
            utente_id=uid,
        ):
            flash("Lo slot non è più disponibile", "warning")
            return redirect(url_for("prenota_public.lista_richieste_admin"))

        nuovo = Appuntamento(
            patient_id=paziente.id,
            utente_id=uid,
            created_by="admin",
            data_appuntamento=richiesta.data_richiesta,
            tipo=richiesta.tipo,
            stato="confermato",
            note=richiesta.note,
        )
        db.session.add(nuovo)
        db.session.flush()

        paziente.stato_cliente = "attivo"
        richiesta.stato = "accettata"
        richiesta.patient_id = paziente.id
        richiesta.appuntamento_id = nuovo.id
        db.session.commit()

        from app.routes.whatsapp.triggers import safe_trigger_appuntamento_stato

        safe_trigger_appuntamento_stato(nuovo, "confermato")

        flash("Richiesta accettata: cliente attivo e appuntamento creato ✅", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore: {e}", "danger")

    return redirect(url_for("prenota_public.lista_richieste_admin"))


@prenota_public_bp.route(
    "/appuntamenti/admin/richieste/<int:id>/rifiuta", methods=["POST"]
)
@admin_required
def rifiuta_richiesta(id):
    """Rifiuta una richiesta e, se collegato, imposta il paziente non attivo."""
    uid = require_tenant()
    richiesta = RichiestaAppuntamento.query.get_or_404(id)
    if tenant_filter_enabled() and richiesta.utente_id != uid:
        flash("Richiesta non trovata", "danger")
        return redirect(url_for("prenota_public.lista_richieste_admin"))
    if richiesta.stato != "in_attesa":
        flash("Questa richiesta è già stata gestita", "warning")
        return redirect(url_for("prenota_public.lista_richieste_admin"))

    try:
        if richiesta.patient_id:
            paziente = Patient.query.get(richiesta.patient_id)
            if paziente and paziente.stato_cliente == "provvisorio":
                assert_patient_tenant(paziente)
                paziente.stato_cliente = "non_attivo"
        richiesta.stato = "rifiutata"
        db.session.commit()
        flash("Richiesta rifiutata, slot liberato", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore: {e}", "danger")

    return redirect(url_for("prenota_public.lista_richieste_admin"))
