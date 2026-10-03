"""
GreenBEE - self-contained database bootstrap.

Har baar app start hone par (ya `python init_db.py` se) ye chalta hai aur HAR cheez pehle check karta hai:
    database -> tables -> columns -> indexes -> triggers
Jo nahi hai sirf wahi banata hai; jo pehle se hai usko touch nahi karta. Baar-baar chalana safe hai.
Local MySQL aur Aiven (SSL) dono config.py ke through automatically chalte hain.
"""

import logging

import mysql.connector
from mysql.connector import Error

from config import Config

log = logging.getLogger("greenbee.init_db")

DB = Config.DB_NAME

# --------------------------------------------------------------------------------------
# Final schema (fresh install). Parent tables pehle, children baad mein (foreign keys).
# --------------------------------------------------------------------------------------
TABLES = {
    "companion": """
        CREATE TABLE companion (
            companion_id        INT AUTO_INCREMENT PRIMARY KEY,
            full_name           VARCHAR(100) NOT NULL,
            dob                 DATE NOT NULL,
            gender              ENUM('Male','Female','Other') NOT NULL,
            phone               VARCHAR(15) NOT NULL UNIQUE,
            bio                 TEXT,
            photo               MEDIUMBLOB,
            photo_type          VARCHAR(50),
            languages           VARCHAR(200),
            skills              VARCHAR(200),
            ngo_reference       VARCHAR(100),
            email               VARCHAR(100) NOT NULL UNIQUE,
            google_id           VARCHAR(100) UNIQUE,
            email_verified      BOOLEAN NOT NULL DEFAULT FALSE,
            city                VARCHAR(50) NOT NULL,
            latitude            DECIMAL(10,7),
            longitude           DECIMAL(10,7),
            service_type        VARCHAR(100),
            hourly_rate         DECIMAL(8,2) NOT NULL,
            service_radius_km   INT NOT NULL DEFAULT 15,
            id_proof_type       ENUM('Aadhar','PAN','Passport','VoterID') NOT NULL,
            id_proof_number     VARCHAR(255) NOT NULL,
            background_check    ENUM('Pending','Passed','Failed') DEFAULT 'Pending',
            verified_by         VARCHAR(100),
            verified_date       DATE,
            emergency_name      VARCHAR(100),
            emergency_relation  VARCHAR(50),
            emergency_phone     VARCHAR(15),
            is_available        BOOLEAN NOT NULL DEFAULT FALSE,
            status              ENUM('Active','Inactive','Suspended','Blacklisted','Deactivated') DEFAULT 'Inactive',
            consent_at          DATETIME NULL,
            created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            CONSTRAINT chk_hourly_rate_positive CHECK (hourly_rate > 0),
            CONSTRAINT chk_service_radius_positive CHECK (service_radius_km > 0)
        )""",
    "customer": """
        CREATE TABLE customer (
            customer_id     INT AUTO_INCREMENT PRIMARY KEY,
            full_name       VARCHAR(100) NOT NULL,
            phone           VARCHAR(15) NOT NULL UNIQUE,
            email           VARCHAR(100) NOT NULL UNIQUE,
            google_id       VARCHAR(100) UNIQUE,
            email_verified  BOOLEAN NOT NULL DEFAULT FALSE,
            city            VARCHAR(50),
            latitude        DECIMAL(10,7),
            longitude       DECIMAL(10,7),
            status          ENUM('Active','Suspended','Blacklisted','Deactivated') DEFAULT 'Active',
            consent_at      DATETIME NULL,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
    "booking": """
        CREATE TABLE booking (
            booking_id       INT AUTO_INCREMENT PRIMARY KEY,
            companion_id     INT NOT NULL,
            customer_id      INT NOT NULL,
            booking_date     DATE NOT NULL,
            start_time       TIME NOT NULL,
            end_time         TIME NOT NULL,
            rate_at_booking  DECIMAL(8,2) NOT NULL,
            total_amount     DECIMAL(10,2) NOT NULL,
            status           ENUM('Pending','Confirmed','Completed','Cancelled') DEFAULT 'Pending',
            rating           TINYINT,
            review_comment   TEXT,
            commission_pct   DECIMAL(5,2) NOT NULL DEFAULT 20.00,
            payout_amount    DECIMAL(10,2),
            payout_status    ENUM('Pending','Processed','Failed') DEFAULT 'Pending',
            payout_date      DATE,
            cancelled_by     VARCHAR(20) NULL,
            payment_status   ENUM('Unpaid','Paid') NOT NULL DEFAULT 'Unpaid',
            completed_at     DATETIME NULL,
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (companion_id) REFERENCES companion(companion_id)
                ON DELETE RESTRICT ON UPDATE CASCADE,
            FOREIGN KEY (customer_id) REFERENCES customer(customer_id)
                ON DELETE RESTRICT ON UPDATE CASCADE,
            CONSTRAINT chk_booking_time CHECK (end_time > start_time),
            CONSTRAINT chk_amount_positive CHECK (total_amount > 0),
            CONSTRAINT chk_rating_range CHECK (rating IS NULL OR rating BETWEEN 1 AND 5),
            CONSTRAINT chk_commission_range CHECK (commission_pct BETWEEN 0 AND 100)
        )""",
    "report": """
        CREATE TABLE report (
            report_id     INT AUTO_INCREMENT PRIMARY KEY,
            booking_id    INT,
            companion_id  INT NOT NULL,
            customer_id   INT NOT NULL,
            reported_by   ENUM('Companion','Customer','Admin') NOT NULL,
            issue_type    VARCHAR(100) NOT NULL,
            description   TEXT,
            status        ENUM('Open','Under Review','Resolved','Dismissed') DEFAULT 'Open',
            action_taken  TEXT,
            is_sos        BOOLEAN NOT NULL DEFAULT FALSE,
            latitude      DECIMAL(10,7) NULL,
            longitude     DECIMAL(10,7) NULL,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (booking_id) REFERENCES booking(booking_id)
                ON DELETE SET NULL ON UPDATE CASCADE,
            FOREIGN KEY (companion_id) REFERENCES companion(companion_id)
                ON DELETE CASCADE ON UPDATE CASCADE,
            FOREIGN KEY (customer_id) REFERENCES customer(customer_id)
                ON DELETE CASCADE ON UPDATE CASCADE
        )""",
    "notification": """
        CREATE TABLE notification (
            notification_id  INT AUTO_INCREMENT PRIMARY KEY,
            user_type        ENUM('Customer','Companion') NOT NULL,
            user_id          INT NOT NULL,
            message          VARCHAR(255) NOT NULL,
            link             VARCHAR(100),
            is_read          BOOLEAN NOT NULL DEFAULT FALSE,
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_notification_user (user_type, user_id, is_read)
        )""",
}

# Purane DB (jahan table pehle se bani thi) ke liye: jo column missing ho wo add hoga.
# (table, column, ddl)
COLUMNS = [
    ("companion", "photo", "MEDIUMBLOB AFTER bio"),
    ("companion", "photo_type", "VARCHAR(50) AFTER photo"),
    ("companion", "service_radius_km", "INT NOT NULL DEFAULT 15 AFTER hourly_rate"),
    ("companion", "consent_at", "DATETIME NULL"),
    ("customer", "consent_at", "DATETIME NULL"),
    ("booking", "cancelled_by", "VARCHAR(20) NULL"),
    ("booking", "payment_status", "ENUM('Unpaid','Paid') NOT NULL DEFAULT 'Unpaid'"),
    ("booking", "completed_at", "DATETIME NULL"),
    ("report", "is_sos", "BOOLEAN NOT NULL DEFAULT FALSE"),
    ("report", "latitude", "DECIMAL(10,7) NULL"),
    ("report", "longitude", "DECIMAL(10,7) NULL"),
]

INDEXES = [
    ("companion", "idx_companion_city", "city"),
    ("companion", "idx_companion_status", "status, is_available"),
    ("companion", "idx_companion_location", "latitude, longitude"),
    ("booking", "idx_booking_date", "booking_date"),
    ("booking", "idx_booking_status", "status"),
]

_AGE_CHECK = """
    BEGIN
        IF TIMESTAMPDIFF(YEAR, NEW.dob, CURDATE()) < 18 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Companion must be at least 18 years old';
        END IF;
    END"""

TRIGGERS = {
    "trg_companion_age_insert": f"CREATE TRIGGER trg_companion_age_insert BEFORE INSERT ON companion FOR EACH ROW {_AGE_CHECK}",
    "trg_companion_age_update": f"CREATE TRIGGER trg_companion_age_update BEFORE UPDATE ON companion FOR EACH ROW {_AGE_CHECK}",
}


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------
def _one(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchone()


def _tables(cur):
    cur.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = %s", (DB,))
    return {r[0] for r in cur.fetchall()}


def _columns(cur, table):
    cur.execute("SELECT COLUMN_NAME, COLUMN_TYPE FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s", (DB, table))
    return {r[0]: r[1] for r in cur.fetchall()}


def _index_exists(cur, table, name):
    return _one(cur, "SELECT 1 FROM INFORMATION_SCHEMA.STATISTICS "
                     "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND INDEX_NAME = %s LIMIT 1",
                (DB, table, name)) is not None


def _trigger_exists(cur, name):
    return _one(cur, "SELECT 1 FROM INFORMATION_SCHEMA.TRIGGERS "
                     "WHERE TRIGGER_SCHEMA = %s AND TRIGGER_NAME = %s LIMIT 1", (DB, name)) is not None


# --------------------------------------------------------------------------------------
# Steps (har ek pehle check karta hai, phir create)
# --------------------------------------------------------------------------------------
def ensure_database(server_cur):
    if _one(server_cur, "SELECT 1 FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = %s", (DB,)):
        return
    server_cur.execute(f"CREATE DATABASE `{DB}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    log.info("Database '%s' created", DB)


def ensure_tables(cur):
    existing = _tables(cur)
    for name, ddl in TABLES.items():
        if name not in existing:
            cur.execute(ddl)
            log.info("Table '%s' created", name)


def ensure_columns(cur):
    """Purani table mein naye columns + purane schema ke fixes (idempotent)."""
    cache = {t: _columns(cur, t) for t in TABLES}

    for table, col, ddl in COLUMNS:
        if col not in cache[table]:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
            log.info("Column '%s.%s' added", table, col)

    comp, cust = cache["companion"], cache["customer"]

    if "photo_url" in comp:  # purana URL column, ab photo BLOB hai
        cur.execute("ALTER TABLE companion DROP COLUMN photo_url")
        log.info("Old column 'companion.photo_url' removed")

    if comp.get("id_proof_number", "").lower() != "varchar(255)":  # encrypted ID ke liye lamba
        cur.execute("ALTER TABLE companion MODIFY id_proof_number VARCHAR(255) NOT NULL")
    if "Deactivated" not in comp.get("status", ""):
        cur.execute("ALTER TABLE companion MODIFY status "
                    "ENUM('Active','Inactive','Suspended','Blacklisted','Deactivated') DEFAULT 'Inactive'")
    if "Deactivated" not in cust.get("status", ""):
        cur.execute("ALTER TABLE customer MODIFY status "
                    "ENUM('Active','Suspended','Blacklisted','Deactivated') DEFAULT 'Active'")


def ensure_indexes(cur):
    for table, name, cols in INDEXES:
        if not _index_exists(cur, table, name):
            cur.execute(f"CREATE INDEX {name} ON {table}({cols})")
            log.info("Index '%s' created", name)


def ensure_triggers(cur):
    for name, ddl in TRIGGERS.items():
        if not _trigger_exists(cur, name):
            cur.execute(ddl)
            log.info("Trigger '%s' created", name)


def encrypt_existing_id_proofs(cur):
    """Purane plain-text id_proof_number ek baar encrypt (jo 'enc:' se shuru hain wo skip)."""
    cur.execute("SELECT companion_id, id_proof_number FROM companion "
                "WHERE id_proof_number NOT LIKE 'enc:%' AND id_proof_number <> 'deleted'")
    rows = cur.fetchall()
    if rows:
        import crypto_util
        for cid, plain in rows:
            cur.execute("UPDATE companion SET id_proof_number = %s WHERE companion_id = %s",
                        (crypto_util.encrypt_id(plain), cid))
        log.info("%d purane ID proof numbers encrypted", len(rows))


# --------------------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------------------
def main():
    """Database + sab kuch ready kar do. Fail hone par exception raise (app start rok deta hai)."""
    server_args = {k: v for k, v in Config.DB_CONFIG.items() if k != "database"}
    try:
        server = mysql.connector.connect(**server_args)
    except Error as e:
        raise RuntimeError(
            f"MySQL server se connect nahi ho paaya ({Config.DB_CONFIG['host']}:{Config.DB_CONFIG['port']}): {e}"
        ) from e

    try:
        cur = server.cursor()
        # Kai gunicorn workers ek saath start hon to setup ek hi baar chale (MySQL advisory lock).
        cur.execute("SELECT GET_LOCK('greenbee_init_db', 60)")
        cur.fetchone()
        try:
            ensure_database(cur)
        except Error as e:
            # Managed DB (Aiven) mein CREATE DATABASE allowed nahi hota - wahan DB pehle se hota hai.
            if not _one(cur, "SELECT 1 FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = %s", (DB,)):
                raise RuntimeError(f"Database '{DB}' nahi hai aur ban bhi nahi paaya: {e}") from e
        cur.execute(f"USE `{DB}`")

        ensure_tables(cur)
        ensure_columns(cur)
        ensure_indexes(cur)
        ensure_triggers(cur)
        encrypt_existing_id_proofs(cur)
        server.commit()
        cur.execute("SELECT RELEASE_LOCK('greenbee_init_db')")
        cur.fetchone()
        cur.close()
    finally:
        server.close()
    log.info("Database '%s' ready", DB)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
    print(f"✅ '{DB}' ready")
