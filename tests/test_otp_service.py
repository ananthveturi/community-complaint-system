import os
import pytest
from datetime import datetime, timedelta
import database
from integrity.otp_service import (
    generate_numeric_otp,
    send_dual_otp,
    send_single_otp,
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


def test_send_single_otp():
    email = "single.target@gmail.com"
    phone = "+919876543299"

    res_email = send_single_otp(target=email, target_type='email', purpose='registration', user_name='Single Tester')
    assert res_email['success'] is True
    assert res_email['dev_otp'] is not None
    assert len(res_email['dev_otp']) == 6

    res_phone = send_single_otp(target=phone, target_type='phone', purpose='registration', user_name='Single Tester')
    assert res_phone['success'] is True
    assert res_phone['dev_otp'] is not None
    assert len(res_phone['dev_otp']) == 6


def test_flask_otp_api_and_complaint_submission_flow(monkeypatch):
    import app as flask_app
    from integrity.email_service import get_sent_emails, clear_sent_emails

    clear_sent_emails()
    # Set testing flag to False to strictly enforce the live OTP gate
    orig_testing = flask_app.app.config.get('TESTING', False)
    flask_app.app.config['TESTING'] = False

    try:
        with flask_app.app.test_client() as client:
            email = 'e2e.tester@gmail.com'
            phone = '9123456780'

            # 1. Attempt registration without OTP -> Should be blocked with email verification required
            rv_reg_blocked = client.post('/register', data={
                'username': 'e2e_otp_user',
                'full_name': 'E2E Tester',
                'email': email,
                'phone': phone,
                'password': 'password123'
            }, follow_redirects=True)
            assert b"Email verification required" in rv_reg_blocked.data

            # 2. Verify email via channel OTP API
            res_e = client.post('/api/otp/send-channel-otp', json={
                'target': email,
                'target_type': 'email',
                'purpose': 'registration',
                'user_name': 'E2E Tester'
            })
            assert res_e.status_code == 200
            otp_email = res_e.get_json()['dev_otp']

            res_v_e = client.post('/api/otp/verify-channel-otp', json={
                'target': email,
                'target_type': 'email',
                'otp_code': otp_email,
                'purpose': 'registration'
            })
            assert res_v_e.status_code == 200

            # 3. Attempt registration with only email verified -> Blocked with phone verification required
            rv_phone_blocked = client.post('/register', data={
                'username': 'e2e_otp_user',
                'full_name': 'E2E Tester',
                'email': email,
                'phone': phone,
                'password': 'password123'
            }, follow_redirects=True)
            assert b"Phone verification required" in rv_phone_blocked.data

            # 4. Verify phone via channel OTP API
            res_p = client.post('/api/otp/send-channel-otp', json={
                'target': phone,
                'target_type': 'phone',
                'purpose': 'registration',
                'user_name': 'E2E Tester'
            })
            assert res_p.status_code == 200
            otp_phone = res_p.get_json()['dev_otp']

            res_v_p = client.post('/api/otp/verify-channel-otp', json={
                'target': phone,
                'target_type': 'phone',
                'otp_code': otp_phone,
                'purpose': 'registration'
            })
            assert res_v_p.status_code == 200

            # 5. Now register succeeds!
            rv_reg = client.post('/register', data={
                'username': 'e2e_otp_user',
                'full_name': 'E2E Tester',
                'email': email,
                'phone': phone,
                'password': 'password123'
            }, follow_redirects=True)
            assert rv_reg.status_code == 200
            assert b"Account registered successfully" in rv_reg.data

            # 6. Login user
            client.post('/login', data={'username': 'e2e_otp_user', 'password': 'password123'})

            # 7. Attempt filing complaint without OTP -> Should be blocked and prompt verification
            rv_blocked = client.post('/file-complaint', data={
                'title': 'Broken Water Valve on 2nd Cross',
                'category': 'Water Supply',
                'location': '2nd Cross, Sector 4',
                'description': 'Water leaking heavily from the valve near the intersection.'
            })
            assert b"Identity verification required" in rv_blocked.data

            # 8. Call send-complaint-otp API
            res_send = client.post('/api/otp/send-complaint-otp', json={})
            assert res_send.status_code == 200
            send_data = res_send.get_json()
            assert send_data['success'] is True
            email_otp = send_data['dev_email_otp']
            phone_otp = send_data['dev_phone_otp']
            assert len(email_otp) == 6
            assert len(phone_otp) == 6

            # 9. Call verify API with invalid code -> should fail
            res_fail = client.post('/api/otp/verify-complaint-otp', json={
                'email_otp': '000000',
                'phone_otp': phone_otp
            })
            assert res_fail.status_code == 400

            # 10. Call verify API with valid codes -> should succeed and set session
            res_ok = client.post('/api/otp/verify-complaint-otp', json={
                'email_otp': email_otp,
                'phone_otp': phone_otp
            })
            assert res_ok.status_code == 200
            assert res_ok.get_json()['success'] is True

            # 11. Submit complaint -> now succeeds and delivers confirmation email
            rv_submit = client.post('/file-complaint', data={
                'title': 'Broken Water Valve on 2nd Cross',
                'category': 'Water Supply',
                'location': '2nd Cross, Sector 4',
                'description': 'Water leaking heavily from the valve near the intersection.'
            }, follow_redirects=True)
            assert rv_submit.status_code == 200
            assert b"submitted successfully" in rv_submit.data

            # 12. Check that confirmation email was dispatched to e2e.tester@gmail.com
            sent = get_sent_emails()
            confirmation_emails = [e for e in sent if e.get('to') == 'e2e.tester@gmail.com' and e.get('type') != 'OTP']
            assert len(confirmation_emails) >= 1
            assert 'Broken Water Valve on 2nd Cross' in confirmation_emails[0]['subject']
    finally:
        flask_app.app.config['TESTING'] = orig_testing


def test_flask_individual_channel_otp_complaint_flow(monkeypatch):
    """Test complaint filing using separate individual channel OTP verification."""
    import app as flask_app
    from integrity.email_service import get_sent_emails, clear_sent_emails

    clear_sent_emails()
    orig_testing = flask_app.app.config.get('TESTING', False)
    flask_app.app.config['TESTING'] = False

    try:
        with flask_app.app.test_client() as client:
            # Create user in DB
            uid = database.create_user(
                username='channel_user',
                password_hash=flask_app.generate_password_hash('pass123'),
                full_name='Channel User',
                email='channel.user@gmail.com',
                phone='9811223344',
                role='citizen'
            )
            # Log in
            client.post('/login', data={'username': 'channel_user', 'password': 'pass123'})

            # Verify email channel individually
            r_e = client.post('/api/otp/send-channel-otp', json={
                'target_type': 'email',
                'purpose': 'complaint_submission'
            })
            assert r_e.status_code == 200
            e_code = r_e.get_json()['dev_otp']

            r_ve = client.post('/api/otp/verify-channel-otp', json={
                'target_type': 'email',
                'otp_code': e_code,
                'purpose': 'complaint_submission'
            })
            assert r_ve.status_code == 200

            # Verify phone channel individually
            r_p = client.post('/api/otp/send-channel-otp', json={
                'target_type': 'phone',
                'purpose': 'complaint_submission'
            })
            assert r_p.status_code == 200
            p_code = r_p.get_json()['dev_otp']

            r_vp = client.post('/api/otp/verify-channel-otp', json={
                'target_type': 'phone',
                'otp_code': p_code,
                'purpose': 'complaint_submission'
            })
            assert r_vp.status_code == 200

            # File complaint -> should succeed because both channels were verified
            rv = client.post('/file-complaint', data={
                'title': 'Overflowing Garbage Bin',
                'category': 'Garbage',
                'location': 'Market Road',
                'description': 'The public garbage bin is overflowing onto the street.'
            }, follow_redirects=True)
            assert rv.status_code == 200
            assert b"submitted successfully" in rv.data

            # Check confirmation email
            sent = get_sent_emails()
            confirmations = [e for e in sent if e.get('to') == 'channel.user@gmail.com' and e.get('type') != 'OTP']
            assert len(confirmations) >= 1
            assert 'Overflowing Garbage Bin' in confirmations[0]['subject']
    finally:
        flask_app.app.config['TESTING'] = orig_testing
