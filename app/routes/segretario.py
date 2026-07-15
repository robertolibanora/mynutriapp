"""
Segretario AI — chiamate inbound via Vapi.

Pagina admin per configurare l'assistente vocale che risponde ai pazienti
quando il nutrizionista non è disponibile, e webhook pubblico che:
- fornisce all'AI gli slot liberi (verifica_disponibilita)
- prenota appuntamenti reali in DB (prenota_appuntamento)
- registra messaggi/richiamate (lascia_messaggio)
- salva il log e la trascrizione di ogni chiamata
"""

import json
import logging
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.config.config import Config
from app.models.models import (
    Appuntamento,
    ChiamataInbound,
    Patient,
    SegretarioConfig,
    db,
)
from app.services.agenda_service import AgendaService
from app.services import vapi_service
from app.services import call_forwarding_service
from app.utils.helpers import normalize_phone
from app.utils.db_schema import ensure_segretario_deviazione_schema

logger = logging.getLogger(__name__)

segretario_bp = Blueprint("segretario", __name__, url_prefix="/admin/segretario")

_GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
_MESI = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]
_TIPI_VALIDI = {"allenamento_1to1", "rinnovo_dieta", "rinnovo_allenamento", "check", "altro"}


# ============================================================
# 🔐 ACCESSO ADMIN
# ============================================================

def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Accesso non autorizzato", "danger")
            return redirect(url_for("auth.login"))
        return func(*args, **kwargs)
    return wrapper


# ============================================================
# 🧱 HELPER
# ============================================================

def get_config() -> SegretarioConfig:
    """Ritorna (creandola se serve) la riga singola di configurazione."""
    ensure_segretario_deviazione_schema()
    cfg = SegretarioConfig.query.first()
    if cfg is None:
        cfg = SegretarioConfig(
            attivo=False,
            nome_studio=Config.WHATSAPP_FROM_NAME or "MyNutriApp",
            nome_assistente="Mario",
            numero_nutrizionista=None,
        )
        db.session.add(cfg)
        db.session.commit()
    return cfg


def _format_slot_it(dt: datetime) -> str:
    return f"{_GIORNI[dt.weekday()]} {dt.day} {_MESI[dt.month - 1]} alle {dt.strftime('%H:%M')}"


def _slot_liberi(giorni: int = 30, limite: int = 8) -> list[dict]:
    """Slot futuri generati da orari settimanali, escluse ferie e prenotazioni."""
    oggi = datetime.now().replace(second=0, microsecond=0)
    fine = oggi + timedelta(days=max(1, giorni))
    slot_db = AgendaService.slot_liberi(oggi, fine)
    liberi = []
    for slot in slot_db:
        liberi.append({
            "data_ora": slot.data_ora.strftime("%Y-%m-%d %H:%M"),
            "label": _format_slot_it(slot.data_ora),
            "note": slot.note or "",
        })
        if len(liberi) >= limite:
            break
    return liberi


def _match_patient(numero: str) -> Patient | None:
    if not numero:
        return None
    norm = normalize_phone(numero)
    if not norm:
        return None
    # confronto sulle ultime 9-10 cifre per tollerare prefissi diversi
    for p in Patient.query.filter(Patient.telefono.isnot(None)).all():
        if normalize_phone(p.telefono) == norm:
            return p
    return None


# ============================================================
# 🖥️ PAGINA ADMIN
# ============================================================

@segretario_bp.route("/")
@admin_required
def dashboard():
    cfg = get_config()
    chiamate = (
        ChiamataInbound.query.order_by(ChiamataInbound.created_at.desc()).limit(30).all()
    )
    totale = ChiamataInbound.query.count()
    con_appuntamento = ChiamataInbound.query.filter_by(appuntamento_creato=True).count()

    stato_vapi = {
        "configured": vapi_service.is_configured(),
        "webhook_url": vapi_service.webhook_url(),
        "public_url_set": bool(Config.VAPI_PUBLIC_URL),
        "phone_set": bool(Config.VAPI_PHONE_NUMBER_ID),
    }
    numero_inbound = ""
    if stato_vapi["configured"] and Config.VAPI_PHONE_NUMBER_ID:
        info = vapi_service.get_phone_number()
        if info:
            numero_inbound = info.get("number") or ""

    stats = {"totale": totale, "con_appuntamento": con_appuntamento}
    deviazione = call_forwarding_service.status_info(cfg.deviazione_attiva)
    deviazione["aggiornata_at"] = cfg.deviazione_aggiornata_at
    return render_template(
        "admin/segretario.html",
        cfg=cfg,
        chiamate=chiamate,
        stats=stats,
        stato_vapi=stato_vapi,
        numero_inbound=numero_inbound,
        deviazione=deviazione,
    )


@segretario_bp.route("/config", methods=["POST"])
@admin_required
def salva_config():
    cfg = get_config()
    try:
        cfg.numero_nutrizionista = (request.form.get("numero_nutrizionista") or "").strip() or None
        cfg.nome_studio = (request.form.get("nome_studio") or "").strip() or "MyNutriApp"
        cfg.nome_assistente = (request.form.get("nome_assistente") or "").strip() or "Mario"
        cfg.messaggio_benvenuto = (request.form.get("messaggio_benvenuto") or "").strip() or None
        cfg.istruzioni_ai = (request.form.get("istruzioni_ai") or "").strip() or None
        cfg.inoltra_a_nutrizionista = bool(request.form.get("inoltra_a_nutrizionista"))
        cfg.conferma_whatsapp = bool(request.form.get("conferma_whatsapp"))
        db.session.commit()
        flash("Configurazione salvata ✅", "success")

        # Sincronizza subito su Vapi se configurato.
        if vapi_service.is_configured():
            ok, msg = vapi_service.push_assistant_config(cfg)
            if ok:
                cfg.ultimo_sync = datetime.now()
                db.session.commit()
                flash(f"Vapi aggiornato: {msg}", "success")
            else:
                flash(f"Salvato in locale ma sync Vapi non riuscito: {msg}", "warning")
        else:
            flash("Credenziali Vapi non configurate nel .env: salvato solo in locale.", "warning")
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        logger.exception("Errore salvataggio config segretario")
        flash(f"Errore: {exc}", "danger")
    return redirect(url_for("segretario.dashboard"))


@segretario_bp.route("/toggle", methods=["POST"])
@admin_required
def toggle():
    cfg = get_config()
    try:
        cfg.attivo = not cfg.attivo
        db.session.commit()
        flash(
            f"Segretario AI {'attivato' if cfg.attivo else 'disattivato'} ✅",
            "success",
        )
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        flash(f"Errore: {exc}", "danger")
    return redirect(request.referrer or url_for("segretario.dashboard"))


@segretario_bp.route("/deviazione/toggle", methods=["POST"])
@admin_required
def toggle_deviazione():
    """Attiva/disattiva deviazione chiamate dal cellulare verso Vapi."""
    cfg = get_config()
    target_state = not cfg.deviazione_attiva
    try:
        ok, msg = call_forwarding_service.set_forwarding(target_state, config=cfg)
        if not ok:
            flash(msg, "warning")
            return redirect(request.referrer or url_for("dashboard.admin_dashboard"))

        cfg.deviazione_attiva = target_state
        cfg.deviazione_aggiornata_at = datetime.now()
        cfg.attivo = target_state
        db.session.commit()

        stato = "attivata" if target_state else "disattivata"
        flash(f"Deviazione chiamate {stato} ✅ {msg}", "success")
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        logger.exception("Errore toggle deviazione chiamate")
        flash(f"Errore deviazione: {exc}", "danger")

    return redirect(request.referrer or url_for("dashboard.admin_dashboard"))


@segretario_bp.route("/sync", methods=["POST"])
@admin_required
def sync():
    cfg = get_config()
    ok, msg = vapi_service.push_assistant_config(cfg)
    if ok:
        cfg.ultimo_sync = datetime.now()
        db.session.commit()
        flash(f"Sincronizzazione completata: {msg}", "success")
    else:
        flash(f"Sincronizzazione non riuscita: {msg}", "danger")
    return redirect(url_for("segretario.dashboard"))


# ============================================================
# 🔁 WEBHOOK VAPI (pubblico)
# ============================================================

@segretario_bp.route("/webhook", methods=["POST"])
def webhook():
    """Riceve gli eventi da Vapi: tool-calls, status-update, end-of-call-report."""
    raw = request.get_data()
    if not vapi_service.verify_webhook(request.headers, raw):
        logger.warning("Webhook Vapi: firma non valida")
        return jsonify({"error": "invalid signature"}), 401

    try:
        payload = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        return jsonify({"error": "invalid json"}), 400

    message = payload.get("message") or {}
    msg_type = str(message.get("type") or "").strip().lower()
    call = message.get("call") or {}
    call_id = str(call.get("id") or "").strip()
    caller = ((call.get("customer") or {}).get("number")) or ""

    try:
        if msg_type in ("tool-calls", "tool_calls", "function-call", "function_call"):
            return _handle_tool_calls(message, call_id, caller)
        if msg_type in ("status-update", "status_update"):
            _handle_status_update(message, call_id, caller)
        elif msg_type in ("end-of-call-report", "end_of_call_report", "end-of-call"):
            _handle_end_of_call(message, call_id, caller)
    except Exception:  # noqa: BLE001
        logger.exception("Webhook Vapi: errore gestione evento %s", msg_type)
        db.session.rollback()

    return jsonify({"ok": True}), 200


def _extract_tool_calls(message: dict) -> list[dict]:
    raw_calls = (
        message.get("toolCalls")
        or message.get("toolCallList")
        or message.get("functionCall")
        or []
    )
    if isinstance(raw_calls, dict):
        raw_calls = [raw_calls]
    out = []
    for tc in raw_calls:
        fn = tc.get("function") or {}
        name = str(tc.get("name") or fn.get("name") or "").strip()
        tcid = str(tc.get("id") or tc.get("toolCallId") or "").strip()
        args = fn.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        if not isinstance(args, dict):
            args = {}
        out.append({"id": tcid, "name": name, "args": args})
    return out


def _handle_tool_calls(message: dict, call_id: str, caller: str):
    chiamata = _upsert_chiamata(call_id, caller, stato="in_corso")
    results = []
    for tc in _extract_tool_calls(message):
        name = tc["name"]
        args = tc["args"]
        if name == "verifica_disponibilita":
            result = _tool_verifica_disponibilita(args)
        elif name == "prenota_appuntamento":
            result = _tool_prenota_appuntamento(args, chiamata, caller)
        elif name == "lascia_messaggio":
            result = _tool_lascia_messaggio(args, chiamata)
        else:
            result = "Strumento non riconosciuto."
        results.append({"toolCallId": tc["id"], "result": result})
    db.session.commit()
    return jsonify({"results": results}), 200


def _tool_verifica_disponibilita(args: dict) -> str:
    giorni = args.get("giorni")
    try:
        giorni = int(giorni) if giorni else 30
    except (TypeError, ValueError):
        giorni = 30
    liberi = _slot_liberi(giorni=giorni)
    if not liberi:
        return ("Al momento non risultano slot liberi nei prossimi giorni. "
                "Proponi di lasciare un messaggio per essere richiamato.")
    righe = [f"- {s['label']}" + (f" ({s['note']})" if s['note'] else "") for s in liberi]
    return "Slot disponibili:\n" + "\n".join(righe)


def _tool_prenota_appuntamento(args: dict, chiamata: ChiamataInbound, caller: str) -> str:
    data_ora_str = (args.get("data_ora") or "").strip()
    nome = (args.get("nome") or "").strip()
    tipo = (args.get("tipo") or "altro").strip()
    note = (args.get("note") or "").strip()
    if tipo not in _TIPI_VALIDI:
        tipo = "altro"

    dt = None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            dt = datetime.strptime(data_ora_str, fmt)
            break
        except ValueError:
            continue
    if dt is None:
        return "Data non valida: chiedi al paziente di indicare una delle date proposte."

    if not AgendaService.is_slot_disponibile(dt):
        return ("Quella data non è più disponibile. Chiama di nuovo verifica_disponibilita "
                "e proponi un altro orario.")

    paziente = chiamata.patient or _match_patient(caller)
    note_parts = ["Prenotato dal Segretario AI"]
    if nome:
        note_parts.append(f"Riferito da: {nome}")
    if note:
        note_parts.append(note)
    if not paziente and caller:
        note_parts.append(f"Numero chiamante: {caller}")
    note_finale = " — ".join(note_parts)

    if not paziente:
        # Niente paziente collegato: registra la richiesta come messaggio.
        chiamata.riassunto = (
            (chiamata.riassunto or "")
            + f"\nRichiesta appuntamento ({_format_slot_it(dt)}) da numero non registrato. "
            + note_finale
        ).strip()
        return ("Il numero non risulta fra i pazienti registrati. Ho preso nota della richiesta "
                f"per {_format_slot_it(dt)} e il nutrizionista confermerà appena possibile.")

    appuntamento = Appuntamento(
        patient_id=paziente.id,
        created_by="Enrico",
        data_appuntamento=dt,
        tipo=tipo,
        stato="in_attesa",
        note=note_finale,
    )
    db.session.add(appuntamento)
    db.session.flush()

    chiamata.patient_id = paziente.id
    chiamata.appuntamento_creato = True
    chiamata.appuntamento_id = appuntamento.id
    chiamata.riassunto = (
        (chiamata.riassunto or "") + f"\nAppuntamento {_format_slot_it(dt)} per {paziente.nome} {paziente.cognome}."
    ).strip()

    _invia_conferma_whatsapp(paziente, appuntamento)
    return (f"Appuntamento fissato per {_format_slot_it(dt)} a nome di "
            f"{paziente.nome} {paziente.cognome}. Conferma al paziente e saluta.")


def _tool_lascia_messaggio(args: dict, chiamata: ChiamataInbound) -> str:
    nome = (args.get("nome") or "").strip()
    messaggio = (args.get("messaggio") or "").strip()
    testo = f"Messaggio per il nutrizionista" + (f" da {nome}" if nome else "") + f": {messaggio}"
    chiamata.riassunto = ((chiamata.riassunto or "") + "\n" + testo).strip()
    return "Ho registrato il messaggio per il nutrizionista, sarà richiamato al più presto."


def _invia_conferma_whatsapp(paziente: Patient, appuntamento: Appuntamento) -> None:
    cfg = SegretarioConfig.query.first()
    if not (cfg and cfg.conferma_whatsapp):
        return
    try:
        from app.routes.whatsapp.sender import invia_whatsapp
        msg = (
            f"Ciao {paziente.nome}! 👋\n\n"
            f"Abbiamo registrato la tua richiesta di appuntamento:\n"
            f"📅 {appuntamento.data_appuntamento.strftime('%d/%m/%Y')} "
            f"alle {appuntamento.data_appuntamento.strftime('%H:%M')}\n\n"
            f"Ti confermeremo al più presto. A presto! 🌿"
        )
        invia_whatsapp(paziente.telefono, msg)
    except Exception:  # noqa: BLE001
        logger.warning("Conferma WhatsApp segretario AI non inviata", exc_info=True)


# ============================================================
# 🗂️ LOG CHIAMATE
# ============================================================

def _upsert_chiamata(call_id: str, caller: str, stato: str | None = None) -> ChiamataInbound:
    chiamata = None
    if call_id:
        chiamata = ChiamataInbound.query.filter_by(vapi_call_id=call_id).first()
    if chiamata is None:
        chiamata = ChiamataInbound(
            vapi_call_id=call_id or None,
            numero_chiamante=caller or None,
            direzione="inbound",
            stato=stato,
        )
        patient = _match_patient(caller)
        if patient:
            chiamata.patient_id = patient.id
        db.session.add(chiamata)
        db.session.flush()
    else:
        if stato:
            chiamata.stato = stato
        if caller and not chiamata.numero_chiamante:
            chiamata.numero_chiamante = caller
    return chiamata


def _handle_status_update(message: dict, call_id: str, caller: str) -> None:
    status = str(message.get("status") or "").strip().lower()
    mappa = {
        "ringing": "squillo",
        "in-progress": "in_corso",
        "in_progress": "in_corso",
        "ended": "terminata",
    }
    _upsert_chiamata(call_id, caller, stato=mappa.get(status, status or None))
    db.session.commit()


def _coerce_int(value) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _handle_end_of_call(message: dict, call_id: str, caller: str) -> None:
    chiamata = _upsert_chiamata(call_id, caller, stato="terminata")
    artifact = message.get("artifact") or {}

    chiamata.esito = str(message.get("endedReason") or message.get("ended_reason") or "").strip() or None

    durata = _coerce_int(
        message.get("durationSeconds")
        or message.get("duration_seconds")
        or message.get("duration")
    )
    if durata is not None:
        chiamata.durata_secondi = durata

    cost = message.get("cost")
    if cost not in (None, ""):
        try:
            chiamata.costo_usd = float(cost)
        except (TypeError, ValueError):
            pass

    transcript = message.get("transcript") or artifact.get("transcript")
    if transcript:
        chiamata.trascrizione = str(transcript)

    summary = message.get("summary") or artifact.get("summary")
    if summary:
        chiamata.riassunto = ((chiamata.riassunto or "") + "\n" + str(summary)).strip()

    rec = (
        message.get("recordingUrl")
        or artifact.get("recordingUrl")
        or artifact.get("stereoRecordingUrl")
    )
    if rec:
        chiamata.registrazione_url = str(rec)[:500]

    db.session.commit()
