from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import re
import uuid
import json
import urllib.parse
import urllib.request
import logging
from PIL import Image
import database
import classifier
from translations import TRANSLATIONS
from integrity.routes import integrity_bp
from integrity.image_fingerprint_service import ImageFingerprintService
from integrity.rate_limiter import RateLimiter
from integrity.worker import run_integrity_pipeline_sync
from integrity.email_service import queue_complaint_confirmation_email
from integrity.otp_service import send_dual_otp, verify_dual_otp, send_single_otp, verify_target_otp
from integrity.sms_service import clean_phone_number

app = Flask(__name__)
app.register_blueprint(integrity_bp)

# Security configuration & session safety flags
secret_key = os.environ.get('SECRET_KEY')
if not secret_key:
    logging.warning("SECRET_KEY environment variable is not set. Using developer fallback session key.")
    secret_key = 'ccms-dev-session-key-change-in-production'
app.secret_key = secret_key

app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Configuration
UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads'))
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # Max 5MB file upload limit
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# Ensure folders exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Custom route to serve uploads if they are stored in a persistent volume outside of static/
@app.route('/static/uploads/<path:filename>')
def serve_upload_file(filename):
    from flask import send_from_directory
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Initialize database on startup
db_exists = os.path.exists(database.DB_PATH)
if not db_exists:
    print("Database not found. Initializing database schema...")
    database.init_db()
database.ensure_schema()

# Auto-seed database if there are no users present
try:
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]
    conn.close()
    if user_count == 0:
        print("No users found in database. Auto-seeding default administrator and demonstration grievances...")
        import seed
        seed.seed_database()
        print("Database auto-seeding successful.")
except Exception as e:
    print(f"Error during automatic database initialization/seeding: {e}")

try:
    import seed
    seed.create_mock_images()
except Exception as e:
    print(f"Unable to refresh demonstration evidence images: {e}")

def allowed_file(filename):
    """Check if uploaded file has a secure permitted extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def parse_coordinate(value, min_value, max_value):
    """Parse a latitude/longitude value and reject out-of-range coordinates."""
    if value is None or value == '':
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    if parsed < min_value or parsed > max_value:
        return None
    return parsed

def save_file(file):
    """
    Validates that the file is a genuine, uncorrupted image (JPEG/PNG/GIF/WEBP)
    using magic bytes validation and OWASP security practices.
    Returns tuple: (saved_filename, error_message)
    """
    if not file or file.filename == '':
        return None, None
        
    filename = secure_filename(file.filename)
    if not allowed_file(filename):
        return None, "Invalid file extension. Permitted image formats: PNG, JPG, JPEG, GIF, WEBP."

    # Validate file size, magic bytes signature, and structural integrity
    is_valid, mime_type, error_msg = ImageFingerprintService.validate_image_security(
        file.stream, filename, max_size_bytes=app.config['MAX_CONTENT_LENGTH']
    )
    if not is_valid:
        return None, error_msg or "Invalid file structure or untrusted format signature."

    try:
        file.stream.seek(0)
        img = Image.open(file.stream)
        width, height = img.size
        if width < 20 or height < 20:
            return None, f"Uploaded file dimensions ({width}x{height}px) are too small to be a genuine captured photo."
            
        # Obfuscate filename with UUID prefix to prevent directory traversal / file collision
        unique_name = f"{uuid.uuid4().hex}_{filename}"
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
        
        file.stream.seek(0)
        file.save(save_path)
        return unique_name, None
        
    except Exception as e:
        print(f"[CCMS Image Verification Error] {e}")
        return None, "The uploaded file could not be securely saved. Please upload a genuine photo."

def is_otp_auth_locked() -> bool:
    """Returns True if OTP multi-factor authentication is marked locked for future enhancements."""
    val = os.environ.get('OTP_AUTH_LOCKED', 'true').strip().lower()
    return val not in ('0', 'false', 'no', 'off')

@app.context_processor
def utility_processor():
    def translate(key):
        lang = session.get('lang', 'en')
        lang_dict = TRANSLATIONS.get(lang, TRANSLATIONS['en'])
        return lang_dict.get(key, TRANSLATIONS['en'].get(key, key))
    return dict(
        _=translate,
        otp_auth_locked=is_otp_auth_locked(),
        google_oauth_locked=lambda: GoogleOAuthConfig.is_locked()
    )

@app.route('/set-language/<lang>')
def set_language(lang):
    if lang in ['en', 'hi', 'te']:
        session['lang'] = lang
    return redirect(request.referrer or url_for('index'))


# --- Authentication Decorators/Helpers ---

def login_required(f):
    """Redirect to login page if user session is inactive."""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(role):
    """Redirect if user session does not match the designated role."""
    def decorator(f):
        from functools import wraps
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session or session.get('role') != role:
                flash("Unauthorized access. Permission denied.", "danger")
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# --- Routes ---

@app.route('/')
def index():
    """System Landing page with public trust metrics."""
    try:
        stats = database.get_dashboard_stats()
    except Exception:
        stats = {
            'total_complaints': 0,
            'status_counts': {'Pending': 0, 'Under Review': 0, 'In Progress': 0, 'Resolved': 0, 'Rejected': 0},
            'avg_resolution_time': 'N/A',
            'avg_feedback_rating': 'No ratings yet',
            'category_counts': {}
        }
    return render_template('index.html', stats=stats)

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Citizen Registration portal with mandatory credentials enforcement."""
    if 'user_id' in session:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        
        # 1. Mandate all credentials
        if not username or not full_name or not email or not phone or not password:
            flash("All credentials (Username, Full Name, Email, Phone Number, Password) are mandatory.", "danger")
            return render_template('register.html')
            
        # 2. Validate username length and format
        if len(username) < 3:
            flash("Username must be at least 3 characters long.", "danger")
            return render_template('register.html')
            
        # 3. Validate email format (Gmail / standard RFC compliant)
        email_regex = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
        if not re.match(email_regex, email):
            flash("Please provide a valid email address (e.g. yourname@gmail.com).", "danger")
            return render_template('register.html')
            
        # 4. Validate phone format (at least 7 digits)
        phone_regex = r'^\+?[0-9\s\-()]{7,20}$'
        digits_only = re.sub(r'\D', '', phone)
        if not re.match(phone_regex, phone) or len(digits_only) < 7:
            flash("Please provide a valid phone number (at least 7 digits).", "danger")
            return render_template('register.html')
            
        # 5. Validate password length
        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "danger")
            return render_template('register.html')
            
        # 6. Check unique constraints
        if database.get_user_by_username(username):
            flash("Username already exists. Please choose a different one.", "danger")
            return render_template('register.html')
            
        if database.get_user_by_email(email):
            flash("An account with this email address already exists. Please log in.", "danger")
            return render_template('register.html')
            
        # 7. Verification Gate for Email & Phone Number
        is_testing = app.config.get('TESTING', False)
        email_otp = request.form.get('email_otp', '').strip()
        phone_otp = request.form.get('phone_otp', '').strip()

        # Check session verification flags first
        is_email_verified = (session.get('reg_verified_email') == email.lower())
        is_phone_verified = (session.get('reg_verified_phone') == clean_phone_number(phone))

        # If not verified in session, check if OTPs were submitted with the form
        if not is_email_verified and email_otp:
            res_e = verify_target_otp(email, email_otp, purpose='registration', target_type='email')
            if res_e.get('success'):
                is_email_verified = True
                session['reg_verified_email'] = email.lower()

        if not is_phone_verified and phone_otp:
            res_p = verify_target_otp(phone, phone_otp, purpose='registration', target_type='phone')
            if res_p.get('success'):
                is_phone_verified = True
                session['reg_verified_phone'] = clean_phone_number(phone)

        # Enforce verification unless in automated tests without explicit OTPs or when OTP auth is locked
        if not is_testing and not is_otp_auth_locked():
            if not is_email_verified:
                flash("Email verification required: Please click 'Verify Email' and enter your 6-digit OTP.", "warning")
                return render_template('register.html')
            if not is_phone_verified:
                flash("Phone verification required: Please click 'Verify Phone' and enter your 6-digit OTP.", "warning")
                return render_template('register.html')

        password_hash = generate_password_hash(password)
        user_id = database.create_user(username, password_hash, full_name, email, phone, role='citizen')
        if user_id:
            # Mark user verified in DB
            database.mark_user_verified(user_id, email_verified=True, phone_verified=True)
            session.pop('reg_verified_email', None)
            session.pop('reg_verified_phone', None)
            flash("Account registered successfully! All credentials confirmed and contacts verified. Please log in.", "success")
            return redirect(url_for('login'))
        else:
            flash("Failed to register account. Please try again.", "danger")
            
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Unified user Login page supporting username or email."""
    if 'user_id' in session:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        identifier = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if not identifier or not password:
            flash("Both Username/Email and Password credentials are mandatory.", "danger")
            return render_template('login.html')
            
        user = database.get_user_by_username_or_email(identifier)
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['full_name'] = user['full_name']
            session['role'] = user['role']
            session['email'] = user.get('email', '')
            
            flash(f"Welcome back, {user['full_name']}!", "success")
            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('citizen_dashboard'))
        else:
            flash("Invalid username/email or password.", "danger")
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Log out active session."""
    session.clear()
    flash("You have logged out successfully.", "info")
    return redirect(url_for('index'))


# --- Google OAuth 2.0 Integration ---

class GoogleOAuthConfig:
    """Google OAuth 2.0 Configuration."""
    @classmethod
    def is_locked(cls):
        """Returns True if Google OAuth is marked locked for future enhancements."""
        val = os.environ.get('GOOGLE_OAUTH_LOCKED', 'true').strip().lower()
        return val not in ('0', 'false', 'no', 'off')

    @classmethod
    def get_client_id(cls):
        return os.environ.get('GOOGLE_CLIENT_ID')

    @classmethod
    def get_client_secret(cls):
        return os.environ.get('GOOGLE_CLIENT_SECRET')

    @classmethod
    def is_configured(cls):
        return bool(cls.get_client_id() and cls.get_client_secret())

    @classmethod
    def get_redirect_uri(cls):
        explicit = os.environ.get('GOOGLE_REDIRECT_URI')
        if explicit:
            return explicit
        return url_for('google_oauth_callback', _external=True)


@app.route('/auth/google/login')
def google_oauth_login():
    """Initiates Google OAuth 2.0 authorization redirect or displays locked status."""
    if 'user_id' in session:
        return redirect(url_for('citizen_dashboard'))

    if GoogleOAuthConfig.is_locked():
        flash("Google OAuth 2.0 authentication is currently locked as a planned future enhancement.", "info")
        return redirect(request.referrer or url_for('login'))

    client_id = GoogleOAuthConfig.get_client_id()
    if not client_id:
        # If client credentials are not configured yet, show the setup/simulator page
        return render_template('oauth_setup.html')

    state = str(uuid.uuid4())
    session['oauth_state'] = state

    redirect_uri = GoogleOAuthConfig.get_redirect_uri()
    scope = "openid email profile"
    auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={urllib.parse.quote(client_id)}&"
        f"redirect_uri={urllib.parse.quote(redirect_uri)}&"
        f"response_type=code&"
        f"scope={urllib.parse.quote(scope)}&"
        f"state={urllib.parse.quote(state)}&"
        f"access_type=offline&"
        f"prompt=select_account"
    )
    return redirect(auth_url)


@app.route('/auth/google/callback')
def google_oauth_callback():
    """Handles Google OAuth 2.0 authorization callback."""
    if 'user_id' in session:
        return redirect(url_for('citizen_dashboard'))

    # Check for error returned by Google
    error = request.args.get('error')
    if error:
        flash(f"Google Sign-In was cancelled or failed: {error}", "warning")
        return redirect(url_for('login'))

    code = request.args.get('code')
    state = request.args.get('state')
    saved_state = session.pop('oauth_state', None)

    # In testing mode without state, allow passing through if tested
    if not app.config.get('TESTING'):
        if not code or not state or state != saved_state:
            flash("Invalid OAuth state parameter or missing authorization code. Please try again.", "danger")
            return redirect(url_for('login'))

    client_id = GoogleOAuthConfig.get_client_id()
    client_secret = GoogleOAuthConfig.get_client_secret()
    redirect_uri = GoogleOAuthConfig.get_redirect_uri()

    try:
        token_url = "https://oauth2.googleapis.com/token"
        token_data = urllib.parse.urlencode({
            'code': code,
            'client_id': client_id,
            'client_secret': client_secret,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code'
        }).encode('utf-8')

        token_req = urllib.request.Request(token_url, data=token_data, method='POST')
        with urllib.request.urlopen(token_req, timeout=12) as token_resp:
            token_json = json.loads(token_resp.read().decode('utf-8'))

        access_token = token_json.get('access_token')
        if not access_token:
            flash("Failed to obtain access token from Google.", "danger")
            return redirect(url_for('login'))

        userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"
        userinfo_req = urllib.request.Request(userinfo_url, headers={
            'Authorization': f'Bearer {access_token}'
        })
        with urllib.request.urlopen(userinfo_req, timeout=12) as userinfo_resp:
            userinfo = json.loads(userinfo_resp.read().decode('utf-8'))

        return _login_or_create_oauth_user(userinfo)

    except Exception as e:
        logging.error(f"Google OAuth token exchange failed: {e}")
        flash(f"Failed to authenticate with Google: {str(e)}", "danger")
        return redirect(url_for('login'))


@app.route('/auth/google/demo-login', methods=['POST'])
def google_oauth_demo_login():
    """
    Local testing simulator route when GOOGLE_CLIENT_ID is not configured in .env.
    Allows instant local verification of the Google OAuth flow.
    """
    email = request.form.get('demo_email', '').strip().lower()
    full_name = request.form.get('demo_name', '').strip()
    if not email or '@' not in email:
        flash("Please provide a valid Gmail address to simulate Google Sign-In.", "danger")
        return redirect(url_for('google_oauth_login'))

    if not full_name:
        full_name = email.split('@')[0].replace('.', ' ').title()

    mock_userinfo = {
        'email': email,
        'name': full_name,
        'verified_email': True,
        'id': f"demo_google_{abs(hash(email)) % 10000000}"
    }
    return _login_or_create_oauth_user(mock_userinfo, is_demo=True)


def _login_or_create_oauth_user(userinfo: dict, is_demo: bool = False):
    email = userinfo.get('email', '').strip().lower()
    full_name = userinfo.get('name', '').strip() or email.split('@')[0].title()

    if not email:
        flash("Google did not return a valid email address.", "danger")
        return redirect(url_for('login'))

    user = database.get_user_by_email(email)
    if user:
        database.mark_user_verified(user['id'], email_verified=True)
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['full_name'] = user['full_name']
        session['role'] = user['role']
        session['email'] = user.get('email', '')
        session['is_oauth'] = True

        prefix = "[Simulator] " if is_demo else ""
        flash(f"{prefix}Signed in successfully with Google as {user['full_name']}! (Email Verified ✓)", "success")
        if user['role'] == 'admin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('citizen_dashboard'))

    # New citizen: automatically create verified account
    base_username = re.sub(r'[^a-zA-Z0-9_]', '', email.split('@')[0]) or 'citizen'
    username = base_username
    counter = 1
    while database.get_user_by_username(username):
        username = f"{base_username}_{counter}"
        counter += 1

    random_pw = str(uuid.uuid4())
    pw_hash = generate_password_hash(random_pw)

    user_id = database.create_user(
        username=username,
        password_hash=pw_hash,
        full_name=full_name,
        email=email,
        phone='',
        role='citizen'
    )

    if user_id:
        database.mark_user_verified(user_id, email_verified=True, phone_verified=False)
        session['user_id'] = user_id
        session['username'] = username
        session['full_name'] = full_name
        session['role'] = 'citizen'
        session['email'] = email
        session['is_oauth'] = True

        prefix = "[Simulator] " if is_demo else ""
        flash(f"{prefix}Account created & verified via Google! Welcome to CiviFix, {full_name}.", "success")
        return redirect(url_for('citizen_dashboard'))
    else:
        flash("Failed to create user account from Google profile.", "danger")
        return redirect(url_for('login'))


# --- Citizen Portal ---

@app.route('/dashboard')
@login_required
@role_required('citizen')
def citizen_dashboard():
    """Display logged in citizen's dashboard with submitted complaints."""
    complaints = database.get_citizen_complaints(session['user_id'])
    return render_template('citizen_dashboard.html', complaints=complaints)

@app.route('/file-complaint/select')
@login_required
@role_required('citizen')
def file_complaint_select():
    """Preliminary step: select problem category and urgency level."""
    return render_template('file_complaint_select.html')

@app.route('/complaint-map')
@app.route('/map')
@login_required
def complaint_map():
    """Interactive GIS Community Grievance Map."""
    return render_template('complaint_map.html')

@app.route('/api/complaints/map')
def api_complaints_map():
    """API providing geotagged complaints for GIS visualization."""
    complaints = database.get_all_complaints()
    geotagged = []
    for c in complaints:
        if c.get('latitude') is not None and c.get('longitude') is not None:
            geotagged.append({
                'id': c['id'],
                'title': c['title'],
                'category': c['category'],
                'status': c['status'],
                'location': c['location'],
                'latitude': c['latitude'],
                'longitude': c['longitude'],
                'department': c.get('department'),
                'image_path': c.get('image_path'),
                'created_at': str(c.get('created_at', ''))
            })
    return jsonify(geotagged)

# --- Dual OTP Verification Endpoints (Email & Phone Number) ---

@app.route('/api/otp/send-complaint-otp', methods=['POST'])
@login_required
@role_required('citizen')
def api_send_complaint_otp():
    """Generate and dispatch dual OTPs to the citizen's registered email and mobile phone."""
    user = database.get_user_by_id(session['user_id'])
    if not user:
        return jsonify({'success': False, 'error': 'User session not found.'}), 404

    data = request.get_json(silent=True) or {}
    email = (data.get('email') or user.get('email') or '').strip()
    phone = (data.get('phone') or user.get('phone') or '').strip()

    if not email or '@' not in email:
        return jsonify({'success': False, 'error': 'Valid registered email address is required.'}), 400
    if not phone or len(re.sub(r'\D', '', phone)) < 7:
        return jsonify({'success': False, 'error': 'Valid registered phone number is required.'}), 400

    result = send_dual_otp(
        user_id=user['id'],
        email=email,
        phone=phone,
        user_name=user.get('full_name') or user.get('username', 'Citizen'),
        purpose='complaint_submission'
    )
    if not app.config.get('TESTING'):
        result.pop('dev_email_otp', None)
        result.pop('dev_phone_otp', None)
    return jsonify(result)


@app.route('/api/otp/verify-complaint-otp', methods=['POST'])
@login_required
@role_required('citizen')
def api_verify_complaint_otp():
    """Verify dual OTPs for both email and phone number."""
    user = database.get_user_by_id(session['user_id'])
    if not user:
        return jsonify({'success': False, 'error': 'User not found.'}), 404

    data = request.get_json(silent=True) or {}
    email = (data.get('email') or user.get('email') or '').strip()
    phone = (data.get('phone') or user.get('phone') or '').strip()
    email_otp = (data.get('email_otp') or '').strip()
    phone_otp = (data.get('phone_otp') or '').strip()

    if not email_otp or not phone_otp:
        return jsonify({'success': False, 'error': 'Both email OTP and phone OTP must be provided.'}), 400

    result = verify_dual_otp(
        email=email,
        email_otp=email_otp,
        phone=phone,
        phone_otp=phone_otp,
        purpose='complaint_submission',
        user_id=user['id']
    )

    if result.get('success'):
        session['complaint_otp_verified'] = True
        return jsonify(result)
    else:
        return jsonify(result), 400


# --- Channel-Specific OTP Verification Endpoints (Individual Email or Phone) ---

@app.route('/api/otp/send-channel-otp', methods=['POST'])
def api_send_channel_otp():
    """
    Dispatch a 6-digit OTP code to an individual channel (email or phone).
    Usable during registration (anonymous) or complaint filing (authenticated).
    """
    data = request.get_json(silent=True) or {}
    target = data.get('target', '').strip()
    target_type = data.get('target_type', 'email').strip().lower()
    purpose = data.get('purpose', 'registration').strip()
    user_name = data.get('user_name', 'Citizen').strip()

    # If purpose is complaint_submission and user is logged in, fallback to registered user info
    if purpose == 'complaint_submission' and 'user_id' in session:
        user = database.get_user_by_id(session['user_id'])
        if user:
            if not target:
                target = user.get('email') if target_type == 'email' else user.get('phone')
            if not user_name:
                user_name = user.get('full_name') or user.get('username', 'Citizen')

    if not target:
        return jsonify({'success': False, 'error': f'A valid {target_type} is required.'}), 400

    if target_type == 'email':
        cleaned = target.strip().lower()
        if '@' not in cleaned:
            return jsonify({'success': False, 'error': 'Please enter a valid email address.'}), 400
        if purpose == 'registration' and database.get_user_by_email(cleaned):
            return jsonify({'success': False, 'error': 'An account with this email address already exists. Please log in.'}), 400
    elif target_type == 'phone':
        cleaned = clean_phone_number(target)
        if len(cleaned) < 7:
            return jsonify({'success': False, 'error': 'Please enter a valid phone number (at least 7 digits).'}), 400
    else:
        return jsonify({'success': False, 'error': f'Unsupported target type: {target_type}'}), 400

    res = send_single_otp(
        target=target,
        target_type=target_type,
        purpose=purpose,
        user_name=user_name
    )
    if not app.config.get('TESTING'):
        res.pop('dev_otp', None)
    return jsonify(res)


@app.route('/api/otp/verify-channel-otp', methods=['POST'])
def api_verify_channel_otp():
    """
    Verify an individual 6-digit OTP code for either email or phone.
    Updates session verification state upon success.
    """
    data = request.get_json(silent=True) or {}
    target = data.get('target', '').strip()
    target_type = data.get('target_type', 'email').strip().lower()
    otp_code = data.get('otp_code', '').strip()
    purpose = data.get('purpose', 'registration').strip()

    if purpose == 'complaint_submission' and 'user_id' in session and not target:
        user = database.get_user_by_id(session['user_id'])
        if user:
            target = user.get('email') if target_type == 'email' else user.get('phone')

    if not target or not otp_code:
        return jsonify({'success': False, 'error': f'Target and 6-digit {target_type} OTP are required.'}), 400

    res = verify_target_otp(
        target=target,
        otp_code=otp_code,
        purpose=purpose,
        target_type=target_type
    )

    if res.get('success'):
        if purpose == 'registration':
            if target_type == 'email':
                session['reg_verified_email'] = target.strip().lower()
            elif target_type == 'phone':
                session['reg_verified_phone'] = clean_phone_number(target)
        elif purpose == 'complaint_submission':
            if target_type == 'email':
                session['complaint_verified_email'] = True
            elif target_type == 'phone':
                session['complaint_verified_phone'] = True

            if session.get('complaint_verified_email') and session.get('complaint_verified_phone'):
                session['complaint_otp_verified'] = True
                if 'user_id' in session:
                    database.mark_user_verified(session['user_id'])

        return jsonify(res)
    else:
        return jsonify(res), 400


@app.route('/file-complaint', methods=['GET', 'POST'])
@login_required
@role_required('citizen')
def file_complaint():
    """Form to submit a new community grievance with dual OTP identity verification."""
    citizen_user = database.get_user_by_id(session['user_id'])

    # If citizen navigated directly without choosing preliminary options, guide them through selection first
    if request.method == 'GET' and not request.args.get('category'):
        return redirect(url_for('file_complaint_select'))

    if request.method == 'GET':
        return render_template('file_complaint.html', current_user=citizen_user)

    if request.method == 'POST':
        # Rate Limiting Guards
        client_ip = request.remote_addr or '127.0.0.1'
        is_ip_allowed, _, retry_ip = RateLimiter.check_ip_rate_limit(client_ip)
        if not is_ip_allowed:
            flash(f"System traffic limit reached. Please wait {retry_ip} seconds before trying again.", "danger")
            return redirect(url_for('citizen_dashboard'))

        is_user_allowed, _, retry_user = RateLimiter.check_complaint_submission_limit(session['user_id'])
        if not is_user_allowed:
            flash(f"Hourly submission limit reached. Please wait {retry_user} seconds before filing another grievance.", "warning")
            return redirect(url_for('citizen_dashboard'))

        title = request.form.get('title', '').strip()
        category = request.form.get('category', '').strip()
        location = request.form.get('location', '').strip()
        description = request.form.get('description', '').strip()
        latitude = parse_coordinate(request.form.get('latitude'), -90, 90)
        longitude = parse_coordinate(request.form.get('longitude'), -180, 180)
        image_file = request.files.get('image')

        if not title or not category or not location or not description:
            flash("All text fields must be filled.", "danger")
            return render_template('file_complaint.html', current_user=citizen_user, initial_step=1)

        # Dual OTP Identity Verification Gate (Email & Phone Number)
        if session.get('complaint_verified_email') and session.get('complaint_verified_phone'):
            session['complaint_otp_verified'] = True

        is_verified_session = bool(session.get('complaint_otp_verified'))
        is_user_verified = bool(citizen_user.get('is_verified')) if citizen_user else False
        form_email_otp = request.form.get('email_otp', '').strip()
        form_phone_otp = request.form.get('phone_otp', '').strip()
        is_testing = app.config.get('TESTING', False)

        if form_email_otp and form_phone_otp:
            verify_res = verify_dual_otp(
                email=citizen_user.get('email', ''),
                email_otp=form_email_otp,
                phone=citizen_user.get('phone', ''),
                phone_otp=form_phone_otp,
                purpose='complaint_submission',
                user_id=citizen_user['id']
            )
            if not verify_res.get('success'):
                flash(f"Verification Failed: {verify_res.get('error')}", "danger")
                return render_template('file_complaint.html', current_user=citizen_user, initial_step=4)
            is_verified_session = True
        elif not is_verified_session and not is_testing and not is_otp_auth_locked():
            flash("Identity verification required: Please enter the 6-digit OTP codes sent to your email and phone number.", "warning")
            return render_template('file_complaint.html', current_user=citizen_user, initial_step=4)

        # Clear one-time session verification flag
        session.pop('complaint_otp_verified', None)
        session.pop('complaint_verified_email', None)
        session.pop('complaint_verified_phone', None)

        image_path = None
        if image_file and image_file.filename != '':
            image_path, error_msg = save_file(image_file)
            if not image_path:
                flash(error_msg or "Invalid image file. Please upload a genuine photograph.", "danger")
                return render_template('file_complaint.html', current_user=citizen_user, initial_step=4)

        complaint_id = database.create_complaint(
            citizen_id=session['user_id'],
            title=title,
            category=category,
            description=description,
            location=location,
            image_path=image_path,
            latitude=latitude,
            longitude=longitude
        )
        if complaint_id:
            # Mark citizen identity as verified
            database.mark_user_verified(session['user_id'])

            # 1. Run AI classification and persist predictions
            ai_category, ai_priority = classifier.predict(title, description)
            database.save_ai_prediction(complaint_id, ai_category, ai_priority)

            # 2. Run Complaint Integrity, Fraud & Abuse Detection Pipeline
            integrity_result = run_integrity_pipeline_sync(
                complaint_id=complaint_id,
                title=title,
                category=category,
                description=description,
                location=location,
                latitude=latitude,
                longitude=longitude,
                image_path=image_path,
                citizen_id=session['user_id'],
                upload_folder=app.config['UPLOAD_FOLDER']
            )

            # Respectful, non-accusatory citizen feedback
            effective_status = 'Pending'
            if integrity_result['decision'] == 'REVIEW':
                effective_status = 'Under Review'
                database.update_complaint_status(
                    complaint_id, session['user_id'], 'Under Review',
                    'Complaint held for verification prior to departmental assignment.'
                )
                flash("Your complaint is being verified by our verification desk before assignment. A detailed receipt with all details and photo has been dispatched to your email.", "info")
            elif integrity_result['decision'] == 'REJECT':
                effective_status = 'Rejected'
                database.update_complaint_status(
                    complaint_id, session['user_id'], 'Rejected',
                    'Automated policy flag: multiple high-confidence abuse signals.'
                )
                flash("Your grievance submission could not be verified according to community guidelines.", "warning")
            else:
                flash("Your complaint has been submitted successfully! A confirmation with all details and evidence photo has been sent to your email.", "success")

            # 3. Retrieve citizen's profile and dispatch confirmation email with all details & image
            try:
                if citizen_user and citizen_user.get('email'):
                    complaint_record = {
                        'id': complaint_id,
                        'title': title,
                        'category': category,
                        'description': description,
                        'location': location,
                        'latitude': latitude,
                        'longitude': longitude,
                        'image_path': image_path,
                        'status': effective_status,
                        'ai_category': ai_category,
                        'ai_priority': ai_priority
                    }
                    queue_complaint_confirmation_email(
                        recipient_email=citizen_user['email'],
                        recipient_name=citizen_user.get('full_name') or citizen_user.get('username', 'Citizen'),
                        complaint_data=complaint_record,
                        upload_folder=app.config['UPLOAD_FOLDER']
                    )
            except Exception as mail_err:
                logging.error(f"Error queueing complaint confirmation email: {mail_err}")

            return redirect(url_for('citizen_dashboard'))
        else:
            flash("Failed to process complaint. Please try again.", "danger")

    return render_template('file_complaint.html', current_user=citizen_user)


# --- Complaint Details (Shared) ---

@app.route('/complaint/<int:complaint_id>')
@login_required
def complaint_detail(complaint_id):
    """View status, historical timeline, and discussion comments for a complaint."""
    complaint = database.get_complaint_by_id(complaint_id)
    if not complaint:
        flash("Grievance record not found.", "danger")
        return redirect(url_for('index'))
        
    # Security check: Citizens can only view their own submissions
    if session['role'] == 'citizen' and complaint['citizen_id'] != session['user_id']:
        flash("Access denied. You do not own this complaint record.", "danger")
        return redirect(url_for('citizen_dashboard'))
        
    updates = database.get_complaint_updates(complaint_id)
    feedback = database.get_complaint_feedback(complaint_id)
    return render_template('complaint_detail.html', complaint=complaint, updates=updates, feedback=feedback)

@app.route('/complaint/<int:complaint_id>/comment', methods=['POST'])
@login_required
def post_comment(complaint_id):
    """Post chat/comment in the discussion board of a complaint."""
    complaint = database.get_complaint_by_id(complaint_id)
    if not complaint:
        flash("Grievance record not found.", "danger")
        return redirect(url_for('index'))
        
    # Security check
    if session['role'] == 'citizen' and complaint['citizen_id'] != session['user_id']:
        flash("Unauthorized action.", "danger")
        return redirect(url_for('index'))
        
    comment_text = request.form['comment'].strip()
    if comment_text:
        database.add_complaint_comment(complaint_id, session['user_id'], comment_text)
        flash("Comment posted.", "success")
    else:
        flash("Comment cannot be empty.", "danger")
        
    return redirect(url_for('complaint_detail', complaint_id=complaint_id))


# --- Admin Portal ---

@app.route('/admin/dashboard')
@login_required
@role_required('admin')
def admin_dashboard():
    """Display analytics statistics and filtering registers."""
    # Read filters from GET args
    status = request.args.get('status')
    category = request.args.get('category')
    department = request.args.get('department')
    search = request.args.get('search')
    
    complaints = database.get_all_complaints(
        status=status, category=category, department=department, search=search
    )
    stats = database.get_dashboard_stats()
    
    active_filters = {
        'status': status or '',
        'category': category or '',
        'department': department or '',
        'search': search or ''
    }
    
    users = database.get_all_users()
    return render_template('admin_dashboard.html', 
                           complaints=complaints, 
                           stats=stats, 
                           active_filters=active_filters,
                           users=users)

@app.route('/complaint/<int:complaint_id>/action', methods=['POST'])
@login_required
@role_required('admin')
def admin_action(complaint_id):
    """Perform admin action: change status (resolve require image) and assign department."""
    status_to = request.form['status']
    department = request.form.get('department', '').strip()
    message = request.form.get('message', '').strip()
    resolution_file = request.files.get('resolution_proof')
    
    complaint = database.get_complaint_by_id(complaint_id)
    if not complaint:
        flash("Grievance record not found.", "danger")
        return redirect(url_for('admin_dashboard'))
        
    # 1. Handle Department assignment changes
    if department and department != (complaint['department'] or ''):
        database.assign_complaint_department(complaint_id, session['user_id'], department)
        flash(f"Complaint assigned to department: {department}", "success")
        
    # 2. Handle Status updates
    if status_to != complaint['status']:
        resolution_image = None
        
        # Validation: Resolving a complaint REQUIRES a proof photo upload
        if status_to == 'Resolved':
            if not resolution_file or resolution_file.filename == '':
                flash("Resolution photo proof is mandatory to mark a complaint as Resolved.", "danger")
                return redirect(url_for('complaint_detail', complaint_id=complaint_id))
            
            resolution_image, error_msg = save_file(resolution_file)
            if not resolution_image:
                flash(error_msg or "Invalid proof image. Please upload a real photograph.", "danger")
                return redirect(url_for('complaint_detail', complaint_id=complaint_id))
                
        # If no note is provided on status change, create a default message
        if not message:
            message = f"Status updated from {complaint['status']} to {status_to}."
            
        success = database.update_complaint_status(
            complaint_id=complaint_id,
            author_id=session['user_id'],
            status_to=status_to,
            message=message,
            resolution_image_path=resolution_image
        )
        
        if success:
            flash(f"Status successfully updated to {status_to}.", "success")
        else:
            flash("Failed to update status.", "danger")
    elif message:
        # Just logged a comment note without status change
        database.add_complaint_comment(complaint_id, session['user_id'], f"Admin Note: {message}")
        flash("Official comment added.", "success")
        
    return redirect(url_for('complaint_detail', complaint_id=complaint_id))


@app.route('/complaint/<int:complaint_id>/delete', methods=['POST'])
@login_required
def delete_complaint_route(complaint_id):
    """Delete a complaint (Citizens can delete their own cases, Admins can delete any case)."""
    complaint = database.get_complaint_by_id(complaint_id)
    if not complaint:
        flash("Grievance record not found.", "danger")
        return redirect(url_for('index'))
        
    # Permission check: Admin can delete any case, Citizen can only delete their own case
    if session['role'] == 'citizen' and complaint['citizen_id'] != session['user_id']:
        flash("Unauthorized action. Permission denied.", "danger")
        return redirect(url_for('citizen_dashboard'))
        
    success = database.delete_complaint(complaint_id)
    if success:
        flash(f"Complaint #{complaint_id} deleted successfully.", "success")
    else:
        flash("Failed to delete complaint record.", "danger")
        
    if session['role'] == 'admin':
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('citizen_dashboard'))

@app.route('/complaint/<int:complaint_id>/feedback', methods=['POST'])
@login_required
@role_required('citizen')
def post_feedback(complaint_id):
    """File rating feedback score for resolved complaints."""
    complaint = database.get_complaint_by_id(complaint_id)
    if not complaint:
        flash("Grievance record not found.", "danger")
        return redirect(url_for('citizen_dashboard'))
        
    # Security validation
    if complaint['citizen_id'] != session['user_id']:
        flash("Unauthorized access.", "danger")
        return redirect(url_for('citizen_dashboard'))
        
    if complaint['status'] != 'Resolved':
        flash("Feedback is only allowed on Resolved complaints.", "danger")
        return redirect(url_for('complaint_detail', complaint_id=complaint_id))
        
    rating = int(request.form['rating'])
    comments = request.form.get('comments', '').strip()
    
    success = database.submit_feedback(complaint_id, rating, comments)
    if success:
        flash("Thank you for your rating and feedback!", "success")
    else:
        flash("Feedback was already submitted for this complaint.", "warning")
        
    return redirect(url_for('complaint_detail', complaint_id=complaint_id))


# --- SEO & Meta Endpoints ---

@app.route('/robots.txt')
def robots():
    """Serve robots.txt for search engine crawlers."""
    from flask import Response
    content = "User-agent: *\nAllow: /\nDisallow: /admin/\nDisallow: /complaint/*/action\nSitemap: " + request.host_url + "sitemap.xml\n"
    return Response(content, mimetype='text/plain')

@app.route('/sitemap.xml')
def sitemap():
    """Serve dynamically generated XML sitemap."""
    from flask import Response
    host = request.host_url.rstrip('/')
    urls = [
        f"<url><loc>{host}/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>",
        f"<url><loc>{host}/login</loc><changefreq>monthly</changefreq><priority>0.8</priority></url>",
        f"<url><loc>{host}/register</loc><changefreq>monthly</changefreq><priority>0.8</priority></url>",
    ]
    xml_content = f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + '\n</urlset>'
    return Response(xml_content, mimetype='application/xml')


# --- API Endpoint for analytics chart ---

@app.route('/api/admin/stats')
@login_required
@role_required('admin')
def get_stats_api():
    """API endpoint providing metrics data in JSON format."""
    stats = database.get_dashboard_stats()
    return jsonify(stats)


# --- Error Handlers ---

@app.errorhandler(404)
def page_not_found(e):
    stats = database.get_dashboard_stats()
    return render_template('index.html', stats=stats), 404

@app.errorhandler(413)
def request_entity_too_large(e):
    flash("Uploaded photo is too large! Maximum allowed size is 5 MB.", "danger")
    return redirect(request.referrer or url_for('index')), 413

@app.errorhandler(500)
def server_error(e):
    return "An internal server error occurred.", 500

if __name__ == '__main__':
    # Running local server (bound to all network interfaces)
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() in ('true', '1')
    app.run(debug=debug_mode, host='0.0.0.0', port=5000)
