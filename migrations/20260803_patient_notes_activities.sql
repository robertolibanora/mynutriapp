-- Reversible migration: patient notes + manual activities
-- UP
CREATE TABLE IF NOT EXISTS patient_notes (
  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  patient_id INT NOT NULL,
  utente_id INT NOT NULL,
  body TEXT NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX ix_patient_notes_patient_id (patient_id),
  INDEX ix_patient_notes_utente_id (utente_id),
  CONSTRAINT fk_patient_notes_patient
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE,
  CONSTRAINT fk_patient_notes_utente
    FOREIGN KEY (utente_id) REFERENCES utente(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS activities (
  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  utente_id INT NOT NULL,
  patient_id INT NULL,
  title VARCHAR(255) NOT NULL,
  tipo VARCHAR(40) NOT NULL DEFAULT 'manuale',
  priority VARCHAR(20) NOT NULL DEFAULT 'medium',
  due_at DATETIME NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'open',
  source VARCHAR(20) NOT NULL DEFAULT 'manual',
  notes TEXT NULL,
  created_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at DATETIME NULL,
  INDEX ix_activities_utente_id (utente_id),
  INDEX ix_activities_patient_id (patient_id),
  INDEX ix_activities_due_at (due_at),
  INDEX ix_activities_status (status),
  CONSTRAINT fk_activities_utente
    FOREIGN KEY (utente_id) REFERENCES utente(id) ON DELETE CASCADE,
  CONSTRAINT fk_activities_patient
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- DOWN
-- DROP TABLE IF EXISTS activities;
-- DROP TABLE IF EXISTS patient_notes;
