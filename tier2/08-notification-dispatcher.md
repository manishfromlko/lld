# 08 — Notification Dispatcher

**Priority:** TIER 2 — HealthifyMe domain relevant (health coach notifications)

---

## Problem Statement

Design a notification system that dispatches notifications through multiple channels (Email, SMS, Push) with priority ordering, retry logic, and configurable channel selection per notification type.

The system must support:
- **Multi-channel delivery** — Email, SMS, and Push notifications via pluggable senders.
- **Priority-based ordering** — HIGH priority notifications are dispatched before MEDIUM or LOW.
- **Retry with exponential backoff** — Transient failures are retried up to a configurable limit.
- **Fallback chain** — If Push fails, try SMS; if SMS fails, try Email.
- **Concurrency** — Multiple worker threads consume from a shared priority queue.
- **Configurable routing** — Notification type + user preference determines the channel.

---

## Clarification Questions

| # | Question | Why It Matters |
|---|----------|----------------|
| 1 | **Which channels are supported?** Email, SMS, Push — or are there future channels like WhatsApp / In-App? | Determines how pluggable the sender abstraction needs to be. |
| 2 | **How is priority determined?** Is it per notification type (ALERT = HIGH) or caller-specified? | Affects whether priority is fixed in config or passed at creation time. |
| 3 | **What is the retry policy?** Max retries, backoff strategy (fixed, exponential, jitter)? | Drives `RetryPolicy` design and scheduler choice. |
| 4 | **Are message templates used?** Or is the message body passed as raw text? | Determines if we need a `TemplateEngine` component. |
| 5 | **Do users have channel preferences?** e.g., "Don't SMS me, only Push." | Affects `NotificationRouter` — must consult user preferences. |
| 6 | **Is there a rate limit per channel or per user?** e.g., max 3 SMS/hour. | May require a token-bucket or sliding-window limiter per channel. |
| 7 | **Do we need strict ordering within the same priority?** FIFO among same-priority notifications? | `PriorityBlockingQueue` is not stable — may need a tie-breaking sequence number. |

---

## Entities

```
┌─────────────────────────────────────────────────────────────────┐
│                      NotificationDispatcher                     │
│  (orchestrator — PriorityBlockingQueue + worker thread pool)    │
│                                                                 │
│  ┌──────────────────┐    ┌──────────────────────────────────┐   │
│  │  PriorityBlocking │    │  Worker Threads (poll + dispatch)│   │
│  │  Queue<Notif>     │───▶│  ┌────────────────────────────┐ │   │
│  └──────────────────┘    │  │   NotificationRouter        │ │   │
│                          │  │   (type + pref → channel)   │ │   │
│                          │  └─────────┬──────────────────┘ │   │
│                          │            │                     │   │
│                          │  ┌─────────▼──────────────────┐ │   │
│                          │  │  NotificationSender        │ │   │
│                          │  │  (Strategy: Email/SMS/Push)│ │   │
│                          │  └─────────┬──────────────────┘ │   │
│                          │            │ on failure          │   │
│                          │  ┌─────────▼──────────────────┐ │   │
│                          │  │  RetryPolicy               │ │   │
│                          │  │  (exponential backoff)     │ │   │
│                          │  └────────────────────────────┘ │   │
│                          └──────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### Enums

| Enum | Values |
|------|--------|
| `NotificationType` | `BOOKING_CONFIRMATION`, `REMINDER`, `ALERT`, `PROMOTION` |
| `NotificationChannel` | `EMAIL`, `SMS`, `PUSH` |
| `NotificationPriority` | `HIGH(1)`, `MEDIUM(2)`, `LOW(3)` |
| `NotificationStatus` | `PENDING`, `SENT`, `FAILED`, `RETRYING` |

### Core Classes

| Class / Interface | Responsibility |
|-------------------|----------------|
| `Notification` | Immutable value object — id, type, recipient, message, priority, channel, status, retryCount. Implements `Comparable` for priority ordering. |
| `NotificationSender` | **Strategy interface** — `boolean send(Notification n)`. Implementations: `EmailSender`, `SmsSender`, `PushSender`. |
| `NotificationRouter` | Determines which channel(s) to use based on notification type + user preference. |
| `NotificationDispatcher` | Orchestrator — accepts notifications, enqueues into `PriorityBlockingQueue`, worker threads poll and dispatch. |
| `NotificationFactory` | Creates `Notification` objects with sensible defaults. |
| `RetryPolicy` | Encapsulates maxRetries + backoff calculation. |

---

## Design Patterns

### 1. Strategy — `NotificationSender`

Swap the delivery mechanism without changing the dispatcher.

```
NotificationSender
├── EmailSender
├── SmsSender
└── PushSender
```

The dispatcher holds a `Map<NotificationChannel, NotificationSender>` and picks the right sender at runtime.

### 2. Observer — Event-Driven Trigger

Domain events (e.g., `BookingConfirmedEvent`) trigger notification creation. The dispatcher observes these events and enqueues notifications.

```
BookingService  ──fires──▶  BookingConfirmedEvent
                                    │
                         NotificationObserver (listener)
                                    │
                          creates Notification
                                    │
                         NotificationDispatcher.enqueue()
```

### 3. Factory — `NotificationFactory`

Centralises creation logic — sets default priority, channel routing, and message template based on `NotificationType`.

### 4. Template Method — Base Sender

```
AbstractNotificationSender
  ├── validate(notification)      // common
  ├── formatMessage(notification) // subclass overrides
  ├── doSend(notification)        // subclass overrides
  └── logResult(notification)     // common
```

`send()` in the abstract class calls these steps in order. Subclasses override `formatMessage` and `doSend`.

### 5. Decorator — Logging / Metrics Wrapper

`LoggingNotificationSender` wraps any `NotificationSender` and logs before/after without modifying the sender itself.

### 6. Chain of Responsibility — Fallback Chain

If Push fails → try SMS → if SMS fails → try Email. Each sender in the chain either handles it or delegates to the next.

```
PushSender ──fails──▶ SmsSender ──fails──▶ EmailSender
```

---

## SOLID Principles

| Principle | How It's Applied |
|-----------|-----------------|
| **S — Single Responsibility** | `NotificationDispatcher` only orchestrates queue + workers. `NotificationSender` only sends. `NotificationRouter` only decides the channel. `RetryPolicy` only computes backoff. |
| **O — Open/Closed** | New channels (e.g., WhatsApp) are added by implementing `NotificationSender` — no changes to `NotificationDispatcher`. |
| **L — Liskov Substitution** | Any `NotificationSender` implementation can replace another — `EmailSender`, `SmsSender`, `PushSender` are interchangeable. |
| **I — Interface Segregation** | `NotificationSender` has a single method `send()`. No fat interfaces. If templating is needed, a separate `TemplateEngine` interface is used. |
| **D — Dependency Inversion** | `NotificationDispatcher` depends on `NotificationSender` (abstraction), not on `EmailSender` (concrete). Senders are injected via constructor or registry map. |

---

## Core Algorithm

```
1. Event occurs (e.g., booking confirmed)
         │
2. NotificationRouter determines channel(s)
   based on NotificationType + user preferences
         │
3. NotificationFactory creates Notification
   with correct priority, channel, message
         │
4. Notification enqueued into PriorityBlockingQueue
   (ordered by priority; ties broken by sequence number)
         │
5. Worker threads (thread pool) poll from queue
         │
6. Worker calls sender.send(notification)
         │
    ┌────┴─────┐
  SUCCESS     FAILURE
    │           │
  mark SENT   retryCount < maxRetries?
    │         ┌──YES──┐       ┌──NO──┐
  done     schedule retry   try fallback chain
           with backoff     Push → SMS → Email
           (1s, 2s, 4s…)        │
              │             all failed → mark FAILED
           re-enqueue
```

### Retry Backoff Formula

```
delay = baseDelay × 2^(retryCount)

Example (baseDelay = 1s):
  Retry 0 → 1s
  Retry 1 → 2s
  Retry 2 → 4s
  Retry 3 → 8s
```

---

## Data Structure Choices

| Data Structure | Usage | Why |
|---------------|-------|-----|
| `PriorityBlockingQueue<Notification>` | Main dispatch queue | Thread-safe, blocks on empty, auto-orders by `Comparable` (priority). No external locking needed. |
| `ConcurrentHashMap<NotificationChannel, NotificationSender>` | Channel → sender registry | O(1) lookup, thread-safe reads from worker threads. |
| `ScheduledExecutorService` | Retry scheduling | `schedule(task, delay, unit)` handles exponential backoff without manual `Thread.sleep`. |
| `AtomicLong` | Sequence number generator | Tie-breaker for same-priority notifications to ensure FIFO ordering. Lock-free. |

### If Interviewer Says "No PriorityBlockingQueue"

Use a `PriorityQueue` (min-heap) protected by `synchronized` blocks, with `wait()` when empty and `notifyAll()` on insert:

```java
synchronized (lock) {
    while (queue.isEmpty()) lock.wait();
    return queue.poll();
}
```

Or use a `TreeMap<CompositeKey, Notification>` where `CompositeKey = (priority, sequenceNumber)` for stable ordering.

---

## Concurrency Strategy

### Primary: `PriorityBlockingQueue` + Fixed Thread Pool

```
Producer Thread(s)            PriorityBlockingQueue           Consumer Thread Pool
  ───offer()───▶             [HIGH, HIGH, MED, LOW]          ◀───take()───
                              (blocks if empty)               (N worker threads)
```

- **Producers** call `dispatcher.enqueue(notification)` — non-blocking `offer()`.
- **Consumers** are `N` threads in `Executors.newFixedThreadPool(N)` — each loops on `queue.take()` (blocking).
- No explicit synchronization needed — `PriorityBlockingQueue` handles it.

### Alternative 1: Custom PriorityQueue + `synchronized` + `wait/notify`

```java
class ManualPriorityQueue<T extends Comparable<T>> {
    private final PriorityQueue<T> heap = new PriorityQueue<>();
    private final Object lock = new Object();

    void enqueue(T item) {
        synchronized (lock) {
            heap.offer(item);
            lock.notifyAll();
        }
    }

    T dequeue() throws InterruptedException {
        synchronized (lock) {
            while (heap.isEmpty()) lock.wait();
            return heap.poll();
        }
    }
}
```

### Alternative 2: Separate Queues Per Priority

```
HIGH   queue  ─── always drained first
MEDIUM queue  ─── drained only when HIGH is empty
LOW    queue  ─── drained only when HIGH and MEDIUM are empty
```

Risk: starvation of LOW priority. Mitigation: after processing `K` HIGH messages, process at least 1 MEDIUM/LOW (weighted fair queuing).

---

## Java Implementation

### Enums

```java
public enum NotificationType {
    BOOKING_CONFIRMATION,
    REMINDER,
    ALERT,
    PROMOTION
}
```

```java
public enum NotificationChannel {
    EMAIL,
    SMS,
    PUSH
}
```

```java
public enum NotificationPriority {
    HIGH(1),
    MEDIUM(2),
    LOW(3);

    private final int level;

    NotificationPriority(int level) {
        this.level = level;
    }

    public int getLevel() {
        return level;
    }
}
```

```java
public enum NotificationStatus {
    PENDING,
    SENT,
    FAILED,
    RETRYING
}
```

### Notification

```java
import java.util.concurrent.atomic.AtomicLong;

public class Notification implements Comparable<Notification> {

    private static final AtomicLong SEQ_GEN = new AtomicLong(0);

    private final String id;
    private final NotificationType type;
    private final String recipient;
    private final String message;
    private final NotificationPriority priority;
    private NotificationChannel channel;
    private NotificationStatus status;
    private int retryCount;
    private final long sequenceNumber;

    public Notification(String id, NotificationType type, String recipient,
                        String message, NotificationPriority priority,
                        NotificationChannel channel) {
        this.id = id;
        this.type = type;
        this.recipient = recipient;
        this.message = message;
        this.priority = priority;
        this.channel = channel;
        this.status = NotificationStatus.PENDING;
        this.retryCount = 0;
        this.sequenceNumber = SEQ_GEN.incrementAndGet();
    }

    @Override
    public int compareTo(Notification other) {
        int cmp = Integer.compare(this.priority.getLevel(), other.priority.getLevel());
        if (cmp != 0) return cmp;
        return Long.compare(this.sequenceNumber, other.sequenceNumber);
    }

    public String getId() { return id; }
    public NotificationType getType() { return type; }
    public String getRecipient() { return recipient; }
    public String getMessage() { return message; }
    public NotificationPriority getPriority() { return priority; }
    public NotificationChannel getChannel() { return channel; }
    public NotificationStatus getStatus() { return status; }
    public int getRetryCount() { return retryCount; }
    public long getSequenceNumber() { return sequenceNumber; }

    public void setChannel(NotificationChannel channel) { this.channel = channel; }
    public void setStatus(NotificationStatus status) { this.status = status; }
    public void incrementRetryCount() { this.retryCount++; }

    @Override
    public String toString() {
        return String.format("[%s] %s → %s via %s (priority=%s, status=%s, retry=%d)",
                id, type, recipient, channel, priority, status, retryCount);
    }
}
```

### NotificationSender — Strategy Interface

```java
public interface NotificationSender {
    boolean send(Notification notification);
    NotificationChannel getChannel();
}
```

### EmailSender

```java
public class EmailSender implements NotificationSender {

    @Override
    public boolean send(Notification notification) {
        System.out.printf("[EMAIL] Sending to %s: %s%n",
                notification.getRecipient(), notification.getMessage());
        // Simulate: 90% success rate
        boolean success = Math.random() > 0.1;
        if (success) {
            System.out.printf("[EMAIL] ✓ Delivered to %s%n", notification.getRecipient());
        } else {
            System.out.printf("[EMAIL] ✗ Failed for %s%n", notification.getRecipient());
        }
        return success;
    }

    @Override
    public NotificationChannel getChannel() {
        return NotificationChannel.EMAIL;
    }
}
```

### SmsSender

```java
public class SmsSender implements NotificationSender {

    @Override
    public boolean send(Notification notification) {
        System.out.printf("[SMS] Sending to %s: %s%n",
                notification.getRecipient(), notification.getMessage());
        boolean success = Math.random() > 0.2;
        if (success) {
            System.out.printf("[SMS] ✓ Delivered to %s%n", notification.getRecipient());
        } else {
            System.out.printf("[SMS] ✗ Failed for %s%n", notification.getRecipient());
        }
        return success;
    }

    @Override
    public NotificationChannel getChannel() {
        return NotificationChannel.SMS;
    }
}
```

### PushSender

```java
public class PushSender implements NotificationSender {

    @Override
    public boolean send(Notification notification) {
        System.out.printf("[PUSH] Sending to %s: %s%n",
                notification.getRecipient(), notification.getMessage());
        boolean success = Math.random() > 0.3;
        if (success) {
            System.out.printf("[PUSH] ✓ Delivered to %s%n", notification.getRecipient());
        } else {
            System.out.printf("[PUSH] ✗ Failed for %s%n", notification.getRecipient());
        }
        return success;
    }

    @Override
    public NotificationChannel getChannel() {
        return NotificationChannel.PUSH;
    }
}
```

### RetryPolicy

```java
public class RetryPolicy {

    private final int maxRetries;
    private final long baseDelayMs;

    public RetryPolicy(int maxRetries, long baseDelayMs) {
        this.maxRetries = maxRetries;
        this.baseDelayMs = baseDelayMs;
    }

    public boolean canRetry(Notification notification) {
        return notification.getRetryCount() < maxRetries;
    }

    public long getNextDelayMs(Notification notification) {
        return baseDelayMs * (1L << notification.getRetryCount());
    }

    public int getMaxRetries() { return maxRetries; }
    public long getBaseDelayMs() { return baseDelayMs; }
}
```

### NotificationRouter

```java
import java.util.*;

public class NotificationRouter {

    private final Map<NotificationType, List<NotificationChannel>> defaultRoutes;
    private final Map<String, Set<NotificationChannel>> userPreferences;

    public NotificationRouter() {
        this.defaultRoutes = new EnumMap<>(NotificationType.class);
        this.userPreferences = new HashMap<>();
        initializeDefaultRoutes();
    }

    private void initializeDefaultRoutes() {
        defaultRoutes.put(NotificationType.ALERT,
                List.of(NotificationChannel.PUSH, NotificationChannel.SMS, NotificationChannel.EMAIL));
        defaultRoutes.put(NotificationType.BOOKING_CONFIRMATION,
                List.of(NotificationChannel.EMAIL, NotificationChannel.PUSH));
        defaultRoutes.put(NotificationType.REMINDER,
                List.of(NotificationChannel.PUSH, NotificationChannel.SMS));
        defaultRoutes.put(NotificationType.PROMOTION,
                List.of(NotificationChannel.EMAIL));
    }

    public void setUserPreference(String userId, Set<NotificationChannel> allowedChannels) {
        userPreferences.put(userId, allowedChannels);
    }

    public NotificationChannel route(NotificationType type, String userId) {
        List<NotificationChannel> candidates = defaultRoutes.getOrDefault(type,
                List.of(NotificationChannel.EMAIL));

        Set<NotificationChannel> userAllowed = userPreferences.get(userId);

        for (NotificationChannel ch : candidates) {
            if (userAllowed == null || userAllowed.contains(ch)) {
                return ch;
            }
        }
        return candidates.get(0);
    }

    public List<NotificationChannel> getFallbackChain(NotificationChannel primary) {
        List<NotificationChannel> chain = new ArrayList<>();
        switch (primary) {
            case PUSH:
                chain.add(NotificationChannel.PUSH);
                chain.add(NotificationChannel.SMS);
                chain.add(NotificationChannel.EMAIL);
                break;
            case SMS:
                chain.add(NotificationChannel.SMS);
                chain.add(NotificationChannel.EMAIL);
                break;
            case EMAIL:
            default:
                chain.add(NotificationChannel.EMAIL);
                break;
        }
        return chain;
    }
}
```

### NotificationFactory

```java
import java.util.UUID;

public class NotificationFactory {

    private final NotificationRouter router;

    public NotificationFactory(NotificationRouter router) {
        this.router = router;
    }

    public Notification create(NotificationType type, String recipient, String message) {
        NotificationPriority priority = resolvePriority(type);
        NotificationChannel channel = router.route(type, recipient);
        String id = UUID.randomUUID().toString().substring(0, 8);
        return new Notification(id, type, recipient, message, priority, channel);
    }

    public Notification create(NotificationType type, String recipient,
                               String message, NotificationPriority priority) {
        NotificationChannel channel = router.route(type, recipient);
        String id = UUID.randomUUID().toString().substring(0, 8);
        return new Notification(id, type, recipient, message, priority, channel);
    }

    private NotificationPriority resolvePriority(NotificationType type) {
        switch (type) {
            case ALERT:                  return NotificationPriority.HIGH;
            case BOOKING_CONFIRMATION:   return NotificationPriority.HIGH;
            case REMINDER:               return NotificationPriority.MEDIUM;
            case PROMOTION:              return NotificationPriority.LOW;
            default:                     return NotificationPriority.MEDIUM;
        }
    }
}
```

### NotificationDispatcher — The Orchestrator

```java
import java.util.*;
import java.util.concurrent.*;

public class NotificationDispatcher {

    private final PriorityBlockingQueue<Notification> queue;
    private final Map<NotificationChannel, NotificationSender> senders;
    private final NotificationRouter router;
    private final RetryPolicy retryPolicy;
    private final ScheduledExecutorService retryScheduler;
    private final ExecutorService workerPool;
    private volatile boolean running;

    public NotificationDispatcher(NotificationRouter router, RetryPolicy retryPolicy,
                                  int workerCount) {
        this.queue = new PriorityBlockingQueue<>();
        this.senders = new ConcurrentHashMap<>();
        this.router = router;
        this.retryPolicy = retryPolicy;
        this.retryScheduler = Executors.newScheduledThreadPool(2);
        this.workerPool = Executors.newFixedThreadPool(workerCount);
        this.running = false;
    }

    public void registerSender(NotificationSender sender) {
        senders.put(sender.getChannel(), sender);
    }

    public void enqueue(Notification notification) {
        notification.setStatus(NotificationStatus.PENDING);
        queue.offer(notification);
        System.out.printf("📥 Enqueued: %s%n", notification);
    }

    public void start() {
        running = true;
        int workerCount = ((ThreadPoolExecutor) workerPool).getCorePoolSize();
        for (int i = 0; i < workerCount; i++) {
            final int workerId = i;
            workerPool.submit(() -> workerLoop(workerId));
        }
        System.out.printf("🚀 Dispatcher started with %d workers%n", workerCount);
    }

    private void workerLoop(int workerId) {
        while (running) {
            try {
                Notification notification = queue.poll(1, TimeUnit.SECONDS);
                if (notification != null) {
                    System.out.printf("  [Worker-%d] Processing: %s%n", workerId, notification);
                    dispatch(notification);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                break;
            }
        }
    }

    private void dispatch(Notification notification) {
        NotificationSender sender = senders.get(notification.getChannel());
        if (sender == null) {
            System.out.printf("  ⚠ No sender for channel %s%n", notification.getChannel());
            notification.setStatus(NotificationStatus.FAILED);
            return;
        }

        boolean success = sender.send(notification);

        if (success) {
            notification.setStatus(NotificationStatus.SENT);
            System.out.printf("  ✅ %s sent successfully%n", notification.getId());
            return;
        }

        if (retryPolicy.canRetry(notification)) {
            notification.incrementRetryCount();
            notification.setStatus(NotificationStatus.RETRYING);
            long delayMs = retryPolicy.getNextDelayMs(notification);
            System.out.printf("  🔄 Scheduling retry #%d for %s in %dms%n",
                    notification.getRetryCount(), notification.getId(), delayMs);
            retryScheduler.schedule(() -> queue.offer(notification),
                    delayMs, TimeUnit.MILLISECONDS);
            return;
        }

        attemptFallback(notification);
    }

    private void attemptFallback(Notification notification) {
        List<NotificationChannel> fallbackChain =
                router.getFallbackChain(notification.getChannel());

        for (NotificationChannel fallbackChannel : fallbackChain) {
            if (fallbackChannel == notification.getChannel()) {
                continue;
            }

            NotificationSender fallbackSender = senders.get(fallbackChannel);
            if (fallbackSender == null) continue;

            System.out.printf("  🔀 Fallback: %s → %s for %s%n",
                    notification.getChannel(), fallbackChannel, notification.getId());
            notification.setChannel(fallbackChannel);
            boolean success = fallbackSender.send(notification);
            if (success) {
                notification.setStatus(NotificationStatus.SENT);
                System.out.printf("  ✅ %s sent via fallback %s%n",
                        notification.getId(), fallbackChannel);
                return;
            }
        }

        notification.setStatus(NotificationStatus.FAILED);
        System.out.printf("  ❌ %s FAILED — all channels exhausted%n", notification.getId());
    }

    public void shutdown() {
        running = false;
        workerPool.shutdown();
        retryScheduler.shutdown();
        try {
            workerPool.awaitTermination(5, TimeUnit.SECONDS);
            retryScheduler.awaitTermination(5, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
        System.out.println("🛑 Dispatcher shut down.");
    }

    public int getQueueSize() {
        return queue.size();
    }
}
```

### Main — Demo

```java
import java.util.Set;

public class NotificationDispatcherDemo {

    public static void main(String[] args) throws InterruptedException {

        // 1. Setup router with user preferences
        NotificationRouter router = new NotificationRouter();
        router.setUserPreference("user-101",
                Set.of(NotificationChannel.PUSH, NotificationChannel.EMAIL));
        router.setUserPreference("user-202",
                Set.of(NotificationChannel.SMS, NotificationChannel.EMAIL));

        // 2. Create retry policy: max 3 retries, 500ms base delay
        RetryPolicy retryPolicy = new RetryPolicy(3, 500);

        // 3. Create dispatcher with 3 worker threads
        NotificationDispatcher dispatcher = new NotificationDispatcher(router, retryPolicy, 3);

        // 4. Register senders
        dispatcher.registerSender(new EmailSender());
        dispatcher.registerSender(new SmsSender());
        dispatcher.registerSender(new PushSender());

        // 5. Create factory
        NotificationFactory factory = new NotificationFactory(router);

        // 6. Start dispatcher
        dispatcher.start();

        // 7. Enqueue notifications of different types and priorities
        dispatcher.enqueue(factory.create(
                NotificationType.ALERT, "user-101",
                "Your heart rate is abnormally high!"));

        dispatcher.enqueue(factory.create(
                NotificationType.BOOKING_CONFIRMATION, "user-202",
                "Your session with Coach Priya is confirmed for 6 PM."));

        dispatcher.enqueue(factory.create(
                NotificationType.REMINDER, "user-101",
                "Don't forget to log your meals today."));

        dispatcher.enqueue(factory.create(
                NotificationType.PROMOTION, "user-202",
                "50% off on annual HealthifyMe Pro subscription!",
                NotificationPriority.LOW));

        dispatcher.enqueue(factory.create(
                NotificationType.ALERT, "user-101",
                "Calorie goal exceeded by 300 kcal."));

        // 8. Let workers process
        Thread.sleep(5000);

        // 9. Graceful shutdown
        dispatcher.shutdown();
    }
}
```

### Expected Output (order may vary due to concurrency)

```
🚀 Dispatcher started with 3 workers
📥 Enqueued: [a1b2c3d4] ALERT → user-101 via PUSH (priority=HIGH, status=PENDING, retry=0)
📥 Enqueued: [e5f6g7h8] BOOKING_CONFIRMATION → user-202 via EMAIL (priority=HIGH, status=PENDING, retry=0)
📥 Enqueued: [i9j0k1l2] REMINDER → user-101 via PUSH (priority=MEDIUM, status=PENDING, retry=0)
📥 Enqueued: [m3n4o5p6] PROMOTION → user-202 via EMAIL (priority=LOW, status=PENDING, retry=0)
📥 Enqueued: [q7r8s9t0] ALERT → user-101 via PUSH (priority=HIGH, status=PENDING, retry=0)
  [Worker-0] Processing: [a1b2c3d4] ...    ← HIGH processed first
  [Worker-1] Processing: [e5f6g7h8] ...    ← HIGH processed first
  [Worker-2] Processing: [q7r8s9t0] ...    ← HIGH processed first
  [Worker-0] Processing: [i9j0k1l2] ...    ← MEDIUM next
  [Worker-1] Processing: [m3n4o5p6] ...    ← LOW last
🛑 Dispatcher shut down.
```

---

## Complexity Analysis

| Operation | Time | Space |
|-----------|------|-------|
| `enqueue()` | O(log n) — heap insertion | O(n) — queue size |
| `take()` / `poll()` | O(log n) — heap extraction | — |
| `dispatch()` | O(1) — map lookup + send | — |
| Retry scheduling | O(1) — `ScheduledExecutorService` | O(r) — pending retries |
| Fallback chain | O(c) — c = number of channels | — |

---

## Edge Cases to Discuss

| Edge Case | Handling |
|-----------|----------|
| All channels fail | Mark as `FAILED`, log for manual review / dead-letter queue. |
| Duplicate notifications | Use idempotency key (notification ID) — sender checks if already sent. |
| Queue full (bounded) | If using bounded queue, `offer()` returns false → apply back-pressure or drop LOW priority. |
| Slow sender blocking workers | Use async I/O or per-sender thread pools to isolate slow channels. |
| Retry storm | Cap total retries in-flight; use jitter in backoff (`delay ± random`) to avoid thundering herd. |
| Shutdown with pending retries | `ScheduledExecutorService.shutdownNow()` cancels pending retries — persist them for recovery. |
| Priority inversion | Sequence number as tie-breaker ensures FIFO within same priority. |

---

## Interview-Ready Answer

> "I'd design the Notification Dispatcher using a **Strategy pattern** for channel-specific senders — `EmailSender`, `SmsSender`, and `PushSender` — all implementing a common `NotificationSender` interface. A `NotificationRouter` maps each notification type plus user preferences to the right channel. Notifications are enqueued into a **`PriorityBlockingQueue`** ordered by priority (with a sequence number tie-breaker for FIFO within the same level). A fixed-size **thread pool** of workers continuously polls from the queue and dispatches via the appropriate sender. On failure, a `RetryPolicy` schedules the notification back into the queue with **exponential backoff** (1s, 2s, 4s…) using a `ScheduledExecutorService`. If retries are exhausted, a **Chain of Responsibility** fallback kicks in: Push → SMS → Email. The entire design is **SOLID** — adding WhatsApp tomorrow means implementing one new `NotificationSender` without touching the dispatcher. For a HealthifyMe context, this handles coach session reminders as HIGH priority Push notifications, promotional offers as LOW priority emails, and health alerts as HIGH priority with aggressive retry and full fallback chains."

---
