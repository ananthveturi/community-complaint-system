import os
import pytest
from datetime import datetime, timedelta
import database
from integrity.otp_service import (
    generate_numeric_otp,
    send_dual_otp,
    verify_target_otp,
    verify_dual_otp
)
from integrity.email_service import get_sent_emails, clear_sent_emails
from integrity.sms_service import get_sent_sms, clear_sent_sms

@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    """Use an isolated test database for OTP tests."""
    db_file = str(tmp_path / "test_otp.db")
    monkeypatch.setattr(database, 'DB_PATH', db_file)
    database.init_db()
    database.ensure_schema()
    clear_sent_emails()
    clear_sent_sms()
    yield

def test_generate_numeric_otp():
    code = generate_numeric_otp(6)
    assert len(code) == 6
    assert code.isdigit()

def test_send_dual_otp_creates_db_records_and_dispatches():
    email = "citizen.test@gmail.com"
    phone = "+919876543210"
    
    res = send_dual_otp(
        email=email,
        phone=phone,
        user_name="Aarav Sharma"
    )
    
    assert res['success'] is True
    assert res['email'] == email
    assert res['phone'] == phone
    assert res['dev_email_otp'] is not None
    assert res['dev_phone_otp'] is not None
    
    # Check that database has active records
    active_email_otp = database.get_active_otp(email, purpose='complaint_submission', target_type='email')
    assert active_email_otp is not None
    assert active_email_otp['otp_code'] == res['dev_email_otp']
    
    active_phone_otp = database.get_active_otp(phone, purpose='complaint_submission', target_type='phone')
    assert active_phone_otp is not None
    assert active_phone_otp['otp_code'] == res['dev_phone_otp']
    
    # Check that dispatch log captured the dispatches
    sent_emails = get_sent_emails()
    assert any(e.get('type') == 'OTP' and e.get('to') == email for e in sent_emails)
    
    sent_sms = get_sent_sms()
    assert any(s.get('to') == phone for s in sent_sms)

def test_verify_target_otp_success_and_consumption():
    email = "verification.check@gmail.com"
    res = send_dual_otp(email=email, phone="1234567890")
    email_code = res['dev_email_otp']
    
    # Valid code check
    verify_res = verify_target_otp(email, email_code, target_type='email')
    assert verify_res['success'] is True
    
    # Verify it was consumed and cannot be reused
    second_attempt = verify_target_otp(email, email_code, target_type='email')
    assert second_attempt['success'] is False
    assert 'expired' in second_attempt['error'].lower() or 'no active' in second_attempt['error'].lower()

def test_verify_target_otp_invalid_code_decrements_attempts():
    phone = "9876543211"
    send_dual_otp(email="user@gmail.com", phone=phone)
    
    # Wrong code
    res = verify_target_otp(phone, "000000", target_type='phone')
    assert res['success'] is False
    assert 'incorrect' in res['error'].lower()

def test_verify_dual_otp_marks_user_verified():
    user_id = database.create_user(
        username="dual_verified_user",
        password_hash="testhash",
        full_name="Priya Patel",
        email="priya.patel@gmail.com",
        phone="9988776655",
        role="citizen"
    )
    
    send_res = send_dual_otp(user_id=user_id)
    email_otp = send_res['dev_email_otp']
    phone_otp = send_res['dev_phone_otp']
    
    # Verify with correct codes
    dual_res = verify_dual_otp(
        email="priya.patel@gmail.com",
        email_otp=email_otp,
        phone="9988776655",
        phone_otp=phone_otp,
        user_id=user_id
    )
    assert dual_res['success'] is True
    
    # Check that user in DB is marked verified
    user = database.get_user_by_id(user_id)
    assert user['is_verified'] == 1
    assert user['is_email_verified'] == 1
    assert user['is_phone_verified'] == 1


def test_flask_otp_api_and_complaint_submission_flow(monkeypatch):
    import app as flask_app
    from integrity.email_service import get_sent_emails, clear_sent_emails

    clear_sent_emails()
    # Set testing flag to False to strictly enforce the live OTP gate
    orig_testing = flask_app.app.config.get('TESTING', False)
    flask_app.app.config['TESTING'] = False

    try:
        with flask_app.app.test_client() as client:
            # 1. Register user
            client.post('/register', data={
                'username': 'e2e_otp_user',
                'full_name': 'E2E Tester',
                'email': 'e2e.tester@gmail.com',
                'phone': '9123456780',
                'password': 'password123'
            })
            client.post('/login', data={'username': 'e2e_otp_user', 'password': 'password123'})

            # 2. Attempt filing complaint without OTP -> Should be blocked and prompt verification
            rv_blocked = client.post('/file-complaint', data={
                'title': 'Broken Water Valve on 2nd Cross',
                'category': 'Water Supply',
                'location': '2nd Cross, Sector 4',
                'description': 'Water leaking heavily from the valve near the intersection.'
            })
            assert b"Identity verification required" in rv_blocked.data

            # 3. Call send-complaint-otp API
            res_send = client.post('/api/otp/send-complaint-otp', json={})
            assert res_send.status_code == 200
            send_data = res_send.get_json()
            assert send_data['success'] is True
            email_otp = send_data['dev_email_otp']
            phone_otp = send_data['dev_phone_otp']
            assert len(email_otp) == 6
            assert len(phone_otp) == 6

            # 4. Call verify API with invalid code -> should fail
            res_fail = client.post('/api/otp/verify-complaint-otp', json={
                'email_otp': '000000',
                'phone_otp': phone_otp
            })
            assert res_fail.status_code == 400

            # 5. Call verify API with valid codes -> should succeed and set session
            res_ok = client.post('/api/otp/verify-complaint-otp', json={
                'email_otp': email_otp,
                'phone_otp': phone_otp
            })
            assert res_ok.status_code == 200
            assert res_ok.get_json()['success'] is True

            # 6. Submit complaint -> now succeeds and delivers confirmation email
            rv_submit = client.post('/file-complaint', data={
                'title': 'Broken Water Valve on 2nd Cross',
                'category': 'Water Supply',
                'location': '2nd Cross, Sector 4',
                'description': 'Water leaking heavily from the valve near the intersection.'
            }, follow_redirects=True)
            assert rv_submit.status_code == 200
            assert b"submitted successfully" in rv_submit.data

            # 7. Check that confirmation email was dispatched to e2e.tester@gmail.com
            sent = get_sent_emails()
            confirmation_emails = [e for e in sent if e.get('to') == 'e2e.tester@gmail.com' and e.get('type') != 'OTP']
            assert len(confirmation_emails) >= 1
            assert 'Broken Water Valve on 2nd Cross' in confirmation_emails[0]['subject']
    finally:
        flask_app.app.config['TESTING'] = orig_testing
