"""
Slot Booking System (Coach / Health Session)
- Strategy Pattern: SlotGenerationStrategy
- Pessimistic locking: synchronized on slot object prevents double booking
- Observer Pattern: notify coach and user on booking events
- TreeMap equivalent: SortedDict (or sorted list) for range queries
"""

import threading
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from enum import Enum
from typing import Optional
from zoneinfo import ZoneInfo


# ──────────────────────────────────────────────
#  Enums
# ──────────────────────────────────────────────

class SlotStatus(Enum):
    AVAILABLE = "AVAILABLE"
    LOCKED = "LOCKED"
    BOOKED = "BOOKED"
    CANCELLED = "CANCELLED"


class BookingStatus(Enum):
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    NO_SHOW = "NO_SHOW"


class BookingResult(Enum):
    SUCCESS = "SUCCESS"
    SLOT_UNAVAILABLE = "SLOT_UNAVAILABLE"
    INVALID_SLOT = "INVALID_SLOT"


# ──────────────────────────────────────────────
#  Entities
# ──────────────────────────────────────────────

@dataclass
class Coach:
    coach_id: str
    name: str
    specialization: str
    work_start: time
    work_end: time
    slot_duration_minutes: int = 30
    buffer_minutes: int = 5

    def __str__(self):
        return f"{self.name} ({self.specialization})"


@dataclass
class User:
    user_id: str
    name: str
    timezone: str = "UTC"

    def __str__(self):
        return f"{self.name} [{self.timezone}]"


class TimeSlot:
    def __init__(self, slot_id: str, coach: Coach,
                 start: datetime, end: datetime):
        self.slot_id = slot_id
        self.coach = coach
        self.start = start
        self.end = end
        self.status = SlotStatus.AVAILABLE
        self._lock = threading.Lock()

    def overlaps_with(self, other_start: datetime, other_end: datetime) -> bool:
        return self.start < other_end and other_start < self.end

    def __str__(self):
        return f"[{self.slot_id}] {self.start.strftime('%H:%M')} → {self.end.strftime('%H:%M')} ({self.status.value})"


@dataclass
class Booking:
    booking_id: str
    user: User
    coach: Coach
    time_slot: TimeSlot
    status: BookingStatus = BookingStatus.CONFIRMED
    booked_at: datetime = field(default_factory=datetime.now)
    cancelled_at: Optional[datetime] = None

    def cancel(self):
        self.status = BookingStatus.CANCELLED
        self.cancelled_at = datetime.now()

    def __str__(self):
        return (f"Booking[{self.booking_id}] {self.user.name} with "
                f"{self.coach.name} at {self.time_slot.start.strftime('%H:%M')} "
                f"({self.status.value})")


# ──────────────────────────────────────────────
#  Slot Generation Strategy (Strategy Pattern)
# ──────────────────────────────────────────────

class SlotGenerationStrategy(ABC):
    @abstractmethod
    def generate(self, coach: Coach, target_date: date) -> list[TimeSlot]:
        pass


class FixedDurationSlotStrategy(SlotGenerationStrategy):
    def generate(self, coach: Coach, target_date: date) -> list[TimeSlot]:
        slots = []
        current = datetime.combine(target_date, coach.work_start)
        end_of_day = datetime.combine(target_date, coach.work_end)
        duration = timedelta(minutes=coach.slot_duration_minutes)
        buffer = timedelta(minutes=coach.buffer_minutes)

        while current + duration <= end_of_day:
            slot_end = current + duration
            slot_id = f"SLOT-{uuid.uuid4().hex[:6].upper()}"
            slots.append(TimeSlot(slot_id, coach, current, slot_end))
            current = slot_end + buffer

        return slots


# ──────────────────────────────────────────────
#  Observer (Booking Notifications)
# ──────────────────────────────────────────────

class BookingObserver(ABC):
    @abstractmethod
    def on_booking_created(self, booking: Booking):
        pass

    @abstractmethod
    def on_booking_cancelled(self, booking: Booking):
        pass


class CoachNotificationListener(BookingObserver):
    def on_booking_created(self, booking: Booking):
        print(f"  [COACH] {booking.coach.name}: new booking with {booking.user.name} "
              f"at {booking.time_slot.start.strftime('%H:%M')}")

    def on_booking_cancelled(self, booking: Booking):
        print(f"  [COACH] {booking.coach.name}: booking with {booking.user.name} cancelled")


class UserNotificationListener(BookingObserver):
    def on_booking_created(self, booking: Booking):
        print(f"  [USER]  {booking.user.name}: booking confirmed with "
              f"{booking.coach.name} at {booking.time_slot.start.strftime('%H:%M')}")

    def on_booking_cancelled(self, booking: Booking):
        print(f"  [USER]  {booking.user.name}: your booking at "
              f"{booking.time_slot.start.strftime('%H:%M')} was cancelled")


# ──────────────────────────────────────────────
#  Slot Service
# ──────────────────────────────────────────────

class SlotService:
    def __init__(self, strategy: SlotGenerationStrategy):
        self._strategy = strategy
        # coach_id → sorted list of TimeSlot
        self._slots: dict[str, list[TimeSlot]] = {}

    def generate_slots(self, coach: Coach, target_date: date) -> list[TimeSlot]:
        slots = self._strategy.generate(coach, target_date)
        existing = self._slots.setdefault(coach.coach_id, [])
        for slot in slots:
            if not self._has_overlap(coach.coach_id, slot.start, slot.end):
                existing.append(slot)
        existing.sort(key=lambda s: s.start)
        return slots

    def get_available_slots(self, coach_id: str) -> list[TimeSlot]:
        return [s for s in self._slots.get(coach_id, [])
                if s.status == SlotStatus.AVAILABLE]

    def get_available_in_range(self, coach_id: str,
                                from_dt: datetime, to_dt: datetime) -> list[TimeSlot]:
        return [s for s in self._slots.get(coach_id, [])
                if s.status == SlotStatus.AVAILABLE
                and from_dt <= s.start < to_dt]

    def _has_overlap(self, coach_id: str, start: datetime, end: datetime) -> bool:
        for slot in self._slots.get(coach_id, []):
            if slot.status in (SlotStatus.BOOKED, SlotStatus.LOCKED):
                if slot.overlaps_with(start, end):
                    return True
        return False


# ──────────────────────────────────────────────
#  Booking Service
# ──────────────────────────────────────────────

class BookingService:
    def __init__(self, slot_service: SlotService):
        self._slot_service = slot_service
        self._bookings: dict[str, Booking] = {}
        self._observers: list[BookingObserver] = []

    def add_observer(self, obs: BookingObserver):
        self._observers.append(obs)

    def book(self, user: User, coach: Coach, slot: TimeSlot) -> BookingResult:
        if slot is None:
            return BookingResult.INVALID_SLOT

        # Pessimistic locking: synchronized on slot object
        with slot._lock:
            if slot.status != SlotStatus.AVAILABLE:
                print(f"  ✗ {user.name} — slot {slot.slot_id} is {slot.status.value}")
                return BookingResult.SLOT_UNAVAILABLE

            slot.status = SlotStatus.LOCKED
            booking_id = f"BKG-{uuid.uuid4().hex[:6].upper()}"
            booking = Booking(booking_id, user, coach, slot)
            slot.status = SlotStatus.BOOKED
            self._bookings[booking_id] = booking

            print(f"  ✓ {user.name} — booked {slot.slot_id} → {booking_id}")
            self._notify(booking, created=True)
            return BookingResult.SUCCESS

    def cancel(self, booking_id: str) -> BookingResult:
        booking = self._bookings.get(booking_id)
        if not booking:
            return BookingResult.INVALID_SLOT

        with booking.time_slot._lock:
            booking.cancel()
            booking.time_slot.status = SlotStatus.AVAILABLE
            print(f"  ↩ {booking_id} cancelled — slot is now AVAILABLE")
            self._notify(booking, created=False)
            return BookingResult.SUCCESS

    def _notify(self, booking: Booking, created: bool):
        for obs in self._observers:
            if created:
                obs.on_booking_created(booking)
            else:
                obs.on_booking_cancelled(booking)

    def all_bookings(self) -> list[Booking]:
        return list(self._bookings.values())


# ──────────────────────────────────────────────
#  Demo
# ──────────────────────────────────────────────

if __name__ == "__main__":
    coach = Coach("C1", "Dr. Priya", "Nutrition",
                  work_start=time(9, 0), work_end=time(11, 0),
                  slot_duration_minutes=30, buffer_minutes=5)

    alice = User("U1", "Alice", "Asia/Kolkata")
    bob = User("U2", "Bob", "America/New_York")

    strategy = FixedDurationSlotStrategy()
    slot_svc = SlotService(strategy)
    booking_svc = BookingService(slot_svc)
    booking_svc.add_observer(CoachNotificationListener())
    booking_svc.add_observer(UserNotificationListener())

    today = date.today()
    slots = slot_svc.generate_slots(coach, today)

    print(f"=== Generated slots for {coach} ===")
    for s in slots:
        print(f"  {s}")

    target = slots[0]
    print(f"\n=== Race condition: Alice and Bob both book {target.slot_id} ===\n")

    barrier = threading.Barrier(2)
    results = {}

    def book_for(user):
        barrier.wait()
        result = booking_svc.book(user, coach, target)
        results[user.name] = result

    t1 = threading.Thread(target=book_for, args=(alice,))
    t2 = threading.Thread(target=book_for, args=(bob,))
    t1.start(); t2.start()
    t1.join(); t2.join()

    print(f"\n  Alice result: {results.get('Alice', 'N/A').value}")
    print(f"  Bob   result: {results.get('Bob', 'N/A').value}")

    print("\n=== All Bookings ===")
    for b in booking_svc.all_bookings():
        print(f"  {b}")

    print(f"\n=== Available slots: {len(slot_svc.get_available_slots(coach.coach_id))} remaining ===")

    print("\n=== Cancellation ===")
    for b in booking_svc.all_bookings():
        booking_svc.cancel(b.booking_id)

    print(f"\n=== Available slots after cancel: {len(slot_svc.get_available_slots(coach.coach_id))} ===")
