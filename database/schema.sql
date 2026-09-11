-- ============================================
-- RENT-A-FRIEND DB - SIMPLIFIED (4 TABLES)
-- ============================================

CREATE DATABASE IF NOT EXISTS rentafriend_db;
USE rentafriend_db;

-- ============================================
-- 1. COMPANION (profile + verification + emergency
--    contact + service/rate + location - all merged)
-- ============================================
CREATE TABLE companion (
    companion_id        INT AUTO_INCREMENT PRIMARY KEY,

    -- profile
    full_name            VARCHAR(100) NOT NULL,
    dob                  DATE NOT NULL,
    gender               ENUM('Male','Female','Other') NOT NULL,
    phone                VARCHAR(15) NOT NULL UNIQUE,
    bio                  TEXT,
    photo                MEDIUMBLOB,
    photo_type           VARCHAR(50),
    languages            VARCHAR(200),
    skills               VARCHAR(200),        -- self-defense/martial arts
    ngo_reference         VARCHAR(100),

    -- google verified login
    email                VARCHAR(100) NOT NULL UNIQUE,
    google_id            VARCHAR(100) UNIQUE,
    email_verified       BOOLEAN NOT NULL DEFAULT FALSE,

    -- location (for "nearby companions" search)
    city                 VARCHAR(50) NOT NULL,
    latitude             DECIMAL(10,7),
    longitude            DECIMAL(10,7),

    -- service/rate (kept simple - one rate per companion)
    service_type         VARCHAR(100),
    hourly_rate          DECIMAL(8,2) NOT NULL,
    service_radius_km    INT NOT NULL DEFAULT 15,

    -- verification
    id_proof_type        ENUM('Aadhar','PAN','Passport','VoterID') NOT NULL,
    id_proof_number       VARCHAR(50) NOT NULL,
    background_check     ENUM('Pending','Passed','Failed') DEFAULT 'Pending',
    verified_by           VARCHAR(100),
    verified_date         DATE,

    -- emergency contact
    emergency_name        VARCHAR(100),
    emergency_relation    VARCHAR(50),
    emergency_phone       VARCHAR(15),

    -- live status
    is_available          BOOLEAN NOT NULL DEFAULT FALSE,
    status                ENUM('Active','Inactive','Suspended','Blacklisted') DEFAULT 'Inactive',

    created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT chk_hourly_rate_positive CHECK (hourly_rate > 0),
    CONSTRAINT chk_service_radius_positive CHECK (service_radius_km > 0)
);

-- Age validation via trigger (CURDATE() not allowed in CHECK)
DELIMITER $$
CREATE TRIGGER trg_companion_age_insert
BEFORE INSERT ON companion
FOR EACH ROW
BEGIN
    IF TIMESTAMPDIFF(YEAR, NEW.dob, CURDATE()) < 18 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Companion must be at least 18 years old';
    END IF;
END$$

CREATE TRIGGER trg_companion_age_update
BEFORE UPDATE ON companion
FOR EACH ROW
BEGIN
    IF TIMESTAMPDIFF(YEAR, NEW.dob, CURDATE()) < 18 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Companion must be at least 18 years old';
    END IF;
END$$
DELIMITER ;

CREATE INDEX idx_companion_city ON companion(city);
CREATE INDEX idx_companion_status ON companion(status, is_available);
CREATE INDEX idx_companion_location ON companion(latitude, longitude);

-- ============================================
-- 2. CUSTOMER (profile + google verified login + location)
-- ============================================
CREATE TABLE customer (
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
);

-- ============================================
-- 3. BOOKING (booking + review + payout merged - all 1-to-1)
-- ============================================
CREATE TABLE booking (
    booking_id        INT AUTO_INCREMENT PRIMARY KEY,
    companion_id      INT NOT NULL,
    customer_id       INT NOT NULL,

    booking_date      DATE NOT NULL,
    start_time        TIME NOT NULL,
    end_time          TIME NOT NULL,
    rate_at_booking   DECIMAL(8,2) NOT NULL,     -- snapshot of companion's rate
    total_amount      DECIMAL(10,2) NOT NULL,
    status            ENUM('Pending','Confirmed','Completed','Cancelled') DEFAULT 'Pending',

    -- review (filled after completion)
    rating            TINYINT,
    review_comment    TEXT,

    -- payout
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
);

CREATE INDEX idx_booking_date ON booking(booking_date);
CREATE INDEX idx_booking_status ON booking(status);

-- ============================================
-- 4. REPORT (complaints - kept standalone, multiple per booking possible)
-- ============================================
CREATE TABLE report (
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
);
