# 05 — Movie Ticket Booking (Python Implementation)

**File:** `movie_ticket_booking.py`  
**Tier:** 2

---

## Problem Statement

Design a concurrent seat-booking system where multiple users can browse seats, temporarily lock them during payment, and either confirm or cancel the booking. No two users should end up with the same seat.

---

## Design Patterns Used

| Pattern | Where | Why |
|---|---|---|
| **Strategy** | `PaymentStrategy` ABC → `UPIPayment`, `WalletPayment` | Swap payment providers without changing `BookingService` |
| **Observer** | `SeatObserver` → `UserNotificationObserver` | Decouple seat-status change events from notification logic |
| **Factory** | `create_show(...)` helper | Wires together `Movie`, `Show`, `Theatre`, and pre-populated `Seat` list |

---

## Class Structure

```
Movie(movie_id, title, duration_mins)
Theatre(theatre_id, name)
Show(show_id, movie, theatre, show_time, seats)
Seat(seat_id, row, category)          — owns threading.Lock
Booking(booking_id, user, show, seats, status)

PaymentStrategy (ABC)
├── UPIPayment
└── WalletPayment

SeatObserver (ABC)
└── UserNotificationObserver

BookingService
├── initiate_booking()   — tryLock seats + schedule timeout
├── confirm_booking()    — process payment → CONFIRMED
└── cancel_booking()     — release locks → AVAILABLE
```

---

## Concurrency — Pessimistic Locking with tryLock

Each `Seat` owns a `threading.Lock`. Booking attempts use **non-blocking acquire** (Python's equivalent of Java's `tryLock(0)`):

```python
def try_lock(self) -> bool:
    acquired = self._lock.acquire(blocking=False)
    if acquired:
        self.status = SeatStatus.LOCKED
    return acquired
```

### Deadlock Prevention — Consistent Lock Ordering

When booking multiple seats, always lock them in sorted order by `seat_id`:

```python
seats_sorted = sorted(seats, key=lambda s: s.seat_id)
locked = []
for seat in seats_sorted:
    if not seat.try_lock():
        # rollback already-locked seats
        for s in locked:
            s.release()
        return BookingResult.SEATS_UNAVAILABLE
    locked.append(seat)
```

If two users try to book seats A and B simultaneously, both acquire locks in the same order (A first, then B). This eliminates the circular-wait condition that causes deadlocks.

---

## Lock Timeout — Auto-Release via `threading.Timer`

After locking seats, a `threading.Timer` is scheduled. If payment is not confirmed within the timeout, seats are automatically released:

```python
def _schedule_timeout(self, booking: Booking):
    def expire():
        if booking.status == BookingStatus.PENDING:
            self.cancel_booking(booking.booking_id)

    t = threading.Timer(LOCK_TIMEOUT_SECONDS, expire)
    t.daemon = True
    t.start()
    self._timers[booking.booking_id] = t
```

On `confirm_booking`, the timer is cancelled before it fires.

---

## Observer — Seat Availability Notifications

```python
class SeatObserver(ABC):
    def on_seat_locked(self, seat, user): ...
    def on_seat_released(self, seat): ...
    def on_seat_booked(self, seat, user): ...

class UserNotificationObserver(SeatObserver):
    def on_seat_booked(self, seat, user):
        print(f"[EMAIL] {user}: Seat {seat.seat_id} confirmed")
```

`BookingService` notifies all registered observers on every status change.

---

## Python vs Java Key Differences

| Concern | Java | Python |
|---|---|---|
| tryLock | `lock.tryLock(0, TimeUnit.SECONDS)` | `lock.acquire(blocking=False)` |
| Scheduled task | `ScheduledExecutorService` | `threading.Timer` |
| Interface | `interface PaymentStrategy` | `ABC` + `@abstractmethod` |
| Enum with fields | `enum BookingStatus` | `class BookingStatus(Enum)` |

---

## Booking Flow

```
1. initiate_booking(user, show, seats)
   → sort seats → try_lock each → schedule timeout → return Booking(PENDING)

2. confirm_booking(booking_id, payment_strategy)
   → cancel timer → process payment
   → if success: seats → BOOKED, booking → CONFIRMED, notify observers
   → if fail:    release locks, booking → PAYMENT_FAILED

3. cancel_booking(booking_id)
   → release all seat locks → seats → AVAILABLE
   → booking → CANCELLED → notify observers
```

---

## Interview Talking Points

1. **Why sort seats before locking?** — Classic deadlock prevention. Two threads locking resources in different orders can deadlock (Thread-1 holds A, waits for B; Thread-2 holds B, waits for A). Consistent ordering breaks the circular wait.
2. **Why `blocking=False` instead of a timed lock?** — Fail-fast is better UX. Rather than waiting an unknown time for another user to release a seat, tell the current user immediately that those seats are taken.
3. **Timer cancellation on confirm** — The `threading.Timer` object exposes `.cancel()`. Always cancel before marking seats BOOKED to avoid a race where the timer fires just as confirmation completes.
4. **What if payment service is slow?** — The timer handles this. If payment takes longer than `LOCK_TIMEOUT_SECONDS`, the seats are released so other users aren't blocked indefinitely.
