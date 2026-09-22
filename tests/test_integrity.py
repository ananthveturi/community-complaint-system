import io
import os
import pytest
from PIL import Image
import numpy as np

from integrity.config import IntegrityConfig
from integrity.spam_service import SpamService
from integrity.image_fingerprint_service import ImageFingerprintService
from integrity.duplicate_service import DuplicateService
from integrity.behavior_service import BehaviorService
from integrity.risk_engine import RiskEngine
from integrity.rate_limiter import RateLimiter
from integrity.captcha_service import CaptchaService
from integrity.repository import IntegrityRepository
import database
from app import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret-key'
    with app.test_client() as client:
        yield client

def create_sample_image(color=(120, 150, 180), size=(200, 200), format='JPEG'):
    """Helper to generate a memory buffer containing a real PIL image."""
    img = Image.new('RGB', size, color=color)
    # Draw some varied pixels so it's not totally blank
    arr = np.array(img)
    arr[20:60, 20:60] = [255, 0, 0]
    arr[70:120, 70:120] = [0, 255, 0]
    arr[130:180, 130:180] = [0, 0, 255]
    real_img = Image.fromarray(arr)

    buf = io.BytesIO()
    real_img.save(buf, format=format)
    buf.seek(0)
    return real_img, buf.getvalue()


# ==========================================
# 1. Duplicate Image Tests
# ==========================================

def test_exact_duplicate_image():
    """Verify cryptographic SHA-256 exact duplicate detection."""
    _, bytes1 = create_sample_image()
    bytes2 = bytes1  # exact duplicate
    hash1 = ImageFingerprintService.calculate_sha256(bytes1)
    hash2 = ImageFingerprintService.calculate_sha256(bytes2)
    assert hash1 == hash2

def test_perceptual_duplicate_image():
    """Verify pHash, dHash, and aHash detect resized and slightly modified copies."""
    img1, _ = create_sample_image(size=(300, 300))
    # Create resized and compressed version
    img2 = img1.resize((150, 150))

    phash1 = ImageFingerprintService.calculate_phash(img1)
    phash2 = ImageFingerprintService.calculate_phash(img2)
    dist_p = ImageFingerprintService.hamming_distance(phash1, phash2)

    dhash1 = ImageFingerprintService.calculate_dhash(img1)
    dhash2 = ImageFingerprintService.calculate_dhash(img2)
    dist_d = ImageFingerprintService.hamming_distance(dhash1, dhash2)

    # Perceptual distance between original and resized version should be very low (<= 8)
    assert dist_p <= IntegrityConfig.PHASH_HAMMING_THRESHOLD
    assert dist_d <= IntegrityConfig.DHASH_HAMMING_THRESHOLD

def test_different_image():
    """Verify completely different images have high Hamming distance."""
    # Pattern 1: Red blocks
    img1 = Image.new('RGB', (200, 200), color=(255, 255, 255))
    arr1 = np.array(img1)
    arr1[10:190, 10:190] = [255, 0, 0]
    img1 = Image.fromarray(arr1)

    # Pattern 2: Diagonal gradient
    arr2 = np.zeros((200, 200, 3), dtype=np.uint8)
    for i in range(200):
        for j in range(200):
            arr2[i, j] = [(i * 2) % 255, (j * 2) % 255, 128]
    img2 = Image.fromarray(arr2)

    phash1 = ImageFingerprintService.calculate_phash(img1)
    phash2 = ImageFingerprintService.calculate_phash(img2)
    dist = ImageFingerprintService.hamming_distance(phash1, phash2)

    # Different images should have substantial Hamming distance
    assert dist > IntegrityConfig.PHASH_HAMMING_THRESHOLD


# ==========================================
# 2. Text Spam Detection Tests
# ==========================================

def test_spam_detection_repeated_chars():
    res = SpamService.analyze("Issue", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    assert res['score'] >= 40.0
    assert any("repetition" in r.lower() for r in res['reasons'])

def test_spam_detection_repeated_words():
    res = SpamService.analyze("Problem", "test test test test test test test test")
    assert res['score'] >= 35.0
    assert any("repetition" in r.lower() for r in res['reasons'])

def test_spam_detection_gibberish():
    res = SpamService.analyze("Notice", "asdfghjkl zxcvbnm qwertyuiop")
    assert res['score'] >= 30.0
    assert any("mashing" in r.lower() or "gibberish" in r.lower() for r in res['reasons'])

def test_spam_detection_promotional_url():
    res = SpamService.analyze("Great Opportunity", "CLICK HERE BUY NOW http://free-crypto-giveaway.xyz")
    assert res['score'] >= 60.0
    assert res['contains_promo_url'] is True
    assert res['risk_tier'] in ("High", "Critical")

def test_legitimate_short_complaint_false_positive_protection():
    """Verify legitimate short complaints are NOT falsely marked as spam."""
    res = SpamService.analyze("Broken Pothole", "Large pothole on 5th avenue near bus stop.")
    assert res['score'] <= IntegrityConfig.SPAM_TIER_LOW_MAX
    assert res['risk_tier'] == "Low"


# ==========================================
# 3. Duplicate Complaint Detection Tests
# ==========================================

def test_duplicate_complaint_text():
    existing = [{
        "id": 101,
        "title": "Deep pothole near central bus station",
        "description": "Large hole causing danger to cars near the main bus depot.",
        "category": "Roads & Traffic",
        "latitude": 28.6139,
        "longitude": 77.2090,
        "status": "In Progress"
    }]

    # Semantically close complaint nearby
    dups = DuplicateService.check_duplicate_complaint(
        new_title="Huge pothole near bus station",
        new_description="Deep hole dangerous to vehicles beside the central bus depot.",
        new_category="Roads & Traffic",
        new_lat=28.6140,  # ~15 meters away
        new_lng=77.2091,
        existing_complaints=existing
    )
    assert len(dups) >= 1
    assert dups[0]['complaint_id'] == 101
    assert dups[0]['distance_meters'] < 200.0
    assert dups[0]['similarity_score'] >= 0.40

def test_nearby_duplicate_complaints():
    existing = [{
        "id": 202,
        "title": "Streetlight broken at 4th cross",
        "description": "Dark stretch at night.",
        "category": "Electricity & Power",
        "latitude": 40.7306,
        "longitude": -73.9352,
        "status": "Pending"
    }]

    # Same location, similar text
    dups = DuplicateService.check_duplicate_complaint(
        new_title="Streetlight out at 4th cross",
        new_description="Street light completely dark at night.",
        new_category="Electricity & Power",
        new_lat=40.7307,
        new_lng=-73.9353,
        existing_complaints=existing
    )
    assert len(dups) == 1
    assert dups[0]['complaint_id'] == 202


# ==========================================
# 4. Repeated Evidence Across Complaints
# ==========================================

def test_repeated_evidence_abuse():
    all_fps = [{
        "id": 5,
        "complaint_id": 1001,
        "citizen_id": 42,
        "sha256": "abc1234567890",
        "phash": "1122334455667788",
        "dhash": "1122334455667788",
        "ahash": "1122334455667788",
        "embedding_reference": None
    }]

    matched = DuplicateService.check_duplicate_image(
        new_sha256="abc1234567890",
        new_phash="1122334455667788",
        new_dhash="1122334455667788",
        new_ahash="1122334455667788",
        new_embedding=None,
        existing_fingerprints=all_fps,
        current_complaint_id=1050,
        current_citizen_id=42
    )
    assert len(matched) == 1
    assert matched[0]['is_repeated_evidence'] is True


# ==========================================
# 5. Image Quality & Security Validation
# ==========================================

def test_image_quality_detection_blank():
    blank = Image.new('RGB', (200, 200), color=(255, 255, 255))
    quality = ImageFingerprintService.evaluate_quality(blank)
    assert "blank" in quality['warning'].lower()

def test_image_quality_detection_dark():
    dark = Image.new('RGB', (200, 200), color=(5, 5, 5))
    quality = ImageFingerprintService.evaluate_quality(dark)
    assert "dark" in quality['warning'].lower()

def test_security_file_validation_valid():
    _, bytes_data = create_sample_image()
    stream = io.BytesIO(bytes_data)
    is_valid, mime, err = ImageFingerprintService.validate_image_security(stream, "photo.jpg")
    assert is_valid is True
    assert mime == 'image/jpeg'
    assert err is None

def test_security_file_validation_fake_extension():
    """File claiming to be .jpg but containing plain text or malware bytes."""
    fake_stream = io.BytesIO(b"MZ\x90\x00\x03\x00\x00\x00not an image binary payload")
    is_valid, mime, err = ImageFingerprintService.validate_image_security(fake_stream, "malware.jpg")
    assert is_valid is False
    assert "magic bytes" in err.lower() or "validation failed" in err.lower()

def test_security_file_validation_oversized():
    oversized_stream = io.BytesIO(b"X" * (6 * 1024 * 1024))
    is_valid, mime, err = ImageFingerprintService.validate_image_security(oversized_stream, "huge.jpg")
    assert is_valid is False
    assert "exceeds" in err.lower()


# ==========================================
# 6. Rate Limiting & CAPTCHA Tests
# ==========================================

def test_rate_limiting_sliding_window():
    key = "test_user_rate_limit"
    # Allow 3 requests in 10-second window
    assert RateLimiter.check_limit(key, 3, 10)[0] is True
    assert RateLimiter.check_limit(key, 3, 10)[0] is True
    assert RateLimiter.check_limit(key, 3, 10)[0] is True
    # 4th request must be rejected
    is_allowed, remaining, retry = RateLimiter.check_limit(key, 3, 10)
    assert is_allowed is False
    assert remaining == 0
    assert retry > 0

def test_captcha_challenge_generation_and_verification():
    ch = CaptchaService.generate_challenge()
    assert "Security Verification" in ch['question']
    token = ch['token']
    parts = token.split(':')
    correct_answer = parts[0]

    # Correct answer passes
    assert CaptchaService.verify_challenge(correct_answer, token) is True
    # Incorrect answer fails
    assert CaptchaService.verify_challenge("9999", token) is False
    # Corrupted token fails
    assert CaptchaService.verify_challenge(correct_answer, "tampered:123:456") is False


# ==========================================
# 7. Decision Engine & False-Positive Safeguards
# ==========================================

def test_decision_engine_accept():
    spam = {"score": 5.0, "risk_tier": "Low", "reasons": []}
    beh = {"score": 8.0, "reasons": []}
    res = RiskEngine.evaluate_risk(spam_result=spam, duplicate_complaints=[], duplicate_images=[], behavior_result=beh)
    assert res['decision'] == "ACCEPT"
    assert res['risk_score'] < 40.0

def test_decision_engine_review():
    spam = {"score": 60.0, "risk_tier": "High", "reasons": ["Promo keywords"]}
    dups = [{"complaint_id": 99, "similarity_score": 0.85, "reason": "Nearby duplicate"}]
    beh = {"score": 20.0, "reasons": []}
    res = RiskEngine.evaluate_risk(spam_result=spam, duplicate_complaints=dups, duplicate_images=[], behavior_result=beh)
    assert res['decision'] == "REVIEW"
    assert res['risk_score'] >= 40.0

def test_decision_engine_false_positive_guard():
    """Even if an AI score is slightly elevated, missing EXIF or single score never forces REJECT."""
    spam = {"score": 75.0, "risk_tier": "High", "reasons": ["Unusual caps"]}
    beh = {"score": 10.0, "reasons": []}
    # No image duplicate, no corroborating abuse
    res = RiskEngine.evaluate_risk(spam_result=spam, duplicate_complaints=[], duplicate_images=[], behavior_result=beh)
    # Must escalate to REVIEW for human inspection rather than permanent automatic punishment
    assert res['decision'] == "REVIEW"


# ==========================================
# 8. Routes & RBAC Integration Tests
# ==========================================

def test_complaint_map_route(client):
    res = client.get('/complaint-map')
    # Unauthenticated redirects to login
    assert res.status_code == 302
    assert '/login' in res.location

def test_api_complaints_map_public_json(client):
    res = client.get('/api/complaints/map')
    assert res.status_code == 200
    data = res.get_json()
    assert isinstance(data, list)

def test_file_complaint_select_route(client):
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = 'citizen'
        sess['username'] = 'citizen1'
        sess['full_name'] = 'Test Citizen'

    res = client.get('/file-complaint/select')
    assert res.status_code == 200
    assert b'What civic issue are you experiencing?' in res.data
    assert b'Roads &amp; Traffic' in res.data or b'Roads & Traffic' in res.data

def test_file_complaint_redirects_to_select_if_no_category(client):
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = 'citizen'
        sess['username'] = 'citizen1'
        sess['full_name'] = 'Test Citizen'

    res = client.get('/file-complaint')
    assert res.status_code == 302
    assert '/file-complaint/select' in res.location

def test_integrity_api_unauthorized_for_citizen(client):
    with client.session_transaction() as sess:
        sess['user_id'] = 2
        sess['role'] = 'citizen'
        sess['username'] = 'citizen2'

    res = client.get('/api/v1/integrity/reviews')
    assert res.status_code in (401, 403)

def test_integrity_api_authorized_for_admin(client):
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = 'admin'
        sess['username'] = 'admin'

    res = client.get('/api/v1/integrity/reviews')
    assert res.status_code == 200
    assert isinstance(res.get_json(), list)
