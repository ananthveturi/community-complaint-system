import os

class IntegrityConfig:
    """Centralized, environment-driven configuration for CiviFix Integrity & Fraud Detection."""

    # Decision Thresholds
    DECISION_ACCEPT_MAX = float(os.environ.get('INTEGRITY_DECISION_ACCEPT_MAX', 39.0))
    DECISION_REVIEW_MAX = float(os.environ.get('INTEGRITY_DECISION_REVIEW_MAX', 69.0))
    AUTO_REJECT_ENABLED = os.environ.get('INTEGRITY_AUTO_REJECT_ENABLED', 'false').lower() in ('true', '1', 'yes')

    # Spam Risk Tiers
    SPAM_TIER_LOW_MAX = float(os.environ.get('INTEGRITY_SPAM_LOW_MAX', 29.0))
    SPAM_TIER_MEDIUM_MAX = float(os.environ.get('INTEGRITY_SPAM_MEDIUM_MAX', 59.0))
    SPAM_TIER_HIGH_MAX = float(os.environ.get('INTEGRITY_SPAM_HIGH_MAX', 79.0))

    # Signal Weights (summed in multi-signal risk calculation)
    WEIGHT_SPAM_TEXT = float(os.environ.get('INTEGRITY_WEIGHT_SPAM_TEXT', 25.0))
    WEIGHT_DUPLICATE_COMPLAINT = float(os.environ.get('INTEGRITY_WEIGHT_DUPLICATE_COMPLAINT', 20.0))
    WEIGHT_DUPLICATE_IMAGE = float(os.environ.get('INTEGRITY_WEIGHT_DUPLICATE_IMAGE', 25.0))
    WEIGHT_LOCATION_MISMATCH = float(os.environ.get('INTEGRITY_WEIGHT_LOCATION_MISMATCH', 15.0))
    WEIGHT_REPEATED_EVIDENCE = float(os.environ.get('INTEGRITY_WEIGHT_REPEATED_EVIDENCE', 20.0))
    WEIGHT_ABNORMAL_FREQUENCY = float(os.environ.get('INTEGRITY_WEIGHT_ABNORMAL_FREQUENCY', 20.0))
    WEIGHT_SUSPICIOUS_METADATA = float(os.environ.get('INTEGRITY_WEIGHT_SUSPICIOUS_METADATA', 10.0))
    WEIGHT_POOR_IMAGE_QUALITY = float(os.environ.get('INTEGRITY_WEIGHT_POOR_IMAGE_QUALITY', 5.0))

    # Duplicate Image Detection Thresholds
    # Hamming distance <= 10 on 64-bit perceptual hashes indicates visual similarity
    PHASH_HAMMING_THRESHOLD = int(os.environ.get('INTEGRITY_PHASH_HAMMING_THRESHOLD', 10))
    DHASH_HAMMING_THRESHOLD = int(os.environ.get('INTEGRITY_DHASH_HAMMING_THRESHOLD', 10))
    AHASH_HAMMING_THRESHOLD = int(os.environ.get('INTEGRITY_AHASH_HAMMING_THRESHOLD', 10))
    IMAGE_SIMILARITY_DUPLICATE_THRESHOLD = float(os.environ.get('INTEGRITY_IMAGE_SIM_DUPLICATE', 0.88))
    IMAGE_SIMILARITY_POSSIBLE_THRESHOLD = float(os.environ.get('INTEGRITY_IMAGE_SIM_POSSIBLE', 0.72))

    # Duplicate Complaint Detection Thresholds
    COMPLAINT_TEXT_SIMILARITY_THRESHOLD = float(os.environ.get('INTEGRITY_COMPLAINT_TEXT_SIM', 0.65))
    COMPLAINT_GEO_DISTANCE_METERS = float(os.environ.get('INTEGRITY_COMPLAINT_GEO_DIST_METERS', 500.0))
    LOCATION_MISMATCH_DISTANCE_METERS = float(os.environ.get('INTEGRITY_LOC_MISMATCH_METERS', 5000.0))

    # Rate Limiting Defaults
    RATE_LIMIT_COMPLAINTS_PER_HOUR = int(os.environ.get('INTEGRITY_RL_COMPLAINTS_HOUR', 10))
    RATE_LIMIT_IMAGES_PER_HOUR = int(os.environ.get('INTEGRITY_RL_IMAGES_HOUR', 50))
    RATE_LIMIT_REQUESTS_PER_MINUTE_IP = int(os.environ.get('INTEGRITY_RL_REQ_MIN_IP', 100))

    # Redis Connection
    REDIS_URL = os.environ.get('REDIS_URL', None)

    # Captcha Configuration
    CAPTCHA_RISK_THRESHOLD = float(os.environ.get('INTEGRITY_CAPTCHA_RISK_THRESHOLD', 45.0))
