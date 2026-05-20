# 01 — Rate Limiter (Python Implementation)

**File:** `rate_limiter.py`  
**Tier:** 1 — Highest priority

---

## Problem Statement

Design an in-memory rate limiter that restricts the number of API requests a client can make within a time window. Support multiple algorithms swappable at runtime without changing client code.

---

## Design Patterns Used

| Pattern | Where | Why |
|---|---|---|
| **Strategy** | `RateLimiter` ABC → `SlidingWindowRateLimiter`, `TokenBucketRateLimiter`, `LeakyBucketRateLimiter` | Swap algorithms at runtime without changing client code |
| **Factory** | `create_rate_limiter(algo, ...)` | One function hides which concrete class to instantiate |

---

## Class Structure

```
RateLimiter (ABC)
├── SlidingWindowRateLimiter   — deque of timestamps per client
├── TokenBucketRateLimiter     — lazy token refill per client
└── LeakyBucketRateLimiter     — water-level drain per client

create_rate_limiter(algo, max_requests, window_seconds) → RateLimiter
```

---

## Python vs Java Key Differences

| Concern | Java | Python |
|---|---|---|
| Interface | `interface RateLimiter` | `ABC` + `@abstractmethod` |
| Per-client lock | `ConcurrentHashMap<String, Object>` lock objects | `dict` with a meta-lock to create per-client `threading.Lock` |
| Synchronized block | `synchronized(lock) { ... }` | `with lock:` context manager |
| Generic types | `Cache<K,V>` | Type hints only (no runtime enforcement) |

---

## Core Algorithms

### Sliding Window (deque of timestamps)
```
allow(client):
  acquire client lock
  now = current time
  drop timestamps older than (now - window)
  if len(timestamps) < max_requests:
      timestamps.append(now)
      return ALLOW
  return DENY
```

### Token Bucket (lazy refill)
```
allow(client):
  acquire client lock
  elapsed = now - last_refill
  tokens = min(capacity, tokens + elapsed * refill_rate)
  last_refill = now
  if tokens >= 1:
      tokens -= 1
      return ALLOW
  return DENY
```

### Leaky Bucket (water-level drain)
```
allow(client):
  acquire client lock
  elapsed = now - last_leak
  water_level = max(0, water_level - elapsed * leak_rate)
  last_leak = now
  if water_level < capacity:
      water_level += 1
      return ALLOW
  return DENY
```

---

## Concurrency Design

Per-client locking: each client gets its own `threading.Lock`. A meta-lock protects the dict that maps `client_id → lock`.

```python
# Creating per-client lock safely
with self._meta_lock:
    if client_id not in self._locks:
        self._locks[client_id] = threading.Lock()
lock = self._locks[client_id]

with lock:   # only this client is blocked; other clients run in parallel
    ...
```

This means requests from different clients execute **in parallel**; only concurrent requests from the **same client** are serialised.

---

## Algorithm Comparison

| Aspect | Sliding Window | Token Bucket | Leaky Bucket |
|---|---|---|---|
| Memory per client | O(N) timestamps | O(1) — 2 fields | O(1) — 2 fields |
| Burst handling | Strict count in window | Allows burst up to capacity | Smooths to constant rate |
| Best for | Strict rate enforcement | APIs that allow occasional spikes | Traffic shaping |

---

## Interview Talking Points

1. **Why per-client locks instead of one global lock?** — A global lock would serialise all clients. Per-client locks let clients A and B run in parallel while still preventing two threads for client A from racing.
2. **Sliding window vs fixed window** — Sliding window avoids the boundary burst problem (e.g., 100 requests at 00:59 + 100 more at 01:01 in a fixed window appears as 200 within two seconds).
3. **Token bucket vs leaky bucket** — Token bucket allows controlled bursts (tokens accumulate); leaky bucket enforces a constant output rate regardless of arrival pattern.
4. **Lock-free alternative** — Use `threading.local()` or an `AtomicInteger` equivalent (`multiprocessing.Value`) with CAS for the token count.
