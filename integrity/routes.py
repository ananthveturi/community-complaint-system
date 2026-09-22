from flask import Blueprint, request, jsonify, render_template, session, redirect, url_for, flash, current_app
from functools import wraps
import database
from .repository import IntegrityRepository
from .spam_service import SpamService
from .duplicate_service import DuplicateService
from .image_fingerprint_service import ImageFingerprintService
from .behavior_service import BehaviorService
from .risk_engine import RiskEngine
from .rate_limiter import RateLimiter
from .captcha_service import CaptchaService

integrity_bp = Blueprint('integrity', __name__)

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            if request.path.startswith('/api/') or request.is_json:
                return jsonify({"error": "Unauthorized. Admin privileges required."}), 403
            flash("Unauthorized access. Admin privileges required.", "danger")
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            if request.path.startswith('/api/') or request.is_json:
                return jsonify({"error": "Authentication required."}), 401
            flash("Please log in to proceed.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


# ==========================================
# 1. Citizen Live Feedback APIs
# ==========================================

@integrity_bp.route('/api/v1/integrity/check-duplicate', methods=['POST'])
@login_required
def check_duplicate_api():
    """
    Live duplicate check during complaint drafting.
    Returns similar complaints nearby without accusing or blocking the citizen.
    """
    data = request.get_json() or {}
    title = data.get('title', '').strip()
    description = data.get('description', '').strip()
    category = data.get('category', '').strip()
    lat = data.get('latitude')
    lng = data.get('longitude')

    if not title and not description:
        return jsonify({"duplicates": []})

    all_complaints = database.get_all_complaints()
    duplicates = DuplicateService.check_duplicate_complaint(
        new_title=title,
        new_description=description,
        new_category=category,
        new_lat=float(lat) if lat is not None and lat != '' else None,
        new_lng=float(lng) if lng is not None and lng != '' else None,
        existing_complaints=all_complaints
    )

    return jsonify({
        "duplicates": duplicates[:3],
        "has_nearby_duplicate": len(duplicates) > 0,
        "message": "Similar complaint found nearby." if duplicates else None
    })

@integrity_bp.route('/api/v1/integrity/check-spam', methods=['POST'])
@login_required
def check_spam_api():
    """Lightweight real-time text analysis."""
    data = request.get_json() or {}
    title = data.get('title', '')
    description = data.get('description', '')
    result = SpamService.analyze(title, description)
    return jsonify(result)


# ==========================================
# 2. REST API Endpoints (Section 17)
# ==========================================

@integrity_bp.route('/api/v1/integrity/analyze-complaint', methods=['POST'])
@login_required
@admin_required
def api_analyze_complaint():
    """Execute on-demand analysis for complaint text and coordinates."""
    data = request.get_json() or {}
    title = data.get('title', '')
    description = data.get('description', '')
    category = data.get('category', '')
    lat = data.get('latitude')
    lng = data.get('longitude')

    spam_res = SpamService.analyze(title, description)
    all_complaints = database.get_all_complaints()
    dup_comps = DuplicateService.check_duplicate_complaint(
        new_title=title,
        new_description=description,
        new_category=category,
        new_lat=float(lat) if lat is not None and lat != '' else None,
        new_lng=float(lng) if lng is not None and lng != '' else None,
        existing_complaints=all_complaints
    )

    risk_eval = RiskEngine.evaluate_risk(
        spam_result=spam_res,
        duplicate_complaints=dup_comps,
        duplicate_images=[],
        behavior_result={"score": 8.0, "reasons": []}
    )

    return jsonify({
        "spam_analysis": spam_res,
        "duplicate_complaints": dup_comps,
        "risk_assessment": risk_eval
    })

@integrity_bp.route('/api/v1/integrity/complaints/<int:complaint_id>', methods=['GET'])
@login_required
@admin_required
def api_get_complaint_integrity(complaint_id):
    """Retrieve full risk assessment and signals for a complaint."""
    assessment = IntegrityRepository.get_risk_assessment(complaint_id)
    if not assessment:
        return jsonify({"error": "No integrity assessment found for this complaint"}), 404
    return jsonify(assessment)

@integrity_bp.route('/api/v1/integrity/reviews', methods=['GET'])
@login_required
@admin_required
def api_get_reviews():
    """Retrieve pending review queue."""
    dash_data = IntegrityRepository.get_integrity_dashboard_data()
    return jsonify(dash_data['reviews_queue'])

@integrity_bp.route('/api/v1/integrity/similar-complaints/<int:complaint_id>', methods=['GET'])
@login_required
@admin_required
def api_get_similar_complaints(complaint_id):
    """Retrieve complaints similar to specified complaint ID."""
    sims = IntegrityRepository.get_complaint_similarities(complaint_id)
    return jsonify(sims)

@integrity_bp.route('/api/v1/integrity/similar-images/<int:complaint_id>', methods=['GET'])
@login_required
@admin_required
def api_get_similar_images(complaint_id):
    """Retrieve image similarities for a complaint."""
    conn = database.get_db()
    try:
        rows = conn.execute('''
            SELECT sim.*, fp2.image_path as matched_image_path, fp2.complaint_id as matched_complaint_id
            FROM image_fingerprints fp1
            JOIN image_similarities sim ON sim.source_image_id = fp1.id
            JOIN image_fingerprints fp2 ON sim.target_image_id = fp2.id
            WHERE fp1.complaint_id = ?
        ''', (complaint_id,)).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()

@integrity_bp.route('/api/v1/integrity/reviews/<int:complaint_id>/approve', methods=['POST'])
@login_required
@admin_required
def api_approve_review(complaint_id):
    """Approve a complaint in review queue."""
    notes = (request.get_json() or {}).get('notes', 'Approved by administrator')
    prior = IntegrityRepository.get_risk_assessment(complaint_id)
    prior_decision = prior.get('decision') if prior else 'REVIEW'

    IntegrityRepository.record_integrity_review(
        complaint_id=complaint_id,
        reviewer_id=session['user_id'],
        action='APPROVE',
        review_notes=notes,
        prior_decision=prior_decision,
        final_decision='ACCEPT'
    )
    return jsonify({"success": True, "message": f"Complaint #{complaint_id} approved and routed for processing."})

@integrity_bp.route('/api/v1/integrity/reviews/<int:complaint_id>/reject', methods=['POST'])
@login_required
@admin_required
def api_reject_review(complaint_id):
    """Reject a fraudulent or invalid complaint."""
    notes = (request.get_json() or {}).get('notes', 'Rejected by administrator')
    prior = IntegrityRepository.get_risk_assessment(complaint_id)
    prior_decision = prior.get('decision') if prior else 'REVIEW'

    IntegrityRepository.record_integrity_review(
        complaint_id=complaint_id,
        reviewer_id=session['user_id'],
        action='REJECT',
        review_notes=notes,
        prior_decision=prior_decision,
        final_decision='REJECT'
    )
    return jsonify({"success": True, "message": f"Complaint #{complaint_id} marked as rejected."})

@integrity_bp.route('/api/v1/integrity/reviews/<int:complaint_id>/mark-duplicate', methods=['POST'])
@login_required
@admin_required
def api_mark_duplicate(complaint_id):
    """Mark complaint as duplicate of an existing case."""
    notes = (request.get_json() or {}).get('notes', 'Marked as duplicate by administrator')
    prior = IntegrityRepository.get_risk_assessment(complaint_id)
    prior_decision = prior.get('decision') if prior else 'REVIEW'

    IntegrityRepository.record_integrity_review(
        complaint_id=complaint_id,
        reviewer_id=session['user_id'],
        action='MARK_DUPLICATE',
        review_notes=notes,
        prior_decision=prior_decision,
        final_decision='REJECT'
    )
    return jsonify({"success": True, "message": f"Complaint #{complaint_id} flagged as duplicate."})

@integrity_bp.route('/api/v1/integrity/users/<int:user_id>/risk', methods=['GET'])
@login_required
@admin_required
def api_get_user_risk(user_id):
    """Retrieve user behavioral risk profile."""
    profile = IntegrityRepository.get_user_risk_profile(user_id)
    return jsonify(profile)


# ==========================================
# 3. Admin UI Dashboard & Review Pages
# ==========================================

@integrity_bp.route('/admin/integrity')
@login_required
@admin_required
def integrity_dashboard():
    """Integrity and Fraud Analytics Dashboard."""
    data = IntegrityRepository.get_integrity_dashboard_data()
    return render_template('integrity_dashboard.html', data=data)

@integrity_bp.route('/admin/integrity/reviews')
@login_required
@admin_required
def integrity_reviews_queue():
    """Human Review Queue List."""
    data = IntegrityRepository.get_integrity_dashboard_data()
    return render_template('integrity_dashboard.html', data=data, view_mode='queue')

@integrity_bp.route('/admin/integrity/review/<int:complaint_id>')
@login_required
@admin_required
def integrity_review_detail(complaint_id):
    """Detailed Review Inspector with side-by-side comparisons."""
    complaint = database.get_complaint_by_id(complaint_id)
    if not complaint:
        flash("Complaint not found.", "danger")
        return redirect(url_for('integrity.integrity_dashboard'))

    assessment = IntegrityRepository.get_risk_assessment(complaint_id)
    similar_complaints = IntegrityRepository.get_complaint_similarities(complaint_id)

    # Get image similarities
    conn = database.get_db()
    similar_images = []
    try:
        rows = conn.execute('''
            SELECT sim.*, fp2.image_path as matched_image_path, fp2.complaint_id as matched_complaint_id,
                   c2.title as matched_title
            FROM image_fingerprints fp1
            JOIN image_similarities sim ON sim.source_image_id = fp1.id
            JOIN image_fingerprints fp2 ON sim.target_image_id = fp2.id
            JOIN complaints c2 ON fp2.complaint_id = c2.id
            WHERE fp1.complaint_id = ?
        ''', (complaint_id,)).fetchall()
        similar_images = [dict(r) for r in rows]
    finally:
        conn.close()

    user_profile = IntegrityRepository.get_user_risk_profile(complaint['citizen_id'])

    return render_template(
        'integrity_review_detail.html',
        complaint=complaint,
        assessment=assessment,
        similar_complaints=similar_complaints,
        similar_images=similar_images,
        user_profile=user_profile
    )

@integrity_bp.route('/admin/integrity/review/<int:complaint_id>/action', methods=['POST'])
@login_required
@admin_required
def integrity_review_action(complaint_id):
    """Process human review actions via HTML form."""
    action = request.form.get('action')
    notes = request.form.get('notes', '').strip()
    prior = IntegrityRepository.get_risk_assessment(complaint_id)
    prior_decision = prior.get('decision') if prior else 'REVIEW'

    if action == 'APPROVE':
        final_dec = 'ACCEPT'
        IntegrityRepository.record_integrity_review(complaint_id, session['user_id'], 'APPROVE', notes, prior_decision, final_dec)
        database.add_complaint_comment(complaint_id, session['user_id'], f"Integrity Review: Approved by administrator. {notes}")
        flash(f"Complaint #{complaint_id} approved for department triage.", "success")
    elif action == 'REJECT':
        final_dec = 'REJECT'
        IntegrityRepository.record_integrity_review(complaint_id, session['user_id'], 'REJECT', notes, prior_decision, final_dec)
        database.add_complaint_comment(complaint_id, session['user_id'], f"Integrity Review: Rejected by administrator. {notes}")
        flash(f"Complaint #{complaint_id} rejected.", "warning")
    elif action == 'MARK_DUPLICATE':
        final_dec = 'REJECT'
        IntegrityRepository.record_integrity_review(complaint_id, session['user_id'], 'MARK_DUPLICATE', notes, prior_decision, final_dec)
        database.add_complaint_comment(complaint_id, session['user_id'], f"Integrity Review: Flagged as duplicate. {notes}")
        flash(f"Complaint #{complaint_id} marked as duplicate.", "info")
    elif action == 'REQUEST_MORE_INFO':
        database.add_complaint_comment(complaint_id, session['user_id'], f"Officer Note: Please provide clearer photographs or more specific landmark details. {notes}")
        flash(f"Information request logged on complaint #{complaint_id}.", "info")
    elif action == 'SUSPEND':
        IntegrityRepository.record_integrity_review(complaint_id, session['user_id'], 'SUSPEND', notes, prior_decision, 'REVIEW')
        flash(f"Complaint #{complaint_id} suspended pending further investigation.", "warning")
    elif action == 'RESTORE':
        IntegrityRepository.record_integrity_review(complaint_id, session['user_id'], 'RESTORE', notes, prior_decision, 'ACCEPT')
        flash(f"Complaint #{complaint_id} restored to active workflow.", "success")

    return redirect(url_for('integrity.integrity_dashboard'))
