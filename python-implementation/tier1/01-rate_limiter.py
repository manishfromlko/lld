"""
Rate Limiter — Sliding Window, Token Bucket, Leaky Bucket
Strategy Pattern: each algorithm implements the same interface.
"""

import time
import threading
from abc import ABC, abstractmethod
from collections import deque
from enum import Enum


# ──────────────────────────────────────────────
#  Strategy Interface
# ──────────────────────────────────────────────

class RateLimiter(ABC):
    @abstractmethod
    def allow_request(self, client_id: str) -> bool:
        pass


# ──────────────────────────────────────────────
#  Algorithm 1: Sliding Window Log
#  Memory: O(N) — stores N timestamps per client
# ──────────────────────────────────────────────

class SlidingWindowRateLimiter(RateLimiter):
    def __init__(self, max_requests: int, window_seconds: float):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps: dict[str, deque] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._meta_lock = threading.Lock()

    def _get_lock(self, client_id: str) -> threading.Lock:
        with self._meta_lock:
            if client_id not in self._locks:
                self._locks[client_id] = threading.Lock()
            return self._locks[client_id]

    def allow_request(self, client_id: str) -> bool:
        lock = self._get_lock(client_id)
        with lock:
            now = time.time()
            window_start = now - self.window_seconds

            if client_id not in self._timestamps:
                self._timestamps[client_id] = deque()

            ts = self._timestamps[client_id]
            # Remove timestamps outside the window
            while ts and ts[0] < window_start:
                ts.popleft()

            if len(ts) < self.max_requests:
                ts.append(now)
                return True
            return False


# ──────────────────────────────────────────────
#  Algorithm 2: Token Bucket (Lazy Refill)
#  Memory: O(1) per client — just 2 fields
# ──────────────────────────────────────────────

class TokenBucketRateLimiter(RateLimiter):
    def __init__(self, capacity: int, refill_rate_per_second: float):
        self.capacity = capacity
        self.refill_rate = refill_rate_per_second  # tokens per second
        self._buckets: dict[str, dict] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._meta_lock = threading.Lock()

    def _get_lock(self, client_id: str) -> threading.Lock:
        with self._meta_lock:
            if client_id not in self._locks:
                self._locks[client_id] = threading.Lock()
            return self._locks[client_id]

    def allow_request(self, client_id: str) -> bool:
        lock = self._get_lock(client_id)
        with lock:
            now = time.time()

            if client_id not in self._buckets:
                self._buckets[client_id] = {"tokens": self.capacity, "last_refill": now}

            bucket = self._buckets[client_id]
            elapsed = now - bucket["last_refill"]
            tokens_to_add = elapsed * self.refill_rate
            bucket["tokens"] = min(self.capacity, bucket["tokens"] + tokens_to_add)
            bucket["last_refill"] = now

            if bucket["tokens"] >= 1:
                bucket["tokens"] -= 1
                return True
            return False


# ──────────────────────────────────────────────
#  Algorithm 3: Leaky Bucket
#  Smooths traffic to a constant rate
# ──────────────────────────────────────────────

class LeakyBucketRateLimiter(RateLimiter):
    def __init__(self, capacity: int, leak_rate_per_second: float):
        self.capacity = capacity
        self.leak_rate = leak_rate_per_second
        self._buckets: dict[str, dict] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._meta_lock = threading.Lock()

    def _get_lock(self, client_id: str) -> threading.Lock:
        with self._meta_lock:
            if client_id not in self._locks:
                self._locks[client_id] = threading.Lock()
            return self._locks[client_id]

    def allow_request(self, client_id: str) -> bool:
        lock = self._get_lock(client_id)
        with lock:
            now = time.time()

            if client_id not in self._buckets:
                self._buckets[client_id] = {"water_level": 0.0, "last_leak": now}

            bucket = self._buckets[client_id]
            elapsed = now - bucket["last_leak"]
            leaked = elapsed * self.leak_rate
            bucket["water_level"] = max(0.0, bucket["water_level"] - leaked)
            bucket["last_leak"] = now

            if bucket["water_level"] < self.capacity:
                bucket["water_level"] += 1
                return True
            return False


# ──────────────────────────────────────────────
#  Factory
# ──────────────────────────────────────────────

class Algorithm(Enum):
    SLIDING_WINDOW = "sliding_window"
    TOKEN_BUCKET = "token_bucket"
    LEAKY_BUCKET = "leaky_bucket"


def create_rate_limiter(algo: Algorithm, max_requests: int, window_seconds: float) -> RateLimiter:
    if algo == Algorithm.SLIDING_WINDOW:
        return SlidingWindowRateLimiter(max_requests, window_seconds)
    elif algo == Algorithm.TOKEN_BUCKET:
        return TokenBucketRateLimiter(max_requests, max_requests / window_seconds)
    elif algo == Algorithm.LEAKY_BUCKET:
        return LeakyBucketRateLimiter(max_requests, max_requests / window_seconds)
    raise ValueError(f"Unknown algorithm: {algo}")


# ──────────────────────────────────────────────
#  Demo
# ──────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Token Bucket: 5 requests per 10 seconds ===")
    limiter = create_rate_limiter(Algorithm.TOKEN_BUCKET, 5, 10)

    for i in range(8):
        result = limiter.allow_request("user-1")
        print(f"  Request {i+1}: {'ALLOWED' if result else 'DENIED'}")

    print("\n=== Sliding Window: 3 requests per second (concurrent) ===")
    limiter2 = create_rate_limiter(Algorithm.SLIDING_WINDOW, 3, 1)
    results = []
    lock = threading.Lock()

    def make_request(req_id):
        allowed = limiter2.allow_request("user-2")
        with lock:
            results.append((req_id, allowed))

    threads = [threading.Thread(target=make_request, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    results.sort()
    for req_id, allowed in results:
        print(f"  Request {req_id}: {'ALLOWED' if allowed else 'DENIED'}")

    allowed_count = sum(1 for _, a in results if a)
    print(f"  Allowed: {allowed_count}/6 (expected 3)")
