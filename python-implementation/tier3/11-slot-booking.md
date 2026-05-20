# 11 — Slot Booking System (Python Implementation)

**File:** `slot_booking.py`  
**Tier:** 3

---

## Problem Statement

Design a coach/health-session slot booking system where coaches generate available time slots and users can book them concurrently. No two users should be able to book the same slot.

---

## Design Patterns Used

| Pattern | Where | Why |
|---|---|---|
| **Strategy** | `SlotGenerationStrategy` ABC → `FixedDurationSlotStrategy` | Add custom slot patterns (irregular hours, break times) without changing `SlotService` |
| **Observer** | `BookingObserver` → `CoachNotificationListener`, `UserNotificationListener` | Decouple booking events from notification logic |

---

## Class Structure

```
SlotStatus  (Enum): AVAILABLE, LOCKED, BOOKED, CANCELLED
BookingStatus (Enum): CONFIRMED, CANCELLED, COMPLETED, NO_SHOW
BookingResult (Enum): SUCCESS, SLOT_UNAVAILABLE, INVALID_SLOT

Coach(coach_id, name, specialization, work_start, work_end, slot_duration_minutes, buffer_minutes)
User(user_id, name, timezone)
TimeSlot(slot_id, coach, start, end)   — owns threading.Lock
Booking(booking_id, user, coach, time_slot, status)

SlotGenerationStrategy (ABC)
└── FixedDurationSlotStrategy          — generates slots between work_start and work_end

SlotService                            — generate_slots / get_available_slots / range queries
BookingService                         — book() / cancel() / observer notifications
```

---

## Slot Generation — Strategy Pattern

`FixedDurationSlotStrategy` generates non-overlapping slots with a buffer between them:

```python
def generate(self, coach: Coach, target_date: date) -> list[TimeSlot]:
    slots = []
    current = datetime.combine(target_date, coach.work_start)
    end_of_day = datetime.combine(target_date, coach.work_end)
    duration = timedelta(minutes=coach.slot_duration_minutes)
    buffer   = timedelta(minutes=coach.buffer_minutes)

    while current + duration <= end_of_day:
        slot_end = current + duration
        slots.append(TimeSlot(slot_id, coach, current, slot_end))
        current = slot_end + buffer   # skip buffer before next slot
    return slots
```

For a coach working 09:00–11:00 with 30-min slots and 5-min buffer:  
`09:00–09:30, 09:35–10:05, 10:10–10:40, 10:45–11:15` ... stops when `current + duration > end_of_day`.

---

## Concurrency — Pessimistic Locking per Slot

Each `TimeSlot` owns a `threading.Lock`. The `book()` method acquires it and checks-then-updates atomically:

```python
def book(self, user, coach, slot) -> BookingResult:
    with slot._lock:                              # pessimistic lock
        if slot.status != SlotStatus.AVAILABLE:
            return BookingResult.SLOT_UNAVAILABLE

        slot.status = SlotStatus.LOCKED           # intermediate state
        booking = Booking(booking_id, user, coach, slot)
        slot.status = SlotStatus.BOOKED           # finalise
        self._bookings[booking_id] = booking

        self._notify(booking, created=True)
        return BookingResult.SUCCESS
```

The `LOCKED` intermediate state is visible only while the thread holds the lock — it's a defensive marker in case of future multi-step transactions.

---

## Race Condition Demo — `threading.Barrier`

The demo uses `threading.Barrier(2)` to force both threads to start simultaneously, reliably demonstrating that only one succeeds:

```python
barrier = threading.Barrier(2)

def book_for(user):
    barrier.wait()           # both threads pause here until both have called wait()
    result = booking_svc.book(user, coach, target)
    results[user.name] = result

t1 = threading.Thread(target=book_for, args=(alice,))
t2 = threading.Thread(target=book_for, args=(bob,))
t1.start(); t2.start()
t1.join(); t2.join()
# Exactly one of Alice/Bob gets SUCCESS, the other gets SLOT_UNAVAILABLE
```

---

## Cancellation — Re-acquiring Lock

Cancellation also acquires the slot lock to restore `AVAILABLE` atomically:

```python
def cancel(self, booking_id: str) -> BookingResult:
    booking = self._bookings.get(booking_id)
    if not booking:
        return BookingResult.INVALID_SLOT

    with booking.time_slot._lock:
        booking.cancel()                               # sets status + cancelled_at
        booking.time_slot.status = SlotStatus.AVAILABLE
        self._notify(booking, created=False)
        return BookingResult.SUCCESS
```

---

## Range Query — Available Slots in Time Window

```python
def get_available_in_range(self, coach_id, from_dt, to_dt):
    return [s for s in self._slots.get(coach_id, [])
            if s.status == SlotStatus.AVAILABLE
            and from_dt <= s.start < to_dt]
```

Slots are stored sorted by `start` time (insertion is followed by `sort(key=lambda s: s.start)`), so a binary search could replace the linear scan for large slot counts — mention this as an optimisation.

---

## Overlap Prevention

`SlotService._has_overlap` prevents generating a new slot that overlaps with an existing BOOKED or LOCKED slot:

```python
def _has_overlap(self, coach_id, start, end) -> bool:
    for slot in self._slots.get(coach_id, []):
        if slot.status in (SlotStatus.BOOKED, SlotStatus.LOCKED):
            if slot.overlaps_with(start, end):
                return True
    return False
```

`TimeSlot.overlaps_with(other_start, other_end)` uses the standard interval-overlap check: `self.start < other_end and other_start < self.end`.

---

## Python vs Java Key Differences

| Concern | Java | Python |
|---|---|---|
| `synchronized` | `synchronized(slot) { ... }` | `with slot._lock:` |
| `TreeMap` range query | `subMap(from, to)` | Sorted list + list comprehension |
| `LocalDateTime` | `LocalDateTime.of(date, time)` | `datetime.combine(date, time)` |
| `java.util.concurrent.Barrier` | `CyclicBarrier(2)` | `threading.Barrier(2)` |

---

## Interview Talking Points

1. **Why pessimistic locking instead of optimistic?** — Slot booking has high contention for popular slots. Optimistic locking (check-without-lock, then CAS) would cause many retries. Pessimistic locking gives a deterministic outcome in one attempt.
2. **Why `LOCKED` intermediate state?** — In a real system, the `LOCKED → BOOKED` transition might involve an external payment call. `LOCKED` prevents other users from booking while payment is in progress, while not yet permanently committing the slot.
3. **TimeZone handling** — `User.timezone` stores the user's timezone string. Slots are stored in coach's local time. For display, convert using `ZoneInfo(user.timezone)` (Python 3.9+). The booking logic operates on UTC-aware datetimes in production.
4. **Scale** — Per-slot locking scales well horizontally. Each slot is an independent resource; locks on different slots never contend. For distributed systems, use Redis `SETNX` (set if not exists) as the distributed equivalent of `threading.Lock`.
