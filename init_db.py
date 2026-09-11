"""
rentafriend_db - INDEPENDENT DATABASE SETUP SCRIPT
Local MySQL aur Aiven.io dono ke saath kaam karta hai - config.py
mein DB_SSL_CA blank hai to local, path diya hai to SSL (Aiven) use hoga.

Safe hai baar-baar chalane ke liye - already-exists errors nahi aayenge.

Run:
    pip install -r requirements.txt
    cp .env.example .env      (apne values daalo)
    python init_db.py
"""

import sys
import mysql.connector
from mysql.connector import Error
from config import Config


TABLE_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS companion (
        companion_id        INT AUTO_INCREMENT PRIMARY KEY,
        full_name            VARCHAR(100) NOT NULL,
        dob                  DATE NOT NULL,
        gender               ENUM('Male','Female','Other') NOT NULL,
        phone                VARCHAR(15) NOT NULL UNIQUE,
        bio                  TEXT,
        photo                MEDIUMBLOB,
        photo_type           VARCHAR(50),
        languages            VARCHAR(200),
        skills               VARCHAR(200),
        ngo_reference         VARCHAR(100),
        email                VARCHAR(100) NOT NULL UNIQUE,
        google_id            VARCHAR(100) UNIQUE,
        email_verified       BOOLEAN NOT NULL DEFAULT FALSE,
        city                 VARCHAR(50) NOT NULL,
        latitude             DECIMAL(10,7),
        longitude            DECIMAL(10,7),
        service_type         VARCHAR(100),
        hourly_rate          DECIMAL(8,2) NOT NULL,
        service_radius_km    INT NOT NULL DEFAULT 15,
        id_proof_type        ENUM('Aadhar','PAN','Passport','VoterID') NOT NULL,
        id_proof_number       VARCHAR(50) NOT NULL,
        background_check     ENUM('Pending','Passed','Failed') DEFAULT 'Pending',
        verified_by           VARCHAR(100),
        verified_date         DATE,
        emergency_name        VARCHAR(100),
        emergency_relation    VARCHAR(50),
        emergency_phone       VARCHAR(15),
        is_available          BOOLEAN NOT NULL DEFAULT FALSE,
        status                ENUM('Active','Inactive','Suspended','Blacklisted') DEFAULT 'Inactive',
        created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        CONSTRAINT chk_hourly_rate_positive CHECK (hourly_rate > 0),
        CONSTRAINT chk_service_radius_positive CHECK (service_radius_km > 0)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS customer (
        customer_id       INT AUTO_INCREMENT PRIMARY KEY,
        full_name         VARCHAR(100) NOT NULL,
        phone             VARCHAR(15) NOT NULL UNIQUE,
        email             VARCHAR(100) NOT NULL UNIQUE,
        google_id         VARCHAR(100) UNIQUE,
        email_verified    BOOLEAN NOT NULL DEFAULT FALSE,
        city              VARCHAR(50),
        latitude          DECIMAL(10,7),
        longitude         DECIMAL(10,7),
        status            ENUM('Active','Suspended','Blacklisted') DEFAULT 'Active',
        created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS booking (
        booking_id        INT AUTO_INCREMENT PRIMARY KEY,
        companion_id      INT NOT NULL,
        customer_id       INT NOT NULL,
        booking_date      DATE NOT NULL,
        start_time        TIME NOT NULL,
        end_time          TIME NOT NULL,
        rate_at_booking   DECIMAL(8,2) NOT NULL,
        total_amount      DECIMAL(10,2) NOT NULL,
        status            ENUM('Pending','Confirmed','Completed','Cancelled') DEFAULT 'Pending',
        rating            TINYINT,
        review_comment    TEXT,
        commission_pct    DECIMAL(5,2) NOT NULL DEFAULT 20.00,
        payout_amount     DECIMAL(10,2),
        payout_status     ENUM('Pending','Processed','Failed') DEFAULT 'Pending',
        payout_date       DATE,
        created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (companion_id) REFERENCES companion(companion_id)
            ON DELETE RESTRICT ON UPDATE CASCADE,
        FOREIGN KEY (customer_id) REFERENCES customer(customer_id)
            ON DELETE RESTRICT ON UPDATE CASCADE,
        CONSTRAINT chk_booking_time CHECK (end_time > start_time),
        CONSTRAINT chk_amount_positive CHECK (total_amount > 0),
        CONSTRAINT chk_rating_range CHECK (rating IS NULL OR rating BETWEEN 1 AND 5),
        CONSTRAINT chk_commission_range CHECK (commission_pct BETWEEN 0 AND 100)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS report (
        report_id         INT AUTO_INCREMENT PRIMARY KEY,
        booking_id        INT,
        companion_id      INT NOT NULL,
        customer_id       INT NOT NULL,
        reported_by       ENUM('Companion','Customer','Admin') NOT NULL,
        issue_type        VARCHAR(100) NOT NULL,
        description       TEXT,
        status            ENUM('Open','Under Review','Resolved','Dismissed') DEFAULT 'Open',
        action_taken      TEXT,
        created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (booking_id) REFERENCES booking(booking_id)
            ON DELETE SET NULL ON UPDATE CASCADE,
        FOREIGN KEY (companion_id) REFERENCES companion(companion_id)
            ON DELETE CASCADE ON UPDATE CASCADE,
        FOREIGN KEY (customer_id) REFERENCES customer(customer_id)
            ON DELETE CASCADE ON UPDATE CASCADE
    )
    """
]

INDEX_STATEMENTS = [
    ("idx_companion_city", "CREATE INDEX idx_companion_city ON companion(city)"),
    ("idx_companion_status", "CREATE INDEX idx_companion_status ON companion(status, is_available)"),
    ("idx_companion_location", "CREATE INDEX idx_companion_location ON companion(latitude, longitude)"),
    ("idx_booking_date", "CREATE INDEX idx_booking_date ON booking(booking_date)"),
    ("idx_booking_status", "CREATE INDEX idx_booking_status ON booking(status)"),
]

TRIGGER_STATEMENTS = [
    ("trg_companion_age_insert", """
        CREATE TRIGGER trg_companion_age_insert
        BEFORE INSERT ON companion
        FOR EACH ROW
        BEGIN
            IF TIMESTAMPDIFF(YEAR, NEW.dob, CURDATE()) < 18 THEN
                SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Companion must be at least 18 years old';
            END IF;
        END
    """),
    ("trg_companion_age_update", """
        CREATE TRIGGER trg_companion_age_update
        BEFORE UPDATE ON companion
        FOR EACH ROW
        BEGIN
            IF TIMESTAMPDIFF(YEAR, NEW.dob, CURDATE()) < 18 THEN
                SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Companion must be at least 18 years old';
            END IF;
        END
    """),
]


def step(label, fn):
    try:
        fn()
        print(f"✅ {label}")
    except Error as e:
        print(f"❌ {label} failed: {e}")
        sys.exit(1)


def connect_without_database():
    """Database select kiye bina connect karta hai (taaki 'unknown database' error na aaye).
       Local aur Aiven (SSL) dono config automatically handle ho jaate hain."""
    conn_args = {k: v for k, v in Config.DB_CONFIG.items() if k != "database"}
    return mysql.connector.connect(**conn_args)


def migrate_photo_column(cursor):
    """
    Purani setup mein 'photo_url VARCHAR' tha, ab 'photo MEDIUMBLOB' + 'photo_type' hai.
    Agar table pehle se ban chuki hai (CREATE TABLE IF NOT EXISTS isko touch nahi karta),
    to yahan safely migrate karte hain - naya column add karo, purana drop karo.
    Fresh install par ye sab silently skip ho jaata hai (columns already sahi hain).
    """
    cursor.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'companion'
    """, (Config.DB_NAME,))
    existing_columns = {row[0] for row in cursor.fetchall()}

    if "photo" not in existing_columns:
        cursor.execute("ALTER TABLE companion ADD COLUMN photo MEDIUMBLOB AFTER bio")
        print("✅ Column 'photo' added to companion")

    if "photo_type" not in existing_columns:
        cursor.execute("ALTER TABLE companion ADD COLUMN photo_type VARCHAR(50) AFTER photo")
        print("✅ Column 'photo_type' added to companion")

    if "photo_url" in existing_columns:
        cursor.execute("ALTER TABLE companion DROP COLUMN photo_url")
        print("ℹ️  Old column 'photo_url' removed (photos ab file upload se aate hain)")

    if "service_radius_km" not in existing_columns:
        cursor.execute(
            "ALTER TABLE companion ADD COLUMN service_radius_km INT NOT NULL DEFAULT 15 AFTER hourly_rate"
        )
        print("✅ Column 'service_radius_km' added to companion (default 15 km)")


def main():
    mode = "Aiven / SSL" if "ssl_ca" in Config.DB_CONFIG else "Local MySQL"
    print(f"🔧 Mode: {mode}  |  Host: {Config.DB_CONFIG['host']}:{Config.DB_CONFIG['port']}\n")

    try:
        conn = connect_without_database()
    except Error as e:
        print(f"❌ MySQL server se connect nahi ho paaya: {e}")
        print("   Check karo: host/port/user/password .env mein sahi hai? Aiven ke liye DB_SSL_CA set hai?")
        sys.exit(1)

    cursor = conn.cursor()

    step(f"Database '{Config.DB_NAME}' ready",
         lambda: cursor.execute(f"CREATE DATABASE IF NOT EXISTS {Config.DB_NAME}"))

    cursor.execute(f"USE {Config.DB_NAME}")

    for stmt in TABLE_STATEMENTS:
        table_name = stmt.split("EXISTS")[1].split("(")[0].strip()
        step(f"Table '{table_name}' ready", lambda s=stmt: cursor.execute(s))

    try:
        migrate_photo_column(cursor)
    except Error as e:
        print(f"❌ Photo column migration failed: {e}")
        sys.exit(1)

    for name, stmt in INDEX_STATEMENTS:
        try:
            cursor.execute(stmt)
            print(f"✅ Index '{name}' created")
        except Error as e:
            if e.errno == 1061:  # duplicate key name = already exists
                print(f"ℹ️  Index '{name}' already exists, skipped")
            else:
                print(f"❌ Index '{name}' failed: {e}")

    for name, stmt in TRIGGER_STATEMENTS:
        try:
            cursor.execute(f"DROP TRIGGER IF EXISTS {name}")
            cursor.execute(stmt)
            print(f"✅ Trigger '{name}' ready")
        except Error as e:
            print(f"❌ Trigger '{name}' failed: {e}")

    conn.commit()
    cursor.close()
    conn.close()
    print(f"\n🎉 Setup complete — '{Config.DB_NAME}' is ready to use ({mode}).")


if __name__ == "__main__":
    main()
