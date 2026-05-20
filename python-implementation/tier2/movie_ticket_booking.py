"""
Movie Ticket Booking System
- Per-seat threading.Lock for concurrent booking
- tryLock semantics: acquire(blocking=False) → fail fast
- ScheduledExecutorService equivalent: threading.Timer for seat timeout
- Strategy Pattern for payment
- Observer Pattern for seat availability notifications
"""

import threading
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


# ──────────────────────────────────────────────
#  Enums
# ──────────────────────────────────────────────

class SeatType(Enum):
    REGULAR = "REGULAR"
    PREMIUM = "PREMIUM"
    VIP = "VIP"


class SeatStatus(Enum):
    AVAILABLE = "AVAILABLE"
    LOCKED = "LOCKED"
    BOOKED = "BOOKED"


class BookingStatus(Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


# ──────────────────────────────────────────────
#  Seat
# ──────────────────────────────────────────────

class Seat:
    def __init__(self, seat_id: str, row: int, col: int, seat_type: SeatType):
        self.seat_id = seat_id
        self.row = row
        self.col = col
        self.seat_type = seat_type
        self.status = SeatStatus.AVAILABLE
        self.held_by: str | None = None
        self._lock = threading.Lock()

    @property
    def price(self) -> float:
        return {SeatType.VIP: 500, SeatType.PREMIUM: 300, SeatType.REGULAR: 150}[self.seat_type]

    def try_lock(self, booking_id: str) -> bool:
        """Non-blocking lock attempt — returns False immediately if seat is taken."""
        acquired = self._lock.acquire(blocking=False)
        if not acquired:
            return False
        if self.status != SeatStatus.AVAILABLE:
            self._lock.release()
            return False
        self.status = SeatStatus.LOCKED
        self.held_by = booking_id
        return True

    def unlock(self):
        self.status = SeatStatus.AVAILABLE
        self.held_by = None
        if self._lock.locked():
            try:
                self._lock.release()
            except RuntimeError:
                pass

    def confirm(self):
        self.status = SeatStatus.BOOKED
        if self._lock.locked():
            try:
                self._lock.release()
            except RuntimeError:
                pass

    def __str__(self):
        return f"{self.seat_id}[{self.seat_type.value}/{self.status.value}]"


# ──────────────────────────────────────────────
#  Movie, Screen, Show, User
# ──────────────────────────────────────────────

@dataclass
class Movie:
    movie_id: str
    title: str
    genre: str


@dataclass
class Screen:
    screen_id: str
    name: str
    rows: int
    cols: int
    seats: list[Seat] = field(default_factory=list)

    def __post_init__(self):
        for r in range(1, self.rows + 1):
            for c in range(1, self.cols + 1):
                seat_type = (SeatType.VIP if r <= 2
                             else SeatType.PREMIUM if r <= 4
                             else SeatType.REGULAR)
                sid = f"{self.screen_id}-R{r}C{c}"
                self.seats.append(Seat(sid, r, c, seat_type))


@dataclass
class Show:
    show_id: str
    movie: Movie
    screen: Screen

    def available_seats(self) -> list[Seat]:
        return [s for s in self.screen.seats if s.status == SeatStatus.AVAILABLE]

    def print_seat_map(self):
        print(f"\n  Seat map — {self.movie.title}")
        symbols = {SeatStatus.AVAILABLE: "[A]", SeatStatus.LOCKED: "[L]", SeatStatus.BOOKED: "[X]"}
        for r in range(1, self.screen.rows + 1):
            row_seats = [s for s in self.screen.seats if s.row == r]
            print("  Row " + str(r) + ": " + " ".join(symbols[s.status] for s in row_seats))
        print("  [A]=Available [L]=Locked [X]=Booked\n")


@dataclass
class User:
    user_id: str
    name: str
    email: str


# ──────────────────────────────────────────────
#  Booking
# ──────────────────────────────────────────────

class Booking:
    def __init__(self, booking_id: str, user: User, show: Show, seats: list[Seat]):
        self.booking_id = booking_id
        self.user = user
        self.show = show
        self.seats = seats
        self.total = sum(s.price for s in seats)
        self.status = BookingStatus.PENDING
        self._timeout_timer: threading.Timer | None = None

    def __str__(self):
        return (f"Booking[{self.booking_id} | {self.user.name} | "
                f"{self.show.movie.title} | {len(self.seats)} seats | "
                f"₹{self.total} | {self.status.value}]")


# ──────────────────────────────────────────────
#  Payment Strategy (Strategy Pattern)
# ──────────────────────────────────────────────

class PaymentStrategy(ABC):
    @abstractmethod
    def pay(self, amount: float) -> bool:
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass


class UPIPayment(PaymentStrategy):
    def __init__(self, upi_id: str):
        self.upi_id = upi_id

    def pay(self, amount: float) -> bool:
        print(f"  [PAYMENT] ₹{amount} via UPI {self.upi_id}")
        return True

    @property
    def name(self):
        return "UPI"


class WalletPayment(PaymentStrategy):
    def __init__(self, balance: float):
        self._balance = balance

    def pay(self, amount: float) -> bool:
        if self._balance >= amount:
            self._balance -= amount
            print(f"  [PAYMENT] ₹{amount} from Wallet. Remaining: ₹{self._balance}")
            return True
        print(f"  [PAYMENT] Insufficient wallet balance (₹{self._balance} < ₹{amount})")
        return False

    @property
    def name(self):
        return "Wallet"


# ──────────────────────────────────────────────
#  Observer (Seat Availability Notification)
# ──────────────────────────────────────────────

class SeatObserver(ABC):
    @abstractmethod
    def on_seats_available(self, show: Show, seats: list[Seat]):
        pass


class UserNotificationObserver(SeatObserver):
    def __init__(self, user: User):
        self.user = user

    def on_seats_available(self, show: Show, seats: list[Seat]):
        print(f"  [NOTIFY] {self.user.name}: {len(seats)} seat(s) now available for {show.movie.title}")


# ──────────────────────────────────────────────
#  Booking Service
# ──────────────────────────────────────────────

LOCK_TIMEOUT_SECONDS = 5  # short for demo; use 300 in production


class BookingService:
    def __init__(self):
        self._bookings: dict[str, Booking] = {}
        self._observers: list[SeatObserver] = []

    def add_observer(self, obs: SeatObserver):
        self._observers.append(obs)

    def _notify_observers(self, show: Show, seats: list[Seat]):
        for obs in self._observers:
            obs.on_seats_available(show, seats)

    def _lock_seats(self, seats: list[Seat], booking_id: str) -> list[Seat]:
        """Lock seats in sorted order to prevent deadlocks. Returns locked seats."""
        sorted_seats = sorted(seats, key=lambda s: s.seat_id)
        locked = []
        for seat in sorted_seats:
            if seat.try_lock(booking_id):
                locked.append(seat)
            else:
                # Rollback
                for s in locked:
                    s.unlock()
                raise RuntimeError(f"Seat {seat.seat_id} is {seat.status.value}")
        return locked

    def _release_seats(self, booking: Booking):
        for seat in booking.seats:
            seat.unlock()

    def _schedule_timeout(self, booking: Booking):
        def expire():
            if booking.status == BookingStatus.PENDING:
                print(f"\n  [TIMEOUT] {booking.booking_id} expired — releasing seats")
                self._release_seats(booking)
                booking.status = BookingStatus.EXPIRED
                self._notify_observers(booking.show, booking.seats)

        timer = threading.Timer(LOCK_TIMEOUT_SECONDS, expire)
        timer.daemon = True
        booking._timeout_timer = timer
        timer.start()

    def initiate_booking(self, user: User, show: Show, seats: list[Seat]) -> Booking | None:
        booking_id = f"BKG-{uuid.uuid4().hex[:6].upper()}"
        print(f"  [BOOKING] {user.name} attempting {len(seats)} seat(s) for {show.movie.title}")
        try:
            locked = self._lock_seats(seats, booking_id)
        except RuntimeError as e:
            print(f"  [BOOKING] FAILED for {user.name} — {e}")
            return None

        booking = Booking(booking_id, user, show, locked)
        self._bookings[booking_id] = booking
        self._schedule_timeout(booking)
        print(f"  [BOOKING] {booking_id} created. Pay within {LOCK_TIMEOUT_SECONDS}s")
        return booking

    def confirm_booking(self, booking: Booking, payment: PaymentStrategy) -> bool:
        if booking.status != BookingStatus.PENDING:
            print(f"  [CONFIRM] {booking.booking_id} is not PENDING")
            return False

        if payment.pay(booking.total):
            if booking._timeout_timer:
                booking._timeout_timer.cancel()
            booking.status = BookingStatus.CONFIRMED
            for seat in booking.seats:
                seat.confirm()
            print(f"  [CONFIRM] {booking.booking_id} CONFIRMED via {payment.name}")
            return True
        else:
            self._release_seats(booking)
            booking.status = BookingStatus.CANCELLED
            if booking._timeout_timer:
                booking._timeout_timer.cancel()
            self._notify_observers(booking.show, booking.seats)
            return False

    def cancel_booking(self, booking: Booking):
        if booking.status in (BookingStatus.CONFIRMED, BookingStatus.PENDING):
            booking.status = BookingStatus.CANCELLED
            if booking._timeout_timer:
                booking._timeout_timer.cancel()
            for seat in booking.seats:
                seat.status = SeatStatus.AVAILABLE
            print(f"  [CANCEL] {booking.booking_id} cancelled")
            self._notify_observers(booking.show, booking.seats)


# ──────────────────────────────────────────────
#  Demo
# ──────────────────────────────────────────────

if __name__ == "__main__":
    movie = Movie("M1", "Inception", "Sci-Fi")
    screen = Screen("S1", "Screen-1", rows=6, cols=5)
    show = Show("SH1", movie, screen)

    alice = User("U1", "Alice", "alice@mail.com")
    bob = User("U2", "Bob", "bob@mail.com")
    charlie = User("U3", "Charlie", "charlie@mail.com")

    service = BookingService()
    service.add_observer(UserNotificationObserver(charlie))

    print("=== MOVIE TICKET BOOKING DEMO ===")
    show.print_seat_map()

    # Target: first 3 VIP seats (row 1)
    vip_seats = [s for s in screen.seats if s.row == 1][:3]

    print("--- Alice and Bob race for the same 3 VIP seats ---\n")
    results = [None, None]
    start = threading.Barrier(2)

    def book_for(idx, user):
        start.wait()
        results[idx] = service.initiate_booking(user, show, vip_seats)

    t1 = threading.Thread(target=book_for, args=(0, alice))
    t2 = threading.Thread(target=book_for, args=(1, bob))
    t1.start(); t2.start()
    t1.join(); t2.join()

    show.print_seat_map()

    winner = next((b for b in results if b), None)
    if winner:
        print(f"--- Winner: {winner.user.name} | Confirming payment ---")
        service.confirm_booking(winner, UPIPayment("winner@upi"))

    show.print_seat_map()

    print("--- Cancellation ---")
    if winner:
        service.cancel_booking(winner)

    show.print_seat_map()
