"""
Notification Dispatcher
- Strategy Pattern: NotificationSender (Email / SMS / Push)
- PriorityQueue: HIGH processed before MEDIUM before LOW
- Retry with exponential backoff via threading.Timer
- Chain of Responsibility: fallback Push → SMS → Email
"""

import threading
import time
import uuid
import heapq
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ──────────────────────────────────────────────
#  Enums
# ──────────────────────────────────────────────

class NotificationType(Enum):
    ALERT = "ALERT"
    BOOKING_CONFIRMATION = "BOOKING_CONFIRMATION"
    REMINDER = "REMINDER"
    PROMOTION = "PROMOTION"


class Channel(Enum):
    EMAIL = "EMAIL"
    SMS = "SMS"
    PUSH = "PUSH"


class Priority(Enum):
    HIGH = 1
    MEDIUM = 2
    LOW = 3


class NotifStatus(Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    RETRYING = "RETRYING"


# ──────────────────────────────────────────────
#  Notification (Comparable for priority queue)
# ──────────────────────────────────────────────

_seq_counter = 0
_seq_lock = threading.Lock()

def _next_seq() -> int:
    global _seq_counter
    with _seq_lock:
        _seq_counter += 1
        return _seq_counter


class Notification:
    def __init__(self, notif_type: NotificationType, recipient: str,
                 message: str, priority: Priority, channel: Channel):
        self.notif_id = uuid.uuid4().hex[:8].upper()
        self.notif_type = notif_type
        self.recipient = recipient
        self.message = message
        self.priority = priority
        self.channel = channel
        self.status = NotifStatus.PENDING
        self.retry_count = 0
        self._seq = _next_seq()

    # Heap ordering: smaller priority.value = higher priority
    def __lt__(self, other: "Notification") -> bool:
        if self.priority.value != other.priority.value:
            return self.priority.value < other.priority.value
        return self._seq < other._seq

    def __str__(self):
        return (f"[{self.notif_id}] {self.notif_type.value} → {self.recipient} "
                f"via {self.channel.value} (priority={self.priority.name}, "
                f"status={self.status.value}, retry={self.retry_count})")


# ──────────────────────────────────────────────
#  Sender Strategy
# ──────────────────────────────────────────────

class NotificationSender(ABC):
    @abstractmethod
    def send(self, notification: Notification) -> bool:
        pass

    @property
    @abstractmethod
    def channel(self) -> Channel:
        pass


class EmailSender(NotificationSender):
    def send(self, n: Notification) -> bool:
        import random
        success = random.random() > 0.1
        status = "✓" if success else "✗"
        print(f"  [EMAIL] {status} to {n.recipient}: {n.message[:40]}")
        return success

    @property
    def channel(self) -> Channel:
        return Channel.EMAIL


class SmsSender(NotificationSender):
    def send(self, n: Notification) -> bool:
        import random
        success = random.random() > 0.2
        status = "✓" if success else "✗"
        print(f"  [SMS]   {status} to {n.recipient}: {n.message[:40]}")
        return success

    @property
    def channel(self) -> Channel:
        return Channel.SMS


class PushSender(NotificationSender):
    def send(self, n: Notification) -> bool:
        import random
        success = random.random() > 0.3
        status = "✓" if success else "✗"
        print(f"  [PUSH]  {status} to {n.recipient}: {n.message[:40]}")
        return success

    @property
    def channel(self) -> Channel:
        return Channel.PUSH


# ──────────────────────────────────────────────
#  Retry Policy
# ──────────────────────────────────────────────

class RetryPolicy:
    def __init__(self, max_retries: int, base_delay_ms: float):
        self.max_retries = max_retries
        self.base_delay_ms = base_delay_ms

    def can_retry(self, n: Notification) -> bool:
        return n.retry_count < self.max_retries

    def next_delay_seconds(self, n: Notification) -> float:
        return (self.base_delay_ms / 1000) * (2 ** n.retry_count)


# ──────────────────────────────────────────────
#  Router
# ──────────────────────────────────────────────

_DEFAULT_ROUTES: dict[NotificationType, list[Channel]] = {
    NotificationType.ALERT:               [Channel.PUSH, Channel.SMS, Channel.EMAIL],
    NotificationType.BOOKING_CONFIRMATION:[Channel.EMAIL, Channel.PUSH],
    NotificationType.REMINDER:            [Channel.PUSH, Channel.SMS],
    NotificationType.PROMOTION:           [Channel.EMAIL],
}

_FALLBACK_CHAINS: dict[Channel, list[Channel]] = {
    Channel.PUSH:  [Channel.PUSH, Channel.SMS, Channel.EMAIL],
    Channel.SMS:   [Channel.SMS, Channel.EMAIL],
    Channel.EMAIL: [Channel.EMAIL],
}

_DEFAULT_PRIORITY: dict[NotificationType, Priority] = {
    NotificationType.ALERT:               Priority.HIGH,
    NotificationType.BOOKING_CONFIRMATION:Priority.HIGH,
    NotificationType.REMINDER:            Priority.MEDIUM,
    NotificationType.PROMOTION:           Priority.LOW,
}


class NotificationRouter:
    def __init__(self):
        self._user_prefs: dict[str, set[Channel]] = {}

    def set_user_preference(self, user_id: str, channels: set[Channel]):
        self._user_prefs[user_id] = channels

    def route(self, notif_type: NotificationType, user_id: str) -> Channel:
        candidates = _DEFAULT_ROUTES.get(notif_type, [Channel.EMAIL])
        allowed = self._user_prefs.get(user_id)
        for ch in candidates:
            if allowed is None or ch in allowed:
                return ch
        return candidates[0]

    def fallback_chain(self, channel: Channel) -> list[Channel]:
        return _FALLBACK_CHAINS.get(channel, [channel])


# ──────────────────────────────────────────────
#  Factory
# ──────────────────────────────────────────────

class NotificationFactory:
    def __init__(self, router: NotificationRouter):
        self._router = router

    def create(self, notif_type: NotificationType, recipient: str,
               message: str, priority: Priority = None) -> Notification:
        channel = self._router.route(notif_type, recipient)
        p = priority or _DEFAULT_PRIORITY.get(notif_type, Priority.MEDIUM)
        return Notification(notif_type, recipient, message, p, channel)


# ──────────────────────────────────────────────
#  Priority Queue (thread-safe wrapper around heapq)
# ──────────────────────────────────────────────

class PriorityNotifQueue:
    def __init__(self):
        self._heap: list[Notification] = []
        self._cond = threading.Condition()

    def put(self, n: Notification):
        with self._cond:
            heapq.heappush(self._heap, n)
            self._cond.notify()

    def poll(self, timeout: float = 1.0) -> Optional[Notification]:
        with self._cond:
            if not self._heap:
                self._cond.wait(timeout)
            if self._heap:
                return heapq.heappop(self._heap)
            return None

    def size(self) -> int:
        return len(self._heap)


# ──────────────────────────────────────────────
#  Dispatcher
# ──────────────────────────────────────────────

class NotificationDispatcher:
    def __init__(self, router: NotificationRouter, retry_policy: RetryPolicy,
                 num_workers: int = 2):
        self._queue = PriorityNotifQueue()
        self._senders: dict[Channel, NotificationSender] = {}
        self._router = router
        self._retry = retry_policy
        self._running = False
        self._workers: list[threading.Thread] = []
        self._num_workers = num_workers

    def register_sender(self, sender: NotificationSender):
        self._senders[sender.channel] = sender

    def enqueue(self, n: Notification):
        n.status = NotifStatus.PENDING
        self._queue.put(n)
        print(f"  [ENQUEUE] {n}")

    def start(self):
        self._running = True
        for i in range(self._num_workers):
            t = threading.Thread(target=self._worker_loop, args=(i,), daemon=True)
            t.start()
            self._workers.append(t)
        print(f"  [START] Dispatcher started with {self._num_workers} workers")

    def _worker_loop(self, worker_id: int):
        while self._running:
            n = self._queue.poll(timeout=1.0)
            if n:
                print(f"  [Worker-{worker_id}] Processing: {n}")
                self._dispatch(n)

    def _dispatch(self, n: Notification):
        sender = self._senders.get(n.channel)
        if not sender:
            n.status = NotifStatus.FAILED
            return

        if sender.send(n):
            n.status = NotifStatus.SENT
            print(f"  [SENT] {n.notif_id} ✅")
            return

        if self._retry.can_retry(n):
            n.retry_count += 1
            n.status = NotifStatus.RETRYING
            delay = self._retry.next_delay_seconds(n)
            print(f"  [RETRY] #{n.retry_count} for {n.notif_id} in {delay:.1f}s")
            t = threading.Timer(delay, lambda: self._queue.put(n))
            t.daemon = True
            t.start()
        else:
            self._attempt_fallback(n)

    def _attempt_fallback(self, n: Notification):
        chain = self._router.fallback_chain(n.channel)
        for ch in chain:
            if ch == n.channel:
                continue
            sender = self._senders.get(ch)
            if not sender:
                continue
            print(f"  [FALLBACK] {n.channel.value} → {ch.value} for {n.notif_id}")
            n.channel = ch
            if sender.send(n):
                n.status = NotifStatus.SENT
                print(f"  [SENT] {n.notif_id} via fallback ✅")
                return
        n.status = NotifStatus.FAILED
        print(f"  [FAILED] {n.notif_id} ❌ all channels exhausted")

    def shutdown(self):
        self._running = False
        for t in self._workers:
            t.join(timeout=2)
        print("  [SHUTDOWN] Dispatcher stopped")


# ──────────────────────────────────────────────
#  Demo
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import random
    random.seed(99)

    router = NotificationRouter()
    router.set_user_preference("user-101", {Channel.PUSH, Channel.EMAIL})
    router.set_user_preference("user-202", {Channel.SMS, Channel.EMAIL})

    retry_policy = RetryPolicy(max_retries=2, base_delay_ms=200)
    dispatcher = NotificationDispatcher(router, retry_policy, num_workers=2)
    dispatcher.register_sender(EmailSender())
    dispatcher.register_sender(SmsSender())
    dispatcher.register_sender(PushSender())

    factory = NotificationFactory(router)
    dispatcher.start()
    print()

    notifications = [
        factory.create(NotificationType.ALERT, "user-101", "High heart rate detected!"),
        factory.create(NotificationType.BOOKING_CONFIRMATION, "user-202", "Session confirmed for 6 PM"),
        factory.create(NotificationType.REMINDER, "user-101", "Log your meals today"),
        factory.create(NotificationType.PROMOTION, "user-202", "50% off HealthifyMe Pro!"),
        factory.create(NotificationType.ALERT, "user-101", "Calorie goal exceeded by 300 kcal"),
    ]

    for n in notifications:
        dispatcher.enqueue(n)

    time.sleep(3)
    dispatcher.shutdown()
