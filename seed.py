import os
import sqlite3
from werkzeug.security import generate_password_hash
import database

# 1x1 Transparent PNG bytes to programmatically seed valid image files
PNG_BYTES = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc`\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'

def create_mock_images():
    """Create mock image files in the upload folder for demo visual proofs."""
    upload_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
    os.makedirs(upload_dir, exist_ok=True)
    
    images = {
        'mock_pothole_issue.png': PNG_BYTES,
        'mock_pothole_fixed.png': PNG_BYTES,
        'mock_garbage_issue.png': PNG_BYTES,
        'mock_swing_broken.png': PNG_BYTES,
        'mock_swing_fixed.png': PNG_BYTES,
        'mock_streetlight_issue.png': PNG_BYTES
    }
    
    for name, data in images.items():
        path = os.path.join(upload_dir, name)
        if not os.path.exists(path):
            with open(path, 'wb') as f:
                f.write(data)
            print(f"Created mock image: {name}")

def seed_database():
    """Wipe database, initialize schema, and populate with rich test data."""
    print("Resetting database...")
    # Delete database if exists
    if os.path.exists(database.DB_PATH):
        try:
            os.remove(database.DB_PATH)
            print("Removed existing complaints.db")
        except Exception as e:
            print(f"Error removing database: {e}")
            
    database.init_db()
    create_mock_images()
    
    conn = database.get_db()
    cursor = conn.cursor()
    
    # 1. Create Users
    admin_pw = generate_password_hash("admin123")
    citizen_pw = generate_password_hash("password123")
    
    users = [
        ('admin', admin_pw, 'Administrator Staff', 'admin@municipal.gov', '555-0100', 'admin'),
        ('john_doe', citizen_pw, 'John Doe', 'john.doe@gmail.com', '555-0101', 'citizen'),
        ('jane_smith', citizen_pw, 'Jane Smith', 'jane.smith@yahoo.com', '555-0102', 'citizen')
    ]
    
    user_ids = {}
    for username, pw, name, email, phone, role in users:
        cursor.execute(
            '''INSERT INTO users (username, password_hash, full_name, email, phone, role)
               VALUES (?, ?, ?, ?, ?, ?)''',
            (username, pw, name, email, phone, role)
        )
        user_ids[username] = cursor.lastrowid
        print(f"Created User: {username} (Role: {role}, ID: {user_ids[username]})")
        
    # 2. Seed Complaint 1: Resolved Pothole
    cursor.execute(
        '''INSERT INTO complaints (citizen_id, title, category, description, location, image_path, status, department, resolution_image_path, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', '-5 days'), datetime('now', '-2 days'))''',
        (
            user_ids['john_doe'],
            "Large Pothole on Maple Street",
            "Roads & Traffic",
            "There is a massive pothole in the middle of Maple Street near the crossing. It's causing traffic bottlenecks and is a severe hazard to motorcyclists.",
            "Maple Street near Crossing",
            "mock_pothole_issue.png",
            "Resolved",
            "Public Works",
            "mock_pothole_fixed.png"
        )
    )
    complaint_1_id = cursor.lastrowid
    
    # Timeline updates for Complaint 1
    # Use standard sqlite datetime modifiers
    updates_1 = [
        (complaint_1_id, user_ids['john_doe'], None, 'Pending', 'Complaint filed successfully.', "-5 days"),
        (complaint_1_id, user_ids['admin'], 'Pending', 'Under Review', 'Grievance verified. Assigning to repair crew.', "-4 days"),
        (complaint_1_id, user_ids['admin'], None, None, 'Assigned to Department: Public Works.', "-4 days"),
        (complaint_1_id, user_ids['john_doe'], None, None, 'Thanks, please resolve it soon as it gets filled with water during rains.', "-3 days"),
        (complaint_1_id, user_ids['admin'], 'Under Review', 'In Progress', 'Maintenance scheduled for Monday morning.', "-3 days"),
        (complaint_1_id, user_ids['admin'], 'In Progress', 'Resolved', 'Road patched and asphalt resurfaced. Uploaded verification photo.', "-2 days")
    ]
    for cid, uid, s_from, s_to, msg, time_offset in updates_1:
        cursor.execute(
            '''INSERT INTO complaint_updates (complaint_id, author_id, status_from, status_to, message, created_at)
               VALUES (?, ?, ?, ?, ?, datetime('now', ?))''',
            (cid, uid, s_from, s_to, msg, time_offset)
        )
        
    # Feedback for Complaint 1
    cursor.execute(
        '''INSERT INTO feedback (complaint_id, rating, comments, created_at)
           VALUES (?, ?, ?, datetime('now', '-1 days'))''',
        (complaint_1_id, 5, "Excellent and quick response! The pothole is completely patched.")
    )

    # 3. Seed Complaint 2: In Progress Garbage Issue
    cursor.execute(
        '''INSERT INTO complaints (citizen_id, title, category, description, location, image_path, status, department, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now', '-2 days'), datetime('now', '-1 day'))''',
        (
            user_ids['jane_smith'],
            "Overflowing Garbage Bin near City Park",
            "Sanitation & Waste",
            "The public garbage bin outside the main gate of City Park has not been cleared for three days. Trash is spilling onto the sidewalk and attracting stray animals.",
            "City Park Main Gate",
            "mock_garbage_issue.png",
            "In Progress",
            "Sanitation Department"
        )
    )
    complaint_2_id = cursor.lastrowid
    
    updates_2 = [
        (complaint_2_id, user_ids['jane_smith'], None, 'Pending', 'Complaint filed.', "-2 days"),
        (complaint_2_id, user_ids['admin'], 'Pending', 'Under Review', 'Garbage overflow acknowledged.', "-1 day"),
        (complaint_2_id, user_ids['admin'], None, None, 'Assigned to Department: Sanitation Department.', "-1 day"),
        (complaint_2_id, user_ids['admin'], 'Under Review', 'In Progress', 'Sanitation truck dispatched to clear the bin.', "-1 day")
    ]
    for cid, uid, s_from, s_to, msg, time_offset in updates_2:
        cursor.execute(
            '''INSERT INTO complaint_updates (complaint_id, author_id, status_from, status_to, message, created_at)
               VALUES (?, ?, ?, ?, ?, datetime('now', ?))''',
            (cid, uid, s_from, s_to, msg, time_offset)
        )

    # 4. Seed Complaint 3: Pending Streetlight
    cursor.execute(
        '''INSERT INTO complaints (citizen_id, title, category, description, location, image_path, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now', '-6 hours'), datetime('now', '-6 hours'))''',
        (
            user_ids['john_doe'],
            "Broken Streetlight on Elm Street",
            "Electricity & Power",
            "The streetlight outside House #42 on Elm Street has been flickering and is now completely dead. The street is dark and feels unsafe at night.",
            "Elm Street outside House #42",
            "mock_streetlight_issue.png",
            "Pending"
        )
    )
    complaint_3_id = cursor.lastrowid
    cursor.execute(
        '''INSERT INTO complaint_updates (complaint_id, author_id, status_from, status_to, message, created_at)
           VALUES (?, ?, NULL, 'Pending', 'Complaint filed successfully.', datetime('now', '-6 hours'))''',
        (complaint_3_id, user_ids['john_doe'])
    )

    # 5. Seed Complaint 4: Under Review Water Supply
    cursor.execute(
        '''INSERT INTO complaints (citizen_id, title, category, description, location, image_path, status, department, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, NULL, ?, ?, datetime('now', '-1 day'), datetime('now', '-4 hours'))''',
        (
            user_ids['jane_smith'],
            "Low Water Pressure in Block B",
            "Water Supply",
            "Since last Tuesday, all households in Block B are experiencing extremely low water pressure. It is difficult to fill overhead storage tanks.",
            "Block B Residential Colony",
            "Under Review",
            "Water Board"
        )
    )
    complaint_4_id = cursor.lastrowid
    updates_4 = [
        (complaint_4_id, user_ids['jane_smith'], None, 'Pending', 'Complaint filed.', "-1 day"),
        (complaint_4_id, user_ids['admin'], 'Pending', 'Under Review', 'Investigating supply pressure.', "-8 hours"),
        (complaint_4_id, user_ids['admin'], None, None, 'Assigned to Department: Water Board.', "-4 hours")
    ]
    for cid, uid, s_from, s_to, msg, time_offset in updates_4:
        cursor.execute(
            '''INSERT INTO complaint_updates (complaint_id, author_id, status_from, status_to, message, created_at)
               VALUES (?, ?, ?, ?, ?, datetime('now', ?))''',
            (cid, uid, s_from, s_to, msg, time_offset)
        )

    # 6. Seed Complaint 5: Resolved swings in parks
    cursor.execute(
        '''INSERT INTO complaints (citizen_id, title, category, description, location, image_path, status, department, resolution_image_path, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', '-10 days'), datetime('now', '-7 days'))''',
        (
            user_ids['john_doe'],
            "Broken Swing in Children's Play Area",
            "Parks & Recreation",
            "One of the swings in the children's park is broken and hanging dangerously. Please fix it before a child gets hurt.",
            "Central Park Children's Play Area",
            "mock_swing_broken.png",
            "Resolved",
            "Parks Department",
            "mock_swing_fixed.png"
        )
    )
    complaint_5_id = cursor.lastrowid
    
    updates_5 = [
        (complaint_5_id, user_ids['john_doe'], None, 'Pending', 'Swings reported broken.', "-10 days"),
        (complaint_5_id, user_ids['admin'], 'Pending', 'Under Review', 'Verified swing chain is rusted.', "-9 days"),
        (complaint_5_id, user_ids['admin'], None, None, 'Assigned to Department: Parks Department.', "-9 days"),
        (complaint_5_id, user_ids['admin'], 'Under Review', 'In Progress', 'Parks maintenance dispatched to replace swing.', "-8 days"),
        (complaint_5_id, user_ids['admin'], 'In Progress', 'Resolved', 'Swing chains replaced. Swing is now safe and functional. Uploaded verification photo.', "-7 days")
    ]
    for cid, uid, s_from, s_to, msg, time_offset in updates_5:
        cursor.execute(
            '''INSERT INTO complaint_updates (complaint_id, author_id, status_from, status_to, message, created_at)
               VALUES (?, ?, ?, ?, ?, datetime('now', ?))''',
            (cid, uid, s_from, s_to, msg, time_offset)
        )
        
    cursor.execute(
        '''INSERT INTO feedback (complaint_id, rating, comments, created_at)
           VALUES (?, ?, ?, datetime('now', '-6 days'))''',
        (complaint_5_id, 4, "Thank you for fixing it quickly!")
    )

    conn.commit()
    conn.close()
    print("Database seeding completed successfully!")

if __name__ == '__main__':
    seed_database()
