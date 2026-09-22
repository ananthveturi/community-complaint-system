import time
import threading
from typing import Tuple, Optional
from .config import IntegrityConfig

class RateLimiter:
    """Multi-tiered sliding-window rate limiter with Redis support and thread-safe in-memory fallback."""

    _lock = threading.Lock()
    _memory_store = {}  # { key: [timestamp, timestamp, ...] }

    @classmethod
    def check_limit(cls, key: str, limit: int, window_seconds: int) -> Tuple[bool, int, int]:
        """
        Check if request is allowed under the sliding window rate limit.
        Returns: (is_allowed, remaining, retry_after_seconds)
        """
        now = time.time()
        window_start = now - window_seconds

        # Redis backend if configured
        if IntegrityConfig.REDIS_URL:
            try:
                import redis
                r = redis.from_url(IntegrityConfig.REDIS_URL)
                pipe = r.pipeline()
                pipe.zremrangebyscore(key, 0, window_start)
                pipe.zadd(key, {str(now): now})
                pipe.zcard(key)
                pipe.expire(key, window_seconds)
                _, _, current_count, _ = pipe.execute()

                remaining = max(0, limit - current_count)
                if current_count > limit:
                    return False, 0, int(window_seconds)
                return True, remaining, 0
            except Exception:
                # Fallback to in-memory on redis connection glitch
                pass

        # Thread-safe In-Memory sliding-window limiter
        with cls._lock:
            timestamps = cls._memory_store.get(key, [])
            # Filter out timestamps outside the window
            timestamps = [t for t in timestamps if t > window_start]

            if len(timestamps) >= limit:
                retry_after = int(window_seconds - (now - timestamps[0]))
                cls._memory_store[key] = timestamps
                return False, 0, max(1, retry_after)

            timestamps.append(now)
            cls._memory_store[key] = timestamps
            remaining = max(0, limit - len(timestamps))
            return True, remaining, 0

    @classmethod
    def check_ip_rate_limit(cls, ip: str) -> Tuple[bool, int, int]:
        return cls.check_limit(f"ip:{ip}", IntegrityConfig.RATE_LIMIT_REQUESTS_PER_MINUTE_IP, 60)

    @classmethod
    def check_complaint_submission_limit(cls, user_id: int) -> Tuple[bool, int, int]:
        return cls.check_limit(f"comp:{user_id}", IntegrityConfig.RATE_LIMIT_COMPLAINTS_PER_HOUR, 3600)

    @classmethod
    def check_image_upload_limit(cls, user_id: int) -> Tuple[bool, int, int]:
        return cls.check_limit(f"img:{user_id}", IntegrityConfig.RATE_LIMIT_IMAGES_PER_HOUR, 3600)
