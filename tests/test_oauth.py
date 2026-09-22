import pytest
import database
import app as flask_app

@pytest.fixture
def client():
    flask_app.app.config['TESTING'] = True
    with flask_app.app.test_client() as client:
        yield client

@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    """Use an isolated test database for OAuth tests."""
    db_file = str(tmp_path / "test_oauth.db")
    monkeypatch.setattr(database, 'DB_PATH', db_file)
    database.init_db()
    database.ensure_schema()
    yield

def test_google_oauth_login_unconfigured_shows_setup_page(client):
    """When GOOGLE_CLIENT_ID is not set, login redirect renders setup / simulator page."""
    rv = client.get('/auth/google/login')
    assert rv.status_code == 200
    assert b"Google OAuth 2.0" in rv.data
    assert b"Test Google Sign-In" in rv.data

def test_google_oauth_login_configured_redirects_to_google(client, monkeypatch):
    """When GOOGLE_CLIENT_ID is set, redirect to accounts.google.com."""
    monkeypatch.setenv('GOOGLE_CLIENT_ID', 'test_client_id_123.apps.googleusercontent.com')
    monkeypatch.setenv('GOOGLE_CLIENT_SECRET', 'test_secret_abc')
    
    rv = client.get('/auth/google/login')
    assert rv.status_code == 302
    assert "accounts.google.com/o/oauth2/v2/auth" in rv.location
    assert "test_client_id_123" in rv.location
    assert "response_type=code" in rv.location
    assert "scope=openid" in rv.location

def test_google_oauth_demo_login_creates_and_verifies_new_citizen(client):
    """Simulator login creates a new citizen account with email verified and logs in."""
    rv = client.post('/auth/google/demo-login', data={
        'demo_email': 'google.citizen@gmail.com',
        'demo_name': 'Google Citizen'
    }, follow_redirects=True)
    assert b"Account created" in rv.data
    assert b"verified via Google" in rv.data

    # Verify user exists in database with verified status
    user = database.get_user_by_email('google.citizen@gmail.com')
    assert user is not None
    assert user['full_name'] == 'Google Citizen'
    assert user['is_verified'] == 1
    assert user['is_email_verified'] == 1
    assert user['role'] == 'citizen'

def test_google_oauth_demo_login_existing_user(client):
    """Simulator login logs in existing user and ensures verified status."""
    uid = database.create_user(
        username='existing_citizen',
        password_hash=flask_app.generate_password_hash('pass123'),
        full_name='Existing Citizen',
        email='existing@gmail.com',
        phone='9876543210',
        role='citizen'
    )
    assert uid is not None

    rv = client.post('/auth/google/demo-login', data={
        'demo_email': 'existing@gmail.com',
        'demo_name': 'Existing Citizen'
    }, follow_redirects=True)
    assert rv.status_code == 200
    assert b"Signed in successfully with Google" in rv.data

    updated = database.get_user_by_id(uid)
    assert updated['is_verified'] == 1
    assert updated['is_email_verified'] == 1

def test_google_oauth_callback_user_cancelled(client):
    """When user cancels on Google authorization page, redirect with message."""
    rv = client.get('/auth/google/callback?error=access_denied', follow_redirects=True)
    assert rv.status_code == 200
    assert b"cancelled or failed" in rv.data

def test_login_and_register_pages_contain_google_buttons(client):
    """Verify that both login and register pages render the Google Sign-In button."""
    rv_login = client.get('/login')
    assert b"Sign in with Google" in rv_login.data
    assert b"/auth/google/login" in rv_login.data

    rv_reg = client.get('/register')
    assert b"Sign up with Google" in rv_reg.data
    assert b"/auth/google/login" in rv_reg.data
