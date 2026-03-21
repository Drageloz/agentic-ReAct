-- ============================================================
-- init.sql — T-SQL schema and seed data for SQL Server
-- Executed by db-init container on first run.
-- Compatible with: SQL Server 2019/2022 (Docker) & Azure SQL
-- ============================================================

-- Create database if it doesn't exist
IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'react_db')
BEGIN
    CREATE DATABASE react_db;
END
GO

USE react_db;
GO

-- ── Users ─────────────────────────────────────────────────────────────────────
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'users')
BEGIN
    CREATE TABLE users (
        id            NVARCHAR(36)   NOT NULL PRIMARY KEY,
        username      NVARCHAR(64)   NOT NULL,
        email         NVARCHAR(128)  NOT NULL,
        full_name     NVARCHAR(128)  NOT NULL,
        department    NVARCHAR(64)   NOT NULL,
        role          NVARCHAR(64)   NOT NULL DEFAULT 'employee',
        -- Sensitive column intentionally present to test adapter-level filtering
        salary        DECIMAL(10,2)  NOT NULL DEFAULT 0.00,
        password_hash NVARCHAR(256)  NOT NULL,
        created_at    DATETIME2      NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT uq_users_username UNIQUE (username),
        CONSTRAINT uq_users_email    UNIQUE (email)
    );
END
GO

-- ── Conversations ──────────────────────────────────────────────────────────────
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'conversations')
BEGIN
    CREATE TABLE conversations (
        id           NVARCHAR(36)   NOT NULL PRIMARY KEY,
        user_id      NVARCHAR(36)   NOT NULL,
        messages     NVARCHAR(MAX)  NOT NULL,
        user_context NVARCHAR(MAX)  NOT NULL,
        rag_id       NVARCHAR(128)  NULL,
        created_at   DATETIME2      NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_at   DATETIME2      NOT NULL DEFAULT SYSUTCDATETIME()
    );
    CREATE INDEX idx_conv_user    ON conversations (user_id);
    CREATE INDEX idx_conv_updated ON conversations (updated_at);
END
GO

-- ── Shipments (ERP simulation) ────────────────────────────────────────────────
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'shipments')
BEGIN
    CREATE TABLE shipments (
        id                 NVARCHAR(36)   NOT NULL PRIMARY KEY,
        tracking_number    NVARCHAR(64)   NOT NULL,
        status             NVARCHAR(32)   NOT NULL DEFAULT 'pending'
                               CONSTRAINT chk_ship_status CHECK (status IN (
                                   'pending','processing','in_transit',
                                   'out_for_delivery','delivered','returned','cancelled'
                               )),
        origin             NVARCHAR(128)  NOT NULL,
        destination        NVARCHAR(128)  NOT NULL,
        estimated_delivery DATE           NULL,
        weight_kg          DECIMAL(8,3)   NOT NULL DEFAULT 0.000,
        carrier            NVARCHAR(64)   NOT NULL,
        user_id            NVARCHAR(36)   NOT NULL,
        created_at         DATETIME2      NOT NULL DEFAULT SYSUTCDATETIME(),
        CONSTRAINT uq_ship_tracking UNIQUE (tracking_number)
    );
    CREATE INDEX idx_ship_user   ON shipments (user_id);
    CREATE INDEX idx_ship_status ON shipments (status);
    CREATE INDEX idx_ship_track  ON shipments (tracking_number);
END
GO

-- ============================================================
-- Seed data (idempotent — MERGE won't duplicate rows)
-- ============================================================

-- Users
MERGE users AS target
USING (VALUES
    ('user-001','alice.johnson','alice@acme.com','Alice Johnson','Logistics','logistics_manager',85000.00,'$2b$12$placeholder_hash_alice'),
    ('user-002','bob.martinez','bob@acme.com','Bob Martinez','Operations','operator',52000.00,'$2b$12$placeholder_hash_bob'),
    ('user-003','carol.white','carol@acme.com','Carol White','Compliance','compliance_officer',67000.00,'$2b$12$placeholder_hash_carol'),
    ('user-004','david.kim','david@acme.com','David Kim','IT','admin',95000.00,'$2b$12$placeholder_hash_david'),
    ('user-005','eva.rodriguez','eva@acme.com','Eva Rodriguez','Logistics','operator',51000.00,'$2b$12$placeholder_hash_eva')
) AS source(id,username,email,full_name,department,role,salary,password_hash)
ON target.id = source.id
WHEN NOT MATCHED THEN
    INSERT (id,username,email,full_name,department,role,salary,password_hash)
    VALUES (source.id,source.username,source.email,source.full_name,
            source.department,source.role,source.salary,source.password_hash);
GO

-- Shipments
MERGE shipments AS target
USING (VALUES
    ('shp-001','TRK-2024-000001','in_transit','Madrid, ES','Paris, FR','2026-03-20',12.500,'DHL Express','user-001'),
    ('shp-002','TRK-2024-000002','delivered','Barcelona, ES','London, UK','2026-03-10',3.200,'FedEx','user-001'),
    ('shp-003','TRK-2024-000003','pending','Berlin, DE','Rome, IT','2026-03-25',25.000,'UPS Freight','user-002'),
    ('shp-004','TRK-2024-000004','out_for_delivery','Amsterdam, NL','Warsaw, PL','2026-03-18',7.800,'GLS','user-002'),
    ('shp-005','TRK-2024-000005','processing','Lisbon, PT','Brussels, BE','2026-03-22',0.450,'TNT','user-003'),
    ('shp-006','TRK-2024-000006','in_transit','Vienna, AT','Prague, CZ','2026-03-21',18.000,'DHL Freight','user-003'),
    ('shp-007','TRK-2024-000007','returned','Stockholm, SE','Helsinki, FI',NULL,5.100,'PostNord','user-004'),
    ('shp-008','TRK-2024-000008','cancelled','Dublin, IE','Edinburgh, UK',NULL,2.300,'An Post','user-005'),
    ('shp-009','TRK-2024-000009','delivered','Zurich, CH','Munich, DE','2026-03-12',9.600,'Swiss Post','user-005'),
    ('shp-010','TRK-2024-000010','in_transit','Copenhagen, DK','Oslo, NO','2026-03-19',33.400,'DB Schenker','user-001')
) AS source(id,tracking_number,status,origin,destination,estimated_delivery,weight_kg,carrier,user_id)
ON target.id = source.id
WHEN NOT MATCHED THEN
    INSERT (id,tracking_number,status,origin,destination,estimated_delivery,weight_kg,carrier,user_id)
    VALUES (source.id,source.tracking_number,source.status,source.origin,source.destination,
            source.estimated_delivery,source.weight_kg,source.carrier,source.user_id);
GO
