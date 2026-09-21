import pytest
import sqlite3
import os
import tempfile
import database

@pytest.fixture
def test_db():
    db_fd, db_path = tempfile.mkstemp()
    old_path = database.DB_PATH
    database.DB_PATH = db_path
    database.init_db()
    database.ensure_schema()
    yield db_path
    database.DB_PATH = old_path
    os.close(db_fd)
    if os.path.exists(db_path):
        os.unlink(db_path)

def test_user_creation_and_retrieval(test_db):
    user_id = database.create_user("testuser", "hash123", "Test User", "test@example.com", "1234567890", role="citizen")
    assert user_id is not None

    user = database.get_user_by_username("testuser")
    assert user is not None
    assert user['full_name'] == "Test User"
    assert user['role'] == "citizen"

    # Duplicate username should fail
    dup_id = database.create_user("testuser", "hash123", "Test User 2", "test2@example.com", "0000000000")
    assert dup_id is None

def test_complaint_workflow(test_db):
    user_id = database.create_user("citizen1", "hash123", "Citizen One", "c1@example.com", "111")
    admin_id = database.create_user("admin1", "hash123", "Admin One", "a1@example.com", "222", role="admin")

    # Create complaint
    complaint_id = database.create_complaint(
        citizen_id=user_id,
        title="Water Leakage in Block A",
        category="Water Supply",
        description="Major water leak near building entrance",
        location="Block A Gate 1"
    )
    assert complaint_id is not None

    complaint = database.get_complaint_by_id(complaint_id)
    assert complaint['status'] == 'Pending'

    # Assign department
    assigned = database.assign_complaint_department(complaint_id, admin_id, "Water Works Dept")
    assert assigned is True

    # Update status to Resolved
    updated = database.update_complaint_status(
        complaint_id=complaint_id,
        author_id=admin_id,
        status_to="Resolved",
        message="Pipe repaired by ground engineers",
        resolution_image_path="test_proof.jpg"
    )
    assert updated is True

    complaint_after = database.get_complaint_by_id(complaint_id)
    assert complaint_after['status'] == 'Resolved'

    # Submit Feedback
    fb_success = database.submit_feedback(complaint_id, rating=5, comments="Great work!")
    assert fb_success is True

    fb = database.get_complaint_feedback(complaint_id)
    assert fb['rating'] == 5
