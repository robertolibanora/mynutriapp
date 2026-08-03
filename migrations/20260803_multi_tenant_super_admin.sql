-- Multi-tenant: super_admin + FK utente su pazienti/agenda
-- Target: mynutriapp_staging (eseguire con mysql root/socket)

USE mynutriapp_staging;

-- ========================================
-- 1) UTENTE: ruolo, password, creato_da
-- ========================================
ALTER TABLE utente
  ADD COLUMN IF NOT EXISTS ruolo VARCHAR(20) NOT NULL DEFAULT 'nutrizionista' AFTER telefono,
  ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255) NULL AFTER ruolo,
  ADD COLUMN IF NOT EXISTS creato_da INT NULL AFTER password_hash;

-- MySQL < 8.0.12 non ha IF NOT EXISTS su ADD COLUMN: gestito anche da script Python.
-- Indici / FK creato_da
-- (aggiunti nello script Python se mancanti)

-- ========================================
-- 2) PATIENTS: unique compositi + nutrizionista obbligatorio (dopo backfill)
-- ========================================
-- Eseguito via Python (drop unique, add composite, backfill, NOT NULL)

-- ========================================
-- 3) AGENDA / RICHIESTE / APPUNTAMENTI / FOODS
-- ========================================
-- Eseguito via Python idempotente in app/utils/db_schema.py::ensure_multi_tenant_schema
;
