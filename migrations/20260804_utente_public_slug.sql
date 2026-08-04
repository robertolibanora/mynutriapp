-- Public booking slug for /prenota/<slug>
-- UP
ALTER TABLE utente
  ADD COLUMN public_slug VARCHAR(80) NULL AFTER needs_password_setup;

ALTER TABLE utente
  ADD UNIQUE KEY uq_utente_public_slug (public_slug);

-- DOWN
-- ALTER TABLE utente DROP INDEX uq_utente_public_slug;
-- ALTER TABLE utente DROP COLUMN public_slug;
