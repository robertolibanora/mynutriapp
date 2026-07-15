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
-- 📋 TABELLA: appuntamenti
-- ========================================
CREATE TABLE IF NOT EXISTS appuntamenti (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id INT NOT NULL,
    created_by ENUM('Enrico', 'user') NOT NULL,
    data_appuntamento DATETIME NOT NULL,
    tipo ENUM('allenamento_1to1', 'rinnovo_dieta', 'rinnovo_allenamento', 'check', 'altro') NOT NULL,
    stato ENUM('in_attesa', 'confermato', 'completato', 'annullato') NOT NULL DEFAULT 'in_attesa',
    note TEXT,
    promemoria_inviato BOOLEAN NOT NULL DEFAULT FALSE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
    INDEX idx_patient_id (patient_id),
    INDEX idx_data_appuntamento (data_appuntamento),
    INDEX idx_stato (stato)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ========================================
-- 📋 TABELLA: richieste_appuntamento (lead da landing pubblica)
-- ========================================
CREATE TABLE IF NOT EXISTS richieste_appuntamento (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    cognome VARCHAR(100) NOT NULL,
    telefono VARCHAR(20) NOT NULL,
    email VARCHAR(120),
    data_richiesta DATETIME NOT NULL,
    tipo ENUM('allenamento_1to1', 'rinnovo_dieta', 'rinnovo_allenamento', 'check', 'altro') NOT NULL DEFAULT 'altro',
    note TEXT,
    stato ENUM('in_attesa', 'accettata', 'rifiutata') NOT NULL DEFAULT 'in_attesa',
    patient_id INT,
    appuntamento_id INT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE SET NULL,
    FOREIGN KEY (appuntamento_id) REFERENCES appuntamenti(id) ON DELETE SET NULL,
    INDEX idx_richieste_stato (stato),
    INDEX idx_richieste_data (data_richiesta),
    INDEX idx_richieste_telefono (telefono)
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
-- 📋 TABELLA: orari_settimanali (slot ordinari ricorrenti)
-- ========================================
CREATE TABLE IF NOT EXISTS orari_settimanali (
    id INT AUTO_INCREMENT PRIMARY KEY,
    giorno_settimana INT NOT NULL,
    ora TIME NOT NULL,
    attivo BOOLEAN NOT NULL DEFAULT TRUE,
    note VARCHAR(255),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_orario_settimanale_giorno_ora (giorno_settimana, ora),
    INDEX idx_giorno_settimana (giorno_settimana)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ========================================
-- 📋 TABELLA: agenda_eccezioni (ferie / chiusure)
-- ========================================
CREATE TABLE IF NOT EXISTS agenda_eccezioni (
    id INT AUTO_INCREMENT PRIMARY KEY,
    data_inizio DATE NOT NULL,
    data_fine DATE NOT NULL,
    tipo VARCHAR(20) NOT NULL DEFAULT 'chiusura',
    note VARCHAR(255),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_data_inizio (data_inizio),
    INDEX idx_data_fine (data_fine)
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
    nome_assistente VARCHAR(80) DEFAULT 'Mario',
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
-- 📋 TABELLA: foods (alimenti locali: importati da provider o custom)
-- ========================================
CREATE TABLE IF NOT EXISTS foods (
    id INT AUTO_INCREMENT PRIMARY KEY,
    professional_id INT NULL,
    provider VARCHAR(50) NULL,
    external_id VARCHAR(100) NULL,
    name VARCHAR(255) NOT NULL,
    brand VARCHAR(255) NULL,
    category VARCHAR(255) NULL,
    serving_size DECIMAL(8, 2) NULL,
    serving_unit VARCHAR(20) NULL,
    kcal_per_100g DECIMAL(8, 2) NULL,
    protein_per_100g DECIMAL(8, 2) NULL,
    carbs_per_100g DECIMAL(8, 2) NULL,
    sugars_per_100g DECIMAL(8, 2) NULL,
    fat_per_100g DECIMAL(8, 2) NULL,
    saturated_fat_per_100g DECIMAL(8, 2) NULL,
    fiber_per_100g DECIMAL(8, 2) NULL,
    salt_per_100g DECIMAL(8, 2) NULL,
    sodium_per_100g DECIMAL(8, 2) NULL,
    source_payload_json JSON NULL,
    is_custom BOOLEAN NOT NULL DEFAULT FALSE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_food_provider_external (provider, external_id),
    INDEX idx_food_professional (professional_id),
    INDEX idx_food_provider (provider),
    INDEX idx_food_external (external_id),
    INDEX idx_food_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ========================================
-- 📋 TABELLA: diet_plans (piano alimentare strutturato)
-- ========================================
CREATE TABLE IF NOT EXISTS diet_plans (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id INT NOT NULL,
    professional_id INT NULL,
    title VARCHAR(255) NOT NULL,
    goal VARCHAR(255) NULL,
    notes TEXT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
    INDEX idx_diet_plan_patient (patient_id),
    INDEX idx_diet_plan_professional (professional_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ========================================
-- 📋 TABELLA: diet_meals (pasti di un piano)
-- ========================================
CREATE TABLE IF NOT EXISTS diet_meals (
    id INT AUTO_INCREMENT PRIMARY KEY,
    diet_plan_id INT NOT NULL,
    day_index INT NOT NULL DEFAULT 0,
    meal_name VARCHAR(100) NOT NULL,
    meal_time TIME NULL,
    notes TEXT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (diet_plan_id) REFERENCES diet_plans(id) ON DELETE CASCADE,
    INDEX idx_diet_meal_plan (diet_plan_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ========================================
-- 📋 TABELLA: diet_meal_items (alimento + quantità in un pasto)
-- ========================================
CREATE TABLE IF NOT EXISTS diet_meal_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    diet_meal_id INT NOT NULL,
    food_id INT NOT NULL,
    quantity_g DECIMAL(8, 2) NOT NULL,
    notes TEXT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (diet_meal_id) REFERENCES diet_meals(id) ON DELETE CASCADE,
    FOREIGN KEY (food_id) REFERENCES foods(id) ON DELETE RESTRICT,
    INDEX idx_diet_meal_item_meal (diet_meal_id),
    INDEX idx_diet_meal_item_food (food_id)
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
