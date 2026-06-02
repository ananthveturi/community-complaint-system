import sqlite3
import os
from datetime import datetime

DB_PATH = os.environ.get('DATABASE_PATH', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'complaints.db'))

def get_db():
    """Establish and return a database connection with dict-like row formatting."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")  # Enable foreign keys
    return conn

def init_db():
    """Initialize the database schema using schema.sql."""
    schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schema.sql')
    with open(schema_path, 'r') as f:
        schema = f.read()
        
    # Ensure the parent directory of the database file exists
    db_dir = os.path.dirname(os.path.abspath(DB_PATH))
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
        
    conn = get_db()
    try:
        conn.executescript(schema)
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

# --- User Management ---

def create_user(username, password_hash, full_name, email, phone, role='citizen'):
    """Insert a new user into the database."""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            '''INSERT INTO users (username, password_hash, full_name, email, phone, role)
               VALUES (?, ?, ?, ?, ?, ?)''',
            (username, password_hash, full_name, email, phone, role)
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def get_user_by_username(username):
    """Retrieve user details by their unique username."""
    conn = get_db()
    try:
        row = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def get_user_by_id(user_id):
    """Retrieve user details by ID."""
    conn = get_db()
    try:
        row = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def get_all_users():
    """Retrieve list of all registered users (citizens and admins)."""
    conn = get_db()
    try:
        rows = conn.execute(
            'SELECT id, username, full_name, email, phone, role, created_at FROM users ORDER BY role ASC, created_at DESC'
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# --- Complaint Management ---

def create_complaint(citizen_id, title, category, description, location, image_path=None):
    """File a new complaint and record the initial 'Pending' status update."""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            '''INSERT INTO complaints (citizen_id, title, category, description, location, image_path, status)
               VALUES (?, ?, ?, ?, ?, ?, 'Pending')''',
            (citizen_id, title, category, description, location, image_path)
        )
        complaint_id = cursor.lastrowid
        
        # Log initial history update
        cursor.execute(
            '''INSERT INTO complaint_updates (complaint_id, author_id, status_from, status_to, message)
               VALUES (?, ?, NULL, 'Pending', 'Complaint filed successfully.')''',
            (complaint_id, citizen_id)
        )
        conn.commit()
        return complaint_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def get_complaint_by_id(complaint_id):
    """Retrieve details for a specific complaint, including citizen details."""
    conn = get_db()
    try:
        row = conn.execute(
            '''SELECT c.*, u.full_name AS citizen_name, u.email AS citizen_email, u.phone AS citizen_phone
               FROM complaints c
               JOIN users u ON c.citizen_id = u.id
               WHERE c.id = ?''', 
            (complaint_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def get_citizen_complaints(citizen_id):
    """Retrieve list of complaints filed by a specific citizen."""
    conn = get_db()
    try:
        rows = conn.execute(
            'SELECT * FROM complaints WHERE citizen_id = ? ORDER BY created_at DESC', 
            (citizen_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def get_all_complaints(status=None, category=None, department=None, search=None):
    """Retrieve all complaints with filters for admins."""
    conn = get_db()
    query = '''SELECT c.*, u.full_name AS citizen_name 
               FROM complaints c
               JOIN users u ON c.citizen_id = u.id 
               WHERE 1=1'''
    params = []
    
    if status:
        query += " AND c.status = ?"
        params.append(status)
    if category:
        query += " AND c.category = ?"
        params.append(category)
    if department:
        query += " AND c.department = ?"
        params.append(department)
    if search:
        query += " AND (c.title LIKE ? OR c.description LIKE ? OR c.location LIKE ? OR u.full_name LIKE ?)"
        search_param = f"%{search}%"
        params.extend([search_param, search_param, search_param, search_param])
        
    query += " ORDER BY c.created_at DESC"
    
    try:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# --- Complaint Status & Assignment updates ---

def update_complaint_status(complaint_id, author_id, status_to, message=None, resolution_image_path=None):
    """Update complaint status and record in history log."""
    conn = get_db()
    try:
        cursor = conn.cursor()
        
        # Get current status
        complaint = cursor.execute('SELECT status FROM complaints WHERE id = ?', (complaint_id,)).fetchone()
        if not complaint:
            return False
        status_from = complaint['status']
        
        # Update main complaints record
        if status_to == 'Resolved' and resolution_image_path:
            cursor.execute(
                '''UPDATE complaints 
                   SET status = ?, resolution_image_path = ?, updated_at = CURRENT_TIMESTAMP 
                   WHERE id = ?''',
                (status_to, resolution_image_path, complaint_id)
            )
        else:
            cursor.execute(
                'UPDATE complaints SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                (status_to, complaint_id)
            )
            
        # Log in complaint_updates
        cursor.execute(
            '''INSERT INTO complaint_updates (complaint_id, author_id, status_from, status_to, message)
               VALUES (?, ?, ?, ?, ?)''',
            (complaint_id, author_id, status_from, status_to, message)
        )
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def assign_complaint_department(complaint_id, author_id, department, message=None):
    """Assign/reassign a complaint to a specific department."""
    conn = get_db()
    try:
        cursor = conn.cursor()
        
        # Fetch current department if any
        row = cursor.execute('SELECT department FROM complaints WHERE id = ?', (complaint_id,)).fetchone()
        if not row:
            return False
        dept_from = row['department'] or 'None'
        
        # Update department
        cursor.execute(
            'UPDATE complaints SET department = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
            (department, complaint_id)
        )
        
        # Log assignment update
        msg = f"Assigned to Department: {department}."
        if message:
            msg += f" Note: {message}"
        cursor.execute(
            '''INSERT INTO complaint_updates (complaint_id, author_id, status_from, status_to, message)
               VALUES (?, ?, NULL, NULL, ?)''',
            (complaint_id, author_id, msg)
        )
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def add_complaint_comment(complaint_id, author_id, message):
    """Add a simple discussion message/comment to the complaint thread."""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            '''INSERT INTO complaint_updates (complaint_id, author_id, status_from, status_to, message)
               VALUES (?, ?, NULL, NULL, ?)''',
            (complaint_id, author_id, message)
        )
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def get_complaint_updates(complaint_id):
    """Retrieve full history log (comments + status updates) of a complaint."""
    conn = get_db()
    try:
        rows = conn.execute(
            '''SELECT cu.*, u.full_name AS author_name, u.role AS author_role
               FROM complaint_updates cu
               JOIN users u ON cu.author_id = u.id
               WHERE cu.complaint_id = ?
               ORDER BY cu.created_at ASC''',
            (complaint_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# --- Citizen Feedback ---

def submit_feedback(complaint_id, rating, comments):
    """Submit feedback rating and text for a resolved complaint."""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            '''INSERT INTO feedback (complaint_id, rating, comments)
               VALUES (?, ?, ?)''',
            (complaint_id, rating, comments)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False  # Feedback already exists
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def get_complaint_feedback(complaint_id):
    """Fetch user feedback for a complaint, if it exists."""
    conn = get_db()
    try:
        row = conn.execute('SELECT * FROM feedback WHERE complaint_id = ?', (complaint_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# --- Admin Dashboard Stats ---

def get_dashboard_stats():
    """Retrieve key metrics and summary counts for admin dashboard."""
    conn = get_db()
    stats = {}
    try:
        # Total counts by status
        status_rows = conn.execute(
            'SELECT status, COUNT(*) as count FROM complaints GROUP BY status'
        ).fetchall()
        
        stats['status_counts'] = {
            'Pending': 0, 'Under Review': 0, 'In Progress': 0, 'Resolved': 0, 'Rejected': 0
        }
        total = 0
        for r in status_rows:
            stats['status_counts'][r['status']] = r['count']
            total += r['count']
        stats['total_complaints'] = total
        
        # Counts by category
        cat_rows = conn.execute(
            'SELECT category, COUNT(*) as count FROM complaints GROUP BY category'
        ).fetchall()
        stats['category_counts'] = {r['category']: r['count'] for r in cat_rows}
        
        # Counts by department
        dept_rows = conn.execute(
            '''SELECT COALESCE(department, 'Unassigned') as dept, COUNT(*) as count 
               FROM complaints GROUP BY dept'''
        ).fetchall()
        stats['department_counts'] = {r['dept']: r['count'] for r in dept_rows}
        
        # Average resolution time (in days)
        # Calculates difference using julian days for complaints with status 'Resolved'
        avg_res_row = conn.execute(
            '''SELECT AVG(julianday(updated_at) - julianday(created_at)) as avg_days
               FROM complaints 
               WHERE status = 'Resolved' AND updated_at >= created_at'''
        ).fetchone()
        
        avg_days = avg_res_row['avg_days']
        if avg_days is not None:
            # Round to 1 decimal place. Show hours if less than a day
            if avg_days < 1:
                stats['avg_resolution_time'] = f"{round(avg_days * 24, 1)} hours"
            else:
                stats['avg_resolution_time'] = f"{round(avg_days, 1)} days"
        else:
            stats['avg_resolution_time'] = "N/A"
            
        # Average feedback rating
        avg_rating_row = conn.execute('SELECT AVG(rating) as avg_rate FROM feedback').fetchone()
        avg_rate = avg_rating_row['avg_rate']
        stats['avg_feedback_rating'] = round(avg_rate, 1) if avg_rate is not None else "No ratings yet"
        
        return stats
    finally:
        conn.close()
