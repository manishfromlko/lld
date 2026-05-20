# 08 — Notification Dispatcher (Python Implementation)

**File:** `notification_dispatcher.py`  
**Tier:** 2

---

## Problem Statement

Design a priority-based notification dispatcher that sends messages via Email / SMS / Push, retries on failure with exponential backoff, and falls back to alternative channels when all retries are exhausted.

---

## Design Patterns Used

| Pattern | Where | Why |
|---|---|---|
| **Strategy** | `NotificationSender` ABC → `EmailSender`, `SmsSender`, `PushSender` | Swap delivery channels without changing dispatcher logic |
| **Chain of Responsibility** | `_attempt_fallback()` walks the fallback channel chain | Each channel tries next if current fails |
| **Factory** | `NotificationFactory.create()` | Picks channel and priority from type + user preferences |
| **Observer** (implicit) | Worker threads react to queue events | Producers and workers are fully decoupled |

---

## Class Structure

```
NotificationType, Channel, Priority, NotifStatus (Enums)

Notification                       — heap-comparable via __lt__
PriorityNotifQueue                 — heapq + threading.Condition (thread-safe)
NotificationSender (ABC)
├── EmailSender
├── SmsSender
└── PushSender

RetryPolicy                        — can_retry() + next_delay_seconds() (exponential)
NotificationRouter                 — type → channel mapping + user preference override
NotificationFactory                — creates Notification with correct channel/priority
NotificationDispatcher             — worker threads + retry + fallback
```

---

## Priority Queue — heapq + Condition

Python's `heapq` is a min-heap. `Notification.__lt__` makes HIGH priority (value=1) sort before MEDIUM (2) before LOW (3). A sequence number breaks ties (FIFO within same priority):

```python
def __lt__(self, other):
    if self.priority.value != other.priority.value:
        return self.priority.value < other.priority.value
    return self._seq < other._seq   # FIFO within same priority
```

The queue is a `threading.Condition`-wrapped heap:

```python
def put(self, n):
    with self._cond:
        heapq.heappush(self._heap, n)
        self._cond.notify()       # wake one waiting worker

def poll(self, timeout=1.0):
    with self._cond:
        if not self._heap:
            self._cond.wait(timeout)
        return heapq.heappop(self._heap) if self._heap else None
```

---

## Retry — Exponential Backoff via `threading.Timer`

```python
def _dispatch(self, n: Notification):
    if sender.send(n):
        n.status = NotifStatus.SENT; return

    if self._retry.can_retry(n):
        n.retry_count += 1
        delay = base_delay_ms / 1000 * (2 ** n.retry_count)
        threading.Timer(delay, lambda: self._queue.put(n)).start()
    else:
        self._attempt_fallback(n)
```

`threading.Timer` fires the lambda after `delay` seconds on a daemon thread, re-enqueuing the notification for another worker to pick up. Backoff sequence: 0.2s → 0.4s → 0.8s → ...

---

## Fallback — Chain of Responsibility

```python
_FALLBACK_CHAINS = {
    Channel.PUSH:  [Channel.PUSH, Channel.SMS, Channel.EMAIL],
    Channel.SMS:   [Channel.SMS, Channel.EMAIL],
    Channel.EMAIL: [Channel.EMAIL],
}

def _attempt_fallback(self, n: Notification):
    for ch in self._router.fallback_chain(n.channel):
        if ch == n.channel: continue
        sender = self._senders.get(ch)
        if sender and sender.send(n):
            n.status = NotifStatus.SENT; return
    n.status = NotifStatus.FAILED
```

Each channel in the chain tries to send. The first success stops the chain. If all fail, the notification is marked `FAILED`.

---

## Routing — User Preferences

```python
class NotificationRouter:
    def route(self, notif_type, user_id) -> Channel:
        candidates = _DEFAULT_ROUTES[notif_type]   # ordered preference
        allowed = self._user_prefs.get(user_id)    # user's opt-in channels
        for ch in candidates:
            if allowed is None or ch in allowed:
                return ch
        return candidates[0]   # fallback to default
```

Default routes encode business rules (ALERT → PUSH first). User preferences filter which channels are allowed.

---

## Worker Thread Pool

```python
def start(self):
    for i in range(self._num_workers):
        t = threading.Thread(target=self._worker_loop, args=(i,), daemon=True)
        t.start()

def _worker_loop(self, worker_id):
    while self._running:
        n = self._queue.poll(timeout=1.0)   # blocks up to 1s
        if n:
            self._dispatch(n)
```

Multiple workers process notifications in parallel. The priority queue ensures HIGH-priority items are always dispatched before LOW-priority ones, regardless of enqueue order.

---

## Python vs Java Key Differences

| Concern | Java | Python |
|---|---|---|
| Priority queue | `PriorityBlockingQueue` | `heapq` + `threading.Condition` |
| Comparable | `implements Comparable` | `__lt__` method |
| Scheduled retry | `ScheduledExecutorService` | `threading.Timer` |
| Interface | `interface NotificationSender` | `ABC` + `@abstractmethod` |

---

## Interview Talking Points

1. **Why `heapq` + `Condition` instead of `queue.PriorityQueue`?** — `queue.PriorityQueue` is thread-safe but doesn't expose a timed-wait poll. The custom wrapper gives `poll(timeout)` semantics needed to let workers shut down cleanly.
2. **Sequence number for tie-breaking** — Without it, Python would compare `Notification` objects on a second field (which might not be comparable). The monotonic sequence number guarantees total ordering within the same priority.
3. **Retry re-enqueue vs inline retry** — Re-enqueuing back into the priority queue (via `Timer`) means a HIGH-priority notification that was retrying doesn't block the worker thread during the backoff delay. Workers stay free to process other notifications.
4. **Fallback ordering** — PUSH → SMS → EMAIL is the typical fallback because push is cheapest and fastest. SMS has cost per message. Email is a last resort for time-sensitive alerts.
