"""Logica agenda: orari settimanali ricorrenti + eccezioni (ferie), scoped per tenant."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import List, Optional, Sequence

from app.config.config import Config
from app.models.models import AgendaEccezione, Appuntamento, OrarioSettimanale, RichiestaAppuntamento, db

GIORNI_SETTIMANA = (
    "Lunedì",
    "Martedì",
    "Mercoledì",
    "Giovedì",
    "Venerdì",
    "Sabato",
    "Domenica",
)


@dataclass(frozen=True)
class SlotVirtuale:
    data_ora: datetime
    occupato: bool = False
    note: Optional[str] = None


class AgendaService:
    """Genera disponibilità da orari settimanali, applicando eccezioni e prenotazioni."""

    @staticmethod
    def _scope_utente(utente_id: Optional[int]) -> Optional[int]:
        if Config.SINGLE_TENANT:
            return utente_id
        return utente_id

    @staticmethod
    def get_orari_settimanali(utente_id: Optional[int] = None) -> List[OrarioSettimanale]:
        q = OrarioSettimanale.query.filter_by(attivo=True)
        if utente_id is not None:
            q = q.filter_by(utente_id=utente_id)
        elif not Config.SINGLE_TENANT:
            return []
        return q.order_by(
            OrarioSettimanale.giorno_settimana.asc(), OrarioSettimanale.ora.asc()
        ).all()

    @staticmethod
    def get_orari_per_giorno(utente_id: Optional[int] = None) -> dict[int, List[OrarioSettimanale]]:
        out: dict[int, List[OrarioSettimanale]] = {i: [] for i in range(7)}
        for orario in AgendaService.get_orari_settimanali(utente_id=utente_id):
            out[orario.giorno_settimana].append(orario)
        return out

    @staticmethod
    def get_eccezioni(
        future_only: bool = False, utente_id: Optional[int] = None
    ) -> List[AgendaEccezione]:
        q = AgendaEccezione.query
        if utente_id is not None:
            q = q.filter_by(utente_id=utente_id)
        elif not Config.SINGLE_TENANT:
            return []
        q = q.order_by(AgendaEccezione.data_inizio.asc())
        if future_only:
            oggi = date.today()
            q = q.filter(AgendaEccezione.data_fine >= oggi)
        return q.all()

    @staticmethod
    def is_giorno_chiuso(
        giorno: date,
        eccezioni: Optional[Sequence[AgendaEccezione]] = None,
        utente_id: Optional[int] = None,
    ) -> bool:
        eccezioni = (
            eccezioni
            if eccezioni is not None
            else AgendaService.get_eccezioni(utente_id=utente_id)
        )
        for exc in eccezioni:
            if exc.tipo == "chiusura" and exc.data_inizio <= giorno <= exc.data_fine:
                return True
        return False

    @staticmethod
    def _orari_attivi(utente_id: Optional[int] = None) -> List[OrarioSettimanale]:
        return AgendaService.get_orari_settimanali(utente_id=utente_id)

    @staticmethod
    def _appuntamenti_occupati(
        da: datetime, a: datetime, utente_id: Optional[int] = None
    ) -> set[datetime]:
        q = Appuntamento.query.filter(
            Appuntamento.data_appuntamento >= da,
            Appuntamento.data_appuntamento <= a,
            Appuntamento.stato != "annullato",
        )
        if utente_id is not None:
            q = q.filter(Appuntamento.utente_id == utente_id)
        rows = q.all()
        occupati = {row.data_appuntamento.replace(second=0, microsecond=0) for row in rows}

        rq = RichiestaAppuntamento.query.filter(
            RichiestaAppuntamento.data_richiesta >= da,
            RichiestaAppuntamento.data_richiesta <= a,
            RichiestaAppuntamento.stato == "in_attesa",
        )
        if utente_id is not None:
            rq = rq.filter(RichiestaAppuntamento.utente_id == utente_id)
        for r in rq.all():
            if r.data_richiesta:
                occupati.add(r.data_richiesta.replace(second=0, microsecond=0))
        return occupati

    @classmethod
    def genera_slot(
        cls,
        da: datetime,
        a: datetime,
        solo_liberi: bool = False,
        utente_id: Optional[int] = None,
    ) -> List[SlotVirtuale]:
        da = da.replace(second=0, microsecond=0)
        a = a.replace(second=0, microsecond=0)
        orari = cls._orari_attivi(utente_id=utente_id)
        eccezioni = cls.get_eccezioni(utente_id=utente_id)
        occupati = cls._appuntamenti_occupati(da, a, utente_id=utente_id)

        if not orari:
            return []

        per_giorno: dict[int, List[OrarioSettimanale]] = {i: [] for i in range(7)}
        for orario in orari:
            per_giorno[orario.giorno_settimana].append(orario)

        risultati: List[SlotVirtuale] = []
        giorno_corrente = da.date()
        fine_giorno = a.date()

        while giorno_corrente <= fine_giorno:
            if not cls.is_giorno_chiuso(giorno_corrente, eccezioni, utente_id=utente_id):
                for orario in per_giorno.get(giorno_corrente.weekday(), []):
                    dt = datetime.combine(giorno_corrente, orario.ora)
                    if dt < da or dt > a:
                        continue
                    occupato = dt in occupati
                    if solo_liberi and occupato:
                        continue
                    risultati.append(
                        SlotVirtuale(data_ora=dt, occupato=occupato, note=orario.note)
                    )
            giorno_corrente += timedelta(days=1)

        risultati.sort(key=lambda s: s.data_ora)
        return risultati

    @classmethod
    def slot_liberi(
        cls,
        da: Optional[datetime] = None,
        a: Optional[datetime] = None,
        utente_id: Optional[int] = None,
    ) -> List[SlotVirtuale]:
        da = da or datetime.now().replace(second=0, microsecond=0)
        a = a or (da + timedelta(days=60))
        return cls.genera_slot(da, a, solo_liberi=True, utente_id=utente_id)

    @classmethod
    def slot_per_giorno(cls, giorno: date, utente_id: Optional[int] = None) -> List[SlotVirtuale]:
        inizio = datetime.combine(giorno, time.min)
        fine = datetime.combine(giorno, time.max)
        return cls.genera_slot(inizio, fine, utente_id=utente_id)

    @staticmethod
    def is_slot_disponibile(
        data_ora: datetime,
        escludi_richiesta_id: Optional[int] = None,
        utente_id: Optional[int] = None,
    ) -> bool:
        data_ora = data_ora.replace(second=0, microsecond=0)
        giorno = data_ora.date()
        if AgendaService.is_giorno_chiuso(giorno, utente_id=utente_id):
            return False

        q_orario = OrarioSettimanale.query.filter_by(
            giorno_settimana=giorno.weekday(),
            ora=data_ora.time().replace(second=0, microsecond=0),
            attivo=True,
        )
        if utente_id is not None:
            q_orario = q_orario.filter_by(utente_id=utente_id)
        if q_orario.first() is None:
            return False

        q_app = Appuntamento.query.filter(
            Appuntamento.data_appuntamento == data_ora,
            Appuntamento.stato != "annullato",
        )
        if utente_id is not None:
            q_app = q_app.filter(Appuntamento.utente_id == utente_id)
        if q_app.first() is not None:
            return False

        q = RichiestaAppuntamento.query.filter(
            RichiestaAppuntamento.data_richiesta == data_ora,
            RichiestaAppuntamento.stato == "in_attesa",
        )
        if utente_id is not None:
            q = q.filter(RichiestaAppuntamento.utente_id == utente_id)
        if escludi_richiesta_id is not None:
            q = q.filter(RichiestaAppuntamento.id != escludi_richiesta_id)
        return q.first() is None

    @staticmethod
    def aggiungi_orario(
        giorno_settimana: int,
        ora: time,
        note: Optional[str] = None,
        *,
        utente_id: int,
    ) -> OrarioSettimanale:
        esistente = OrarioSettimanale.query.filter_by(
            utente_id=utente_id,
            giorno_settimana=giorno_settimana,
            ora=ora,
        ).first()
        if esistente:
            esistente.attivo = True
            if note:
                esistente.note = note
            db.session.commit()
            return esistente

        row = OrarioSettimanale(
            utente_id=utente_id,
            giorno_settimana=giorno_settimana,
            ora=ora,
            attivo=True,
            note=note or None,
        )
        db.session.add(row)
        db.session.commit()
        return row

    @staticmethod
    def rimuovi_orario(orario_id: int, utente_id: Optional[int] = None) -> None:
        q = OrarioSettimanale.query.filter_by(id=orario_id)
        if utente_id is not None:
            q = q.filter_by(utente_id=utente_id)
        row = q.first_or_404()
        db.session.delete(row)
        db.session.commit()

    @staticmethod
    def aggiungi_eccezione(
        data_inizio: date,
        data_fine: date,
        note: Optional[str] = None,
        *,
        utente_id: int,
    ) -> AgendaEccezione:
        if data_fine < data_inizio:
            raise ValueError("La data fine deve essere successiva o uguale alla data inizio")
        row = AgendaEccezione(
            utente_id=utente_id,
            data_inizio=data_inizio,
            data_fine=data_fine,
            tipo="chiusura",
            note=note or None,
        )
        db.session.add(row)
        db.session.commit()
        return row

    @staticmethod
    def rimuovi_eccezione(eccezione_id: int, utente_id: Optional[int] = None) -> None:
        q = AgendaEccezione.query.filter_by(id=eccezione_id)
        if utente_id is not None:
            q = q.filter_by(utente_id=utente_id)
        row = q.first_or_404()
        db.session.delete(row)
        db.session.commit()

    @staticmethod
    def slot_liberi_per_select(limite: int = 100, utente_id: Optional[int] = None) -> List[dict]:
        """Formato per dropdown prenotazione utente."""
        slot = AgendaService.slot_liberi(utente_id=utente_id)[:limite]
        mesi_it = {
            "Monday": "lunedì", "Tuesday": "martedì", "Wednesday": "mercoledì",
            "Thursday": "giovedì", "Friday": "venerdì", "Saturday": "sabato", "Sunday": "domenica",
            "January": "gennaio", "February": "febbraio", "March": "marzo", "April": "aprile",
            "May": "maggio", "June": "giugno", "July": "luglio", "August": "agosto",
            "September": "settembre", "October": "ottobre", "November": "novembre", "December": "dicembre",
        }
        out = []
        for s in slot:
            label = s.data_ora.strftime("%A %d %B %Y ore %H:%M")
            for en, it in mesi_it.items():
                label = label.replace(en, it)
            if s.note:
                label += f" — {s.note}"
            out.append({
                "data": s.data_ora.strftime("%Y-%m-%d %H:%M:%S"),
                "label": label,
                "note": s.note or "",
            })
        return out
