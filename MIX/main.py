"""
main.py — Wild Society
FastAPI + SQLite + Stripe Checkout + Evolution API (WhatsApp)
"""
import os
import hmac
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import InvalidOperation
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Depends, HTTPException, Request, Form
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from starlette.middleware.sessions import SessionMiddleware

from app.database import (
    init_db, get_db, Event, Order, Ticket, EventAddon, TicketAddon,
    InviteCode, InviteCodeAddon,
)
from app import stripe_utils
from app import whatsapp
from app.money import fmt_eur, fmt_euro_input, parse_euro_to_cents

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tavola.liba")

DASHBOARD_USERNAME = os.getenv("DASHBOARD_USERNAME", "")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "")
SECRET_KEY = os.getenv("SECRET_KEY", "cambia-questa-chiave-in-produzione")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8100").rstrip("/")


def _dashboard_admins() -> list[tuple[str, str]]:
    admins: list[tuple[str, str]] = []
    if DASHBOARD_USERNAME and DASHBOARD_PASSWORD:
        admins.append((DASHBOARD_USERNAME, DASHBOARD_PASSWORD))
    i = 2
    while True:
        username = os.getenv(f"DASHBOARD_USERNAME_{i}", "")
        password = os.getenv(f"DASHBOARD_PASSWORD_{i}", "")
        if not username and not password:
            break
        if username and password:
            admins.append((username, password))
        i += 1
    return admins


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Wild Society", docs_url=None, redoc_url=None, lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STATIC_DIR = os.path.join(ROOT_DIR, "static")
TEMPLATES_DIR = os.path.join(ROOT_DIR, "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/manifest.webmanifest", include_in_schema=False)
def web_manifest():
    return FileResponse(
        os.path.join(STATIC_DIR, "manifest.webmanifest"),
        media_type="application/manifest+json",
    )


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    return FileResponse(
        os.path.join(STATIC_DIR, "sw.js"),
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(os.path.join(STATIC_DIR, "favicon.ico"))


@app.get("/dashboard/manifest.webmanifest", include_in_schema=False)
def dashboard_manifest():
    return FileResponse(
        os.path.join(STATIC_DIR, "manifest-admin.webmanifest"),
        media_type="application/manifest+json",
    )


@app.get("/dashboard/sw.js", include_in_schema=False)
def dashboard_service_worker():
    return FileResponse(
        os.path.join(STATIC_DIR, "sw-admin.js"),
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/dashboard/"},
    )


templates.env.filters["eur"] = fmt_eur
templates.env.filters["euro_input"] = fmt_euro_input


# ---------------------------------------------------------------- helpers
def get_cart(request: Request) -> list[dict]:
    return request.session.setdefault("cart", [])


def _generate_invite_code(db: Session) -> str:
    for _ in range(20):
        code = secrets.token_hex(4).upper()
        if not db.query(InviteCode).filter(InviteCode.code == code).first():
            return code
    raise HTTPException(500, "Impossibile generare il codice invito")


def _get_invite_by_code(db: Session, code: str) -> InviteCode | None:
    if not code:
        return None
    return (
        db.query(InviteCode)
        .options(joinedload(InviteCode.addon_links))
        .filter(InviteCode.code == code.strip().upper())
        .first()
    )


def _invite_has_paid_ticket(db: Session, invite_id: int) -> bool:
    return (
        db.query(Ticket.id)
        .join(Order)
        .filter(
            Ticket.invite_code_id == invite_id,
            Order.status == "paid",
        )
        .first()
        is not None
    )


def _invite_eliminabile(db: Session, invite: InviteCode) -> bool:
    return not invite.usato() and not _invite_has_paid_ticket(db, invite.id)


def _invite_has_pending_ticket(db: Session, invite_id: int) -> bool:
    return (
        db.query(Ticket.id)
        .join(Order)
        .filter(
            Ticket.invite_code_id == invite_id,
            Order.status == "pending",
        )
        .first()
        is not None
    )


def _cleanup_pending_invite_orders(db: Session, invite_id: int) -> None:
    pending_orders = (
        db.query(Order)
        .join(Ticket)
        .filter(
            Ticket.invite_code_id == invite_id,
            Order.status == "pending",
        )
        .all()
    )
    for order in pending_orders:
        db.delete(order)


def _release_invite_from_pending_orders(
    db: Session,
    invite_id: int,
    *,
    keep_order_id: int | None = None,
) -> None:
    """Rimuove claim sull'invito da ordini pending abbandonati."""
    q = (
        db.query(Ticket)
        .join(Order)
        .filter(
            Ticket.invite_code_id == invite_id,
            Order.status == "pending",
        )
    )
    if keep_order_id is not None:
        q = q.filter(Order.id != keep_order_id)
    for ticket in q.all():
        ticket.invite_code_id = None


def _invite_usabile(db: Session, invite: InviteCode | None) -> bool:
    if not invite or not invite.attivo or invite.usato():
        return False
    return not _invite_has_paid_ticket(db, invite.id)


def _get_invite_for_cart(item: dict, db: Session) -> InviteCode | None:
    code = item.get("invite_code")
    if not code:
        return None
    invite = _get_invite_by_code(db, code)
    if not invite or invite.event_id != item.get("event_id"):
        return None
    if not _invite_usabile(db, invite):
        return None
    return invite


def cart_item_total(item: dict, db: Session, cart: list[dict] | None = None) -> int:
    invite = _get_invite_for_cart(item, db)
    if invite:
        return invite.prezzo_cents
    ev = db.query(Event).filter(Event.id == item["event_id"]).first()
    if not ev:
        return 0
    ev.consolidate_aumento_prezzo(db)
    total = ev.prezzo_vendita_cents()
    active = {a.id: a for a in ev.addons_attivi()}
    for aid in item.get("addon_ids", []):
        addon = active.get(aid)
        if addon:
            total += addon.importo_cents
    return total


def cart_total(cart: list[dict], db: Session) -> int:
    return sum(cart_item_total(item, db, cart) for item in cart)


def _parse_addon_rows(form) -> list[dict]:
    ids = form.getlist("addon_id")
    nomi = form.getlist("addon_nome")
    descrizioni = form.getlist("addon_descrizione")
    importi = form.getlist("addon_importo")
    rows: list[dict] = []
    for i, nome in enumerate(nomi):
        nome = nome.strip()
        if not nome:
            continue
        try:
            importo = parse_euro_to_cents(importi[i] if i < len(importi) else 0)
        except (ValueError, InvalidOperation):
            continue
        if importo <= 0:
            continue
        raw_id = ids[i].strip() if i < len(ids) and ids[i] else ""
        aid = int(raw_id) if raw_id.isdigit() else None
        desc = (descrizioni[i] if i < len(descrizioni) else "").strip()
        rows.append({
            "id": aid,
            "nome": nome,
            "descrizione": desc,
            "importo_cents": importo,
        })
    return rows


def _apply_fasce_prezzo(ev: Event, form) -> str | None:
    try:
        early = parse_euro_to_cents(form.get("importo", 0))
        mid = parse_euro_to_cents(form.get("importo_mid", 0))
        late = parse_euro_to_cents(form.get("importo_late", 0))
        soglia_mid = int(form.get("posti_soglia_mid", 0))
        soglia_late = int(form.get("posti_soglia_late", 0))
    except (ValueError, TypeError, InvalidOperation):
        return "Fasce prezzo non valide."

    if early <= 0 or mid <= 0 or late <= 0:
        return "I prezzi delle tre fasce devono essere maggiori di zero."
    if not (early < mid < late):
        return "I prezzi devono crescere: early < mid < late."
    if soglia_mid <= 0 or soglia_late <= 0:
        return "Le soglie di capienza devono essere almeno 1."
    if soglia_mid >= soglia_late:
        return "La soglia mid deve essere inferiore alla soglia late."
    if soglia_late >= ev.posti_max:
        return "La soglia late deve essere inferiore ai posti totali."

    ev.importo_cents = early
    ev.importo_mid_cents = mid
    ev.importo_late_cents = late
    ev.posti_soglia_mid = soglia_mid
    ev.posti_soglia_late = soglia_late
    return None


def _sync_event_addons(db: Session, ev: Event, rows: list[dict]) -> None:
    existing = {a.id: a for a in ev.addons}
    kept_ids: set[int] = set()
    for ordine, row in enumerate(rows):
        if row.get("id") and row["id"] in existing:
            addon = existing[row["id"]]
            addon.nome = row["nome"]
            addon.descrizione = row["descrizione"]
            addon.importo_cents = row["importo_cents"]
            addon.ordine = ordine
            addon.attivo = True
            kept_ids.add(addon.id)
        else:
            db.add(EventAddon(
                event_id=ev.id,
                nome=row["nome"],
                descrizione=row["descrizione"],
                importo_cents=row["importo_cents"],
                obbligatorio=False,
                attivo=True,
                ordine=ordine,
            ))
    for aid, addon in existing.items():
        if aid in kept_ids:
            continue
        if addon.ticket_addons:
            addon.attivo = False
        else:
            db.delete(addon)


def _valid_addon_ids(ev: Event, raw_ids: list) -> list[int]:
    active = {a.id for a in ev.addons_attivi()}
    result: list[int] = []
    for raw in raw_ids:
        try:
            aid = int(raw)
        except (ValueError, TypeError):
            continue
        if aid in active:
            result.append(aid)
    return result


def admin_guard(request: Request) -> RedirectResponse | None:
    if not request.session.get("admin"):
        return RedirectResponse("/dashboard/login", status_code=303)
    return None


def order_matches_search(order: Order, q: str) -> bool:
    needle = q.strip().casefold()
    if not needle:
        return True
    phone_needle = "".join(c for c in q if c.isdigit())
    for t in order.tickets:
        if needle in f"{t.nome} {t.cognome}".casefold():
            return True
        if needle in t.nome.casefold() or needle in t.cognome.casefold():
            return True
        if t.event and needle in t.event.nome.casefold():
            return True
        if phone_needle:
            phone = "".join(c for c in t.telefono if c.isdigit())
            if phone_needle in phone:
                return True
    return False


def broadcast_contacts(db: Session) -> list[dict]:
    """Contatti unici da biglietti pagati (per broadcast WhatsApp)."""
    query = (
        db.query(Ticket)
        .join(Order)
        .filter(Order.status == "paid")
        .order_by(Order.created_at.desc())
    )

    by_phone: dict[str, dict] = {}
    for t in query.all():
        key = whatsapp.normalize_phone(t.telefono)
        if key not in by_phone:
            by_phone[key] = {
                "phone_norm": key,
                "phone": t.telefono,
                "nome": t.nome,
                "cognome": t.cognome,
            }

    contacts = list(by_phone.values())
    contacts.sort(key=lambda c: (c["cognome"].casefold(), c["nome"].casefold()))
    return contacts


def paid_tickets_for(ev: Event) -> list[Ticket]:
    paid = [t for t in ev.tickets if t.order and t.order.status == "paid"]
    paid.sort(key=lambda t: (t.cognome.lower(), t.nome.lower()))
    return paid


def ticket_name_key(nome: str, cognome: str) -> tuple[str, str]:
    return nome.strip().casefold(), cognome.strip().casefold()


def nome_gia_pagato(ev: Event, nome: str, cognome: str) -> bool:
    key = ticket_name_key(nome, cognome)
    return any(
        t.order and t.order.status == "paid" and ticket_name_key(t.nome, t.cognome) == key
        for t in ev.tickets
    )


def nome_in_carrello(cart: list[dict], event_id: int, nome: str, cognome: str) -> bool:
    key = ticket_name_key(nome, cognome)
    return any(
        item["event_id"] == event_id and ticket_name_key(item["nome"], item["cognome"]) == key
        for item in cart
    )


def cart_needs_addon_confirm(cart: list[dict], db: Session) -> bool:
    if len(cart) != 1:
        return False
    if cart[0].get("invite_code"):
        return False
    if cart[0].get("addon_ids"):
        return False
    if cart[0].get("addons_declined"):
        return False
    ev = db.query(Event).filter(Event.id == cart[0]["event_id"]).first()
    if not ev:
        return False
    return bool(ev.addons_attivi())


def checkout_cart(cart: list[dict], db: Session) -> str:
    if not cart:
        raise HTTPException(400, "Nessun posto in sospeso")
    if len(cart) > 1:
        raise HTTPException(400, "Un solo posto per acquisto")

    by_event: dict[int, list[dict]] = {}
    for item in cart:
        by_event.setdefault(item["event_id"], []).append(item)

    events = {}
    for event_id, tks in by_event.items():
        ev = db.query(Event).filter(Event.id == event_id, Event.attivo == True).first()
        if not ev:
            raise HTTPException(400, f"Evento {event_id} non trovato o non attivo")
        rimanenti = ev.posti_max - ev.posti_venduti()
        if len(tks) > rimanenti:
            raise HTTPException(400, f"Posti esauriti per «{ev.nome}»: ne restano {rimanenti}")
        visti: set[tuple[str, str]] = set()
        for tk in tks:
            key = ticket_name_key(tk["nome"], tk["cognome"])
            if key in visti:
                raise HTTPException(400, f"Due prenotazioni allo stesso nome per «{ev.nome}»")
            visti.add(key)
            if nome_gia_pagato(ev, tk["nome"], tk["cognome"]):
                raise HTTPException(
                    400,
                    f"Esiste già un posto a nome {tk['cognome']} {tk['nome']} per «{ev.nome}»",
                )
        events[event_id] = ev

    totale = cart_total(cart, db)

    for item in cart:
        if item.get("invite_code") and not _get_invite_for_cart(item, db):
            raise HTTPException(400, "Codice invito non valido o già utilizzato.")

    order = Order(status="pending", totale_cents=totale)
    db.add(order)
    db.flush()

    line_counts: dict[tuple[str, int], int] = {}
    checkout_invite_id: int | None = None
    for item in cart:
        ev = events[item["event_id"]]
        invite = _get_invite_for_cart(item, db)
        active_addons = {a.id: a for a in ev.addons_attivi()}

        if invite:
            _release_invite_from_pending_orders(db, invite.id)
            checkout_invite_id = invite.id
            ticket = Ticket(
                order_id=order.id,
                event_id=item["event_id"],
                nome=item["nome"].strip(),
                cognome=item["cognome"].strip(),
                telefono=item["telefono"].strip(),
                importo_cents=invite.prezzo_cents,
            )
            db.add(ticket)
            db.flush()

            label = f"{ev.nome} — Invito speciale"
            if invite.etichetta:
                label = f"{ev.nome} — Invito ({invite.etichetta})"
            key = (label, invite.prezzo_cents)
            line_counts[key] = line_counts.get(key, 0) + 1

            for aid in invite.addon_ids():
                addon = active_addons.get(aid)
                if not addon:
                    continue
                db.add(TicketAddon(
                    ticket_id=ticket.id,
                    event_addon_id=addon.id,
                    importo_cents=0,
                ))
            continue

        ev.consolidate_aumento_prezzo(db)
        prezzo_posto = ev.prezzo_vendita_cents()
        ticket = Ticket(
            order_id=order.id,
            event_id=item["event_id"],
            nome=item["nome"].strip(),
            cognome=item["cognome"].strip(),
            telefono=item["telefono"].strip(),
            importo_cents=prezzo_posto,
        )
        db.add(ticket)
        db.flush()

        key = (f"{ev.nome} — Posto a tavola", prezzo_posto)
        line_counts[key] = line_counts.get(key, 0) + 1

        for aid in item.get("addon_ids", []):
            addon = active_addons.get(aid)
            if not addon:
                continue
            db.add(TicketAddon(
                ticket_id=ticket.id,
                event_addon_id=addon.id,
                importo_cents=addon.importo_cents,
            ))
            akey = (f"{ev.nome} — {addon.nome}", addon.importo_cents)
            line_counts[akey] = line_counts.get(akey, 0) + 1

    items = [
        {"event_nome": label, "importo_cents": cents, "quantity": qty}
        for (label, cents), qty in line_counts.items()
    ]

    try:
        session = stripe_utils.create_checkout_session(
            order.id,
            items,
            invite_code_id=checkout_invite_id,
        )
    except Exception as e:
        db.rollback()
        logger.error("Stripe error: %s", e)
        raise HTTPException(502, "Pagamento momentaneamente non disponibile. Riprova tra poco.")

    order.stripe_session_id = session.id
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(400, "Questo codice invito è già stato utilizzato.")
    return session.url


async def finalize_paid_order(
    order: Order,
    db: Session,
    invite_code_id: int | None = None,
) -> bool:
    """Marca ordine pagato e invia WhatsApp. Ritorna True se appena finalizzato."""
    if order.status == "paid":
        return False
    order.status = "paid"
    db.flush()

    tickets = db.query(Ticket).filter(Ticket.order_id == order.id).all()
    if invite_code_id is None:
        for ticket in tickets:
            if ticket.invite_code_id:
                invite_code_id = ticket.invite_code_id
                break

    if invite_code_id:
        invite = (
            db.query(InviteCode)
            .filter(InviteCode.id == invite_code_id)
            .with_for_update()
            .first()
        )
        if invite and not invite.usato():
            _release_invite_from_pending_orders(db, invite_code_id, keep_order_id=order.id)
            invite.used_at = datetime.utcnow()
            for ticket in tickets:
                if not ticket.invite_code_id:
                    ticket.invite_code_id = invite.id
        elif invite and invite.usato():
            logger.warning(
                "Invito %s già usato; ordine %s pagato senza collegamento invito",
                invite_code_id,
                order.id,
            )

    db.commit()

    order = (
        db.query(Order)
        .options(
            joinedload(Order.tickets).joinedload(Ticket.event),
            joinedload(Order.tickets)
            .joinedload(Ticket.addons)
            .joinedload(TicketAddon.event_addon),
        )
        .filter(Order.id == order.id)
        .first()
    )
    if not order:
        return False

    tickets_by_event: dict = {}
    for t in order.tickets:
        tickets_by_event.setdefault(t.event, []).append(t)
    try:
        await whatsapp.notify_order_paid(order, tickets_by_event)
    except Exception as e:
        logger.error("WhatsApp notify error: %s", e)
    return True


# ---------------------------------------------------------------- pagine pubbliche
@app.get("/")
def index(request: Request, db: Session = Depends(get_db)):
    events = db.query(Event).filter(Event.attivo == True).order_by(Event.data).all()
    for ev in events:
        ev.consolidate_aumento_prezzo(db)
    db.commit()
    cart = get_cart(request)
    return templates.TemplateResponse(
        request,
        "public/index.html",
        {"events": events, "cart_count": len(cart)},
    )


@app.get("/evento/{event_id}")
def evento_page(event_id: int, request: Request, db: Session = Depends(get_db)):
    ev = db.query(Event).filter(Event.id == event_id, Event.attivo == True).first()
    if not ev:
        raise HTTPException(404, "Evento non trovato")
    ev.consolidate_aumento_prezzo(db)
    db.commit()
    cart = get_cart(request)
    rimanenti = ev.posti_max - ev.posti_venduti()
    return templates.TemplateResponse(
        request,
        "public/evento.html",
        {
            "event": ev,
            "rimanenti": rimanenti,
            "soldout": rimanenti <= 0,
            "cart_count": len(cart),
            "cart_has_ticket": len(cart) >= 1,
            "error": request.query_params.get("error"),
        },
    )


@app.post("/evento/{event_id}/aggiungi")
async def evento_aggiungi(
    event_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    ev = db.query(Event).filter(Event.id == event_id, Event.attivo == True).first()
    if not ev:
        raise HTTPException(404, "Evento non trovato")

    form = await request.form()
    nomi = [v.strip() for v in form.getlist("nome")]
    cognomi = [v.strip() for v in form.getlist("cognome")]
    telefoni = [v.strip() for v in form.getlist("telefono")]

    if not nomi or len(nomi) != len(cognomi) or len(nomi) != len(telefoni) or len(nomi) != 1:
        return RedirectResponse(f"/evento/{event_id}?error=Controlla+i+dati+inseriti+e+riprova.", status_code=303)

    nome, cognome, telefono = nomi[0], cognomi[0], telefoni[0]
    if not nome or not cognome or not telefono:
        return RedirectResponse(
            f"/evento/{event_id}?error=Compila+tutti+i+campi+per+continuare.",
            status_code=303,
        )

    cart = get_cart(request)
    if cart:
        return RedirectResponse(
            f"/evento/{event_id}?error=Hai+già+un+ordine+in+corso.+Completa+il+pagamento+o+scegli+un%27altra+serata.",
            status_code=303,
        )

    rimanenti = ev.posti_max - ev.posti_venduti()
    if rimanenti <= 0:
        return RedirectResponse(f"/evento/{event_id}?error=Posti+esauriti+per+questa+serata.+Torna+presto.", status_code=303)

    if nome_gia_pagato(ev, nome, cognome):
        return RedirectResponse(
            "/evento/" + str(event_id) + "?error=Esiste+già+un+posto+a+questo+nome+per+questa+serata.",
            status_code=303,
        )

    addon_ids = _valid_addon_ids(ev, form.getlist("addon_ids"))
    request.session["cart"] = [{
        "event_id": event_id,
        "nome": nome,
        "cognome": cognome,
        "telefono": telefono,
        "addon_ids": addon_ids,
    }]
    return RedirectResponse("/carrello", status_code=303)


@app.get("/invito/{code}")
def invito_page(code: str, request: Request, db: Session = Depends(get_db)):
    invite = _get_invite_by_code(db, code)
    cart = get_cart(request)
    if not invite or not _invite_usabile(db, invite):
        return templates.TemplateResponse(
            request,
            "public/invito.html",
            {
                "invalid": True,
                "cart_count": len(get_cart(request)),
            },
        )
    ev = db.query(Event).filter(Event.id == invite.event_id, Event.attivo == True).first()
    if not ev:
        raise HTTPException(404, "Evento non trovato")
    ev.consolidate_aumento_prezzo(db)
    db.commit()
    rimanenti = ev.posti_max - ev.posti_venduti()
    return templates.TemplateResponse(
        request,
        "public/invito.html",
        {
            "invalid": False,
            "invite": invite,
            "event": ev,
            "addons_inclusi": invite.addons_inclusi(ev),
            "rimanenti": rimanenti,
            "soldout": rimanenti <= 0,
            "cart_count": len(cart),
            "cart_has_ticket": len(cart) >= 1,
            "error": request.query_params.get("error"),
        },
    )


@app.post("/invito/{code}/prenota")
async def invito_prenota(code: str, request: Request, db: Session = Depends(get_db)):
    invite = _get_invite_by_code(db, code)
    cart = get_cart(request)
    if not invite or not _invite_usabile(db, invite):
        return RedirectResponse("/invito/" + code + "?error=Questo+invito+non+è+più+valido.", status_code=303)
    ev = db.query(Event).filter(Event.id == invite.event_id, Event.attivo == True).first()
    if not ev:
        raise HTTPException(404, "Evento non trovato")

    form = await request.form()
    nome = form.get("nome", "").strip()
    cognome = form.get("cognome", "").strip()
    telefono = form.get("telefono", "").strip()
    if not nome or not cognome or not telefono:
        return RedirectResponse(
            "/invito/" + code + "?error=Compila+tutti+i+campi+per+continuare.",
            status_code=303,
        )

    cart = get_cart(request)
    if cart:
        return RedirectResponse(
            "/invito/" + code + "?error=Hai+già+un+ordine+in+corso.+Completa+il+pagamento.",
            status_code=303,
        )

    rimanenti = ev.posti_max - ev.posti_venduti()
    if rimanenti <= 0:
        return RedirectResponse("/invito/" + code + "?error=Posti+esauriti+per+questa+serata.", status_code=303)

    if nome_gia_pagato(ev, nome, cognome):
        return RedirectResponse(
            "/invito/" + code + "?error=Esiste+già+un+posto+a+questo+nome.",
            status_code=303,
        )

    request.session["cart"] = [{
        "event_id": ev.id,
        "nome": nome,
        "cognome": cognome,
        "telefono": telefono,
        "addon_ids": invite.addon_ids(),
        "invite_code": invite.code,
    }]
    return RedirectResponse("/carrello/regolamento", status_code=303)


@app.get("/regolamento")
def regolamento_page(request: Request):
    return templates.TemplateResponse(
        request,
        "public/regolamento.html",
        {"cart_count": len(get_cart(request))},
    )


@app.get("/carrello")
def carrello_page(request: Request, db: Session = Depends(get_db)):
    cart = get_cart(request)
    items = []
    for i, item in enumerate(cart):
        ev = db.query(Event).filter(Event.id == item["event_id"]).first()
        if not ev:
            continue
        addon_map = {a.id: a for a in ev.addons}
        selected_addons = [
            addon_map[aid] for aid in item.get("addon_ids", []) if aid in addon_map
        ]
        invite = _get_invite_for_cart(item, db)
        items.append({
            "index": i,
            "event": ev,
            "selected_addons": selected_addons,
            "item_total": cart_item_total(item, db, cart),
            "invite": invite,
            **item,
        })
    needs_confirm = cart_needs_addon_confirm(cart, db)
    available_addons = []
    if needs_confirm and cart:
        ev = db.query(Event).filter(Event.id == cart[0]["event_id"]).first()
        if ev:
            ev.consolidate_aumento_prezzo(db)
            db.commit()
            available_addons = ev.addons_attivi()
    elif cart:
        ev = db.query(Event).filter(Event.id == cart[0]["event_id"]).first()
        if ev:
            ev.consolidate_aumento_prezzo(db)
            db.commit()

    return templates.TemplateResponse(
        request,
        "public/carrello.html",
        {
            "items": items,
            "total": cart_total(cart, db),
            "cart_count": len(cart),
            "error": request.query_params.get("error"),
            "conferma_addon": request.query_params.get("conferma_addon") == "1",
            "needs_addon_confirm": needs_confirm,
            "available_addons": available_addons,
        },
    )


@app.post("/carrello/rimuovi/{index}")
def carrello_rimuovi(index: int, request: Request, db: Session = Depends(get_db)):
    cart = get_cart(request)
    if 0 <= index < len(cart):
        cart.pop(index)
        request.session["cart"] = cart
    return RedirectResponse("/carrello", status_code=303)


@app.post("/carrello/svuota")
def carrello_svuota(request: Request, db: Session = Depends(get_db)):
    request.session["cart"] = []
    return RedirectResponse("/carrello", status_code=303)


def _regolamento_accettato(form) -> bool:
    return form.get("accept_regolamento") == "1"


def _cart_item_detail(cart: list[dict], db: Session) -> dict | None:
    if len(cart) != 1:
        return None
    item = cart[0]
    ev = db.query(Event).filter(Event.id == item["event_id"]).first()
    if not ev:
        return None
    ev.consolidate_aumento_prezzo(db)
    db.flush()
    addon_map = {a.id: a for a in ev.addons}
    selected_addons = [
        addon_map[aid] for aid in item.get("addon_ids", []) if aid in addon_map
    ]
    invite = _get_invite_for_cart(item, db)
    return {
        "event": ev,
        "selected_addons": selected_addons,
        "item_total": cart_item_total(item, db, cart),
        "invite": invite,
        **item,
    }


@app.get("/carrello/regolamento")
def carrello_regolamento_page(request: Request, db: Session = Depends(get_db)):
    cart = get_cart(request)
    if not cart:
        return RedirectResponse("/carrello", status_code=303)
    if cart_needs_addon_confirm(cart, db):
        return RedirectResponse("/carrello?conferma_addon=1", status_code=303)
    item = _cart_item_detail(cart, db)
    if not item:
        return RedirectResponse("/carrello", status_code=303)
    if cart[0].get("invite_code") and not item.get("invite"):
        return RedirectResponse(
            "/carrello?error=Questo+invito+non+è+più+disponibile.",
            status_code=303,
        )
    db.commit()
    return templates.TemplateResponse(
        request,
        "public/carrello_regolamento.html",
        {
            "item": item,
            "total": cart_total(cart, db),
            "cart_count": len(cart),
            "error": request.query_params.get("error"),
        },
    )


@app.post("/carrello/regolamento")
async def carrello_regolamento_conferma(request: Request, db: Session = Depends(get_db)):
    cart = get_cart(request)
    if len(cart) != 1:
        return RedirectResponse("/carrello?error=Qualcosa+non+va+con+la+prenotazione.+Riprova.", status_code=303)
    if cart_needs_addon_confirm(cart, db):
        return RedirectResponse("/carrello?conferma_addon=1", status_code=303)
    form = await request.form()
    if not _regolamento_accettato(form):
        return RedirectResponse(
            "/carrello/regolamento?error=Accetta+le+condizioni+per+procedere+al+pagamento.",
            status_code=303,
        )
    try:
        url = checkout_cart(cart, db)
        request.session["cart"] = []
        return RedirectResponse(url, status_code=303)
    except HTTPException as e:
        return RedirectResponse(f"/carrello/regolamento?error={e.detail}", status_code=303)


@app.post("/carrello/aggiorna-addons")
async def carrello_aggiorna_addons(request: Request, db: Session = Depends(get_db)):
    cart = get_cart(request)
    if len(cart) != 1:
        return RedirectResponse("/carrello?error=Qualcosa+non+va+con+la+prenotazione.+Riprova.", status_code=303)
    ev = db.query(Event).filter(Event.id == cart[0]["event_id"]).first()
    if not ev:
        return RedirectResponse("/carrello", status_code=303)
    form = await request.form()
    cart[0]["addon_ids"] = _valid_addon_ids(ev, form.getlist("addon_ids"))
    request.session["cart"] = cart

    if form.get("proceed") == "1":
        if not cart[0].get("addon_ids"):
            return RedirectResponse(
                "/carrello?conferma_addon=1&error=Scegli+un+extra+oppure+continua+senza.",
                status_code=303,
            )
        return RedirectResponse("/carrello/regolamento", status_code=303)

    return RedirectResponse("/carrello", status_code=303)


@app.post("/carrello/paga")
async def carrello_paga(request: Request, db: Session = Depends(get_db)):
    cart = get_cart(request)
    if len(cart) != 1:
        return RedirectResponse(
            "/carrello?error=Puoi+completare+un+solo+biglietto+alla+volta.",
            status_code=303,
        )
    form = await request.form()
    if form.get("confirm_no_addons") == "1":
        cart[0]["addons_declined"] = True
        request.session["cart"] = cart
    elif cart_needs_addon_confirm(cart, db):
        return RedirectResponse("/carrello?conferma_addon=1", status_code=303)
    return RedirectResponse("/carrello/regolamento", status_code=303)


@app.get("/success")
async def success(
    request: Request,
    session_id: str = "",
    db: Session = Depends(get_db),
):
    if session_id:
        try:
            session = stripe_utils.retrieve_checkout_session(session_id)
            if session.payment_status == "paid":
                order_id = (session.metadata or {}).get("order_id")
                if order_id:
                    order = db.query(Order).filter(Order.id == int(order_id)).first()
                    if order:
                        invite_raw = (session.metadata or {}).get("invite_code_id")
                        invite_id = int(invite_raw) if invite_raw else None
                        await finalize_paid_order(order, db, invite_id)
        except Exception as e:
            logger.error("Conferma pagamento da /success: %s", e)

    return templates.TemplateResponse(request, "public/success.html")


# ---------------------------------------------------------------- webhook Stripe
@app.post("/api/stripe/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = stripe_utils.verify_webhook(payload, sig)
    except Exception as e:
        logger.error("Webhook Stripe rifiutato (controlla STRIPE_WEBHOOK_SECRET, deve iniziare con whsec_): %s", e)
        raise HTTPException(400, "Firma webhook non valida")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        order_id = session.get("metadata", {}).get("order_id")
        order = db.query(Order).filter(Order.id == int(order_id)).first() if order_id else None
        if order:
            invite_raw = session.get("metadata", {}).get("invite_code_id")
            invite_id = int(invite_raw) if invite_raw else None
            await finalize_paid_order(order, db, invite_id)

    return JSONResponse({"received": True})


# ---------------------------------------------------------------- admin
@app.get("/dashboard")
def dashboard_home(request: Request):
    if request.session.get("admin"):
        return RedirectResponse("/dashboard/eventi", status_code=303)
    return RedirectResponse("/dashboard/login", status_code=303)


@app.get("/admin")
def admin_redirect():
    return RedirectResponse("/dashboard", status_code=303)


@app.get("/dashboard/login")
def dashboard_login(request: Request):
    if request.session.get("admin"):
        return RedirectResponse("/dashboard/eventi", status_code=303)
    return templates.TemplateResponse(
        request,
        "admin/login.html",
        {"error": request.query_params.get("error")},
    )


def _dashboard_login_ok(username: str, password: str) -> bool:
    admins = _dashboard_admins()
    if not admins:
        logger.warning("Login dashboard rifiutato: nessun admin configurato in .env")
        return False
    username = username.strip().casefold()
    for admin_username, admin_password in admins:
        user_ok = hmac.compare_digest(username, admin_username.strip().casefold())
        pass_ok = hmac.compare_digest(password, admin_password)
        if user_ok and pass_ok:
            return True
    logger.info("Login dashboard fallito per username=%r", username)
    return False


@app.post("/dashboard/login")
def dashboard_login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    if not _dashboard_login_ok(username, password):
        return RedirectResponse("/dashboard/login?error=1", status_code=303)
    request.session["admin"] = True
    return RedirectResponse("/dashboard/eventi", status_code=303)


@app.post("/dashboard/logout")
def dashboard_logout(request: Request):
    request.session.clear()
    return RedirectResponse("/dashboard/login", status_code=303)


@app.get("/dashboard/eventi")
def dashboard_eventi(request: Request, db: Session = Depends(get_db)):
    if redir := admin_guard(request):
        return redir
    events = db.query(Event).order_by(Event.data.desc()).all()
    for ev in events:
        ev.consolidate_aumento_prezzo(db)
    db.commit()
    return templates.TemplateResponse(
        request,
        "admin/eventi.html",
        {
            "events": events,
            "msg": request.query_params.get("msg"),
            "error": request.query_params.get("error"),
        },
    )


@app.get("/dashboard/eventi/nuovo")
def dashboard_evento_nuovo(request: Request):
    if redir := admin_guard(request):
        return redir
    return templates.TemplateResponse(
        request,
        "admin/evento_form.html",
        {"event": None, "error": None},
    )


@app.post("/dashboard/eventi/nuovo")
async def dashboard_evento_crea(
    request: Request,
    db: Session = Depends(get_db),
):
    if redir := admin_guard(request):
        return redir
    form = await request.form()
    nome = form.get("nome", "").strip()
    data = form.get("data", "").strip()
    descrizione = form.get("descrizione", "").strip()
    try:
        posti_max = int(form.get("posti_max", 0))
    except (ValueError, TypeError):
        posti_max = 0
    attivo = form.get("attivo") == "on"
    if not nome or not data or posti_max <= 0:
        return templates.TemplateResponse(
            request,
            "admin/evento_form.html",
            {
                "event": None,
                "error": "Compila nome, data e numero di posti.",
                "form": {
                    "nome": nome,
                    "data": data,
                    "descrizione": descrizione,
                    "posti_max": posti_max,
                    "attivo": attivo,
                    "importo": form.get("importo", ""),
                    "importo_mid": form.get("importo_mid", ""),
                    "importo_late": form.get("importo_late", ""),
                    "posti_soglia_mid": form.get("posti_soglia_mid", ""),
                    "posti_soglia_late": form.get("posti_soglia_late", ""),
                },
                "addon_rows": _parse_addon_rows(form),
            },
        )
    ev = Event(
        nome=nome,
        data=data,
        descrizione=descrizione,
        importo_cents=1,
        posti_max=posti_max,
        attivo=attivo,
    )
    err_fasce = _apply_fasce_prezzo(ev, form)
    if err_fasce:
        return templates.TemplateResponse(
            request,
            "admin/evento_form.html",
            {
                "event": None,
                "error": err_fasce,
                "form": {
                    "nome": nome,
                    "data": data,
                    "descrizione": descrizione,
                    "posti_max": posti_max,
                    "attivo": attivo,
                    "importo": form.get("importo", ""),
                    "importo_mid": form.get("importo_mid", ""),
                    "importo_late": form.get("importo_late", ""),
                    "posti_soglia_mid": form.get("posti_soglia_mid", ""),
                    "posti_soglia_late": form.get("posti_soglia_late", ""),
                },
                "addon_rows": _parse_addon_rows(form),
            },
        )
    db.add(ev)
    db.flush()
    _sync_event_addons(db, ev, _parse_addon_rows(form))
    db.commit()
    return RedirectResponse("/dashboard/eventi?msg=Serata+creata.", status_code=303)


def _load_event_admin(db: Session, event_id: int) -> Event | None:
    return (
        db.query(Event)
        .options(
            joinedload(Event.tickets).joinedload(Ticket.order),
            joinedload(Event.tickets)
            .joinedload(Ticket.addons)
            .joinedload(TicketAddon.event_addon),
            joinedload(Event.invite_codes).joinedload(InviteCode.addon_links),
        )
        .filter(Event.id == event_id)
        .first()
    )


def _event_detail_url(event_id: int, request: Request) -> str:
    url = f"/dashboard/eventi/{event_id}"
    if request.url.query:
        url = f"{url}?{request.url.query}"
    return url


def _inviti_url(event_id: int, request: Request) -> str:
    url = f"/dashboard/eventi/{event_id}/inviti"
    if request.url.query:
        url = f"{url}?{request.url.query}"
    return url


def _invite_creato_context(
    request: Request, db: Session, event_id: int
) -> dict | None:
    creato_code = request.query_params.get("creato", "").strip().upper()
    if not creato_code:
        return None
    invite = (
        db.query(InviteCode)
        .filter(InviteCode.event_id == event_id, InviteCode.code == creato_code)
        .first()
    )
    if not invite:
        return None
    nome = invite.etichetta.strip() if invite.etichetta else invite.code
    return {
        "nome": nome,
        "url": f"{BASE_URL}/invito/{invite.code}",
    }


def _event_admin_context(ev: Event, request: Request) -> dict:
    paid = paid_tickets_for(ev)
    arrivati = sum(1 for t in paid if t.arrivato)
    return {
        "event": ev,
        "biglietti": paid,
        "posti_venduti": len(paid),
        "posti_rimanenti": max(0, ev.posti_max - len(paid)),
        "raccolto_cents": sum(t.totale_cents() for t in paid),
        "arrivati": arrivati,
        "ospiti_count": len(paid),
        "base_url": BASE_URL,
        "msg": request.query_params.get("msg"),
        "error": request.query_params.get("error"),
    }


@app.get("/dashboard/eventi/{event_id}")
def dashboard_evento_dettaglio(event_id: int, request: Request, db: Session = Depends(get_db)):
    if redir := admin_guard(request):
        return redir
    ev = _load_event_admin(db, event_id)
    if not ev:
        raise HTTPException(404, "Evento non trovato")
    ev.consolidate_aumento_prezzo(db)
    db.commit()
    ctx = _event_admin_context(ev, request)
    return templates.TemplateResponse(request, "admin/evento.html", ctx)


@app.get("/dashboard/eventi/{event_id}/ospiti")
def dashboard_evento_ospiti(event_id: int, request: Request, db: Session = Depends(get_db)):
    if redir := admin_guard(request):
        return redir
    if not db.query(Event.id).filter(Event.id == event_id).first():
        raise HTTPException(404, "Evento non trovato")
    return RedirectResponse(_event_detail_url(event_id, request), status_code=302)


@app.get("/dashboard/eventi/{event_id}/inviti")
def dashboard_evento_inviti(event_id: int, request: Request, db: Session = Depends(get_db)):
    if redir := admin_guard(request):
        return redir
    ev = _load_event_admin(db, event_id)
    if not ev:
        raise HTTPException(404, "Evento non trovato")
    ctx = _event_admin_context(ev, request)
    if invite_creato := _invite_creato_context(request, db, event_id):
        ctx["invite_creato"] = invite_creato
    ctx["inviti_eliminabili"] = {
        inv.id for inv in ev.invite_codes if _invite_eliminabile(db, inv)
    }
    ctx["inviti_pending"] = {
        inv.id for inv in ev.invite_codes if _invite_has_pending_ticket(db, inv.id)
    }
    return templates.TemplateResponse(request, "admin/evento_inviti.html", ctx)


@app.post("/dashboard/eventi/{event_id}/inviti/nuovo")
async def dashboard_invito_nuovo(
    event_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    if redir := admin_guard(request):
        return redir
    ev = db.query(Event).filter(Event.id == event_id).first()
    if not ev:
        raise HTTPException(404, "Evento non trovato")
    form = await request.form()
    etichetta = form.get("etichetta", "").strip()
    if not etichetta:
        return RedirectResponse(
            f"/dashboard/eventi/{event_id}/inviti?error=Indica+il+nome+dell%27invito.",
            status_code=303,
        )
    try:
        prezzo_cents = parse_euro_to_cents(form.get("prezzo", 0))
    except (ValueError, TypeError, InvalidOperation):
        prezzo_cents = 0
    if prezzo_cents <= 0:
        return RedirectResponse(
            f"/dashboard/eventi/{event_id}/inviti?error=Indica+un+prezzo+invito+valido.",
            status_code=303,
        )
    addon_ids = _valid_addon_ids(ev, form.getlist("addon_ids"))
    code = _generate_invite_code(db)
    invite = InviteCode(
        event_id=event_id,
        code=code,
        etichetta=etichetta,
        prezzo_cents=prezzo_cents,
    )
    db.add(invite)
    db.flush()
    for aid in addon_ids:
        db.add(InviteCodeAddon(invite_code_id=invite.id, event_addon_id=aid))
    db.commit()
    return RedirectResponse(
        f"/dashboard/eventi/{event_id}/inviti?creato={code}",
        status_code=303,
    )


@app.post("/dashboard/eventi/{event_id}/inviti/{invite_id}/elimina")
def dashboard_invito_elimina(
    event_id: int,
    invite_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    if redir := admin_guard(request):
        return redir
    invite = (
        db.query(InviteCode)
        .filter(InviteCode.id == invite_id, InviteCode.event_id == event_id)
        .first()
    )
    if not invite:
        raise HTTPException(404, "Invito non trovato")
    if not _invite_eliminabile(db, invite):
        return RedirectResponse(
            f"/dashboard/eventi/{event_id}/inviti?error=Invito+già+utilizzato,+non+eliminabile.",
            status_code=303,
        )
    _cleanup_pending_invite_orders(db, invite.id)
    nome = invite.etichetta.strip() if invite.etichetta else invite.code
    db.delete(invite)
    db.commit()
    return RedirectResponse(
        f"/dashboard/eventi/{event_id}/inviti?msg=Invito+{nome}+eliminato.",
        status_code=303,
    )


@app.get("/dashboard/eventi/{event_id}/biglietti/{ticket_id}")
def dashboard_biglietto_dettaglio(
    event_id: int,
    ticket_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    if redir := admin_guard(request):
        return redir
    ticket = (
        db.query(Ticket)
        .options(
            joinedload(Ticket.order),
            joinedload(Ticket.event),
            joinedload(Ticket.invite_code),
            joinedload(Ticket.addons).joinedload(TicketAddon.event_addon),
        )
        .filter(Ticket.id == ticket_id, Ticket.event_id == event_id)
        .first()
    )
    if not ticket or not ticket.order or ticket.order.status != "paid":
        raise HTTPException(404, "Partecipante non trovato")
    return templates.TemplateResponse(
        request,
        "admin/biglietto.html",
        {
            "event": ticket.event,
            "ticket": ticket,
            "order": ticket.order,
        },
    )


@app.post("/dashboard/eventi/{event_id}/biglietti/{ticket_id}/arrivato")
def dashboard_biglietto_arrivato(
    event_id: int,
    ticket_id: int,
    request: Request,
    next_url: str | None = Form(None, alias="next"),
    db: Session = Depends(get_db),
):
    if redir := admin_guard(request):
        return redir
    ticket = (
        db.query(Ticket)
        .filter(Ticket.id == ticket_id, Ticket.event_id == event_id)
        .first()
    )
    if not ticket or not ticket.order or ticket.order.status != "paid":
        raise HTTPException(404, "Biglietto non trovato")
    ticket.arrivato = not ticket.arrivato
    db.commit()
    dest = f"/dashboard/eventi/{event_id}"
    if next_url and next_url.startswith("/dashboard/"):
        dest = next_url
    return RedirectResponse(dest, status_code=303)


@app.get("/dashboard/eventi/{event_id}/modifica")
def dashboard_evento_modifica(event_id: int, request: Request, db: Session = Depends(get_db)):
    if redir := admin_guard(request):
        return redir
    ev = db.query(Event).filter(Event.id == event_id).first()
    if not ev:
        raise HTTPException(404, "Evento non trovato")
    ev.consolidate_aumento_prezzo(db)
    db.commit()
    return templates.TemplateResponse(
        request,
        "admin/evento_form.html",
        {"event": ev, "error": None},
    )


@app.post("/dashboard/eventi/{event_id}/modifica")
async def dashboard_evento_salva(
    event_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    if redir := admin_guard(request):
        return redir
    ev = db.query(Event).filter(Event.id == event_id).first()
    if not ev:
        raise HTTPException(404, "Evento non trovato")
    form = await request.form()
    nome = form.get("nome", "").strip()
    data = form.get("data", "").strip()
    descrizione = form.get("descrizione", "").strip()
    try:
        posti_max = int(form.get("posti_max", 0))
    except (ValueError, TypeError):
        posti_max = 0
    attivo = form.get("attivo") == "on"
    if not nome or not data or posti_max <= 0:
        return templates.TemplateResponse(
            request,
            "admin/evento_form.html",
            {
                "event": ev,
                "error": "Compila nome, data e numero di posti.",
                "addon_rows": _parse_addon_rows(form),
            },
        )
    ev.nome = nome
    ev.data = data
    ev.descrizione = descrizione
    ev.posti_max = posti_max
    ev.attivo = attivo
    err_fasce = _apply_fasce_prezzo(ev, form)
    if err_fasce:
        return templates.TemplateResponse(
            request,
            "admin/evento_form.html",
            {
                "event": ev,
                "error": err_fasce,
                "addon_rows": _parse_addon_rows(form),
            },
        )
    _sync_event_addons(db, ev, _parse_addon_rows(form))
    db.commit()
    return RedirectResponse(f"/dashboard/eventi/{event_id}", status_code=303)


@app.post("/dashboard/eventi/{event_id}/elimina")
def dashboard_evento_elimina(event_id: int, request: Request, db: Session = Depends(get_db)):
    if redir := admin_guard(request):
        return redir
    ev = db.query(Event).filter(Event.id == event_id).first()
    if not ev:
        raise HTTPException(404, "Evento non trovato")
    if ev.posti_venduti() > 0:
        return RedirectResponse(
            "/dashboard/eventi?error=Serata+con+ospiti+pagati:+disattivala+invece+di+eliminarla.",
            status_code=303,
        )
    for ticket in db.query(Ticket).filter(Ticket.event_id == event_id).all():
        db.delete(ticket)
    db.delete(ev)
    db.commit()
    return RedirectResponse("/dashboard/eventi?msg=Serata+eliminata.", status_code=303)


@app.get("/dashboard/ordini")
def dashboard_ordini(request: Request, db: Session = Depends(get_db)):
    if redir := admin_guard(request):
        return redir
    q = request.query_params.get("q", "").strip()
    orders = (
        db.query(Order)
        .options(
            joinedload(Order.tickets).joinedload(Ticket.event),
            joinedload(Order.tickets).joinedload(Ticket.invite_code),
            joinedload(Order.tickets)
            .joinedload(Ticket.addons)
            .joinedload(TicketAddon.event_addon),
        )
        .filter(Order.status == "paid")
        .order_by(Order.created_at.desc())
        .all()
    )
    if q:
        orders = [o for o in orders if order_matches_search(o, q)]
    return templates.TemplateResponse(
        request,
        "admin/ordini.html",
        {"orders": orders, "q": q},
    )


@app.get("/dashboard/broadcast")
def dashboard_broadcast(
    request: Request,
    db: Session = Depends(get_db),
):
    if redir := admin_guard(request):
        return redir
    contacts = broadcast_contacts(db)
    return templates.TemplateResponse(
        request,
        "admin/broadcast.html",
        {
            "contacts": contacts,
            "total": len(contacts),
            "msg": request.query_params.get("msg", ""),
            "error": request.query_params.get("error", ""),
            "sent": request.query_params.get("sent"),
            "failed": request.query_params.get("failed"),
        },
    )


@app.post("/dashboard/broadcast")
async def dashboard_broadcast_send(
    request: Request,
    db: Session = Depends(get_db),
    message: str = Form(...),
    phones: list[str] = Form(default=[]),
):
    if redir := admin_guard(request):
        return redir

    text = message.strip()
    if not text:
        return RedirectResponse(
            "/dashboard/broadcast?error=Scrivi+il+messaggio+prima+di+inviare.",
            status_code=303,
        )
    if len(text) > 4000:
        return RedirectResponse(
            "/dashboard/broadcast?error=Messaggio+troppo+lungo+(max+4000+caratteri).",
            status_code=303,
        )

    allowed = {c["phone_norm"]: c for c in broadcast_contacts(db)}
    selected = [p for p in phones if p in allowed]
    if not selected:
        return RedirectResponse(
            "/dashboard/broadcast?error=Seleziona+almeno+un+destinatario.",
            status_code=303,
        )

    sent = 0
    failed = 0
    for phone_norm in selected:
        contact = allowed[phone_norm]
        ok = await whatsapp.send_whatsapp(contact["phone"], text)
        if ok:
            sent += 1
        else:
            failed += 1

    logger.info(
        "Broadcast admin: %s inviati, %s falliti su %s destinatari",
        sent, failed, len(selected),
    )
    params = f"sent={sent}&failed={failed}"
    if failed:
        params += f"&msg=Invio+completato+con+{failed}+errori."
    else:
        params += f"&msg=Inviati+{sent}+messaggi."
    return RedirectResponse(f"/dashboard/broadcast?{params}", status_code=303)
