import re
import math
from .config import IntegrityConfig

class SpamService:
    """Multi-signal text spam, promotional content, repetition, and gibberish analyzer."""

    PROMO_PATTERNS = [
        r'\b(?:buy\s+now|click\s+here|free\s+gift|winner|lottery|crypto|bitcoin|forex|casino|betting|discount|loan|earn\s+money|subscribe|telegram\s+channel|whatsapp\s+group)\b',
        r'https?://[^\s]+',
        r'www\.[^\s]+',
        r'\b[a-zA-Z0-9.-]+\.(?:xyz|top|work|buzz|club|online|icu|loan|click|shop)\b'
    ]

    KEYBOARD_MASH_PATTERNS = [
        r'(?:asdfgh|qwerty|zxcvbn|123456|qazwsx|edcrfv)',
        r'(?:[bcdfghjklmnpqrstvwxyz]{6,})',  # 6+ consonants in a row with no vowels
    ]

    @staticmethod
    def calculate_entropy(text: str) -> float:
        """Calculate Shannon entropy of character distribution in text."""
        if not text:
            return 0.0
        clean_text = re.sub(r'\s+', '', text.lower())
        if not clean_text:
            return 0.0
        frequencies = {}
        for char in clean_text:
            frequencies[char] = frequencies.get(char, 0) + 1
        entropy = 0.0
        length = len(clean_text)
        for count in frequencies.values():
            p = count / length
            entropy -= p * math.log2(p)
        return entropy

    @classmethod
    def analyze(cls, title: str, description: str) -> dict:
        """
        Analyze title and description for spam signals.
        Returns a dictionary with score (0-100), risk_tier, triggered reasons, and metrics.
        """
        title = title or ""
        description = description or ""
        combined = f"{title.strip()} {description.strip()}".strip()

        score = 0.0
        reasons = []
        contains_promo = False

        if not combined:
            return {
                "score": 100.0,
                "risk_tier": "Critical",
                "reasons": ["Empty title and description"],
                "repeated_char_ratio": 0.0,
                "entropy_score": 0.0,
                "contains_promo_url": False
            }

        # 1. Check Repeated Characters (e.g. "aaaaaaaaaaaa" or "help!!!!!!!!!")
        repeated_char_matches = re.findall(r'(.)\1{4,}', combined)
        max_repeated_len = 0
        for match in re.finditer(r'(.)\1{3,}', combined):
            span_len = match.end() - match.start()
            if span_len > max_repeated_len:
                max_repeated_len = span_len

        repeated_char_ratio = max_repeated_len / max(1, len(combined))
        if max_repeated_len >= 10:
            score += 45.0
            reasons.append(f"Excessive character repetition ({max_repeated_len} repeated characters)")
        elif max_repeated_len >= 5:
            score += 20.0
            reasons.append(f"Noticeable character repetition ({max_repeated_len} repeated characters)")

        # 2. Repeated Words / Phrases (e.g. "test test test test" or "pothole pothole pothole")
        words = [w.lower() for w in re.findall(r'\b[a-zA-Z0-9_-]+\b', combined)]
        if len(words) >= 3:
            word_counts = {}
            for w in words:
                word_counts[w] = word_counts.get(w, 0) + 1
            max_word_freq = max(word_counts.values())
            repetition_ratio = max_word_freq / len(words)
            if repetition_ratio >= 0.70 and len(words) >= 4:
                score += 40.0
                reasons.append(f"Word repetition detected ('{max(word_counts, key=word_counts.get)}' repeated {max_word_freq} times)")
            elif repetition_ratio >= 0.50 and len(words) >= 6:
                score += 20.0
                reasons.append("High word repetition ratio")

        # 3. Excessive Capitalization (SHOUTING / SPAM)
        letters = re.findall(r'[a-zA-Z]', combined)
        if len(letters) >= 12:
            caps = [c for c in letters if c.isupper()]
            caps_ratio = len(caps) / len(letters)
            if caps_ratio > 0.85:
                score += 25.0
                reasons.append(f"Excessive capitalization ({round(caps_ratio * 100)}% uppercase)")
            elif caps_ratio > 0.65 and len(letters) > 20:
                score += 15.0
                reasons.append(f"High uppercase ratio ({round(caps_ratio * 100)}%)")

        # 4. Excessive Special Characters / Symbols
        symbols = re.findall(r'[^a-zA-Z0-9\s.,?!]', combined)
        if len(combined) > 10:
            symbol_ratio = len(symbols) / len(combined)
            if symbol_ratio > 0.35:
                score += 30.0
                reasons.append("Excessive special symbols/characters")
            elif symbol_ratio > 0.20:
                score += 15.0
                reasons.append("Elevated special symbol count")

        # 5. URLs and Promotional Patterns
        for pat in cls.PROMO_PATTERNS:
            matches = re.findall(pat, combined, re.IGNORECASE)
            if matches:
                contains_promo = True
                score += 65.0
                reasons.append(f"Promotional keyword or URL detected: {matches[0][:30]}")
                break

        # 6. Randomness / Gibberish & Entropy Detection
        entropy = cls.calculate_entropy(combined)
        # Very low entropy on non-trivial string means repeated single characters (e.g. "aaaaaaaa")
        if len(combined) > 15 and entropy < 1.6:
            score += 35.0
            reasons.append(f"Abnormally low entropy ({round(entropy, 2)}), indicating repetitive gibberish")

        # Keyboard mash patterns (e.g. "asdfghjkl", "qwertyuiop")
        for kpat in cls.KEYBOARD_MASH_PATTERNS:
            if re.search(kpat, combined, re.IGNORECASE):
                score += 35.0
                reasons.append("Keyboard mashing / non-word sequence detected")
                break

        # 7. Short Description Evaluation (Protecting legitimate short complaints!)
        # Do NOT automatically reject legitimate short complaints like "Pothole on Main St"
        # Only add a very small informational signal if < 8 characters and not already flagged
        if len(combined) < 10 and not reasons:
            score += 5.0  # minimal bump, still Low Risk

        # Cap score between 0 and 100
        score = min(100.0, max(0.0, score))

        # Assign risk tier
        if score <= IntegrityConfig.SPAM_TIER_LOW_MAX:
            tier = "Low"
        elif score <= IntegrityConfig.SPAM_TIER_MEDIUM_MAX:
            tier = "Medium"
        elif score <= IntegrityConfig.SPAM_TIER_HIGH_MAX:
            tier = "High"
        else:
            tier = "Critical"

        return {
            "score": round(score, 1),
            "risk_tier": tier,
            "reasons": reasons,
            "repeated_char_ratio": round(repeated_char_ratio, 3),
            "entropy_score": round(entropy, 2),
            "contains_promo_url": contains_promo
        }
