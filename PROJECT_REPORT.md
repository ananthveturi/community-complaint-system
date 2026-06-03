# Community Complaint System – Project Report

## 1. Overview
The **Community Complaint System** is a Flask‑based web application that enables citizens to file grievances, track their status, and provide feedback. Administrators can manage, assign, and resolve complaints with proof of resolution.

## 2. Architecture
- **Framework**: Flask (Python 3)
- **Database**: SQLite (file‑based) accessed via `sqlite3` with a thin data‑access layer in `database.py`.
- **Templating**: Jinja2 HTML templates located in `templates/`.
- **Static Assets**: CSS/JS and uploaded images stored under `static/` (uploads in `static/uploads`).
- **Authentication**: Session‑based login using Flask `session` and password hashing via `werkzeug.security`.
- **Roles**: `citizen` (regular users) and `admin` (staff). Role‑based view protection via decorators `login_required` and `role_required`.
- **Configuration**: Environment variables for `SECRET_KEY`, `UPLOAD_FOLDER`, and `DATABASE_PATH`.

## 3. Database Schema (`schema.sql`)
| Table | Primary Key | Important Columns | Description |
|-------|------------|------------------|-------------|
| `users` | `id` | `username`, `password_hash`, `full_name`, `email`, `phone`, `role` | Stores citizen and admin credentials. |
| `complaints` | `id` | `citizen_id`, `title`, `category`, `description`, `location`, `image_path`, `status`, `department`, `resolution_image_path` | Core grievance records. |
| `complaint_updates` | `id` | `complaint_id`, `author_id`, `status_from`, `status_to`, `message` | History log for status changes and comments. |
| `feedback` | `id` | `complaint_id`, `rating`, `comments` | Post‑resolution feedback from citizens. |

A trigger (`update_complaint_timestamp`) automatically refreshes `updated_at` on any complaint update.

## 4. Core Code Modules
- **`app.py`** – Flask application, route declarations, file upload handling, and session management.
- **`database.py`** – Helper functions for CRUD operations on users, complaints, updates, and analytics.
- **`seed.py`** – Populates an initial admin user and sample complaints when the DB is empty.
- **`requirements.txt`** – Lists Python dependencies (Flask, Werkzeug, etc.).

## 5. Routes & Functionality
| Endpoint | Methods | Access | Purpose |
|----------|---------|--------|---------|
| `/` | GET | Public | Landing page. |
| `/register` | GET/POST | Public | Citizen sign‑up. |
| `/login` | GET/POST | Public | Authentication. |
| `/logout` | GET | Authenticated | Session clear. |
| `/dashboard` | GET | Citizen | List citizen’s own complaints. |
| `/file-complaint` | GET/POST | Citizen | Submit a new grievance (optional image). |
| `/complaint/<id>` | GET | Authenticated | View complaint details; citizens see only their own. |
| `/complaint/<id>/comment` | POST | Authenticated | Add a comment to the thread. |
| `/admin/dashboard` | GET | Admin | Overview with filters, stats, and user list. |
| `/complaint/<id>/action` | POST | Admin | Change status, assign department, upload resolution proof. |
| `/complaint/<id>/feedback` | POST | Citizen | Submit rating after resolution. |
| `/api/admin/stats` | GET | Admin | JSON endpoint for analytics charts. |
| `/static/uploads/<filename>` | GET | Public | Serve uploaded images. |

All routes use `login_required` and `role_required` decorators to enforce security.

## 6. Security & Validation
- **Password storage** – `werkzeug.security.generate_password_hash` and `check_password_hash` (bcrypt). No plaintext passwords.
- **Session protection** – Flask secret key (`SECRET_KEY`) must be strong in production.
- **Role‑based access** – Citizens cannot view or modify other users’ complaints; admins have full access.
- **File upload validation** – Only `png`, `jpg`, `jpeg`, `gif` allowed; filenames sanitized with `secure_filename` and prefixed with a UUID.
- **SQL injection mitigation** – All DB queries use parameterised statements (`?`).
- **Foreign‑key enforcement** – `PRAGMA foreign_keys = ON` in SQLite connections.
- **Error handling** – Generic 404/500 pages; flash messages for user feedback.
- **CSRF** – Not currently implemented; consider adding `Flask‑WTF` CSRF protection for production.

## 7. File Upload Handling
- Uploaded files are saved to `app.config['UPLOAD_FOLDER']` (default `<project>/static/uploads`).
- Size limited to 5 MB via `MAX_CONTENT_LENGTH`.
- Served through a dedicated Flask route to avoid exposing the entire static directory.

## 8. Deployment & Running
```bash
# Set environment variables (example)
export SECRET_KEY="super‑secret-key"
export FLASK_APP=app.py
export FLASK_DEBUG=1   # optional for development
python -m flask run   # runs on http://0.0.0.0:5000
```
- Ensure the process has write permission to the directory containing `complaints.db` and the upload folder.
- For production, use a WSGI server (Gunicorn, uWSGI) and a reverse proxy (NGINX) with TLS.
- If deploying to platforms like Heroku, the provided `Procfile` (`web: python app.py`) will start the app.

## 9. Analytics (Admin Dashboard)
`database.get_dashboard_stats()` aggregates:
- Complaint counts by status, category, and department.
- Average resolution time (days or hours).
- Average feedback rating.
These metrics populate the admin dashboard UI and a JSON API (`/api/admin/stats`).

## 10. Extensibility Ideas
- **OAuth / SSO** – Integrate Flask‑Login with Google or GitHub for authentication.
- **REST API** – Expose CRUD endpoints for mobile clients (e.g., Flask‑RESTful).
- **Email notifications** – Trigger emails on status changes or when a complaint is assigned.
- **Internationalisation** – Add Flask‑Babel for multi‑language support.
- **Database migration** – Replace SQLite with PostgreSQL/MySQL for scaling; adjust `database.py` accordingly.
- **Testing** – Write unit tests with `pytest` and integration tests for routes.

---
*Generated on 2026‑06‑03. The report is saved as `PROJECT_REPORT.md` in the repository root.*
