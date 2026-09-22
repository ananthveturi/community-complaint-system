import json
from typing import List, Dict, Any, Optional, Tuple
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

from .config import IntegrityConfig
from .image_fingerprint_service import ImageFingerprintService

class DuplicateService:
    """Duplicate complaint and image detection across text, location, and visual representations."""

    @classmethod
    def calculate_text_similarity(cls, text1: str, text2: str) -> float:
        """Calculate TF-IDF cosine similarity between two text snippets."""
        if not text1 or not text2:
            return 0.0
        t1, t2 = text1.strip().lower(), text2.strip().lower()
        if t1 == t2:
            return 1.0

        try:
            vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words='english')
            tfidf_matrix = vectorizer.fit_transform([t1, t2])
            sim = float(cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0])
            return round(sim, 3)
        except Exception:
            # Fallback simple token jaccard similarity if vocabulary is too sparse
            tokens1 = set(t1.split())
            tokens2 = set(t2.split())
            if not tokens1 or not tokens2:
                return 0.0
            return round(len(tokens1 & tokens2) / len(tokens1 | tokens2), 3)

    @classmethod
    def check_duplicate_complaint(
        cls,
        new_title: str,
        new_description: str,
        new_category: str,
        new_lat: Optional[float],
        new_lng: Optional[float],
        existing_complaints: List[Dict[str, Any]],
        exclude_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Compare new complaint against list of existing complaints.
        Returns list of similar complaints exceeding similarity/proximity criteria.
        """
        new_text = f"{new_title} {new_description}".strip()
        duplicates = []

        for comp in existing_complaints:
            if exclude_id and comp.get('id') == exclude_id:
                continue

            # We compare complaints in the same or related categories, or overall
            comp_text = f"{comp.get('title', '')} {comp.get('description', '')}".strip()
            text_sim = cls.calculate_text_similarity(new_text, comp_text)

            # Calculate distance if coordinates exist
            distance = None
            comp_lat = comp.get('latitude')
            comp_lng = comp.get('longitude')
            if new_lat is not None and new_lng is not None and comp_lat is not None and comp_lng is not None:
                distance = ImageFingerprintService.haversine_distance(new_lat, new_lng, comp_lat, comp_lng)

            # Conditions for possible duplicate:
            # A. Close geographic proximity (<= 500m) AND (text similarity >= 0.30 OR title keyword overlap)
            # B. High text similarity (>= 0.65) in same category
            # C. Near-identical text description (>= 0.75)
            is_dup = False
            reason = ""

            new_title_words = set(new_title.lower().split())
            comp_title_words = set(comp.get('title', '').lower().split())
            common_title_words = new_title_words & comp_title_words - {'a', 'an', 'the', 'in', 'on', 'at', 'near', 'of', 'and', '&', 'is', 'to'}

            if distance is not None and distance <= IntegrityConfig.COMPLAINT_GEO_DISTANCE_METERS and (text_sim >= 0.30 or common_title_words):
                is_dup = True
                effective_sim = max(text_sim, 0.50 if common_title_words else 0.40)
                text_sim = round(effective_sim, 3)
                reason = f"Geographically close ({round(distance)}m) with related description ({round(effective_sim*100)}% match)"
            elif text_sim >= IntegrityConfig.COMPLAINT_TEXT_SIMILARITY_THRESHOLD and comp.get('category') == new_category:
                is_dup = True
                dist_str = f" ({round(distance)}m away)" if distance is not None else ""
                reason = f"Strong semantic similarity ({round(text_sim*100)}%) in same category{dist_str}"
            elif text_sim >= 0.75:
                is_dup = True
                reason = f"Near-identical text description ({round(text_sim*100)}% match)"

            if is_dup:
                duplicates.append({
                    "complaint_id": comp.get('id'),
                    "title": comp.get('title'),
                    "category": comp.get('category'),
                    "status": comp.get('status'),
                    "similarity_score": text_sim,
                    "distance_meters": round(distance, 1) if distance is not None else None,
                    "reason": reason,
                    "created_at": str(comp.get('created_at', ''))
                })

        # Sort by similarity score descending
        duplicates.sort(key=lambda d: d['similarity_score'], reverse=True)
        return duplicates

    @classmethod
    def check_duplicate_image(
        cls,
        new_sha256: str,
        new_phash: Optional[str],
        new_dhash: Optional[str],
        new_ahash: Optional[str],
        new_embedding: Optional[List[float]],
        existing_fingerprints: List[Dict[str, Any]],
        current_complaint_id: Optional[int] = None,
        current_citizen_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Scan historical image fingerprints for:
        1. Exact duplicate (SHA-256 match)
        2. Perceptual duplicate (pHash, dHash, aHash within Hamming threshold)
        3. Embedding similarity (Cosine similarity >= threshold)
        4. Cross-complaint / repeated photo abuse
        """
        matched = []

        for fp in existing_fingerprints:
            # Skip if it is from the same complaint record
            if current_complaint_id and fp.get('complaint_id') == current_complaint_id:
                continue

            match_type = None
            sim_score = 0.0

            # 1. Exact SHA-256 match
            if new_sha256 and fp.get('sha256') == new_sha256:
                match_type = "EXACT_HASH"
                sim_score = 1.0

            # 2. Perceptual Hashes (pHash / dHash / aHash)
            elif new_phash and fp.get('phash'):
                dist_p = ImageFingerprintService.hamming_distance(new_phash, fp['phash'])
                dist_d = ImageFingerprintService.hamming_distance(new_dhash or "", fp.get('dhash') or "") if new_dhash else 64
                dist_a = ImageFingerprintService.hamming_distance(new_ahash or "", fp.get('ahash') or "") if new_ahash else 64

                # If pHash <= 10 or dHash <= 8, visually very similar
                if dist_p <= IntegrityConfig.PHASH_HAMMING_THRESHOLD or dist_d <= IntegrityConfig.DHASH_HAMMING_THRESHOLD:
                    match_type = "PERCEPTUAL_HASH"
                    min_dist = min(dist_p, dist_d)
                    sim_score = round(1.0 - (min_dist / 64.0), 3)

            # 3. Embedding Cosine Similarity
            if not match_type and new_embedding and fp.get('embedding_reference'):
                try:
                    ref_vec = json.loads(fp['embedding_reference'])
                    cos_sim = ImageFingerprintService.cosine_similarity(new_embedding, ref_vec)
                    if cos_sim >= IntegrityConfig.IMAGE_SIMILARITY_DUPLICATE_THRESHOLD:
                        match_type = "VISUAL_EMBEDDING"
                        sim_score = round(cos_sim, 3)
                except Exception:
                    pass

            if match_type:
                is_repeated_evidence = (
                    current_citizen_id is not None
                    and fp.get('citizen_id') == current_citizen_id
                    and fp.get('complaint_id') != current_complaint_id
                )

                matched.append({
                    "fingerprint_id": fp.get('id'),
                    "matched_complaint_id": fp.get('complaint_id'),
                    "matched_image_path": fp.get('image_path'),
                    "match_type": match_type,
                    "similarity_score": sim_score,
                    "is_repeated_evidence": is_repeated_evidence,
                    "matched_citizen_id": fp.get('citizen_id'),
                    "created_at": str(fp.get('created_at', ''))
                })

        # Sort matches by similarity score
        matched.sort(key=lambda m: m['similarity_score'], reverse=True)
        return matched
