-- Studio slug, account paziente (invite), token sicuri (invito / reset password)
-- UP

ALTER TABLE utente
  ADD COLUMN studio_nome VARCHAR(120) NULL AFTER public_slug;

-- Backfill: nome studio da slug esistente (best-effort)
UPDATE utente
SET studio_nome = REPLACE(public_slug, '-', ' ')
WHERE public_slug IS NOT NULL AND (studio_nome IS NULL OR studio_nome = '');

ALTER TABLE patients
  ADD COLUMN account_status VARCHAR(20) NOT NULL DEFAULT 'active'
    COMMENT 'invited|active|disabled' AFTER stato_cliente;

ALTER TABLE patients
  ADD COLUMN token_version INT NOT NULL DEFAULT 0 AFTER account_status;

-- Utenti esistenti con password operativa: account attivo
UPDATE patients
SET account_status = 'active'
WHERE account_status IS NULL OR account_status = '';

CREATE TABLE IF NOT EXISTS auth_secure_tokens (
    id INT AUTO_INCREMENT PRIMARY KEY,
    purpose VARCHAR(32) NOT NULL COMMENT 'patient_invite|patient_reset|utente_reset',
    subject_id INT NOT NULL,
    token_hash CHAR(64) NOT NULL,
    expires_at DATETIME NOT NULL,
    used_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_auth_secure_tokens_hash (token_hash),
    KEY ix_auth_secure_tokens_purpose_subject (purpose, subject_id),
    KEY ix_auth_secure_tokens_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- DOWN
-- DROP TABLE IF EXISTS auth_secure_tokens;
-- ALTER TABLE patients DROP COLUMN token_version;
-- ALTER TABLE patients DROP COLUMN account_status;
-- ALTER TABLE utente DROP COLUMN studio_nome;
