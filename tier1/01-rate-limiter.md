# 01 — Rate Limiter (Sliding Window + Token Bucket + Leaky Bucket)

**Priority:** TIER 1 — HIGHEST (reported at both Netcore & HealthifyMe)

---

## Problem Statement

Design an in-memory rate limiter that restricts the number of API requests a client can make within a time window. Support multiple rate-limiting algorithms that can be swapped at runtime.

---

## Clarification Questions to Ask the Interviewer

1. **Scope:** Are we rate-limiting per client (API key/IP) or globally?
2. **Algorithm:** Should I support multiple algorithms (Sliding Window, Token Bucket, Leaky Bucket) or just one?
3. **Concurrency:** Will multiple threads be calling this simultaneously? (Expect YES)
4. **Distributed:** Is this in-memory (single JVM) or distributed (multiple servers)? (For LLD, usually in-memory)
5. **Response:** Should we return remaining tokens/retry-after time, or just allow/deny?
6. **Cleanup:** Should we handle memory cleanup for inactive clients?
7. **Config:** Can different clients have different rate limits (tiers)?

---

## Entities

```
RateLimiter (interface)
├── SlidingWindowRateLimiter
├── TokenBucketRateLimiter
└── LeakyBucketRateLimiter

RateLimitConfig
├── maxRequests
├── windowSizeInMs (for sliding window)
├── capacity + refillRate (for token bucket)
└── capacity + leakRate (for leaky bucket)

RateLimitResponse
├── allowed (boolean)
├── remainingRequests
└── retryAfterMs
```

---

## Design Patterns

| Pattern | Where | Why |
|---|---|---|
| **Strategy** | `RateLimiter` interface with multiple implementations | Swap algorithms without changing client code |
| **Singleton** | `RateLimiterFactory` | One factory instance globally |
| **Factory** | `RateLimiterFactory.create(type, config)` | Create the right limiter based on config |

---

## SOLID Principles Applied

| Principle | How |
|---|---|
| **S** — Single Responsibility | Each limiter class handles only its algorithm |
| **O** — Open/Closed | Add new algorithms (e.g., Fixed Window) without modifying existing code |
| **L** — Liskov Substitution | Any `RateLimiter` implementation can replace another |
| **I** — Interface Segregation | `RateLimiter` interface has only `allowRequest()` — lean contract |
| **D** — Dependency Inversion | Client code depends on `RateLimiter` interface, not concrete class |

---

## Concurrency Strategy

**Primary:** Per-client locking — `synchronized(clientBucket)`

```
Thread-1: allowRequest("userA") → locks userA's bucket → checks → unlocks
Thread-2: allowRequest("userB") → locks userB's bucket → runs in PARALLEL
Thread-3: allowRequest("userA") → WAITS for Thread-1 (same client)
```

**Alternative 1:** `ReentrantLock` per client (supports tryLock with timeout)
**Alternative 2:** CAS + `AtomicLong` for token bucket (lock-free)

If interviewer says "don't use synchronized", use `AtomicLong` for token count with CAS:

```java
// Lock-free token bucket
AtomicLong tokens;
AtomicLong lastRefillTime;

boolean tryConsume() {
    while (true) {
        long current = tokens.get();
        refillIfNeeded();
        if (current <= 0) return false;
        if (tokens.compareAndSet(current, current - 1)) return true;
    }
}
```

---

## Data Structure Choices

| Algorithm | Data Structure | Why |
|---|---|---|
| Sliding Window | `Deque<Long>` (timestamps) | O(1) add/remove from both ends, ordered by time |
| Token Bucket | Two fields: `double tokens` + `long lastRefillTime` | O(1) space per client, lazy refill |
| Leaky Bucket | One field: `double waterLevel` + `long lastLeakTime` | O(1) space per client |
| Client mapping | `ConcurrentHashMap<String, Bucket>` | O(1) lookup, thread-safe |

---

## Core Algorithms

### Algorithm 1: Sliding Window Log

```
1. Get client's timestamp queue
2. Remove all timestamps older than (now - windowSize)
3. If queue.size() < maxRequests → add timestamp, return ALLOW
4. Else → return DENY
```

### Algorithm 2: Token Bucket (Lazy Refill)

```
1. Calculate timePassed = now - lastRefillTime
2. tokensToAdd = timePassed * refillRate
3. tokens = min(capacity, tokens + tokensToAdd)
4. Update lastRefillTime = now
5. If tokens >= 1 → tokens--, return ALLOW
6. Else → return DENY
```

### Algorithm 3: Leaky Bucket

```
1. Calculate timePassed = now - lastLeakTime
2. leaked = timePassed * leakRate
3. waterLevel = max(0, waterLevel - leaked)
4. Update lastLeakTime = now
5. If waterLevel < capacity → waterLevel++, return ALLOW
6. Else → return DENY (overflow)
```

---

## Java Implementation

### RateLimiter Interface (Strategy Pattern)

```java
public interface RateLimiter {
    boolean allowRequest(String clientId);
}
```

### RateLimitConfig

```java
public class RateLimitConfig {
    private final int maxRequests;
    private final long windowSizeInMs;
    private final long capacity;
    private final double refillRatePerSecond;

    public RateLimitConfig(int maxRequests, long windowSizeInMs) {
        this.maxRequests = maxRequests;
        this.windowSizeInMs = windowSizeInMs;
        this.capacity = maxRequests;
        this.refillRatePerSecond = (double) maxRequests / (windowSizeInMs / 1000.0);
    }

    // getters...
    public int getMaxRequests() { return maxRequests; }
    public long getWindowSizeInMs() { return windowSizeInMs; }
    public long getCapacity() { return capacity; }
    public double getRefillRatePerSecond() { return refillRatePerSecond; }
}
```

### Sliding Window Rate Limiter (Per-Client Locking)

```java
import java.util.*;
import java.util.concurrent.*;

public class SlidingWindowRateLimiter implements RateLimiter {
    private final int maxRequests;
    private final long windowSizeInMs;
    private final ConcurrentHashMap<String, Deque<Long>> clientTimestamps = new ConcurrentHashMap<>();
    private final ConcurrentHashMap<String, Object> locks = new ConcurrentHashMap<>();

    public SlidingWindowRateLimiter(int maxRequests, long windowSizeInMs) {
        this.maxRequests = maxRequests;
        this.windowSizeInMs = windowSizeInMs;
    }

    @Override
    public boolean allowRequest(String clientId) {
        Object lock = locks.computeIfAbsent(clientId, k -> new Object());

        synchronized (lock) {
            long now = System.currentTimeMillis();
            long windowStart = now - windowSizeInMs;

            Deque<Long> timestamps = clientTimestamps.computeIfAbsent(clientId, k -> new LinkedList<>());

            while (!timestamps.isEmpty() && timestamps.peekFirst() < windowStart) {
                timestamps.pollFirst();
            }

            if (timestamps.size() < maxRequests) {
                timestamps.addLast(now);
                return true;
            }
            return false;
        }
    }
}
```

### Token Bucket Rate Limiter (Per-Client Locking)

```java
import java.util.concurrent.*;

public class TokenBucketRateLimiter implements RateLimiter {
    private final long capacity;
    private final double refillRatePerMs;
    private final ConcurrentHashMap<String, TokenBucket> buckets = new ConcurrentHashMap<>();

    public TokenBucketRateLimiter(long capacity, long refillRatePerSecond) {
        this.capacity = capacity;
        this.refillRatePerMs = refillRatePerSecond / 1000.0;
    }

    private static class TokenBucket {
        double tokens;
        long lastRefillTime;

        TokenBucket(long capacity) {
            this.tokens = capacity;
            this.lastRefillTime = System.currentTimeMillis();
        }
    }

    @Override
    public boolean allowRequest(String clientId) {
        TokenBucket bucket = buckets.computeIfAbsent(clientId, k -> new TokenBucket(capacity));

        synchronized (bucket) {
            long now = System.currentTimeMillis();
            long timePassed = now - bucket.lastRefillTime;

            double tokensToAdd = timePassed * refillRatePerMs;
            bucket.tokens = Math.min(capacity, bucket.tokens + tokensToAdd);
            bucket.lastRefillTime = now;

            if (bucket.tokens >= 1.0) {
                bucket.tokens -= 1.0;
                return true;
            }
            return false;
        }
    }
}
```

### Leaky Bucket Rate Limiter

```java
import java.util.concurrent.*;

public class LeakyBucketRateLimiter implements RateLimiter {
    private final long capacity;
    private final double leakRatePerMs;
    private final ConcurrentHashMap<String, LeakyBucket> buckets = new ConcurrentHashMap<>();

    public LeakyBucketRateLimiter(long capacity, int leakRatePerSecond) {
        this.capacity = capacity;
        this.leakRatePerMs = leakRatePerSecond / 1000.0;
    }

    private static class LeakyBucket {
        double waterLevel = 0;
        long lastLeakTime = System.currentTimeMillis();
    }

    @Override
    public boolean allowRequest(String clientId) {
        LeakyBucket bucket = buckets.computeIfAbsent(clientId, k -> new LeakyBucket());

        synchronized (bucket) {
            long now = System.currentTimeMillis();
            long timePassed = now - bucket.lastLeakTime;

            double leaked = timePassed * leakRatePerMs;
            if (leaked > 0) {
                bucket.waterLevel = Math.max(0, bucket.waterLevel - leaked);
                bucket.lastLeakTime = now;
            }

            if (bucket.waterLevel < capacity) {
                bucket.waterLevel++;
                return true;
            }
            return false;
        }
    }
}
```

### Factory

```java
public class RateLimiterFactory {
    public enum Algorithm { SLIDING_WINDOW, TOKEN_BUCKET, LEAKY_BUCKET }

    public static RateLimiter create(Algorithm algo, RateLimitConfig config) {
        return switch (algo) {
            case SLIDING_WINDOW -> new SlidingWindowRateLimiter(config.getMaxRequests(), config.getWindowSizeInMs());
            case TOKEN_BUCKET -> new TokenBucketRateLimiter(config.getCapacity(), (long) config.getRefillRatePerSecond());
            case LEAKY_BUCKET -> new LeakyBucketRateLimiter(config.getCapacity(), (int) config.getRefillRatePerSecond());
        };
    }
}
```

### Main Class (Demo)

```java
public class Main {
    public static void main(String[] args) throws InterruptedException {
        RateLimitConfig config = new RateLimitConfig(5, 10_000); // 5 requests per 10 seconds
        RateLimiter limiter = RateLimiterFactory.create(
            RateLimiterFactory.Algorithm.TOKEN_BUCKET, config
        );

        // Simulate 10 threads hitting the limiter
        for (int i = 0; i < 10; i++) {
            final int reqId = i;
            new Thread(() -> {
                boolean allowed = limiter.allowRequest("user-123");
                System.out.println("Request " + reqId + ": " + (allowed ? "ALLOWED" : "DENIED"));
            }).start();
        }

        Thread.sleep(2000);
    }
}
```

---

## Algorithm Comparison (Know This for Interview)

| Aspect | Sliding Window | Token Bucket | Leaky Bucket |
|---|---|---|---|
| Memory per client | O(N) — N timestamps | O(1) — 2 fields | O(1) — 2 fields |
| Burst handling | Strict — counts exact window | Allows burst up to capacity | Smooths to constant rate |
| Use case | Strict rate enforcement | APIs allowing occasional spikes | Traffic shaping to legacy systems |
| Math.min needed? | No | Yes (cap at capacity) | No (Math.max for floor at 0) |

---

## Cleanup Service (Mention in Interview)

```java
ScheduledExecutorService cleaner = Executors.newScheduledThreadPool(1);
cleaner.scheduleAtFixedRate(() -> {
    long cutoff = System.currentTimeMillis() - 3600_000; // 1 hour
    clientTimestamps.entrySet().removeIf(e -> {
        Deque<Long> ts = e.getValue();
        return ts.isEmpty() || ts.peekLast() < cutoff;
    });
    locks.entrySet().removeIf(e -> !clientTimestamps.containsKey(e.getKey()));
}, 1, 1, TimeUnit.HOURS);
```

---

## Interview-Ready Answer

> "I'd design the rate limiter using the Strategy pattern with a `RateLimiter` interface and three implementations: Sliding Window (accurate, O(N) memory), Token Bucket (efficient, allows bursts), and Leaky Bucket (smooths traffic). For thread safety, I'd use per-client locking — each client gets its own lock object stored in a ConcurrentHashMap, so requests from different clients run in parallel. If you want lock-free, I can use AtomicLong with CAS for the token counter. I'd add a ScheduledExecutorService for cleanup of inactive clients."
