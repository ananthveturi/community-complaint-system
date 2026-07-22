from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import uuid
import database
import classifier
from translations import TRANSLATIONS

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-fallback-change-me-in-production')

# Configuration
UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads'))
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # Max 5MB file upload limit
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

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
    """Save upload to static/uploads/ with an obfuscated unique filename."""
    if not file or file.filename == '':
        return None
    if allowed_file(file.filename):
        filename = secure_filename(file.filename)
        # Prefix with unique UUID to avoid file collisions
        unique_name = f"{uuid.uuid4().hex}_{filename}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_name))
        return unique_name
    return None

@app.context_processor
def utility_processor():
    def translate(key):
        lang = session.get('lang', 'en')
        lang_dict = TRANSLATIONS.get(lang, TRANSLATIONS['en'])
        return lang_dict.get(key, TRANSLATIONS['en'].get(key, key))
    return dict(_=translate)

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
    """Citizen Registration portal."""
    if 'user_id' in session:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form['username'].strip()
        full_name = request.form['full_name'].strip()
        email = request.form['email'].strip()
        phone = request.form.get('phone', '').strip()
        password = request.form['password']
        
        if not username or not full_name or not email or not password:
            flash("All fields are required.", "danger")
            return render_template('register.html')
            
        password_hash = generate_password_hash(password)
        
        user_id = database.create_user(username, password_hash, full_name, email, phone, role='citizen')
        if user_id:
            flash("Account registered successfully! Please log in.", "success")
            return redirect(url_for('login'))
        else:
            flash("Username already exists. Please choose a different one.", "danger")
            
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Unified user Login page."""
    if 'user_id' in session:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        
        user = database.get_user_by_username(username)
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['full_name'] = user['full_name']
            session['role'] = user['role']
            
            flash(f"Welcome back, {user['full_name']}!", "success")
            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('citizen_dashboard'))
        else:
            flash("Invalid username or password.", "danger")
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Log out active session."""
    session.clear()
    flash("You have logged out successfully.", "info")
    return redirect(url_for('index'))


# --- Citizen Portal ---

@app.route('/dashboard')
@login_required
@role_required('citizen')
def citizen_dashboard():
    """Display logged in citizen's dashboard with submitted complaints."""
    complaints = database.get_citizen_complaints(session['user_id'])
    return render_template('citizen_dashboard.html', complaints=complaints)

@app.route('/file-complaint', methods=['GET', 'POST'])
@login_required
@role_required('citizen')
def file_complaint():
    """Form to submit a new community grievance."""
    if request.method == 'POST':
        title = request.form['title'].strip()
        category = request.form['category']
        location = request.form['location'].strip()
        description = request.form['description'].strip()
        latitude = parse_coordinate(request.form.get('latitude'), -90, 90)
        longitude = parse_coordinate(request.form.get('longitude'), -180, 180)
        image_file = request.files.get('image')
        
        if not title or not category or not location or not description:
            flash("All text fields must be filled.", "danger")
            return render_template('file_complaint.html')
            
        image_path = None
        if image_file and image_file.filename != '':
            image_path = save_file(image_file)
            if not image_path:
                flash("Invalid image type. Permitted: png, jpg, jpeg, gif.", "danger")
                return render_template('file_complaint.html')
                
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
            # Run AI classification and persist predictions
            ai_category, ai_priority = classifier.predict(title, description)
            database.save_ai_prediction(complaint_id, ai_category, ai_priority)
            flash("Your complaint has been submitted successfully!", "success")
            return redirect(url_for('citizen_dashboard'))
        else:
            flash("Failed to process complaint. Please try again.", "danger")
            
    return render_template('file_complaint.html')


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
            
            resolution_image = save_file(resolution_file)
            if not resolution_image:
                flash("Invalid proof image type. Permitted: png, jpg, jpeg, gif.", "danger")
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

@app.errorhandler(500)
def server_error(e):
    return "An internal server error occurred.", 500

if __name__ == '__main__':
    # Running local server (bound to all network interfaces)
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() in ('true', '1')
    app.run(debug=debug_mode, host='0.0.0.0', port=5000)
