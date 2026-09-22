import pytest
import os
import tempfile
import app
import database

@pytest.fixture
def client():
    db_fd, db_path = tempfile.mkstemp()
    old_path = database.DB_PATH
    database.DB_PATH = db_path
    database.init_db()
    database.ensure_schema()
    
    app.app.config['TESTING'] = True
    app.app.config['SECRET_KEY'] = 'test-secret-key'
    
    with app.app.test_client() as client:
        yield client
        
    database.DB_PATH = old_path
    os.close(db_fd)
    if os.path.exists(db_path):
        os.unlink(db_path)

def test_index_page(client):
    rv = client.get('/')
    assert rv.status_code == 200
    assert b"CivicConnect" in rv.data or b"Community Complaint" in rv.data

def test_registration_and_login_flow(client):
    # Register user
    rv = client.post('/register', data={
        'username': 'johndoe',
        'full_name': 'John Doe',
        'email': 'john@example.com',
        'phone': '1234567890',
        'password': 'password123'
    }, follow_redirects=True)
    assert rv.status_code == 200
    assert b"Account registered successfully" in rv.data

    # Login user
    rv = client.post('/login', data={
        'username': 'johndoe',
        'password': 'password123'
    }, follow_redirects=True)
    assert rv.status_code == 200
    assert b"Welcome back" in rv.data

def test_file_complaint_and_citizen_dashboard(client):
    # Register & Login
    client.post('/register', data={
        'username': 'citizen2',
        'full_name': 'Citizen Two',
        'email': 'c2@example.com',
        'phone': '9999999999',
        'password': 'password123'
    })
    client.post('/login', data={'username': 'citizen2', 'password': 'password123'})

    # Submit Complaint
    rv = client.post('/file-complaint', data={
        'title': 'Streetlight flickering on Main St',
        'category': 'Electricity & Power',
        'location': 'Main St Crossing',
        'description': 'Streetlight flickers uncontrollably causing glare'
    }, follow_redirects=True)
    assert rv.status_code == 200
    assert b"submitted successfully" in rv.data

    # View citizen dashboard
    rv = client.get('/dashboard')
    assert rv.status_code == 200
    assert b"Streetlight flickering on Main St" in rv.data

def test_sitemap_and_robots(client):
    rv = client.get('/robots.txt')
    assert rv.status_code == 200
    assert b"User-agent" in rv.data

    rv = client.get('/sitemap.xml')
    assert rv.status_code == 200
    assert b"urlset" in rv.data

def test_delete_complaint_flow(client):
    client.post('/register', data={
        'username': 'deleter',
        'full_name': 'Deleter User',
        'email': 'del@example.com',
        'phone': '1234567890',
        'password': 'password123'
    })
    client.post('/login', data={'username': 'deleter', 'password': 'password123'})

    # File complaint
    client.post('/file-complaint', data={
        'title': 'Case to be deleted',
        'category': 'Roads & Traffic',
        'location': 'Delete Street',
        'description': 'Temporary complaint'
    })

    user = database.get_user_by_username('deleter')
    complaints = database.get_citizen_complaints(user['id'])
    cid = complaints[0]['id']

    # Delete complaint
    rv = client.post(f'/complaint/{cid}/delete', follow_redirects=True)
    assert rv.status_code == 200
    assert b"deleted successfully" in rv.data


def test_mandatory_credentials_registration(client):
    """Ensure all 5 credentials are strictly mandatory on registration."""
    # Missing username
    rv = client.post('/register', data={
        'username': '',
        'full_name': 'Jane Doe',
        'email': 'jane@gmail.com',
        'phone': '9876543210',
        'password': 'password123'
    }, follow_redirects=True)
    assert b"All credentials" in rv.data

    # Missing full name
    rv = client.post('/register', data={
        'username': 'janedoe',
        'full_name': '',
        'email': 'jane@gmail.com',
        'phone': '9876543210',
        'password': 'password123'
    }, follow_redirects=True)
    assert b"All credentials" in rv.data

    # Missing email
    rv = client.post('/register', data={
        'username': 'janedoe',
        'full_name': 'Jane Doe',
        'email': '',
        'phone': '9876543210',
        'password': 'password123'
    }, follow_redirects=True)
    assert b"All credentials" in rv.data

    # Invalid email format
    rv = client.post('/register', data={
        'username': 'janedoe',
        'full_name': 'Jane Doe',
        'email': 'not-an-email',
        'phone': '9876543210',
        'password': 'password123'
    }, follow_redirects=True)
    assert b"valid email address" in rv.data

    # Missing phone
    rv = client.post('/register', data={
        'username': 'janedoe',
        'full_name': 'Jane Doe',
        'email': 'jane@gmail.com',
        'phone': '',
        'password': 'password123'
    }, follow_redirects=True)
    assert b"All credentials" in rv.data

    # Invalid phone format (< 7 digits)
    rv = client.post('/register', data={
        'username': 'janedoe',
        'full_name': 'Jane Doe',
        'email': 'jane@gmail.com',
        'phone': '123',
        'password': 'password123'
    }, follow_redirects=True)
    assert b"valid phone number" in rv.data

    # Short password (< 6 chars)
    rv = client.post('/register', data={
        'username': 'janedoe',
        'full_name': 'Jane Doe',
        'email': 'jane@gmail.com',
        'phone': '9876543210',
        'password': '123'
    }, follow_redirects=True)
    assert b"at least 6 characters long" in rv.data


def test_login_with_email_or_username(client):
    """Verify citizen can log in using either username or email address."""
    client.post('/register', data={
        'username': 'civicuser',
        'full_name': 'Civic Resident',
        'email': 'civic.resident@gmail.com',
        'phone': '+91 9876543210',
        'password': 'securepassword'
    })

    # Log in with username
    rv = client.post('/login', data={
        'username': 'civicuser',
        'password': 'securepassword'
    }, follow_redirects=True)
    assert rv.status_code == 200
    assert b"Welcome back, Civic Resident!" in rv.data

    # Log out
    client.get('/logout')

    # Log in with Gmail / Email address
    rv = client.post('/login', data={
        'username': 'civic.resident@gmail.com',
        'password': 'securepassword'
    }, follow_redirects=True)
    assert rv.status_code == 200
    assert b"Welcome back, Civic Resident!" in rv.data

    # Log out
    client.get('/logout', follow_redirects=True)

    # Reject empty credentials
    rv = client.post('/login', data={
        'username': '',
        'password': ''
    }, follow_redirects=True)
    assert b"credentials are mandatory" in rv.data


def test_email_dispatch_on_complaint_submission(client, tmp_path):
    """Verify automated email dispatch with complaint details and evidence image."""
    from integrity.email_service import get_sent_emails, clear_sent_emails
    import io
    from PIL import Image

    clear_sent_emails()

    # Register user with Gmail address
    client.post('/register', data={
        'username': 'emailtestuser',
        'full_name': 'Email Tester',
        'email': 'tester.civifix@gmail.com',
        'phone': '9876543210',
        'password': 'password123'
    })
    client.post('/login', data={'username': 'emailtestuser', 'password': 'password123'})

    # Create dummy image
    img = Image.new('RGB', (120, 120), color=(30, 144, 255))
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='JPEG')
    img_byte_arr.seek(0)

    # Submit complaint with image and coordinates
    rv = client.post('/file-complaint', data={
        'title': 'Dangerous Pothole on Oak Ave',
        'category': 'Roads & Traffic',
        'location': 'Corner of Oak & 5th Avenue',
        'latitude': '12.9716',
        'longitude': '77.5946',
        'description': 'A severe pothole approximately 2 feet wide on the eastbound lane.',
        'image': (img_byte_arr, 'pothole_evidence.jpg')
    }, follow_redirects=True)
    assert rv.status_code == 200

    # Verify email was dispatched
    sent = get_sent_emails()
    assert len(sent) >= 1
    last_email = sent[-1]
    assert last_email['to'] == 'tester.civifix@gmail.com'
    assert 'Dangerous Pothole on Oak Ave' in last_email['subject']
    assert last_email['has_image'] is True
    assert last_email['image_filename'] is not None


def test_password_visibility_toggle_and_mobile_elements(client):
    """Verify password toggle (eye symbol) and mobile drawer elements exist in markup."""
    # Login page
    rv = client.get('/login')
    assert rv.status_code == 200
    assert b'togglePasswordVisibility' in rv.data
    assert b'data-lucide="eye"' in rv.data
    assert b'mobileDrawer' in rv.data
    assert b'viewport-fit=cover' in rv.data

    # Register page
    rv = client.get('/register')
    assert rv.status_code == 200
    assert b'togglePasswordVisibility' in rv.data
    assert b'data-lucide="eye"' in rv.data


def test_multistep_wizard_structure(client):
    """Verify 4-step wizard structure and review card on file complaint page."""
    # Register & Login
    client.post('/register', data={
        'username': 'wizarduser',
        'full_name': 'Wizard Citizen',
        'email': 'wizard@gmail.com',
        'phone': '9876543210',
        'password': 'password123'
    })
    client.post('/login', data={'username': 'wizarduser', 'password': 'password123'})

    # Direct access to file complaint with category
    rv = client.get('/file-complaint?category=Roads%20%26%20Traffic')
    assert rv.status_code == 200
    # Check for all 4 step panes
    assert b'step-pane-1' in rv.data
    assert b'step-pane-2' in rv.data
    assert b'step-pane-3' in rv.data
    assert b'step-pane-4' in rv.data
    assert b'step-progress-fill' in rv.data
    # Check review preview card
    assert b'review-category' in rv.data
    assert b'review-title' in rv.data
    assert b'review-location' in rv.data
    # Check mobile navigation drawer and bottom nav bar
    assert b'mobileDrawer' in rv.data
    assert b'mobileMenuBtn' in rv.data
