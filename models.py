from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# ========================
#   MODEL: Patient
# ========================

class Patient(db.Model):
    __tablename__ = "patients"  # Nome esatto della tabella MySQL

    # 🔑 Chiave primaria
    id = db.Column(db.Integer, primary_key=True)

    # 🔐 Accesso / identificazione
    password_hash = db.Column(db.String(255), nullable=False)
    telefono = db.Column(db.String(20), unique=True, nullable=False)

    # 👤 Dati anagrafici
    nome = db.Column(db.String(100), nullable=False)
    cognome = db.Column(db.String(100), nullable=False)
    sesso = db.Column(db.Enum('M', 'F', 'Altro'), nullable=False)
    data_nascita = db.Column(db.Date, nullable=False)

    # ⚖️ Dati fisici di base
    altezza_cm = db.Column(db.Integer, nullable=False)
    peso_iniziale = db.Column(db.Numeric(5, 2), nullable=False)

    # 🍽️ Dati nutrizionali / sanitari
    intolleranze = db.Column(db.Text)
    cibi_da_ev = db.Column(db.Text)
    patologie = db.Column(db.Text)
    allenamenti_descr = db.Column(db.Text)
    esami_biochimici = db.Column(db.Text)

    # 🕒 Metadati
    data_creazione = db.Column(db.DateTime, server_default=db.func.now())

    # 🔗 Relazioni (1:N)
    diete = db.relationship('Dieta', backref='patient', lazy=True, cascade="all, delete-orphan")
    allenamenti = db.relationship('Allenamento', backref='patient', lazy=True, cascade="all, delete-orphan")
    progressi = db.relationship('Progresso', backref='patient', lazy=True, cascade="all, delete-orphan")
    documenti = db.relationship('Documento', backref='patient', lazy=True, cascade="all, delete-orphan")
    appuntamenti = db.relationship('Appuntamento', backref='patient', lazy=True, cascade="all, delete-orphan")
    vendite = db.relationship('Vendita', backref='patient', lazy=True, cascade="all, delete-orphan")
    misure_antropometriche = db.relationship('MisureAntropometriche', backref='patient', lazy=True, cascade="all, delete-orphan")
    composizione_corporea = db.relationship('ComposizioneCorporea', backref='patient', lazy=True, cascade="all, delete-orphan")

    # 🧠 Metodo utile per debug o pannello admin
    def __repr__(self):
        return f"<Patient {self.nome} {self.cognome}>"

# ========================
#   MODEL: Dieta
# ========================

class Dieta(db.Model):
    __tablename__ = "diete"

    # 🔑 Chiave primaria
    id = db.Column(db.Integer, primary_key=True)

    # 🔗 Relazione 1:N verso Patient
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)

    # 📅 Periodo validità dieta
    data_inizio = db.Column(db.Date, nullable=False)
    data_fine = db.Column(db.Date, nullable=False)

    # 📁 File e contenuti
    pdf_path = db.Column(db.String(255), nullable=False)

    # 🔢 Valori nutrizionali
    kcal = db.Column(db.Integer, nullable=False)
    carbo = db.Column(db.Numeric(6, 2))
    proteine = db.Column(db.Numeric(6, 2))
    grassi = db.Column(db.Numeric(6, 2))

    # 📝 Note personali di Enrico
    note = db.Column(db.Text)

    # 🕒 Data creazione automatica
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def __repr__(self):
        return f"<Dieta {self.id} - Paziente {self.patient_id}>"

# ========================
#   MODEL: Allenamento
# ========================

class Allenamento(db.Model):
    __tablename__ = "allenamenti"

    # 🔑 Chiave primaria
    id = db.Column(db.Integer, primary_key=True)

    # 🔗 Relazione con Patient
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)

    # 📅 Durata piano di allenamento
    data_inizio = db.Column(db.Date, nullable=False)
    data_fine = db.Column(db.Date, nullable=False)

    # 📁 File PDF dell'allenamento
    pdf_path = db.Column(db.String(255), nullable=False)

    # 📝 Note opzionali di Enrico
    note = db.Column(db.Text)

    # 🕒 Creazione automatica record
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def __repr__(self):
        return f"<Allenamento {self.id} - Paziente {self.patient_id}>"

# ========================
#   MODEL: Progresso
# ========================

class Progresso(db.Model):
    __tablename__ = "progressi"

    # 🔑 Chiave primaria
    id = db.Column(db.Integer, primary_key=True)

    # 🔗 Relazione con Patient
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)

    # 📅 Data del controllo settimanale
    data_check = db.Column(db.Date, nullable=False)

    # 🏷️ Tipo di check
    tipo_check = db.Column(
        db.Enum("paziente", "nutrizionista"),
        nullable=False,
        server_default="paziente"
    )

    # ⚖️ Dati fisici misurati (per check paziente)
    peso_settimanale = db.Column(db.Numeric(5, 2))  # ora opzionale
    frequenza_allenamenti = db.Column(db.Text)       # es. "3 allenamenti / settimana"
    foto_path = db.Column(db.String(255))            # upload opzionale
    aderenza = db.Column(db.Integer)                 # punteggio 1–10
    check_richiesta = db.Column(db.Boolean)          # flag se l'utente ha richiesto un check

    # 📏 Dati dinamici in formato JSON (deprecati, ora usiamo tabelle dedicate)
    misure_antropometriche = db.Column(db.JSON)   # DEPRECATO - usa tabella dedicata
    composizione_corporea = db.Column(db.JSON)    # DEPRECATO - usa tabella dedicata

    # 🕒 Timestamp automatico
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    # 🔗 Relazioni con misure dedicate
    misure_antropometriche_rel = db.relationship('MisureAntropometriche', backref='progresso', lazy=True, cascade="all, delete-orphan")
    composizione_corporea_rel = db.relationship('ComposizioneCorporea', backref='progresso', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Progresso {self.id} - Paziente {self.patient_id} - {self.tipo_check}>"

# ========================
#   MODEL: MisureAntropometriche
# ========================

class MisureAntropometriche(db.Model):
    __tablename__ = "misure_antropometriche"

    # 🔑 Chiave primaria
    id = db.Column(db.Integer, primary_key=True)

    # 🔗 Relazione con Patient
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)

    # 🔗 Relazione con Progresso (opzionale, per collegare a un controllo specifico)
    progresso_id = db.Column(db.Integer, db.ForeignKey("progressi.id"), nullable=True)

    # 📅 Data della misurazione
    data_misurazione = db.Column(db.Date, nullable=False)

    # 📏 Circonferenze (in cm)
    circonferenza_braccio = db.Column(db.Numeric(5, 2))
    circonferenza_spalle = db.Column(db.Numeric(5, 2))
    circonferenza_torace = db.Column(db.Numeric(5, 2))
    circonferenza_vita = db.Column(db.Numeric(5, 2))
    circonferenza_fianchi = db.Column(db.Numeric(5, 2))
    circonferenza_coscia = db.Column(db.Numeric(5, 2))
    circonferenza_polpaccio = db.Column(db.Numeric(5, 2))

    # 📏 Pliche cutanee (in mm)
    plica_addominale = db.Column(db.Numeric(5, 2))
    plica_tricipitale = db.Column(db.Numeric(5, 2))
    plica_soprailiaca = db.Column(db.Numeric(5, 2))
    plica_sottoscapolare = db.Column(db.Numeric(5, 2))
    plica_cutanea_coscia = db.Column(db.Numeric(5, 2))

    # 📝 Note aggiuntive
    note = db.Column(db.Text)

    # 🕒 Timestamp automatico
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def __repr__(self):
        return f"<MisureAntropometriche {self.id} - Paziente {self.patient_id}>"

# ========================
#   MODEL: ComposizioneCorporea
# ========================

class ComposizioneCorporea(db.Model):
    __tablename__ = "composizione_corporea"

    # 🔑 Chiave primaria
    id = db.Column(db.Integer, primary_key=True)

    # 🔗 Relazione con Patient
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)

    # 🔗 Relazione con Progresso (opzionale, per collegare a un controllo specifico)
    progresso_id = db.Column(db.Integer, db.ForeignKey("progressi.id"), nullable=True)

    # 📅 Data della misurazione
    data_misurazione = db.Column(db.Date, nullable=False)

    # 🧮 Composizione corporea (in % o kg)
    grasso_corporeo = db.Column(db.Numeric(5, 2))  # %
    massa_muscolare = db.Column(db.Numeric(5, 2))  # kg
    grasso_viscerale = db.Column(db.Numeric(5, 2))  # livello 1-59
    tbw = db.Column(db.Numeric(5, 2))  # Total Body Water in %
    tasso_metabolico_basale = db.Column(db.Integer)  # kcal/giorno
    eta_metabolica = db.Column(db.Integer)  # anni
    punteggio_postura = db.Column(db.Integer)  # 0-100
    massa_ossea = db.Column(db.Numeric(5, 2))  # kg
    bmi = db.Column(db.Numeric(5, 2))  # kg/m²

    # 📝 Note aggiuntive
    note = db.Column(db.Text)

    # 🕒 Timestamp automatico
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def __repr__(self):
        return f"<ComposizioneCorporea {self.id} - Paziente {self.patient_id}>"

# ========================
#   MODEL: Documento
# ========================

class Documento(db.Model):
    __tablename__ = "documents"

    # 🔑 Chiave primaria
    id = db.Column(db.Integer, primary_key=True)

    # 🔗 Relazione con Patient
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)

    # 📄 Tipo documento
    tipo = db.Column(
        db.Enum("analisi", "referto", "excel", "pdf_altro"),
        nullable=False
    )

    # 📁 Percorso del file caricato
    file_path = db.Column(db.String(255), nullable=False)

    # 📝 Descrizione opzionale (es. “Analisi sangue gennaio 2025”)
    descrizione = db.Column(db.Text)

    # 🕒 Timestamp automatico
    data_upload = db.Column(db.DateTime, server_default=db.func.now())

    def __repr__(self):
        return f"<Documento {self.tipo} - Paziente {self.patient_id}>"

# ========================
#   MODEL: Appuntamento
# ========================

class Appuntamento(db.Model):
    __tablename__ = "appuntamenti"

    # 🔑 Chiave primaria
    id = db.Column(db.Integer, primary_key=True)

    # 🔗 Relazioni esterne
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    vendita_id = db.Column(db.Integer, db.ForeignKey("vendite.id"), nullable=True)

    # 🧑‍⚕️ Creatore dell'appuntamento
    created_by = db.Column(db.Enum("Enrico", "user"), nullable=False)

    # 📅 Informazioni temporali
    data_appuntamento = db.Column(db.DateTime, nullable=False)
    tipo = db.Column(
        db.Enum("allenamento_1to1", "rinnovo_dieta", "rinnovo_allenamento", "check", "altro"),
        nullable=False
    )

    # ⚙️ Stato gestione
    stato = db.Column(
        db.Enum("in_attesa", "confermato", "completato", "annullato"),
        nullable=False,
        server_default="in_attesa"
    )

    # 📝 Dettagli e note
    note = db.Column(db.Text)

    # 🔔 Promemoria WhatsApp
    promemoria_inviato = db.Column(db.Boolean, nullable=False, server_default="0")

    # 🕒 Timestamp automatico
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    # 🔗 Relazione con Vendita (una vendita può avere più appuntamenti)
    vendita = db.relationship("Vendita", back_populates="appuntamenti", lazy=True)

    def __repr__(self):
        return f"<Appuntamento {self.id} - Paziente {self.patient_id}>"

# ========================
#   MODEL: Listino
# ========================

class Listino(db.Model):
    __tablename__ = "listino"

    # 🔑 Chiave primaria
    id = db.Column(db.Integer, primary_key=True)

    # 📦 Dati principali
    nome_prodotto = db.Column(db.String(100), nullable=False)
    categoria = db.Column(
        db.Enum("nutrizione", "allenamento", "completo", "1to1"),
        nullable=False
    )
    durata_mesi = db.Column(db.Integer, nullable=False)

    # 📅 Dati accessori
    check_inclusi = db.Column(db.Integer, server_default="0")
    prezzo = db.Column(db.Numeric(8, 2), nullable=False)
    
    
    note = db.Column(db.Text)

    # ⚙️ Attivazione prodotto
    attivo = db.Column(db.Boolean, nullable=False, server_default="1")

    # 🕒 Timestamp automatico
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    # 🔗 Relazione con Vendite (1:N)
    vendite = db.relationship("Vendita", backref="listino", lazy=True)

    def __repr__(self):
        return f"<Listino {self.nome_prodotto} - {self.categoria}>"
    

# ========================
#   MODEL: Vendita
# ========================

class Vendita(db.Model):
    __tablename__ = "vendite"

    # 🔑 Chiave primaria
    id = db.Column(db.Integer, primary_key=True)

    # 🔗 Relazioni con altre tabelle
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    listino_id = db.Column(db.Integer, db.ForeignKey("listino.id"), nullable=False)

    # 💰 Dati principali della transazione
    data_acquisto = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    data_inizio = db.Column(db.Date, nullable=False)

    metodo_pagamento = db.Column(
        db.Enum("contanti", "bonifico", "carta", "altro"),
        nullable=False,
        server_default="contanti"
    )

    sconto = db.Column(db.Numeric(6, 2), server_default="0.00")
    
    # 💰 Importo finale
    importo_finale = db.Column(db.Numeric(8, 2), nullable=False)

    stato = db.Column(
        db.Enum("pagato", "in_attesa", "rimborsato"),
        nullable=False,
        server_default="pagato"
    )

    # 📝 Note o memo contabili
    note = db.Column(db.Text)

    # 🕒 Timestamp
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    # 🔗 Relazioni inverse
    appuntamenti = db.relationship("Appuntamento", back_populates="vendita", lazy=True)

    def __repr__(self):
        return f"<Vendita {self.id} - Paziente {self.patient_id} - Importo {self.importo_finale}€>"

# ========================
#   MODEL: SlotDisponibilita
# ========================

class SlotDisponibilita(db.Model):
    __tablename__ = "slot_disponibilita"

    # 🔑 Chiave primaria
    id = db.Column(db.Integer, primary_key=True)

    # 📅 Data e ora dello slot
    data_ora = db.Column(db.DateTime, nullable=False, unique=True)

    # ✅ Slot attivo o disattivato
    attivo = db.Column(db.Boolean, default=True, nullable=False)

    # 📝 Note opzionali (es: "Solo prima visita")
    note = db.Column(db.String(255))

    # 🕒 Timestamp creazione
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def __repr__(self):
        return f"<SlotDisponibilita {self.data_ora.strftime('%d/%m/%Y %H:%M')}>"