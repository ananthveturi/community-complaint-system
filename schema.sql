-- SQLite Schema for Community Complaint System (CiviFix)

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT,
    role TEXT NOT NULL CHECK(role IN ('citizen', 'admin')),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS complaints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    citizen_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    location TEXT NOT NULL,
    latitude REAL,
    longitude REAL,
    image_path TEXT, -- original file upload
    status TEXT NOT NULL DEFAULT 'Pending' CHECK(status IN ('Pending', 'Under Review', 'In Progress', 'Resolved', 'Rejected')),
    department TEXT, -- assigned department
    resolution_image_path TEXT, -- admin resolution proof photo
    ai_category TEXT,
    ai_priority TEXT,
    integrity_status TEXT DEFAULT 'PENDING' CHECK(integrity_status IN ('PENDING', 'ACCEPTED', 'REVIEW_REQUIRED', 'REJECTED', 'FLAGGED_DUPLICATE')),
    risk_score REAL DEFAULT 0.0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(citizen_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS complaint_updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    complaint_id INTEGER NOT NULL,
    author_id INTEGER NOT NULL,
    status_from TEXT CHECK(status_from IN ('Pending', 'Under Review', 'In Progress', 'Resolved', 'Rejected', NULL)),
    status_to TEXT CHECK(status_to IN ('Pending', 'Under Review', 'In Progress', 'Resolved', 'Rejected', NULL)),
    message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(complaint_id) REFERENCES complaints(id) ON DELETE CASCADE,
    FOREIGN KEY(author_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    complaint_id INTEGER UNIQUE NOT NULL,
    rating INTEGER NOT NULL CHECK(rating >= 1 AND rating <= 5),
    comments TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(complaint_id) REFERENCES complaints(id) ON DELETE CASCADE
);

-- Integrity & Fraud Detection Tables
CREATE TABLE IF NOT EXISTS complaint_risk_assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    complaint_id INTEGER NOT NULL,
    risk_score REAL NOT NULL,
    decision TEXT NOT NULL CHECK(decision IN ('ACCEPT', 'REVIEW', 'REJECT')),
    pipeline_version TEXT DEFAULT '1.0.0',
    signals_summary TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(complaint_id) REFERENCES complaints(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS fraud_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    risk_assessment_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    score REAL NOT NULL,
    weight REAL DEFAULT 1.0,
    explanation TEXT NOT NULL,
    metadata TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(risk_assessment_id) REFERENCES complaint_risk_assessments(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS image_fingerprints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    complaint_id INTEGER NOT NULL,
    image_path TEXT NOT NULL,
    sha256 TEXT UNIQUE NOT NULL,
    phash TEXT,
    dhash TEXT,
    ahash TEXT,
    embedding_reference TEXT,
    image_width INTEGER,
    image_height INTEGER,
    file_size_bytes INTEGER,
    mime_type TEXT,
    exif_timestamp DATETIME,
    exif_latitude REAL,
    exif_longitude REAL,
    exif_camera_model TEXT,
    quality_warning TEXT,
    is_manipulated INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(complaint_id) REFERENCES complaints(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS image_similarities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_image_id INTEGER NOT NULL,
    target_image_id INTEGER NOT NULL,
    similarity_score REAL NOT NULL,
    method TEXT NOT NULL,
    is_cross_complaint INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(source_image_id) REFERENCES image_fingerprints(id) ON DELETE CASCADE,
    FOREIGN KEY(target_image_id) REFERENCES image_fingerprints(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS complaint_similarities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    complaint_id INTEGER NOT NULL,
    similar_complaint_id INTEGER NOT NULL,
    similarity_score REAL NOT NULL,
    distance_meters REAL,
    reason TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(complaint_id) REFERENCES complaints(id) ON DELETE CASCADE,
    FOREIGN KEY(similar_complaint_id) REFERENCES complaints(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS spam_detection_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    complaint_id INTEGER NOT NULL,
    spam_score REAL NOT NULL,
    risk_tier TEXT NOT NULL,
    repeated_char_ratio REAL,
    entropy_score REAL,
    contains_promo_url INTEGER DEFAULT 0,
    flagged_reasons TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(complaint_id) REFERENCES complaints(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS integrity_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    complaint_id INTEGER NOT NULL,
    reviewer_id INTEGER,
    action TEXT NOT NULL,
    review_notes TEXT,
    prior_decision TEXT,
    final_decision TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(complaint_id) REFERENCES complaints(id) ON DELETE CASCADE,
    FOREIGN KEY(reviewer_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS user_risk_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE NOT NULL,
    behavioral_risk_score REAL DEFAULT 0.0,
    complaint_count_total INTEGER DEFAULT 0,
    complaint_count_hour INTEGER DEFAULT 0,
    rejected_count INTEGER DEFAULT 0,
    spam_count INTEGER DEFAULT 0,
    duplicate_count INTEGER DEFAULT 0,
    last_submission_at DATETIME,
    captcha_required INTEGER DEFAULT 0,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS rate_limit_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE NOT NULL,
    hits INTEGER DEFAULT 1,
    window_start DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME NOT NULL
);

-- Trigger to update updated_at timestamp on complaints
CREATE TRIGGER IF NOT EXISTS update_complaint_timestamp 
AFTER UPDATE ON complaints
BEGIN
    UPDATE complaints SET updated_at = CURRENT_TIMESTAMP WHERE id = new.id;
END;
