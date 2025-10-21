-- ========================================
-- 🗄️ SCRIPT DI INIZIALIZZAZIONE DATABASE
-- MyNutriApp - MySQL 8.0
-- ========================================

-- Crea il database se non esiste
CREATE DATABASE IF NOT EXISTS mynutriapp 
CHARACTER SET utf8mb4 
COLLATE utf8mb4_unicode_ci;

-- Crea utente specifico per l'applicazione
CREATE USER IF NOT EXISTS 'mynutriapp'@'%' 
IDENTIFIED BY 'mynutriapp_password_sicura_456!';

-- Assegna tutti i privilegi sul database mynutriapp
GRANT ALL PRIVILEGES ON mynutriapp.* TO 'mynutriapp'@'%';

-- Applica le modifiche
FLUSH PRIVILEGES;

-- Seleziona il database per le operazioni successive
USE mynutriapp;

-- ========================================
-- 📝 NOTE PER L'AMMINISTRATORE:
-- 
-- 1. Questo script viene eseguito automaticamente
--    quando il container MySQL viene avviato per la prima volta
-- 
-- 2. L'utente 'mynutriapp' avrà accesso completo al database
--    'mynutriapp' ma non agli altri database del sistema
-- 
-- 3. La password viene impostata tramite variabile d'ambiente
--    MYSQL_PASSWORD nel file docker-compose.yml
-- 
-- 4. Per sicurezza, l'utente root ha una password diversa
--    impostata tramite MYSQL_ROOT_PASSWORD
-- ========================================
