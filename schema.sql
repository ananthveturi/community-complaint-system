-- SQLite Schema for Community Complaint System

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

-- Trigger to update updated_at timestamp on complaints
CREATE TRIGGER IF NOT EXISTS update_complaint_timestamp 
AFTER UPDATE ON complaints
BEGIN
    UPDATE complaints SET updated_at = CURRENT_TIMESTAMP WHERE id = new.id;
END;
