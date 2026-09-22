import os
import io
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
from typing import Dict, Any, Optional

from .config import IntegrityConfig
from .spam_service import SpamService
from .image_fingerprint_service import ImageFingerprintService
from .duplicate_service import DuplicateService
from .behavior_service import BehaviorService
from .risk_engine import RiskEngine
from .repository import IntegrityRepository
import database

# Thread pool for non-blocking asynchronous integrity processing
_executor = ThreadPoolExecutor(max_workers=4)

def run_integrity_pipeline_sync(
    complaint_id: int,
    title: str,
    category: str,
    description: str,
    location: str,
    latitude: Optional[float],
    longitude: Optional[float],
    image_path: Optional[str],
    citizen_id: int,
    upload_folder: str
) -> Dict[str, Any]:
    """
    Executes the full end-to-end integrity pipeline for a complaint.
    Can be run synchronously or submitted to background worker.
    """
    # 1. Text Spam Analysis
    spam_result = SpamService.analyze(title, description)

    # 2. Duplicate Complaint Analysis
    all_complaints = database.get_all_complaints()
    dup_complaints = DuplicateService.check_duplicate_complaint(
        new_title=title,
        new_description=description,
        new_category=category,
        new_lat=latitude,
        new_lng=longitude,
        existing_complaints=all_complaints,
        exclude_id=complaint_id
    )

    # 3. Image Analysis (if photo was attached)
    dup_images = []
    location_mismatch = False
    loc_distance = None
    quality_result = None
    metadata_manipulation = False
    manipulation_signals = []

    if image_path:
        full_image_path = os.path.join(upload_folder, image_path)
        if os.path.exists(full_image_path):
            try:
                with open(full_image_path, 'rb') as f:
                    file_bytes = f.read()

                sha256 = ImageFingerprintService.calculate_sha256(file_bytes)
                img = Image.open(io.BytesIO(file_bytes))
                width, height = img.size
                mime_type = f"image/{img.format.lower()}" if img.format else "image/jpeg"

                # Hashes and visual representations
                ahash = ImageFingerprintService.calculate_ahash(img)
                dhash = ImageFingerprintService.calculate_dhash(img)
                phash = ImageFingerprintService.calculate_phash(img)
                embedding = ImageFingerprintService.generate_visual_embedding(img)

                # Quality evaluation
                quality_result = ImageFingerprintService.evaluate_quality(img)

                # EXIF Metadata analysis
                metadata = ImageFingerprintService.extract_metadata(img)
                metadata_manipulation = metadata.get('is_manipulated', False)
                manipulation_signals = metadata.get('manipulation_signals', [])

                # Compare EXIF GPS with Complaint GPS
                exif_lat = metadata.get('latitude')
                exif_lng = metadata.get('longitude')
                if exif_lat is not None and exif_lng is not None and latitude is not None and longitude is not None:
                    loc_distance = ImageFingerprintService.haversine_distance(latitude, longitude, exif_lat, exif_lng)
                    if loc_distance > IntegrityConfig.LOCATION_MISMATCH_DISTANCE_METERS:
                        location_mismatch = True

                # Check Duplicate Images across database
                all_fps = IntegrityRepository.get_all_image_fingerprints()
                dup_images = DuplicateService.check_duplicate_image(
                    new_sha256=sha256,
                    new_phash=phash,
                    new_dhash=dhash,
                    new_ahash=ahash,
                    new_embedding=embedding,
                    existing_fingerprints=all_fps,
                    current_complaint_id=complaint_id,
                    current_citizen_id=citizen_id
                )

                # Save fingerprint in DB
                fp_id = IntegrityRepository.save_image_fingerprint(
                    complaint_id=complaint_id,
                    image_path=image_path,
                    sha256=sha256,
                    phash=phash,
                    dhash=dhash,
                    ahash=ahash,
                    embedding=embedding,
                    image_width=width,
                    image_height=height,
                    file_size_bytes=len(file_bytes),
                    mime_type=mime_type,
                    exif_meta=metadata,
                    quality_info=quality_result,
                    is_manipulated=metadata_manipulation
                )

                # Save cross-image similarities
                for d_img in dup_images:
                    if fp_id and d_img.get('fingerprint_id'):
                        IntegrityRepository.save_image_similarity(
                            source_id=fp_id,
                            target_id=d_img['fingerprint_id'],
                            score=d_img['similarity_score'],
                            method=d_img['match_type'],
                            is_cross=d_img.get('is_repeated_evidence', False)
                        )

            except Exception as img_err:
                print(f"[Integrity Worker Error processing image]: {img_err}")

    # 4. User Behavior Analysis
    user_profile = IntegrityRepository.get_user_risk_profile(citizen_id)
    user_complaints = database.get_citizen_complaints(citizen_id)
    behavior_result = BehaviorService.evaluate_behavior(
        user_profile=user_profile,
        recent_user_complaints=user_complaints
    )

    # 5. Risk Scoring & Decision Engine
    risk_assessment = RiskEngine.evaluate_risk(
        spam_result=spam_result,
        duplicate_complaints=dup_complaints,
        duplicate_images=dup_images,
        behavior_result=behavior_result,
        location_mismatch=location_mismatch,
        location_distance_meters=loc_distance,
        image_quality_result=quality_result,
        metadata_manipulation=metadata_manipulation,
        manipulation_signals=manipulation_signals
    )

    # 6. Save Assessment and Signals to Database
    IntegrityRepository.save_risk_assessment(
        complaint_id=complaint_id,
        risk_score=risk_assessment['risk_score'],
        decision=risk_assessment['decision'],
        pipeline_version=risk_assessment['pipeline_version'],
        signals=risk_assessment['signals'],
        explanations=risk_assessment['explanations']
    )

    # Save spam detection metrics
    IntegrityRepository.save_spam_result(
        complaint_id=complaint_id,
        spam_score=spam_result['score'],
        risk_tier=spam_result['risk_tier'],
        repeated_char_ratio=spam_result['repeated_char_ratio'],
        entropy_score=spam_result['entropy_score'],
        contains_promo=spam_result['contains_promo_url'],
        reasons=spam_result['reasons']
    )

    # Save complaint similarities
    for d_comp in dup_complaints:
        IntegrityRepository.save_complaint_similarity(
            complaint_id=complaint_id,
            similar_id=d_comp['complaint_id'],
            score=d_comp['similarity_score'],
            distance=d_comp.get('distance_meters'),
            reason=d_comp['reason']
        )

    return risk_assessment

def queue_integrity_analysis(
    complaint_id: int,
    title: str,
    category: str,
    description: str,
    location: str,
    latitude: Optional[float],
    longitude: Optional[float],
    image_path: Optional[str],
    citizen_id: int,
    upload_folder: str
):
    """Submits integrity analysis to background thread pool."""
    _executor.submit(
        run_integrity_pipeline_sync,
        complaint_id,
        title,
        category,
        description,
        location,
        latitude,
        longitude,
        image_path,
        citizen_id,
        upload_folder
    )
