from typing import Dict, Any, List, Optional
from .config import IntegrityConfig

class RiskEngine:
    """
    Centralized Multi-Signal Risk Scoring and Decision Engine.
    Aggregates text spam, image duplicate, complaint duplicate, location mismatch,
    behavior, and quality signals into an explainable decision with false-positive safeguards.
    """

    @classmethod
    def evaluate_risk(
        cls,
        spam_result: Dict[str, Any],
        duplicate_complaints: List[Dict[str, Any]],
        duplicate_images: List[Dict[str, Any]],
        behavior_result: Dict[str, Any],
        location_mismatch: bool = False,
        location_distance_meters: Optional[float] = None,
        image_quality_result: Optional[Dict[str, Any]] = None,
        metadata_manipulation: bool = False,
        manipulation_signals: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Calculates cumulative risk score, triggered signals, and decision.
        Returns:
        {
            'risk_score': float,
            'decision': 'ACCEPT' | 'REVIEW' | 'REJECT',
            'signals': [
                { 'type': str, 'score': float, 'weight': float, 'explanation': str }
            ],
            'explanations': [str],
            'pipeline_version': '1.0.0'
        }
        """
        signals = []
        raw_weighted_sum = 0.0

        # 1. Text Spam Signal
        spam_score = spam_result.get('score', 0.0)
        if spam_score >= 60.0:
            signal_score = IntegrityConfig.WEIGHT_SPAM_TEXT
            raw_weighted_sum += signal_score
            # If standalone spam is high, reflect direct elevated risk
            if spam_score >= 70.0:
                raw_weighted_sum = max(raw_weighted_sum, 45.0)
            signals.append({
                "type": "SPAM_TEXT",
                "score": signal_score,
                "weight": IntegrityConfig.WEIGHT_SPAM_TEXT,
                "explanation": f"Spam detection score {spam_score}/100 ({spam_result.get('risk_tier')} Risk). Reasons: {', '.join(spam_result.get('reasons', []))}"
            })
        elif spam_score >= 30.0:
            signal_score = round(IntegrityConfig.WEIGHT_SPAM_TEXT * 0.6, 1)
            raw_weighted_sum += signal_score
            signals.append({
                "type": "SPAM_TEXT",
                "score": signal_score,
                "weight": IntegrityConfig.WEIGHT_SPAM_TEXT,
                "explanation": f"Spam detection score {spam_score}/100 ({spam_result.get('risk_tier')} Risk). Reasons: {', '.join(spam_result.get('reasons', []))}"
            })

        # 2. Duplicate Complaint Signal
        if duplicate_complaints:
            top_dup = duplicate_complaints[0]
            sim = top_dup.get('similarity_score', 0.0)
            signal_score = IntegrityConfig.WEIGHT_DUPLICATE_COMPLAINT
            raw_weighted_sum += signal_score
            dist_txt = f" ({round(top_dup['distance_meters'])}m away)" if top_dup.get('distance_meters') is not None else ""
            signals.append({
                "type": "DUPLICATE_COMPLAINT",
                "score": signal_score,
                "weight": IntegrityConfig.WEIGHT_DUPLICATE_COMPLAINT,
                "explanation": f"Similar complaint #{top_dup.get('complaint_id')} detected{dist_txt}: '{top_dup.get('title')}' ({round(sim*100)}% match). {top_dup.get('reason')}"
            })

        # 3. Duplicate Image Signal
        if duplicate_images:
            top_img = duplicate_images[0]
            sim = top_img.get('similarity_score', 1.0)
            signal_score = IntegrityConfig.WEIGHT_DUPLICATE_IMAGE
            raw_weighted_sum += signal_score
            signals.append({
                "type": "DUPLICATE_IMAGE",
                "score": signal_score,
                "weight": IntegrityConfig.WEIGHT_DUPLICATE_IMAGE,
                "explanation": f"Visual duplicate of photo in complaint #{top_img.get('matched_complaint_id')} via {top_img.get('match_type')} ({round(sim*100)}% visual match)"
            })

            # Check if this user repeatedly reuses evidence across cases
            if any(img.get('is_repeated_evidence') for img in duplicate_images):
                raw_weighted_sum += IntegrityConfig.WEIGHT_REPEATED_EVIDENCE
                signals.append({
                    "type": "REPEATED_EVIDENCE",
                    "score": IntegrityConfig.WEIGHT_REPEATED_EVIDENCE,
                    "weight": IntegrityConfig.WEIGHT_REPEATED_EVIDENCE,
                    "explanation": "Citizen uploaded the identical photograph across different grievance cases"
                })

        # 4. Location Mismatch Signal (EXIF GPS vs Complaint GPS)
        if location_mismatch:
            raw_weighted_sum += IntegrityConfig.WEIGHT_LOCATION_MISMATCH
            dist_km = round(location_distance_meters / 1000.0, 1) if location_distance_meters else "N/A"
            signals.append({
                "type": "LOCATION_MISMATCH",
                "score": IntegrityConfig.WEIGHT_LOCATION_MISMATCH,
                "weight": IntegrityConfig.WEIGHT_LOCATION_MISMATCH,
                "explanation": f"Significant discrepancy ({dist_km} km) between photo EXIF GPS and filed complaint location"
            })

        # 5. User Behaviour Anomaly Signal
        beh_score = behavior_result.get('score', 0.0)
        if beh_score >= 60.0:
            signal_score = IntegrityConfig.WEIGHT_ABNORMAL_FREQUENCY
            raw_weighted_sum += signal_score
            signals.append({
                "type": "ABNORMAL_FREQUENCY",
                "score": signal_score,
                "weight": IntegrityConfig.WEIGHT_ABNORMAL_FREQUENCY,
                "explanation": f"Abnormal submission activity ({round(beh_score)}/100). Reasons: {', '.join(behavior_result.get('reasons', []))}"
            })
        elif beh_score >= 35.0:
            signal_score = round(IntegrityConfig.WEIGHT_ABNORMAL_FREQUENCY * 0.6, 1)
            raw_weighted_sum += signal_score
            signals.append({
                "type": "ABNORMAL_FREQUENCY",
                "score": signal_score,
                "weight": IntegrityConfig.WEIGHT_ABNORMAL_FREQUENCY,
                "explanation": f"Elevated submission activity ({round(beh_score)}/100). Reasons: {', '.join(behavior_result.get('reasons', []))}"
            })

        # 6. Suspicious Metadata & Manipulation Signal
        if metadata_manipulation:
            raw_weighted_sum += IntegrityConfig.WEIGHT_SUSPICIOUS_METADATA
            signals.append({
                "type": "POSSIBLE_MANIPULATION",
                "score": IntegrityConfig.WEIGHT_SUSPICIOUS_METADATA,
                "weight": IntegrityConfig.WEIGHT_SUSPICIOUS_METADATA,
                "explanation": f"Image metadata shows editing software artifacts: {', '.join(manipulation_signals or [])}"
            })

        # 7. Poor Image Quality Signal
        if image_quality_result and not image_quality_result.get('is_usable', True):
            raw_weighted_sum += IntegrityConfig.WEIGHT_POOR_IMAGE_QUALITY
            signals.append({
                "type": "POOR_IMAGE_QUALITY",
                "score": IntegrityConfig.WEIGHT_POOR_IMAGE_QUALITY,
                "weight": IntegrityConfig.WEIGHT_POOR_IMAGE_QUALITY,
                "explanation": f"Image quality warning: {image_quality_result.get('warning')}"
            })

        # Calculate final normalized risk score between 0 and 100
        final_risk_score = round(min(100.0, max(0.0, raw_weighted_sum)), 1)

        # Decision Engine with FALSE-POSITIVE PROTECTION
        # 0–39: ACCEPT
        # 40–69: REVIEW
        # 70–100: REVIEW or REJECT depending on multi-signal corroboration & policy
        if final_risk_score <= IntegrityConfig.DECISION_ACCEPT_MAX:
            decision = "ACCEPT"
        elif final_risk_score <= IntegrityConfig.DECISION_REVIEW_MAX:
            decision = "REVIEW"
        else:
            # Protect against false positives:
            # Never automatically REJECT solely on one AI score or missing EXIF.
            # Only mark REJECT if:
            # 1. AUTO_REJECT_ENABLED is True, AND
            # 2. At least two high-confidence signals are present (e.g. Critical Spam + Rapid submission/Duplicate abuse)
            has_critical_spam = any(s['type'] == 'SPAM_TEXT' and s['score'] >= 20.0 for s in signals)
            has_corroborating_abuse = len([s for s in signals if s['score'] >= 15.0]) >= 2

            if IntegrityConfig.AUTO_REJECT_ENABLED and has_critical_spam and has_corroborating_abuse:
                decision = "REJECT"
            else:
                # Default to human review to protect citizens
                decision = "REVIEW"

        explanations = [s['explanation'] for s in signals]
        if not explanations:
            explanations = ["Normal civic complaint submission. All integrity criteria passed."]

        return {
            "risk_score": final_risk_score,
            "decision": decision,
            "signals": signals,
            "explanations": explanations,
            "pipeline_version": "1.0.0"
        }
