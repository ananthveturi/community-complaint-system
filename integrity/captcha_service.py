import random
import hmac
import hashlib
import time
import os

class CaptchaService:
    """Lightweight adaptive friction challenge generator and validator."""

    SECRET = os.environ.get('CAPTCHA_SECRET', 'civifix-captcha-secret-key-salt')

    @classmethod
    def generate_challenge(cls) -> dict:
        """Generate a simple arithmetic security challenge."""
        num1 = random.randint(3, 12)
        num2 = random.randint(2, 9)
        operator = random.choice(['+', '-'])
        answer = num1 + num2 if operator == '+' else num1 - num2

        timestamp = int(time.time())
        token_payload = f"{answer}:{timestamp}"
        signature = hmac.new(cls.SECRET.encode(), token_payload.encode(), hashlib.sha256).hexdigest()
        challenge_token = f"{token_payload}:{signature}"

        return {
            "question": f"Security Verification: What is {num1} {operator} {num2}?",
            "token": challenge_token
        }

    @classmethod
    def verify_challenge(cls, user_answer: str, challenge_token: str) -> bool:
        """Verify the user's answer against the signed token."""
        if not user_answer or not challenge_token:
            return False

        parts = challenge_token.split(':')
        if len(parts) != 3:
            return False

        expected_answer, timestamp_str, signature = parts
        token_payload = f"{expected_answer}:{timestamp_str}"
        expected_sig = hmac.new(cls.SECRET.encode(), token_payload.encode(), hashlib.sha256).hexdigest()

        # Check signature integrity
        if not hmac.compare_digest(signature, expected_sig):
            return False

        # Check token expiration (max 10 minutes)
        try:
            timestamp = int(timestamp_str)
            if time.time() - timestamp > 600:
                return False
        except ValueError:
            return False

        # Check answer
        try:
            return int(user_answer.strip()) == int(expected_answer)
        except ValueError:
            return False
