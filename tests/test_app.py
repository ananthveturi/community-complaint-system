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
        'phone': '123',
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
