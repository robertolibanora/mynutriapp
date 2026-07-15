"""Logica agenda: orari settimanali ricorrenti + eccezioni (ferie)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Iterable, List, Optional, Sequence

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
    def get_orari_settimanali() -> List[OrarioSettimanale]:
        return (
            OrarioSettimanale.query.filter_by(attivo=True)
            .order_by(OrarioSettimanale.giorno_settimana.asc(), OrarioSettimanale.ora.asc())
            .all()
        )

    @staticmethod
    def get_orari_per_giorno() -> dict[int, List[OrarioSettimanale]]:
        out: dict[int, List[OrarioSettimanale]] = {i: [] for i in range(7)}
        for orario in AgendaService.get_orari_settimanali():
            out[orario.giorno_settimana].append(orario)
        return out

    @staticmethod
    def get_eccezioni(future_only: bool = False) -> List[AgendaEccezione]:
        q = AgendaEccezione.query.order_by(AgendaEccezione.data_inizio.asc())
        if future_only:
            oggi = date.today()
            q = q.filter(AgendaEccezione.data_fine >= oggi)
        return q.all()

    @staticmethod
    def is_giorno_chiuso(giorno: date, eccezioni: Optional[Sequence[AgendaEccezione]] = None) -> bool:
        eccezioni = eccezioni if eccezioni is not None else AgendaService.get_eccezioni()
        for exc in eccezioni:
            if exc.tipo == "chiusura" and exc.data_inizio <= giorno <= exc.data_fine:
                return True
        return False

    @staticmethod
    def _orari_attivi() -> List[OrarioSettimanale]:
        return OrarioSettimanale.query.filter_by(attivo=True).all()

    @staticmethod
    def _appuntamenti_occupati(da: datetime, a: datetime) -> set[datetime]:
        rows = Appuntamento.query.filter(
            Appuntamento.data_appuntamento >= da,
            Appuntamento.data_appuntamento <= a,
            Appuntamento.stato != "annullato",
        ).all()
        occupati = {row.data_appuntamento.replace(second=0, microsecond=0) for row in rows}

        # Richieste pubbliche in attesa bloccano lo slot fino ad accettazione/rifiuto
        richieste = RichiestaAppuntamento.query.filter(
            RichiestaAppuntamento.data_richiesta >= da,
            RichiestaAppuntamento.data_richiesta <= a,
            RichiestaAppuntamento.stato == "in_attesa",
        ).all()
        for r in richieste:
            if r.data_richiesta:
                occupati.add(r.data_richiesta.replace(second=0, microsecond=0))
        return occupati

    @classmethod
    def genera_slot(
        cls,
        da: datetime,
        a: datetime,
        solo_liberi: bool = False,
    ) -> List[SlotVirtuale]:
        """Genera slot concreti dall'orario settimanale, escludendo ferie e prenotazioni."""
        da = da.replace(second=0, microsecond=0)
        a = a.replace(second=0, microsecond=0)
        orari = cls._orari_attivi()
        eccezioni = cls.get_eccezioni()
        occupati = cls._appuntamenti_occupati(da, a)

        if not orari:
            return []

        per_giorno: dict[int, List[OrarioSettimanale]] = {i: [] for i in range(7)}
        for orario in orari:
            per_giorno[orario.giorno_settimana].append(orario)

        risultati: List[SlotVirtuale] = []
        giorno_corrente = da.date()
        fine_giorno = a.date()

        while giorno_corrente <= fine_giorno:
            if not cls.is_giorno_chiuso(giorno_corrente, eccezioni):
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
    def slot_liberi(cls, da: Optional[datetime] = None, a: Optional[datetime] = None) -> List[SlotVirtuale]:
        da = da or datetime.now().replace(second=0, microsecond=0)
        a = a or (da + timedelta(days=60))
        return cls.genera_slot(da, a, solo_liberi=True)

    @classmethod
    def slot_per_giorno(cls, giorno: date) -> List[SlotVirtuale]:
        inizio = datetime.combine(giorno, time.min)
        fine = datetime.combine(giorno, time.max)
        return cls.genera_slot(inizio, fine)

    @staticmethod
    def is_slot_disponibile(data_ora: datetime, escludi_richiesta_id: Optional[int] = None) -> bool:
        data_ora = data_ora.replace(second=0, microsecond=0)
        giorno = data_ora.date()
        if AgendaService.is_giorno_chiuso(giorno):
            return False

        orario = OrarioSettimanale.query.filter_by(
            giorno_settimana=giorno.weekday(),
            ora=data_ora.time().replace(second=0, microsecond=0),
            attivo=True,
        ).first()
        if orario is None:
            return False

        esistente = Appuntamento.query.filter(
            Appuntamento.data_appuntamento == data_ora,
            Appuntamento.stato != "annullato",
        ).first()
        if esistente is not None:
            return False

        q = RichiestaAppuntamento.query.filter(
            RichiestaAppuntamento.data_richiesta == data_ora,
            RichiestaAppuntamento.stato == "in_attesa",
        )
        if escludi_richiesta_id is not None:
            q = q.filter(RichiestaAppuntamento.id != escludi_richiesta_id)
        return q.first() is None

    @staticmethod
    def aggiungi_orario(giorno_settimana: int, ora: time, note: Optional[str] = None) -> OrarioSettimanale:
        esistente = OrarioSettimanale.query.filter_by(
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
            giorno_settimana=giorno_settimana,
            ora=ora,
            attivo=True,
            note=note or None,
        )
        db.session.add(row)
        db.session.commit()
        return row

    @staticmethod
    def rimuovi_orario(orario_id: int) -> None:
        row = OrarioSettimanale.query.get_or_404(orario_id)
        db.session.delete(row)
        db.session.commit()

    @staticmethod
    def aggiungi_eccezione(
        data_inizio: date,
        data_fine: date,
        note: Optional[str] = None,
    ) -> AgendaEccezione:
        if data_fine < data_inizio:
            raise ValueError("La data fine deve essere successiva o uguale alla data inizio")
        row = AgendaEccezione(
            data_inizio=data_inizio,
            data_fine=data_fine,
            tipo="chiusura",
            note=note or None,
        )
        db.session.add(row)
        db.session.commit()
        return row

    @staticmethod
    def rimuovi_eccezione(eccezione_id: int) -> None:
        row = AgendaEccezione.query.get_or_404(eccezione_id)
        db.session.delete(row)
        db.session.commit()

    @staticmethod
    def slot_liberi_per_select(limite: int = 100) -> List[dict]:
        """Formato per dropdown prenotazione utente."""
        slot = AgendaService.slot_liberi()[:limite]
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
