import json
import sqlite3
from typing import Dict, Any, List, Optional
import database

class IntegrityRepository:
    """Encapsulates all database operations for CiviFix Integrity & Fraud tables."""

    @staticmethod
    def save_risk_assessment(
        complaint_id: int,
        risk_score: float,
        decision: str,
        pipeline_version: str,
        signals: List[Dict[str, Any]],
        explanations: List[str]
    ) -> int:
        conn = database.get_db()
        try:
            cursor = conn.cursor()
            signals_summary = "; ".join(explanations)
            cursor.execute('''
                INSERT INTO complaint_risk_assessments (complaint_id, risk_score, decision, pipeline_version, signals_summary)
                VALUES (?, ?, ?, ?, ?)
            ''', (complaint_id, risk_score, decision, pipeline_version, signals_summary))
            assessment_id = cursor.lastrowid

            for sig in signals:
                cursor.execute('''
                    INSERT INTO fraud_signals (risk_assessment_id, type, score, weight, explanation, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    assessment_id,
                    sig.get('type'),
                    sig.get('score', 0.0),
                    sig.get('weight', 1.0),
                    sig.get('explanation', ''),
                    json.dumps(sig.get('metadata', {})) if sig.get('metadata') else None
                ))

            # Update complaint integrity columns
            cursor.execute('''
                UPDATE complaints
                SET risk_score = ?,
                    integrity_status = ?
                WHERE id = ?
            ''', (risk_score, "REVIEW_REQUIRED" if decision == "REVIEW" else ("REJECTED" if decision == "REJECT" else "ACCEPTED"), complaint_id))

            conn.commit()
            return assessment_id
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    @staticmethod
    def get_risk_assessment(complaint_id: int) -> Optional[Dict[str, Any]]:
        conn = database.get_db()
        try:
            row = conn.execute('''
                SELECT * FROM complaint_risk_assessments
                WHERE complaint_id = ?
                ORDER BY created_at DESC LIMIT 1
            ''', (complaint_id,)).fetchone()
            if not row:
                return None
            res = dict(row)

            signals = conn.execute('''
                SELECT * FROM fraud_signals
                WHERE risk_assessment_id = ?
                ORDER BY score DESC
            ''', (res['id'],)).fetchall()
            res['signals'] = [dict(s) for s in signals]
            return res
        finally:
            conn.close()

    @staticmethod
    def save_image_fingerprint(
        complaint_id: int,
        image_path: str,
        sha256: str,
        phash: Optional[str],
        dhash: Optional[str],
        ahash: Optional[str],
        embedding: Optional[List[float]],
        image_width: int,
        image_height: int,
        file_size_bytes: int,
        mime_type: str,
        exif_meta: Optional[Dict[str, Any]] = None,
        quality_info: Optional[Dict[str, Any]] = None,
        is_manipulated: bool = False
    ) -> int:
        conn = database.get_db()
        try:
            cursor = conn.cursor()
            exif_meta = exif_meta or {}
            quality_info = quality_info or {}

            cursor.execute('''
                INSERT INTO image_fingerprints (
                    complaint_id, image_path, sha256, phash, dhash, ahash,
                    embedding_reference, image_width, image_height, file_size_bytes,
                    mime_type, exif_timestamp, exif_latitude, exif_longitude,
                    exif_camera_model, quality_warning, is_manipulated
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                complaint_id,
                image_path,
                sha256,
                phash,
                dhash,
                ahash,
                json.dumps(embedding) if embedding else None,
                image_width,
                image_height,
                file_size_bytes,
                mime_type,
                exif_meta.get('timestamp'),
                exif_meta.get('latitude'),
                exif_meta.get('longitude'),
                exif_meta.get('camera_model'),
                quality_info.get('warning'),
                1 if is_manipulated else 0
            ))
            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            # Already exists for exact sha256
            row = conn.execute('SELECT id FROM image_fingerprints WHERE sha256 = ?', (sha256,)).fetchone()
            return row['id'] if row else None
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    @staticmethod
    def get_all_image_fingerprints() -> List[Dict[str, Any]]:
        conn = database.get_db()
        try:
            rows = conn.execute('''
                SELECT f.*, c.citizen_id, c.title as complaint_title, c.category as complaint_category
                FROM image_fingerprints f
                JOIN complaints c ON f.complaint_id = c.id
                ORDER BY f.created_at DESC
            ''').fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @staticmethod
    def save_image_similarity(source_id: int, target_id: int, score: float, method: str, is_cross: bool = False) -> int:
        conn = database.get_db()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO image_similarities (source_image_id, target_image_id, similarity_score, method, is_cross_complaint)
                VALUES (?, ?, ?, ?, ?)
            ''', (source_id, target_id, score, method, 1 if is_cross else 0))
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    @staticmethod
    def save_complaint_similarity(complaint_id: int, similar_id: int, score: float, distance: Optional[float], reason: str) -> int:
        conn = database.get_db()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO complaint_similarities (complaint_id, similar_complaint_id, similarity_score, distance_meters, reason)
                VALUES (?, ?, ?, ?, ?)
            ''', (complaint_id, similar_id, score, distance, reason))
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    @staticmethod
    def get_complaint_similarities(complaint_id: int) -> List[Dict[str, Any]]:
        conn = database.get_db()
        try:
            rows = conn.execute('''
                SELECT cs.*, c.title as similar_title, c.status as similar_status, c.category as similar_category,
                       c.location as similar_location, c.image_path as similar_image
                FROM complaint_similarities cs
                JOIN complaints c ON cs.similar_complaint_id = c.id
                WHERE cs.complaint_id = ?
                ORDER BY cs.similarity_score DESC
            ''', (complaint_id,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @staticmethod
    def save_spam_result(
        complaint_id: int,
        spam_score: float,
        risk_tier: str,
        repeated_char_ratio: Optional[float],
        entropy_score: Optional[float],
        contains_promo: bool,
        reasons: List[str]
    ) -> int:
        conn = database.get_db()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO spam_detection_results (
                    complaint_id, spam_score, risk_tier, repeated_char_ratio,
                    entropy_score, contains_promo_url, flagged_reasons
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                complaint_id,
                spam_score,
                risk_tier,
                repeated_char_ratio,
                entropy_score,
                1 if contains_promo else 0,
                "; ".join(reasons) if reasons else None
            ))
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    @staticmethod
    def get_user_risk_profile(user_id: int) -> Dict[str, Any]:
        conn = database.get_db()
        try:
            row = conn.execute('SELECT * FROM user_risk_profiles WHERE user_id = ?', (user_id,)).fetchone()
            if row:
                return dict(row)
            # Create baseline profile if none exists
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO user_risk_profiles (user_id, behavioral_risk_score, complaint_count_total)
                VALUES (?, 0.0, 0)
            ''', (user_id,))
            conn.commit()
            new_row = conn.execute('SELECT * FROM user_risk_profiles WHERE user_id = ?', (user_id,)).fetchone()
            return dict(new_row)
        finally:
            conn.close()

    @staticmethod
    def record_integrity_review(
        complaint_id: int,
        reviewer_id: int,
        action: str,
        review_notes: str,
        prior_decision: str,
        final_decision: str
    ) -> int:
        conn = database.get_db()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO integrity_reviews (complaint_id, reviewer_id, action, review_notes, prior_decision, final_decision)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (complaint_id, reviewer_id, action, review_notes, prior_decision, final_decision))

            # Update complaint status based on review action
            new_complaint_status = None
            new_integrity_status = None
            if action == 'APPROVE':
                new_complaint_status = 'Pending'
                new_integrity_status = 'ACCEPTED'
            elif action == 'REJECT':
                new_complaint_status = 'Rejected'
                new_integrity_status = 'REJECTED'
            elif action == 'MARK_DUPLICATE':
                new_complaint_status = 'Rejected'
                new_integrity_status = 'FLAGGED_DUPLICATE'
            elif action == 'SUSPEND':
                new_complaint_status = 'Under Review'
                new_integrity_status = 'REVIEW_REQUIRED'
            elif action == 'RESTORE':
                new_complaint_status = 'In Progress'
                new_integrity_status = 'ACCEPTED'

            if new_integrity_status:
                cursor.execute('''
                    UPDATE complaints
                    SET integrity_status = ?,
                        status = COALESCE(?, status)
                    WHERE id = ?
                ''', (new_integrity_status, new_complaint_status, complaint_id))

            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    @staticmethod
    def get_integrity_dashboard_data() -> Dict[str, Any]:
        conn = database.get_db()
        try:
            total_analyzed = conn.execute('SELECT COUNT(*) FROM complaint_risk_assessments').fetchone()[0]
            under_review = conn.execute("SELECT COUNT(*) FROM complaints WHERE integrity_status = 'REVIEW_REQUIRED'").fetchone()[0]
            rejected = conn.execute("SELECT COUNT(*) FROM complaints WHERE integrity_status = 'REJECTED'").fetchone()[0]
            spam_detected = conn.execute("SELECT COUNT(*) FROM spam_detection_results WHERE spam_score >= 30.0").fetchone()[0]
            possible_duplicates = conn.execute('SELECT COUNT(DISTINCT complaint_id) FROM complaint_similarities').fetchone()[0]
            duplicate_images = conn.execute('SELECT COUNT(DISTINCT source_image_id) FROM image_similarities').fetchone()[0]

            # Risk Distribution
            low_risk = conn.execute('SELECT COUNT(*) FROM complaint_risk_assessments WHERE risk_score < 30.0').fetchone()[0]
            med_risk = conn.execute('SELECT COUNT(*) FROM complaint_risk_assessments WHERE risk_score >= 30.0 AND risk_score < 60.0').fetchone()[0]
            high_risk = conn.execute('SELECT COUNT(*) FROM complaint_risk_assessments WHERE risk_score >= 60.0 AND risk_score < 80.0').fetchone()[0]
            critical_risk = conn.execute('SELECT COUNT(*) FROM complaint_risk_assessments WHERE risk_score >= 80.0').fetchone()[0]

            # Reviews for human queue
            reviews_queue = conn.execute('''
                SELECT c.id, c.title, c.category, c.location, c.created_at, c.image_path, c.status, c.integrity_status,
                       u.full_name as citizen_name, u.email as citizen_email,
                       cra.risk_score, cra.decision, cra.signals_summary
                FROM complaints c
                JOIN users u ON c.citizen_id = u.id
                LEFT JOIN complaint_risk_assessments cra ON cra.complaint_id = c.id
                WHERE c.integrity_status = 'REVIEW_REQUIRED' OR c.status = 'Under Review'
                ORDER BY cra.risk_score DESC, c.created_at DESC
                LIMIT 50
            ''').fetchall()

            # Top fraud signals
            top_signals = conn.execute('''
                SELECT type, COUNT(*) as count, AVG(score) as avg_score
                FROM fraud_signals
                GROUP BY type
                ORDER BY count DESC
                LIMIT 6
            ''').fetchall()

            # Recent reviews completed
            recent_reviews = conn.execute('''
                SELECT ir.*, u.full_name as reviewer_name, c.title as complaint_title
                FROM integrity_reviews ir
                LEFT JOIN users u ON ir.reviewer_id = u.id
                JOIN complaints c ON ir.complaint_id = c.id
                ORDER BY ir.created_at DESC
                LIMIT 10
            ''').fetchall()

            false_positive_rate = "0.0%"
            total_reviews = conn.execute('SELECT COUNT(*) FROM integrity_reviews').fetchone()[0]
            if total_reviews > 0:
                approved_after_review = conn.execute("SELECT COUNT(*) FROM integrity_reviews WHERE action = 'APPROVE'").fetchone()[0]
                fp_rate = (approved_after_review / total_reviews) * 100
                false_positive_rate = f"{round(fp_rate, 1)}%"

            return {
                "total_analyzed": total_analyzed,
                "under_review": under_review,
                "rejected": rejected,
                "spam_detected": spam_detected,
                "possible_duplicates": possible_duplicates,
                "duplicate_images": duplicate_images,
                "false_positive_rate": false_positive_rate,
                "risk_distribution": {
                    "low": low_risk,
                    "medium": med_risk,
                    "high": high_risk,
                    "critical": critical_risk
                },
                "reviews_queue": [dict(r) for r in reviews_queue],
                "top_signals": [dict(s) for s in top_signals],
                "recent_reviews": [dict(r) for r in recent_reviews]
            }
        finally:
            conn.close()
