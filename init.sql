-- ========================================
-- 🗄️ SCRIPT DI INIZIALIZZAZIONE DATABASE
-- MyNutriApp - MySQL 8.0
-- ========================================
--
-- Importa su MySQL nativo (systemd):
--   mysql -u root -p < init.sql
--
-- Crea prima database e utente, ad esempio:
--   CREATE DATABASE mynutriapp CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
--   CREATE USER 'mynutriapp'@'localhost' IDENTIFIED BY 'password';
--   GRANT ALL PRIVILEGES ON mynutriapp.* TO 'mynutriapp'@'localhost';
--   FLUSH PRIVILEGES;
--
-- Questo script crea tutte le tabelle necessarie per l'applicazione.
-- ========================================

-- Seleziona il database (già creato da MySQL)
USE mynutriapp;

-- ========================================
-- 📋 TABELLA: patients
-- ========================================
CREATE TABLE IF NOT EXISTS patients (
    id INT AUTO_INCREMENT PRIMARY KEY,
    password_hash VARCHAR(255) NOT NULL,
    telefono VARCHAR(20) NOT NULL UNIQUE,
    nome VARCHAR(100) NOT NULL,
    cognome VARCHAR(100) NOT NULL,
    sesso ENUM('M', 'F', 'Altro') NOT NULL,
    data_nascita DATE NOT NULL,
    altezza_cm INT NOT NULL,
    peso_iniziale DECIMAL(5, 2) NOT NULL,
    intolleranze TEXT,
    cibi_da_ev TEXT,
    patologie TEXT,
    allenamenti_descr TEXT,
    esami_biochimici TEXT,
    data_creazione DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_telefono (telefono),
    INDEX idx_nome_cognome (nome, cognome)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ========================================
-- 📋 TABELLA: diete
-- ========================================
CREATE TABLE IF NOT EXISTS diete (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id INT NOT NULL,
    data_inizio DATE NOT NULL,
    data_fine DATE NOT NULL,
    pdf_path VARCHAR(255) NOT NULL,
    kcal INT NOT NULL,
    carbo DECIMAL(6, 2),
    proteine DECIMAL(6, 2),
    grassi DECIMAL(6, 2),
    note TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
    INDEX idx_patient_id (patient_id),
    INDEX idx_date_range (data_inizio, data_fine)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ========================================
-- 📋 TABELLA: allenamenti
-- ========================================
CREATE TABLE IF NOT EXISTS allenamenti (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id INT NOT NULL,
    data_inizio DATE NOT NULL,
    data_fine DATE NOT NULL,
    pdf_path VARCHAR(255) NOT NULL,
    note TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
    INDEX idx_patient_id (patient_id),
    INDEX idx_date_range (data_inizio, data_fine)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ========================================
-- 📋 TABELLA: progressi
-- ========================================
CREATE TABLE IF NOT EXISTS progressi (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id INT NOT NULL,
    data_check DATE NOT NULL,
    tipo_check ENUM('paziente', 'nutrizionista') NOT NULL DEFAULT 'paziente',
    peso_settimanale DECIMAL(5, 2),
    frequenza_allenamenti TEXT,
    foto_path VARCHAR(255),
    aderenza INT,
    check_richiesta BOOLEAN DEFAULT FALSE,
    misure_antropometriche JSON,
    composizione_corporea JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
    INDEX idx_patient_id (patient_id),
    INDEX idx_data_check (data_check),
    INDEX idx_tipo_check (tipo_check)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ========================================
-- 📋 TABELLA: misure_antropometriche
-- ========================================
CREATE TABLE IF NOT EXISTS misure_antropometriche (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id INT NOT NULL,
    progresso_id INT,
    data_misurazione DATE NOT NULL,
    circonferenza_braccio DECIMAL(5, 2),
    circonferenza_spalle DECIMAL(5, 2),
    circonferenza_torace DECIMAL(5, 2),
    circonferenza_vita DECIMAL(5, 2),
    circonferenza_fianchi DECIMAL(5, 2),
    circonferenza_coscia DECIMAL(5, 2),
    circonferenza_polpaccio DECIMAL(5, 2),
    plica_addominale DECIMAL(5, 2),
    plica_tricipitale DECIMAL(5, 2),
    plica_soprailiaca DECIMAL(5, 2),
    plica_sottoscapolare DECIMAL(5, 2),
    plica_cutanea_coscia DECIMAL(5, 2),
    note TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
    FOREIGN KEY (progresso_id) REFERENCES progressi(id) ON DELETE SET NULL,
    INDEX idx_patient_id (patient_id),
    INDEX idx_data_misurazione (data_misurazione)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ========================================
-- 📋 TABELLA: composizione_corporea
-- ========================================
CREATE TABLE IF NOT EXISTS composizione_corporea (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id INT NOT NULL,
    progresso_id INT,
    data_misurazione DATE NOT NULL,
    grasso_corporeo DECIMAL(5, 2),
    massa_muscolare DECIMAL(5, 2),
    grasso_viscerale DECIMAL(5, 2),
    tbw DECIMAL(5, 2),
    tasso_metabolico_basale INT,
    eta_metabolica INT,
    punteggio_postura INT,
    massa_ossea DECIMAL(5, 2),
    bmi DECIMAL(5, 2),
    note TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
    FOREIGN KEY (progresso_id) REFERENCES progressi(id) ON DELETE SET NULL,
    INDEX idx_patient_id (patient_id),
    INDEX idx_data_misurazione (data_misurazione)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ========================================
-- 📋 TABELLA: documents
-- ========================================
CREATE TABLE IF NOT EXISTS documents (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id INT NOT NULL,
    tipo ENUM('analisi', 'referto', 'excel', 'pdf_altro') NOT NULL,
    file_path VARCHAR(255) NOT NULL,
    descrizione TEXT,
    data_upload DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
    INDEX idx_patient_id (patient_id),
    INDEX idx_tipo (tipo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ========================================
-- 📋 TABELLA: listino
-- ========================================
CREATE TABLE IF NOT EXISTS listino (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome_prodotto VARCHAR(100) NOT NULL,
    categoria ENUM('nutrizione', 'allenamento', 'completo', '1to1') NOT NULL,
    durata_mesi INT NOT NULL,
    check_inclusi INT DEFAULT 0,
    prezzo DECIMAL(8, 2) NOT NULL,
    note TEXT,
    attivo BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_categoria (categoria),
    INDEX idx_attivo (attivo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ========================================
-- 📋 TABELLA: vendite
-- ========================================
CREATE TABLE IF NOT EXISTS vendite (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id INT NOT NULL,
    listino_id INT NOT NULL,
    data_acquisto DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    data_inizio DATE NOT NULL,
    metodo_pagamento ENUM('contanti', 'bonifico', 'carta', 'altro') NOT NULL DEFAULT 'contanti',
    sconto DECIMAL(6, 2) DEFAULT 0.00,
    importo_finale DECIMAL(8, 2) NOT NULL,
    stato ENUM('pagato', 'in_attesa', 'rimborsato') NOT NULL DEFAULT 'pagato',
    note TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
    FOREIGN KEY (listino_id) REFERENCES listino(id) ON DELETE RESTRICT,
    INDEX idx_patient_id (patient_id),
    INDEX idx_listino_id (listino_id),
    INDEX idx_data_acquisto (data_acquisto),
    INDEX idx_stato (stato)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ========================================
-- 📋 TABELLA: appuntamenti
-- ========================================
CREATE TABLE IF NOT EXISTS appuntamenti (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id INT NOT NULL,
    vendita_id INT,
    created_by ENUM('Enrico', 'user') NOT NULL,
    data_appuntamento DATETIME NOT NULL,
    tipo ENUM('allenamento_1to1', 'rinnovo_dieta', 'rinnovo_allenamento', 'check', 'altro') NOT NULL,
    stato ENUM('in_attesa', 'confermato', 'completato', 'annullato') NOT NULL DEFAULT 'in_attesa',
    note TEXT,
    promemoria_inviato BOOLEAN NOT NULL DEFAULT FALSE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
    FOREIGN KEY (vendita_id) REFERENCES vendite(id) ON DELETE SET NULL,
    INDEX idx_patient_id (patient_id),
    INDEX idx_vendita_id (vendita_id),
    INDEX idx_data_appuntamento (data_appuntamento),
    INDEX idx_stato (stato)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ========================================
-- 📋 TABELLA: slot_disponibilita
-- ========================================
CREATE TABLE IF NOT EXISTS slot_disponibilita (
    id INT AUTO_INCREMENT PRIMARY KEY,
    data_ora DATETIME NOT NULL UNIQUE,
    attivo BOOLEAN NOT NULL DEFAULT TRUE,
    note VARCHAR(255),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_data_ora (data_ora),
    INDEX idx_attivo (attivo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ========================================
-- 📋 TABELLA: segretario_config (Segretario AI inbound Vapi)
-- ========================================
CREATE TABLE IF NOT EXISTS segretario_config (
    id INT AUTO_INCREMENT PRIMARY KEY,
    attivo BOOLEAN NOT NULL DEFAULT FALSE,
    deviazione_attiva BOOLEAN NOT NULL DEFAULT FALSE,
    deviazione_aggiornata_at DATETIME,
    numero_nutrizionista VARCHAR(30),
    nome_studio VARCHAR(120) DEFAULT 'MyNutriApp',
    nome_assistente VARCHAR(80) DEFAULT 'Sara',
    messaggio_benvenuto TEXT,
    istruzioni_ai TEXT,
    inoltra_a_nutrizionista BOOLEAN NOT NULL DEFAULT TRUE,
    conferma_whatsapp BOOLEAN NOT NULL DEFAULT TRUE,
    ultimo_sync DATETIME,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ========================================
-- 📋 TABELLA: chiamate_inbound (log chiamate Segretario AI)
-- ========================================
CREATE TABLE IF NOT EXISTS chiamate_inbound (
    id INT AUTO_INCREMENT PRIMARY KEY,
    vapi_call_id VARCHAR(100) UNIQUE,
    numero_chiamante VARCHAR(30),
    direzione VARCHAR(20) DEFAULT 'inbound',
    patient_id INT NULL,
    stato VARCHAR(30),
    esito VARCHAR(80),
    durata_secondi INT,
    costo_usd DECIMAL(8, 4),
    trascrizione TEXT,
    riassunto TEXT,
    registrazione_url VARCHAR(500),
    appuntamento_creato BOOLEAN NOT NULL DEFAULT FALSE,
    appuntamento_id INT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE SET NULL,
    FOREIGN KEY (appuntamento_id) REFERENCES appuntamenti(id) ON DELETE SET NULL,
    INDEX idx_vapi_call_id (vapi_call_id),
    INDEX idx_numero_chiamante (numero_chiamante),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ========================================
-- 📋 TABELLA: audit_log
-- ========================================
CREATE TABLE IF NOT EXISTS audit_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    timestamp DATETIME NOT NULL,
    user_id INT NULL,
    user_role ENUM('admin', 'user', 'anonymous') NOT NULL,
    action VARCHAR(50) NOT NULL,
    resource_type VARCHAR(50) NOT NULL,
    resource_id INT NULL,
    ip_address VARCHAR(45),
    user_agent VARCHAR(255),
    details TEXT,
    INDEX idx_timestamp (timestamp),
    INDEX idx_action (action),
    INDEX idx_resource_type (resource_type),
    INDEX idx_resource_id (resource_id),
    INDEX idx_user_time (user_id, timestamp),
    INDEX idx_resource (resource_type, resource_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ========================================
-- ✅ VERIFICA CREAZIONE TABELLE
-- ========================================
-- Mostra tutte le tabelle create
SHOW TABLES;

-- ========================================
-- 📝 NOTE FINALI
-- ========================================
-- 
-- ✅ Tutte le tabelle sono state create con:
--    - Charset UTF8MB4 per supporto completo Unicode
--    - Foreign keys con CASCADE o RESTRICT appropriati
--    - Indici per ottimizzare le query più comuni
--    - Timestamp automatici per tracciamento
-- 
-- 🔄 Per ricreare il database da zero:
--    1. DROP DATABASE mynutriapp;
--    2. Ricrea database e utente (vedi header)
--    3. Reimporta: mysql -u root -p < init.sql
-- 
-- 📊 Le tabelle sono pronte per l'uso con Flask-SQLAlchemy!
-- ========================================
