from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from .config import IntegrityConfig

class BehaviorService:
    """Evaluates citizen submission velocity, historical rejections, and behavioral anomalies."""

    @classmethod
    def evaluate_behavior(
        cls,
        user_profile: Optional[Dict[str, Any]],
        recent_user_complaints: List[Dict[str, Any]],
        current_submission_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Calculates a non-punitive behavioral risk score based on submission telemetry.
        Returns: { 'score': float, 'reasons': list, 'captcha_required': bool }
        """
        now = current_submission_time or datetime.utcnow()
        score = 0.0
        reasons = []

        if not user_profile:
            # New or unprofiled user -> default baseline low risk (8.0)
            return {
                "score": 8.0,
                "reasons": ["Standard new profile baseline"],
                "captcha_required": False
            }

        one_hour_ago = now - timedelta(hours=1)
        one_day_ago = now - timedelta(days=1)

        # 1. Frequency in past hour
        recent_hour = 0
        recent_day = 0
        last_time = None

        for comp in recent_user_complaints:
            # Parse created_at
            created_str = comp.get('created_at')
            if created_str:
                try:
                    # SQLite default format: YYYY-MM-DD HH:MM:SS
                    c_time = datetime.strptime(str(created_str)[:19], "%Y-%m-%d %H:%M:%S")
                    if c_time > one_hour_ago:
                        recent_hour += 1
                    if c_time > one_day_ago:
                        recent_day += 1
                    if last_time is None or c_time > last_time:
                        last_time = c_time
                except Exception:
                    pass

        # Check submission bursts
        if recent_hour >= 10:
            score += 35.0
            reasons.append(f"High hourly submission rate ({recent_hour} cases in past hour)")
        elif recent_hour >= 5:
            score += 15.0
            reasons.append(f"Elevated submission activity ({recent_hour} cases in past hour)")

        # Rapid succession check (< 15 seconds since previous submission)
        if last_time:
            delta_seconds = (now - last_time).total_seconds()
            if delta_seconds < 15 and delta_seconds >= 0:
                score += 30.0
                reasons.append(f"Extremely rapid automated-like submission ({round(delta_seconds)}s after prior case)")
            elif delta_seconds < 60 and delta_seconds >= 0:
                score += 15.0
                reasons.append("Submissions in quick succession (< 1 min)")

        # 2. Historical rejection and spam history
        rejected_count = user_profile.get('rejected_count', 0)
        spam_count = user_profile.get('spam_count', 0)
        total_count = user_profile.get('complaint_count_total', 0)

        if total_count >= 5:
            reject_ratio = (rejected_count + spam_count) / max(1, total_count)
            if reject_ratio >= 0.50:
                score += 30.0
                reasons.append(f"High historical complaint rejection/spam ratio ({round(reject_ratio*100)}%)")
            elif reject_ratio >= 0.30:
                score += 15.0
                reasons.append("Noticeable historical rejection rate")

        # 3. Repeat identical coordinates clustering
        if len(recent_user_complaints) >= 4:
            locs = [c.get('location') for c in recent_user_complaints if c.get('location')]
            if locs:
                most_freq_loc_count = max(locs.count(loc_item) for loc_item in set(locs))
                if most_freq_loc_count >= 5:
                    score += 15.0
                    reasons.append(f"Frequent clustering at identical location ({most_freq_loc_count} times)")

        score = min(100.0, max(5.0, score))
        captcha_required = score >= IntegrityConfig.CAPTCHA_RISK_THRESHOLD or user_profile.get('captcha_required', False)

        return {
            "score": round(score, 1),
            "reasons": reasons,
            "captcha_required": bool(captcha_required)
        }
