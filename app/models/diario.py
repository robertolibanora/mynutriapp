"""Modelli ORM del dominio Diario del paziente.

La tabella paziente riusa ``patients`` (già presente in MySQL): i campi
richiesti dalla feature (email, consensi, nutrizionista_id, timestamps)
sono aggiunti lì. Le tabelle nuove seguono i nomi dello schema diary.
"""

from __future__ import annotations

from app.models.enums import ConsultationStato, UtenteRuolo
from app.models.models import db


class Utente(db.Model):
    """Super admin o nutrizionista (tenant root)."""

    __tablename__ = "utente"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    cognome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    telefono = db.Column(db.String(20), unique=True, nullable=True)
    ruolo = db.Column(
        db.String(20),
        nullable=False,
        default=UtenteRuolo.NUTRIZIONISTA.value,
        server_default=UtenteRuolo.NUTRIZIONISTA.value,
    )
    password_hash = db.Column(db.String(255), nullable=True)
    creato_da = db.Column(
        db.Integer,
        db.ForeignKey("utente.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    attivo = db.Column(db.Boolean, nullable=False, default=True, server_default=db.text("1"))
    # Piano SaaS (starter / professional / studio / enterprise)
    plan = db.Column(
        db.String(32),
        nullable=False,
        default="starter",
        server_default="starter",
    )
    stripe_customer_id = db.Column(db.String(255), nullable=True, unique=True)
    stripe_subscription_id = db.Column(db.String(255), nullable=True)
    subscription_status = db.Column(
        db.String(32),
        nullable=False,
        default="none",
        server_default="none",
    )
    # True = creato da Stripe, deve impostare password su /billing/completa-account
    needs_password_setup = db.Column(
        db.Boolean, nullable=False, default=False, server_default=db.text("0")
    )
    # Slug pubblico per /prenota/<public_slug>
    public_slug = db.Column(db.String(80), nullable=True, unique=True)
    creato_il = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    aggiornato_il = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.now(),
        onupdate=db.func.now(),
    )

    pazienti = db.relationship("Patient", back_populates="nutrizionista", lazy=True)
    consultations = db.relationship("Consultation", back_populates="nutrizionista", lazy=True)
    diary_revisions = db.relationship(
        "DiaryEntry",
        back_populates="revisore",
        lazy=True,
        foreign_keys="DiaryEntry.revisionato_da",
    )
    creatore = db.relationship("Utente", remote_side=[id], foreign_keys=[creato_da])

    @property
    def is_super_admin(self) -> bool:
        return self.ruolo == UtenteRuolo.SUPER_ADMIN.value

    @property
    def is_nutrizionista(self) -> bool:
        return self.ruolo == UtenteRuolo.NUTRIZIONISTA.value

    def __repr__(self) -> str:
        return f"<Utente {self.id} {self.ruolo} {self.email}>"


class Consultation(db.Model):
    """Colloquio / sessione di diario collegata a un paziente."""

    __tablename__ = "consultation"
    __table_args__ = (
        db.Index("ix_consultation_patient_data", "patient_id", "data_colloquio"),
        db.Index("ix_consultation_data_colloquio", "data_colloquio"),
    )

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(
        db.Integer,
        db.ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    nutrizionista_id = db.Column(
        db.Integer,
        db.ForeignKey("utente.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    data_colloquio = db.Column(db.DateTime, nullable=False)
    stato = db.Column(
        db.Enum(ConsultationStato, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=ConsultationStato.BOZZA,
        server_default=ConsultationStato.BOZZA.value,
    )
    note_manuali = db.Column(db.Text, nullable=True)
    errore_pipeline = db.Column(db.Text, nullable=True)
    creato_il = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    aggiornato_il = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.now(),
        onupdate=db.func.now(),
    )

    patient = db.relationship("Patient", back_populates="consultations")
    nutrizionista = db.relationship("Utente", back_populates="consultations")
    audio_recording = db.relationship(
        "AudioRecording",
        back_populates="consultation",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    transcript = db.relationship(
        "Transcript",
        back_populates="consultation",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    diary_entry = db.relationship(
        "DiaryEntry",
        back_populates="consultation",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Consultation {self.id} patient={self.patient_id} stato={self.stato}>"


class AudioRecording(db.Model):
    """File audio associato 1:1 a una consultation."""

    __tablename__ = "audio_recording"

    id = db.Column(db.Integer, primary_key=True)
    consultation_id = db.Column(
        db.Integer,
        db.ForeignKey("consultation.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    path_file = db.Column(db.String(512), nullable=False)
    nome_originale = db.Column(db.String(255), nullable=False)
    mime_type = db.Column(db.String(100), nullable=False)
    dimensione_byte = db.Column(db.BigInteger, nullable=False)
    durata_sec = db.Column(db.Float, nullable=True)
    checksum_sha256 = db.Column(db.String(64), nullable=False)
    cifrato = db.Column(db.Boolean, nullable=False, default=False, server_default=db.text("0"))
    cancellato_il = db.Column(db.DateTime, nullable=True)
    creato_il = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    consultation = db.relationship("Consultation", back_populates="audio_recording")

    def __repr__(self) -> str:
        return f"<AudioRecording {self.id} consultation={self.consultation_id}>"


class Transcript(db.Model):
    """Trascrizione 1:1 di una consultation."""

    __tablename__ = "transcript"

    id = db.Column(db.Integer, primary_key=True)
    consultation_id = db.Column(
        db.Integer,
        db.ForeignKey("consultation.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    testo = db.Column(db.Text, nullable=False)
    lingua = db.Column(db.String(16), nullable=False, default="it", server_default="it")
    provider = db.Column(db.String(64), nullable=False)
    modello = db.Column(db.String(128), nullable=False)
    durata_elaborazione_sec = db.Column(db.Float, nullable=True)
    creato_il = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    consultation = db.relationship("Consultation", back_populates="transcript")

    def __repr__(self) -> str:
        return f"<Transcript {self.id} consultation={self.consultation_id}>"


class DiaryEntry(db.Model):
    """Estratto strutturato del diario (output AI + eventuale revisione)."""

    __tablename__ = "diary_entry"

    id = db.Column(db.Integer, primary_key=True)
    consultation_id = db.Column(
        db.Integer,
        db.ForeignKey("consultation.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    patient_id = db.Column(
        db.Integer,
        db.ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # MySQL 8: tipo JSON (equivalente pratico a JSONB Postgres)
    contenuto_json = db.Column(db.JSON, nullable=False)
    riassunto_testo = db.Column(db.Text, nullable=True)
    modello_usato = db.Column(db.String(128), nullable=False)
    revisionato_da = db.Column(
        db.Integer,
        db.ForeignKey("utente.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    revisionato_il = db.Column(db.DateTime, nullable=True)
    modificato_manualmente = db.Column(
        db.Boolean, nullable=False, default=False, server_default=db.text("0")
    )
    creato_il = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    aggiornato_il = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.now(),
        onupdate=db.func.now(),
    )

    consultation = db.relationship("Consultation", back_populates="diary_entry")
    patient = db.relationship("Patient", back_populates="diary_entries")
    revisore = db.relationship(
        "Utente",
        back_populates="diary_revisions",
        foreign_keys=[revisionato_da],
    )

    def __repr__(self) -> str:
        return f"<DiaryEntry {self.id} patient={self.patient_id}>"
