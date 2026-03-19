-- ============================================================
-- init.sql — Database schema and seed data
-- Runs automatically when the MySQL container starts fresh.
-- ============================================================

CREATE DATABASE IF NOT EXISTS react_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE react_db;

-- ── Users ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id            VARCHAR(36)  NOT NULL PRIMARY KEY,
    username      VARCHAR(64)  NOT NULL UNIQUE,
    email         VARCHAR(128) NOT NULL UNIQUE,
    full_name     VARCHAR(128) NOT NULL,
    department    VARCHAR(64)  NOT NULL,
    role          VARCHAR(64)  NOT NULL DEFAULT 'employee',
    -- Sensitive column intentionally present to test adapter-level filtering
    salary        DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    password_hash VARCHAR(256) NOT NULL,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ── Conversations ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS conversations (
    id           VARCHAR(36)  NOT NULL PRIMARY KEY,
    user_id      VARCHAR(36)  NOT NULL,
    messages     LONGTEXT     NOT NULL,
    -- user_context: arbitrary JSON blob (language, role, preferences, etc.)
    user_context LONGTEXT     NOT NULL,
    -- rag_id: links this conversation to a specific RAG document set / session
    rag_id       VARCHAR(128) NULL,
    created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_conv_user (user_id),
    INDEX idx_conv_updated (updated_at)
);

-- ── Shipments (ERP simulation) ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS shipments (
    id                 VARCHAR(36)  NOT NULL PRIMARY KEY,
    tracking_number    VARCHAR(64)  NOT NULL UNIQUE,
    status             ENUM(
                           'pending',
                           'processing',
                           'in_transit',
                           'out_for_delivery',
                           'delivered',
                           'returned',
                           'cancelled'
                       ) NOT NULL DEFAULT 'pending',
    origin             VARCHAR(128) NOT NULL,
    destination        VARCHAR(128) NOT NULL,
    estimated_delivery DATE         NULL,
    weight_kg          DECIMAL(8,3) NOT NULL DEFAULT 0.000,
    carrier            VARCHAR(64)  NOT NULL,
    user_id            VARCHAR(36)  NOT NULL,
    created_at         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_ship_user   (user_id),
    INDEX idx_ship_status (status),
    INDEX idx_ship_track  (tracking_number)
);

-- ============================================================
-- Seed data
-- ============================================================

-- Users
INSERT IGNORE INTO users (id, username, email, full_name, department, role, salary, password_hash) VALUES
('user-001', 'alice.johnson',  'alice@acme.com',   'Alice Johnson',   'Logistics',  'logistics_manager', 85000.00, '$2b$12$placeholder_hash_alice'),
('user-002', 'bob.martinez',   'bob@acme.com',     'Bob Martinez',    'Operations', 'operator',          52000.00, '$2b$12$placeholder_hash_bob'),
('user-003', 'carol.white',    'carol@acme.com',   'Carol White',     'Compliance', 'compliance_officer',67000.00, '$2b$12$placeholder_hash_carol'),
('user-004', 'david.kim',      'david@acme.com',   'David Kim',       'IT',         'admin',             95000.00, '$2b$12$placeholder_hash_david'),
('user-005', 'eva.rodriguez',  'eva@acme.com',     'Eva Rodriguez',   'Logistics',  'operator',          51000.00, '$2b$12$placeholder_hash_eva');

-- Shipments
INSERT IGNORE INTO shipments (id, tracking_number, status, origin, destination, estimated_delivery, weight_kg, carrier, user_id) VALUES
('shp-001', 'TRK-2024-000001', 'in_transit',        'Madrid, ES',      'Paris, FR',       '2026-03-20', 12.500, 'DHL Express',   'user-001'),
('shp-002', 'TRK-2024-000002', 'delivered',         'Barcelona, ES',   'London, UK',      '2026-03-10', 3.200,  'FedEx',         'user-001'),
('shp-003', 'TRK-2024-000003', 'pending',           'Berlin, DE',      'Rome, IT',        '2026-03-25', 25.000, 'UPS Freight',   'user-002'),
('shp-004', 'TRK-2024-000004', 'out_for_delivery',  'Amsterdam, NL',   'Warsaw, PL',      '2026-03-18', 7.800,  'GLS',           'user-002'),
('shp-005', 'TRK-2024-000005', 'processing',        'Lisbon, PT',      'Brussels, BE',    '2026-03-22', 0.450,  'TNT',           'user-003'),
('shp-006', 'TRK-2024-000006', 'in_transit',        'Vienna, AT',      'Prague, CZ',      '2026-03-21', 18.000, 'DHL Freight',   'user-003'),
('shp-007', 'TRK-2024-000007', 'returned',          'Stockholm, SE',   'Helsinki, FI',    NULL,          5.100,  'PostNord',      'user-004'),
('shp-008', 'TRK-2024-000008', 'cancelled',         'Dublin, IE',      'Edinburgh, UK',   NULL,          2.300,  'An Post',       'user-005'),
('shp-009', 'TRK-2024-000009', 'delivered',         'Zurich, CH',      'Munich, DE',      '2026-03-12', 9.600,  'Swiss Post',    'user-005'),
('shp-010', 'TRK-2024-000010', 'in_transit',        'Copenhagen, DK',  'Oslo, NO',        '2026-03-19', 33.400, 'DB Schenker',   'user-001');

