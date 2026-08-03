"""Landing pubblica: richiesta appuntamento senza login (fuori dalla root)."""

from datetime import datetime
from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.models.diario import Utente
from app.models.enums import UtenteRuolo
from app.models.models import Appuntamento, Patient, db
from app.services.agenda_service import AgendaService
from app.services.licensing_service import PlanLimitError
from app.services.paziente_service import crea_paziente_provvisorio
from app.utils.db_schema import ensure_patient_stato_schema, ensure_richieste_appuntamento_schema
from app.utils.helpers import normalize_phone

prenota_public_bp = Blueprint("prenota_public", __name__)

TIPI_PUBBLICI = {
    "altro": "Prima consulenza",
    "check": "Check",
    "allenamento_1to1": "Allenamento 1to1",
}


@prenota_public_bp.before_request
def _ensure_schema():
    ensure_patient_stato_schema()
    ensure_richieste_appuntamento_schema()


def _default_tenant_id() -> int | None:
    """Tenant per prenota pubblica: ?n=<id> oppure primo nutrizionista attivo."""
    raw = request.args.get("n") or request.form.get("n")
    if raw:
        try:
            uid = int(raw)
        except (TypeError, ValueError):
            uid = None
        if uid:
            row = Utente.query.filter_by(
                id=uid, ruolo=UtenteRuolo.NUTRIZIONISTA.value, attivo=True
            ).first()
            if row:
                return int(row.id)
    row = (
        Utente.query.filter_by(ruolo=UtenteRuolo.NUTRIZIONISTA.value, attivo=True)
        .order_by(Utente.id.asc())
        .first()
    )
    return int(row.id) if row else None


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


# ========================
# PUBBLICO: PRENOTA (/prenota)
# ========================
@prenota_public_bp.route("/prenota", methods=["GET", "POST"])
def prenota_landing():
    """Pagina pubblica di prenotazione appuntamento."""
    if request.method == "GET" and session.get("role") == "user":
        return redirect(url_for("dashboard.user_dashboard"))

    tenant_id = _default_tenant_id()
    if tenant_id is None:
        flash("Nessun nutrizionista disponibile per le prenotazioni.", "warning")
        return render_template(
            "public/prenota.html",
            slot_liberi=[],
            tipi=TIPI_PUBBLICI,
            inviato=False,
        )

    if request.method == "POST":
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
                return redirect(url_for("prenota_public.prenota_landing", n=tenant_id))

            try:
                altezza_cm = int(float(altezza_raw.replace(",", ".")))
                peso_iniziale = float(peso_raw.replace(",", "."))
            except ValueError:
                flash("Altezza e peso devono essere numerici", "warning")
                return redirect(url_for("prenota_public.prenota_landing", n=tenant_id))

            if not (100 <= altezza_cm <= 250):
                flash("Inserisci un'altezza valida (100–250 cm)", "warning")
                return redirect(url_for("prenota_public.prenota_landing", n=tenant_id))
            if not (30 <= peso_iniziale <= 300):
                flash("Inserisci un peso valido (30–300 kg)", "warning")
                return redirect(url_for("prenota_public.prenota_landing", n=tenant_id))

            if tipo not in TIPI_PUBBLICI:
                tipo = "altro"

            if len(normalize_phone(telefono)) < 9:
                flash("Inserisci un numero di telefono valido", "warning")
                return redirect(url_for("prenota_public.prenota_landing", n=tenant_id))

            data_appuntamento = datetime.strptime(data_str, "%Y-%m-%d %H:%M:%S")
            if not AgendaService.is_slot_disponibile(data_appuntamento, utente_id=tenant_id):
                flash("Questo orario non è più disponibile. Scegline un altro.", "warning")
                return redirect(url_for("prenota_public.prenota_landing", n=tenant_id))

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

            return redirect(url_for("prenota_public.prenota_landing", ok=1, n=tenant_id))

        except PlanLimitError as exc:
            db.session.rollback()
            flash(exc.message, "danger")
            return redirect(url_for("prenota_public.prenota_landing", n=tenant_id))
        except ValueError:
            flash("Data o orario non validi", "danger")
            return redirect(url_for("prenota_public.prenota_landing", n=tenant_id))
        except Exception as e:
            db.session.rollback()
            flash(f"Errore durante l'invio: {e}", "danger")
            return redirect(url_for("prenota_public.prenota_landing", n=tenant_id))

    slot_liberi = AgendaService.slot_liberi_per_select(utente_id=tenant_id)
    return render_template(
        "public/prenota.html",
        slot_liberi=slot_liberi,
        tipi=TIPI_PUBBLICI,
        inviato=request.args.get("ok") == "1",
    )
