# 05 — Movie Ticket Booking (BookMyShow)

**Priority:** TIER 2 — common senior LLD, tests seat locking, timeout, payment

---

## Problem Statement

Design an in-memory movie ticket booking system where multiple users can browse movies, view shows, select seats, and book tickets. The system must handle **concurrent seat selection** with proper locking, a **payment timeout** mechanism (seats auto-unlock if payment isn't completed within a window), and support cancellation with seat release.

### Functional Requirements

1. Browse movies playing in a city / theater.
2. View available shows for a movie on a given date.
3. View the seat map for a show (available / locked / booked).
4. Select one or more seats — seats are **temporarily locked** for the selecting user.
5. Complete payment within a **timeout window** (e.g., 5 minutes) — on success, seats become BOOKED.
6. If payment is not completed in time, seats **auto-unlock** and become available again.
7. Cancel a confirmed booking — seats return to AVAILABLE.

### Non-Functional Requirements

- **Concurrency:** Two users selecting the same seat at the same instant — only one succeeds.
- **Consistency:** No double-booking under any race condition.
- **Low latency:** Lock acquisition should fail fast rather than block indefinitely.
- All data is **in-memory** (no database).

---

## Clarification Questions

| # | Question | Assumed Answer |
|---|----------|----------------|
| 1 | How many theaters and screens do we support? | Multiple theaters, each with multiple screens. |
| 2 | Can a show span across screens? | No — one show maps to exactly one screen. |
| 3 | What seat types exist? | REGULAR, PREMIUM, VIP — each with different pricing. |
| 4 | How do we handle two users selecting the same seat concurrently? | First user to acquire the lock wins; the second gets an immediate failure (no blocking). |
| 5 | What is the payment timeout window? | 5 minutes — configurable. Seats auto-unlock on expiry. |
| 6 | Can a user cancel a confirmed booking? | Yes — seats go back to AVAILABLE and a refund is initiated. |
| 7 | Do we need to notify users when previously-locked seats become available? | Yes — Observer pattern to notify waitlisted users. |

---

## Entities

```
Movie
 ├── movieId, title, genre, durationMinutes

Theater
 ├── theaterId, name, city
 └── screens: List<Screen>

Screen
 ├── screenId, name
 └── seats: List<Seat>        // physical layout

Show
 ├── showId
 ├── movie: Movie
 ├── screen: Screen
 ├── startTime: LocalDateTime
 └── seatStatusMap: Map<Seat, SeatStatus>

Seat
 ├── seatId, row, col
 ├── seatType: SeatType
 ├── lock: ReentrantLock       // per-seat concurrency control
 └── status: SeatStatus

Booking
 ├── bookingId
 ├── user: User
 ├── show: Show
 ├── seats: List<Seat>
 ├── status: BookingStatus
 ├── totalAmount: double
 ├── createdAt: LocalDateTime
 └── scheduledUnlock: ScheduledFuture<?>

User
 ├── userId, name, email
```

### Enums

| Enum | Values |
|------|--------|
| `SeatType` | REGULAR, PREMIUM, VIP |
| `SeatStatus` | AVAILABLE, LOCKED, BOOKED |
| `BookingStatus` | PENDING, CONFIRMED, CANCELLED, EXPIRED |

### Services

| Service | Responsibility |
|---------|---------------|
| `MovieService` | CRUD for movies |
| `TheaterService` | Manage theaters, screens, shows |
| `SeatAvailabilityService` | Query available seats for a show |
| `BookingService` | Lock seats, confirm/cancel bookings, timeout handling |
| `PaymentService` | Process payment via strategy |
| `NotificationService` | Observer — notify on seat availability |

---

## Design Patterns

### 1. Strategy Pattern — Payment

Different payment methods share a common interface; the concrete strategy is chosen at runtime.

```
<<interface>> PaymentStrategy
  + pay(amount: double): boolean

CreditCardPayment ─implements─▶ PaymentStrategy
UPIPayment        ─implements─▶ PaymentStrategy
WalletPayment     ─implements─▶ PaymentStrategy
```

### 2. Factory Pattern — Booking Creation

`BookingFactory` encapsulates Booking construction, assigns IDs, sets initial status, and calculates the total amount.

```
BookingFactory
  + createBooking(user, show, seats): Booking
```

### 3. Observer Pattern — Seat Availability Notification

When a booking is cancelled or a lock expires, all registered observers (waitlisted users) are notified.

```
<<interface>> SeatAvailabilityObserver
  + onSeatsAvailable(show: Show, seats: List<Seat>)

UserNotificationObserver ─implements─▶ SeatAvailabilityObserver
```

### 4. State Pattern — Seat Lifecycle

```
AVAILABLE ──[user selects]──▶ LOCKED ──[payment success]──▶ BOOKED
                                │                              │
                                │ [timeout / payment fail]     │ [cancellation]
                                ▼                              ▼
                             AVAILABLE                      AVAILABLE
```

Each transition is guarded by a lock to prevent illegal state changes.

---

## SOLID Principles

| Principle | How It's Applied |
|-----------|-----------------|
| **S — Single Responsibility** | `BookingService` handles booking logic only; `PaymentService` handles payment only; `SeatAvailabilityService` handles seat queries. No god class. |
| **O — Open/Closed** | Adding a new payment method (e.g., NetBanking) requires only a new `PaymentStrategy` implementation — no changes to `BookingService`. |
| **L — Liskov Substitution** | Any `PaymentStrategy` implementation can be swapped in without altering calling code behavior. |
| **I — Interface Segregation** | `PaymentStrategy` has a single `pay()` method. `SeatAvailabilityObserver` has a single `onSeatsAvailable()` method. Clients depend only on what they use. |
| **D — Dependency Inversion** | `BookingService` depends on the `PaymentStrategy` interface, not on `CreditCardPayment` directly. Concrete strategies are injected. |

---

## Core Algorithm — Seat Locking with Timeout

This is the **key concurrency challenge** interviewers focus on.

### The Problem

1. User A and User B both see Seat-5 as AVAILABLE.
2. Both click "Select" at the same instant.
3. Without locking, both could proceed to payment → **double booking**.

### The Solution — ReentrantLock.tryLock with Timeout

Each `Seat` object owns a `ReentrantLock`. When a user selects seats:

```java
public boolean lockSeats(List<Seat> seats, String bookingId) {
    List<Seat> lockedSeats = new ArrayList<>();
    try {
        for (Seat seat : seats) {
            // tryLock(0, ...) = non-blocking: succeed or fail immediately
            if (seat.getLock().tryLock(0, TimeUnit.SECONDS)) {
                if (seat.getStatus() == SeatStatus.AVAILABLE) {
                    seat.setStatus(SeatStatus.LOCKED);
                    seat.setHeldByBookingId(bookingId);
                    lockedSeats.add(seat);
                } else {
                    seat.getLock().unlock(); // seat not available, release lock
                    throw new SeatUnavailableException("Seat " + seat.getSeatId() + " is " + seat.getStatus());
                }
            } else {
                throw new SeatUnavailableException("Seat " + seat.getSeatId() + " is being held by another user");
            }
        }
        return true;
    } catch (SeatUnavailableException | InterruptedException e) {
        // rollback: unlock all seats we already locked
        for (Seat s : lockedSeats) {
            s.setStatus(SeatStatus.AVAILABLE);
            s.setHeldByBookingId(null);
            s.getLock().unlock();
        }
        return false;
    }
}
```

### Timeout Mechanism — ScheduledExecutorService

After seats are locked, a **scheduled task** auto-unlocks them if payment is not completed within the window:

```java
private final ScheduledExecutorService scheduler = Executors.newScheduledThreadPool(4);
private static final long LOCK_TIMEOUT_MINUTES = 5;

public ScheduledFuture<?> scheduleUnlock(Booking booking) {
    return scheduler.schedule(() -> {
        if (booking.getStatus() == BookingStatus.PENDING) {
            System.out.println("[TIMEOUT] Booking " + booking.getBookingId() + " expired. Releasing seats.");
            releaseSeats(booking);
            booking.setStatus(BookingStatus.EXPIRED);
            notifyObservers(booking.getShow(), booking.getSeats());
        }
    }, LOCK_TIMEOUT_MINUTES, TimeUnit.MINUTES);
}
```

### Why This Works

| Scenario | Outcome |
|----------|---------|
| User A selects Seat-5, User B selects Seat-5 at the same time | `tryLock(0)` — one wins, the other gets `false` immediately (no blocking). |
| User A locks Seat-5 but never pays | `ScheduledExecutorService` fires after 5 min → seat returns to AVAILABLE. |
| User A locks Seat-5 and pays successfully | Scheduled task is cancelled; seat moves to BOOKED. |

---

## Data Structure Choices

| Structure | Purpose | Why |
|-----------|---------|-----|
| `ConcurrentHashMap<String, Show>` | Show registry (showId → Show) | Thread-safe reads/writes without external sync. |
| `ConcurrentHashMap<String, List<Seat>>` | Show → Seats mapping | Quick seat lookup per show. |
| `ReentrantLock` (per Seat) | Per-seat mutual exclusion | Fine-grained: locking Seat-5 doesn't block Seat-6. `tryLock` enables fail-fast. |
| `ScheduledExecutorService` | Lock timeout expiry | Fire-and-forget delayed task; can be cancelled on successful payment. |
| `CopyOnWriteArrayList<SeatAvailabilityObserver>` | Observer list | Safe iteration during notification; writes (add/remove observer) are rare. |
| `AtomicInteger` (booking ID generator) | Unique ID generation | Lock-free thread-safe counter. |

---

## Concurrency Strategy

### Primary: ReentrantLock.tryLock(timeout) per Seat

- **Granularity:** One lock per seat — maximum parallelism.
- **Fail-fast:** `tryLock(0, TimeUnit.SECONDS)` returns `false` immediately if the seat is held.
- **Deadlock-free:** We always acquire locks in a consistent order (by seatId) and use `tryLock` with timeout.

### Alternative 1: synchronized on Show Object (Coarser)

```java
synchronized (show) {
    // check and lock all seats
}
```

- **Pros:** Simple; no explicit lock management.
- **Cons:** Coarse — locks the entire show; only one user can select seats at a time, even for different seats.

### Alternative 2: Optimistic Locking with AtomicInteger

```java
// Each seat has an AtomicInteger version
if (seat.getVersion().compareAndSet(expectedVersion, expectedVersion + 1)) {
    // success — mark as locked
} else {
    // conflict — another user modified
}
```

- **Pros:** No blocking at all; purely CAS-based.
- **Cons:** Harder to implement multi-seat atomicity; retry storms under high contention.

### Why ReentrantLock Is Best for This Problem

| Criterion | ReentrantLock | synchronized | Optimistic (CAS) |
|-----------|:------------:|:------------:|:-----------------:|
| Fail-fast (no blocking) | ✅ tryLock | ❌ blocks | ✅ CAS |
| Per-seat granularity | ✅ | ❌ (per show) | ✅ |
| Timeout support | ✅ native | ❌ | ❌ (manual) |
| Multi-seat atomicity | ✅ (ordered locks) | ✅ | ⚠️ complex |
| Simplicity | ✅ | ✅✅ | ❌ |

### Race Condition Scenario and Resolution

```
Timeline:
─────────────────────────────────────────────────────────
t0: User A sees Seat-5 AVAILABLE
t1: User B sees Seat-5 AVAILABLE
t2: User A calls tryLock(0) on Seat-5 → SUCCESS → marks LOCKED
t3: User B calls tryLock(0) on Seat-5 → FAILS (lock held by A)
t4: User B gets "Seat unavailable" response immediately
t5: User A completes payment → Seat-5 = BOOKED

Resolution: tryLock(0) is atomic. At t2 only one thread enters the
critical section. The other thread at t3 gets false and backs off.
No double-booking is possible.
```

---

## Java Implementation

### Enums

```java
public enum SeatType {
    REGULAR, PREMIUM, VIP
}

public enum SeatStatus {
    AVAILABLE, LOCKED, BOOKED
}

public enum BookingStatus {
    PENDING, CONFIRMED, CANCELLED, EXPIRED
}
```

### Movie

```java
public class Movie {
    private final String movieId;
    private final String title;
    private final String genre;
    private final int durationMinutes;

    public Movie(String movieId, String title, String genre, int durationMinutes) {
        this.movieId = movieId;
        this.title = title;
        this.genre = genre;
        this.durationMinutes = durationMinutes;
    }

    public String getMovieId() { return movieId; }
    public String getTitle() { return title; }
    public String getGenre() { return genre; }
    public int getDurationMinutes() { return durationMinutes; }

    @Override
    public String toString() {
        return title + " (" + genre + ", " + durationMinutes + " min)";
    }
}
```

### Theater

```java
import java.util.ArrayList;
import java.util.List;

public class Theater {
    private final String theaterId;
    private final String name;
    private final String city;
    private final List<Screen> screens;

    public Theater(String theaterId, String name, String city) {
        this.theaterId = theaterId;
        this.name = name;
        this.city = city;
        this.screens = new ArrayList<>();
    }

    public void addScreen(Screen screen) { screens.add(screen); }

    public String getTheaterId() { return theaterId; }
    public String getName() { return name; }
    public String getCity() { return city; }
    public List<Screen> getScreens() { return screens; }
}
```

### Screen

```java
import java.util.ArrayList;
import java.util.List;

public class Screen {
    private final String screenId;
    private final String name;
    private final List<Seat> seats;

    public Screen(String screenId, String name, int rows, int cols) {
        this.screenId = screenId;
        this.name = name;
        this.seats = new ArrayList<>();
        initializeSeats(rows, cols);
    }

    private void initializeSeats(int rows, int cols) {
        for (int r = 1; r <= rows; r++) {
            for (int c = 1; c <= cols; c++) {
                SeatType type;
                if (r <= 2) type = SeatType.VIP;
                else if (r <= 5) type = SeatType.PREMIUM;
                else type = SeatType.REGULAR;

                String seatId = screenId + "-R" + r + "C" + c;
                seats.add(new Seat(seatId, r, c, type));
            }
        }
    }

    public String getScreenId() { return screenId; }
    public String getName() { return name; }
    public List<Seat> getSeats() { return seats; }
}
```

### Seat

```java
import java.util.concurrent.locks.ReentrantLock;

public class Seat {
    private final String seatId;
    private final int row;
    private final int col;
    private final SeatType seatType;
    private final ReentrantLock lock;

    private volatile SeatStatus status;
    private volatile String heldByBookingId;

    public Seat(String seatId, int row, int col, SeatType seatType) {
        this.seatId = seatId;
        this.row = row;
        this.col = col;
        this.seatType = seatType;
        this.status = SeatStatus.AVAILABLE;
        this.lock = new ReentrantLock(true); // fair lock
    }

    public String getSeatId() { return seatId; }
    public int getRow() { return row; }
    public int getCol() { return col; }
    public SeatType getSeatType() { return seatType; }
    public ReentrantLock getLock() { return lock; }

    public SeatStatus getStatus() { return status; }
    public void setStatus(SeatStatus status) { this.status = status; }

    public String getHeldByBookingId() { return heldByBookingId; }
    public void setHeldByBookingId(String heldByBookingId) { this.heldByBookingId = heldByBookingId; }

    public double getPrice() {
        return switch (seatType) {
            case VIP -> 500.0;
            case PREMIUM -> 300.0;
            case REGULAR -> 150.0;
        };
    }

    @Override
    public String toString() {
        return seatId + " [" + seatType + "] " + status;
    }
}
```

### Show

```java
import java.time.LocalDateTime;
import java.util.List;
import java.util.stream.Collectors;

public class Show {
    private final String showId;
    private final Movie movie;
    private final Screen screen;
    private final LocalDateTime startTime;

    public Show(String showId, Movie movie, Screen screen, LocalDateTime startTime) {
        this.showId = showId;
        this.movie = movie;
        this.screen = screen;
        this.startTime = startTime;
    }

    public String getShowId() { return showId; }
    public Movie getMovie() { return movie; }
    public Screen getScreen() { return screen; }
    public LocalDateTime getStartTime() { return startTime; }

    public List<Seat> getAvailableSeats() {
        return screen.getSeats().stream()
                .filter(s -> s.getStatus() == SeatStatus.AVAILABLE)
                .collect(Collectors.toList());
    }

    @Override
    public String toString() {
        return movie.getTitle() + " @ " + startTime + " [" + screen.getName() + "]";
    }
}
```

### User

```java
public class User {
    private final String userId;
    private final String name;
    private final String email;

    public User(String userId, String name, String email) {
        this.userId = userId;
        this.name = name;
        this.email = email;
    }

    public String getUserId() { return userId; }
    public String getName() { return name; }
    public String getEmail() { return email; }

    @Override
    public String toString() { return name + " (" + email + ")"; }
}
```

### Booking

```java
import java.time.LocalDateTime;
import java.util.List;
import java.util.concurrent.ScheduledFuture;

public class Booking {
    private final String bookingId;
    private final User user;
    private final Show show;
    private final List<Seat> seats;
    private final double totalAmount;
    private final LocalDateTime createdAt;

    private volatile BookingStatus status;
    private ScheduledFuture<?> timeoutTask;

    public Booking(String bookingId, User user, Show show, List<Seat> seats) {
        this.bookingId = bookingId;
        this.user = user;
        this.show = show;
        this.seats = seats;
        this.totalAmount = seats.stream().mapToDouble(Seat::getPrice).sum();
        this.createdAt = LocalDateTime.now();
        this.status = BookingStatus.PENDING;
    }

    public String getBookingId() { return bookingId; }
    public User getUser() { return user; }
    public Show getShow() { return show; }
    public List<Seat> getSeats() { return seats; }
    public double getTotalAmount() { return totalAmount; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public BookingStatus getStatus() { return status; }
    public void setStatus(BookingStatus status) { this.status = status; }
    public ScheduledFuture<?> getTimeoutTask() { return timeoutTask; }
    public void setTimeoutTask(ScheduledFuture<?> timeoutTask) { this.timeoutTask = timeoutTask; }

    @Override
    public String toString() {
        return "Booking{" + bookingId + ", user=" + user.getName()
                + ", show=" + show.getMovie().getTitle()
                + ", seats=" + seats.size() + ", total=₹" + totalAmount
                + ", status=" + status + "}";
    }
}
```

### PaymentStrategy (Strategy Pattern)

```java
public interface PaymentStrategy {
    boolean pay(double amount);
    String getMethodName();
}

public class CreditCardPayment implements PaymentStrategy {
    private final String cardNumber;

    public CreditCardPayment(String cardNumber) {
        this.cardNumber = cardNumber;
    }

    @Override
    public boolean pay(double amount) {
        System.out.println("  [PAYMENT] ₹" + amount + " charged to Credit Card ending " + cardNumber.substring(cardNumber.length() - 4));
        return true; // simulate success
    }

    @Override
    public String getMethodName() { return "CreditCard"; }
}

public class UPIPayment implements PaymentStrategy {
    private final String upiId;

    public UPIPayment(String upiId) {
        this.upiId = upiId;
    }

    @Override
    public boolean pay(double amount) {
        System.out.println("  [PAYMENT] ₹" + amount + " paid via UPI: " + upiId);
        return true;
    }

    @Override
    public String getMethodName() { return "UPI"; }
}

public class WalletPayment implements PaymentStrategy {
    private double balance;

    public WalletPayment(double balance) {
        this.balance = balance;
    }

    @Override
    public boolean pay(double amount) {
        if (balance >= amount) {
            balance -= amount;
            System.out.println("  [PAYMENT] ₹" + amount + " deducted from Wallet. Remaining: ₹" + balance);
            return true;
        }
        System.out.println("  [PAYMENT] Wallet balance insufficient. Required: ₹" + amount + ", Available: ₹" + balance);
        return false;
    }

    @Override
    public String getMethodName() { return "Wallet"; }
}
```

### SeatAvailabilityObserver (Observer Pattern)

```java
import java.util.List;

public interface SeatAvailabilityObserver {
    void onSeatsAvailable(Show show, List<Seat> seats);
}

public class UserNotificationObserver implements SeatAvailabilityObserver {
    private final User user;

    public UserNotificationObserver(User user) {
        this.user = user;
    }

    @Override
    public void onSeatsAvailable(Show show, List<Seat> seats) {
        System.out.println("  [NOTIFY] " + user.getName() + ": " + seats.size()
                + " seat(s) now available for " + show.getMovie().getTitle());
    }
}
```

### BookingFactory (Factory Pattern)

```java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

public class BookingFactory {
    private static final AtomicInteger counter = new AtomicInteger(0);

    public static Booking createBooking(User user, Show show, List<Seat> seats) {
        String bookingId = "BKG-" + counter.incrementAndGet();
        return new Booking(bookingId, user, show, seats);
    }
}
```

### SeatAvailabilityService

```java
import java.util.List;
import java.util.stream.Collectors;

public class SeatAvailabilityService {

    public List<Seat> getAvailableSeats(Show show) {
        return show.getScreen().getSeats().stream()
                .filter(seat -> seat.getStatus() == SeatStatus.AVAILABLE)
                .collect(Collectors.toList());
    }

    public List<Seat> getAvailableSeatsByType(Show show, SeatType type) {
        return getAvailableSeats(show).stream()
                .filter(seat -> seat.getSeatType() == type)
                .collect(Collectors.toList());
    }

    public void printSeatMap(Show show) {
        System.out.println("\n  Seat Map for: " + show);
        System.out.println("  " + "-".repeat(50));
        int maxRow = show.getScreen().getSeats().stream().mapToInt(Seat::getRow).max().orElse(0);
        int maxCol = show.getScreen().getSeats().stream().mapToInt(Seat::getCol).max().orElse(0);

        for (int r = 1; r <= maxRow; r++) {
            StringBuilder sb = new StringBuilder("  Row " + r + ": ");
            for (int c = 1; c <= maxCol; c++) {
                final int row = r, col = c;
                Seat seat = show.getScreen().getSeats().stream()
                        .filter(s -> s.getRow() == row && s.getCol() == col)
                        .findFirst().orElse(null);
                if (seat != null) {
                    String symbol = switch (seat.getStatus()) {
                        case AVAILABLE -> "[A]";
                        case LOCKED -> "[L]";
                        case BOOKED -> "[X]";
                    };
                    sb.append(symbol).append(" ");
                }
            }
            System.out.println(sb);
        }
        System.out.println("  Legend: [A]=Available  [L]=Locked  [X]=Booked\n");
    }
}
```

### BookingService — Core Concurrency Logic

```java
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.locks.ReentrantLock;

public class BookingService {
    private static final long LOCK_TIMEOUT_MINUTES = 5;

    private final ScheduledExecutorService scheduler = Executors.newScheduledThreadPool(4);
    private final ConcurrentHashMap<String, Booking> bookings = new ConcurrentHashMap<>();
    private final List<SeatAvailabilityObserver> observers = new CopyOnWriteArrayList<>();

    // ──────────────────────────────────────────────
    //  1. LOCK SEATS — acquire per-seat ReentrantLock
    // ──────────────────────────────────────────────
    private boolean lockSeats(List<Seat> seats, String bookingId) {
        // Sort by seatId to prevent deadlocks when two users lock overlapping sets in different order
        List<Seat> sorted = new ArrayList<>(seats);
        sorted.sort(Comparator.comparing(Seat::getSeatId));

        List<Seat> lockedSoFar = new ArrayList<>();
        try {
            for (Seat seat : sorted) {
                if (seat.getLock().tryLock(0, TimeUnit.SECONDS)) {
                    if (seat.getStatus() == SeatStatus.AVAILABLE) {
                        seat.setStatus(SeatStatus.LOCKED);
                        seat.setHeldByBookingId(bookingId);
                        lockedSoFar.add(seat);
                    } else {
                        seat.getLock().unlock();
                        throw new RuntimeException("Seat " + seat.getSeatId() + " is " + seat.getStatus());
                    }
                } else {
                    throw new RuntimeException("Seat " + seat.getSeatId() + " is held by another user");
                }
            }
            return true;
        } catch (InterruptedException | RuntimeException e) {
            // Rollback: release all locks acquired so far
            for (Seat s : lockedSoFar) {
                s.setStatus(SeatStatus.AVAILABLE);
                s.setHeldByBookingId(null);
                s.getLock().unlock();
            }
            System.out.println("  [LOCK FAILED] " + e.getMessage());
            return false;
        }
    }

    // ──────────────────────────────────────────────
    //  2. RELEASE SEATS — unlock and reset status
    // ──────────────────────────────────────────────
    private void releaseSeats(Booking booking) {
        for (Seat seat : booking.getSeats()) {
            seat.setStatus(SeatStatus.AVAILABLE);
            seat.setHeldByBookingId(null);
            if (seat.getLock().isHeldByCurrentThread()) {
                seat.getLock().unlock();
            }
        }
    }

    // ──────────────────────────────────────────────
    //  3. SCHEDULE TIMEOUT — auto-unlock after window
    // ──────────────────────────────────────────────
    private ScheduledFuture<?> scheduleTimeout(Booking booking) {
        return scheduler.schedule(() -> {
            if (booking.getStatus() == BookingStatus.PENDING) {
                System.out.println("\n  [TIMEOUT] Booking " + booking.getBookingId()
                        + " expired. Releasing " + booking.getSeats().size() + " seat(s).");
                releaseSeats(booking);
                booking.setStatus(BookingStatus.EXPIRED);
                notifyObservers(booking.getShow(), booking.getSeats());
            }
        }, LOCK_TIMEOUT_MINUTES, TimeUnit.MINUTES);
    }

    // ──────────────────────────────────────────────
    //  4. INITIATE BOOKING — lock + schedule timeout
    // ──────────────────────────────────────────────
    public Booking initiateBooking(User user, Show show, List<Seat> requestedSeats) {
        Booking booking = BookingFactory.createBooking(user, show, requestedSeats);
        System.out.println("  [BOOKING] " + user.getName() + " attempting to lock "
                + requestedSeats.size() + " seat(s) for " + show.getMovie().getTitle());

        if (lockSeats(requestedSeats, booking.getBookingId())) {
            ScheduledFuture<?> timeout = scheduleTimeout(booking);
            booking.setTimeoutTask(timeout);
            bookings.put(booking.getBookingId(), booking);
            System.out.println("  [BOOKING] " + booking.getBookingId() + " created. Seats locked. Pay within "
                    + LOCK_TIMEOUT_MINUTES + " min.");
            return booking;
        }
        System.out.println("  [BOOKING] Failed for " + user.getName() + " — seats unavailable.");
        return null;
    }

    // ──────────────────────────────────────────────
    //  5. CONFIRM BOOKING — process payment, mark BOOKED
    // ──────────────────────────────────────────────
    public boolean confirmBooking(Booking booking, PaymentStrategy paymentStrategy) {
        if (booking.getStatus() != BookingStatus.PENDING) {
            System.out.println("  [CONFIRM] Booking " + booking.getBookingId() + " is not PENDING (status=" + booking.getStatus() + ")");
            return false;
        }

        boolean paymentSuccess = paymentStrategy.pay(booking.getTotalAmount());

        if (paymentSuccess) {
            // Cancel the timeout task since payment is done
            if (booking.getTimeoutTask() != null) {
                booking.getTimeoutTask().cancel(false);
            }
            booking.setStatus(BookingStatus.CONFIRMED);
            for (Seat seat : booking.getSeats()) {
                seat.setStatus(SeatStatus.BOOKED);
                // Release the ReentrantLock — seat is now permanently booked
                if (seat.getLock().isHeldByCurrentThread()) {
                    seat.getLock().unlock();
                }
            }
            System.out.println("  [CONFIRM] " + booking.getBookingId() + " CONFIRMED via " + paymentStrategy.getMethodName());
            return true;
        } else {
            // Payment failed — release seats immediately
            releaseSeats(booking);
            booking.setStatus(BookingStatus.CANCELLED);
            if (booking.getTimeoutTask() != null) {
                booking.getTimeoutTask().cancel(false);
            }
            notifyObservers(booking.getShow(), booking.getSeats());
            System.out.println("  [CONFIRM] Payment failed for " + booking.getBookingId() + ". Seats released.");
            return false;
        }
    }

    // ──────────────────────────────────────────────
    //  6. CANCEL BOOKING — refund and release
    // ──────────────────────────────────────────────
    public void cancelBooking(Booking booking) {
        if (booking.getStatus() == BookingStatus.CONFIRMED || booking.getStatus() == BookingStatus.PENDING) {
            booking.setStatus(BookingStatus.CANCELLED);
            if (booking.getTimeoutTask() != null) {
                booking.getTimeoutTask().cancel(false);
            }
            for (Seat seat : booking.getSeats()) {
                seat.setStatus(SeatStatus.AVAILABLE);
                seat.setHeldByBookingId(null);
            }
            System.out.println("  [CANCEL] " + booking.getBookingId() + " cancelled. Seats released.");
            notifyObservers(booking.getShow(), booking.getSeats());
        }
    }

    // ──────────────────────────────────────────────
    //  Observer management
    // ──────────────────────────────────────────────
    public void addObserver(SeatAvailabilityObserver observer) { observers.add(observer); }
    public void removeObserver(SeatAvailabilityObserver observer) { observers.remove(observer); }

    private void notifyObservers(Show show, List<Seat> seats) {
        for (SeatAvailabilityObserver obs : observers) {
            obs.onSeatsAvailable(show, seats);
        }
    }

    public void shutdown() { scheduler.shutdown(); }
}
```

### Main — Concurrent Demo (3 Users Booking Same Seats)

```java
import java.time.LocalDateTime;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MovieTicketBookingDemo {

    public static void main(String[] args) throws InterruptedException {
        // ── Setup ──
        Movie movie = new Movie("M1", "Inception", "Sci-Fi", 148);
        Screen screen = new Screen("S1", "Screen-1", 8, 10); // 8 rows × 10 cols
        Theater theater = new Theater("T1", "PVR Cinemas", "Bangalore");
        theater.addScreen(screen);

        Show show = new Show("SH1", movie, screen, LocalDateTime.now().plusHours(3));

        User alice = new User("U1", "Alice", "alice@mail.com");
        User bob = new User("U2", "Bob", "bob@mail.com");
        User charlie = new User("U3", "Charlie", "charlie@mail.com");

        BookingService bookingService = new BookingService();
        SeatAvailabilityService seatService = new SeatAvailabilityService();

        // Register Charlie as an observer (wants to know when seats free up)
        bookingService.addObserver(new UserNotificationObserver(charlie));

        // Target seats: Row-1, Cols 3,4,5 (VIP)
        Seat seat3 = screen.getSeats().stream()
                .filter(s -> s.getRow() == 1 && s.getCol() == 3).findFirst().orElseThrow();
        Seat seat4 = screen.getSeats().stream()
                .filter(s -> s.getRow() == 1 && s.getCol() == 4).findFirst().orElseThrow();
        Seat seat5 = screen.getSeats().stream()
                .filter(s -> s.getRow() == 1 && s.getCol() == 5).findFirst().orElseThrow();

        List<Seat> targetSeats = Arrays.asList(seat3, seat4, seat5);

        System.out.println("=== MOVIE TICKET BOOKING SYSTEM DEMO ===\n");
        seatService.printSeatMap(show);

        // ── Concurrent Booking Attempt ──
        System.out.println("--- 3 users attempting to book the SAME 3 VIP seats concurrently ---\n");

        CountDownLatch startGate = new CountDownLatch(1);
        CountDownLatch doneLatch = new CountDownLatch(3);
        ExecutorService executor = Executors.newFixedThreadPool(3);

        // Result holders
        final Booking[] results = new Booking[3];

        // Alice
        executor.submit(() -> {
            try {
                startGate.await();
                results[0] = bookingService.initiateBooking(alice, show, targetSeats);
            } catch (InterruptedException ignored) {
            } finally {
                doneLatch.countDown();
            }
        });

        // Bob
        executor.submit(() -> {
            try {
                startGate.await();
                results[1] = bookingService.initiateBooking(bob, show, targetSeats);
            } catch (InterruptedException ignored) {
            } finally {
                doneLatch.countDown();
            }
        });

        // Charlie
        executor.submit(() -> {
            try {
                startGate.await();
                results[2] = bookingService.initiateBooking(charlie, show, targetSeats);
            } catch (InterruptedException ignored) {
            } finally {
                doneLatch.countDown();
            }
        });

        startGate.countDown(); // release all threads simultaneously
        doneLatch.await();     // wait for all to finish

        System.out.println("\n--- After concurrent lock attempt ---");
        seatService.printSeatMap(show);

        // ── Payment Phase ──
        System.out.println("--- Payment Phase ---\n");

        // Find the winner (non-null booking)
        Booking winnerBooking = null;
        for (Booking b : results) {
            if (b != null) {
                winnerBooking = b;
                break;
            }
        }

        if (winnerBooking != null) {
            System.out.println("Winner: " + winnerBooking.getUser().getName()
                    + " (Booking: " + winnerBooking.getBookingId() + ")");
            PaymentStrategy payment = new UPIPayment("winner@upi");
            boolean confirmed = bookingService.confirmBooking(winnerBooking, payment);
            System.out.println("  Confirmed: " + confirmed);
        }

        System.out.println("\n--- After payment ---");
        seatService.printSeatMap(show);

        // ── Cancellation Demo ──
        System.out.println("--- Cancellation Demo ---\n");

        if (winnerBooking != null) {
            System.out.println("Cancelling " + winnerBooking.getBookingId() + "...");
            bookingService.cancelBooking(winnerBooking);
        }

        System.out.println("\n--- After cancellation ---");
        seatService.printSeatMap(show);

        // ── Cleanup ──
        executor.shutdown();
        bookingService.shutdown();
        System.out.println("=== DEMO COMPLETE ===");
    }
}
```

### Expected Output (Approximate)

```
=== MOVIE TICKET BOOKING SYSTEM DEMO ===

  Seat Map for: Inception @ 2026-03-21T18:00 [Screen-1]
  --------------------------------------------------
  Row 1: [A] [A] [A] [A] [A] [A] [A] [A] [A] [A]
  Row 2: [A] [A] [A] [A] [A] [A] [A] [A] [A] [A]
  ...
  Legend: [A]=Available  [L]=Locked  [X]=Booked

--- 3 users attempting to book the SAME 3 VIP seats concurrently ---

  [BOOKING] Alice attempting to lock 3 seat(s) for Inception
  [BOOKING] Bob attempting to lock 3 seat(s) for Inception
  [BOOKING] Charlie attempting to lock 3 seat(s) for Inception
  [BOOKING] BKG-1 created. Seats locked. Pay within 5 min.
  [LOCK FAILED] Seat S1-R1C3 is LOCKED
  [BOOKING] Failed for Bob — seats unavailable.
  [LOCK FAILED] Seat S1-R1C3 is held by another user
  [BOOKING] Failed for Charlie — seats unavailable.

--- After concurrent lock attempt ---
  Row 1: [A] [A] [L] [L] [L] [A] [A] [A] [A] [A]
  ...

--- Payment Phase ---
Winner: Alice (Booking: BKG-1)
  [PAYMENT] ₹1500.0 paid via UPI: winner@upi
  [CONFIRM] BKG-1 CONFIRMED via UPI
  Confirmed: true

--- After payment ---
  Row 1: [A] [A] [X] [X] [X] [A] [A] [A] [A] [A]
  ...

--- Cancellation Demo ---
Cancelling BKG-1...
  [CANCEL] BKG-1 cancelled. Seats released.
  [NOTIFY] Charlie: 3 seat(s) now available for Inception

--- After cancellation ---
  Row 1: [A] [A] [A] [A] [A] [A] [A] [A] [A] [A]
  ...

=== DEMO COMPLETE ===
```

---

## Class Diagram (Text)

```
┌──────────────┐      ┌──────────────┐      ┌───────────────┐
│    Movie     │      │   Theater    │──────▶│    Screen     │
│  movieId     │      │  theaterId   │ 1..*  │   screenId    │
│  title       │      │  name, city  │       │   seats[]     │
│  genre       │      └──────────────┘       └───────┬───────┘
│  duration    │                                     │ 1..*
└──────┬───────┘                                     ▼
       │ 1                                   ┌───────────────┐
       │                                     │     Seat      │
       ▼                                     │   seatId      │
┌──────────────┐                             │   row, col    │
│    Show      │─────────────────────────────▶│   seatType    │
│  showId      │ uses screen                 │   status      │
│  startTime   │                             │   lock: RL    │
└──────┬───────┘                             └───────────────┘
       │ 1
       │                                     ┌───────────────┐
       ▼                                     │    User       │
┌──────────────┐          ┌──────────────┐   │   userId      │
│   Booking    │──────────▶│   Booking    │   │   name, email │
│  bookingId   │          │   Service    │   └───────┬───────┘
│  user        │◀─────────│  lockSeats() │           │
│  seats[]     │          │  confirm()   │◀──────────┘
│  status      │          │  cancel()    │   uses
│  totalAmount │          │  timeout()   │
└──────────────┘          └──────┬───────┘
                                 │ uses
                                 ▼
                          ┌──────────────┐
                          │  <<interface>>│
                          │ PaymentStrat │
                          │  + pay()     │
                          └──────┬───────┘
                        ┌────────┼────────┐
                        ▼        ▼        ▼
                   CreditCard   UPI    Wallet
```

---

## Interview-Ready Answer

> "I would design the movie ticket booking system around a `Show` entity that links a `Movie` to a `Screen` at a specific time. Each `Seat` is a first-class object with its own `ReentrantLock`. When a user selects seats, the `BookingService` calls `tryLock(0, TimeUnit.SECONDS)` on each seat — this is non-blocking, so if another user already holds the lock, we fail fast instead of blocking. On a successful lock, the seats transition from AVAILABLE to LOCKED and a `ScheduledExecutorService` task is registered to auto-release them after a 5-minute payment window. If the user completes payment via an injected `PaymentStrategy` (Strategy pattern), the seats move to BOOKED and the timeout task is cancelled. If payment times out, the scheduled task fires, resets seats to AVAILABLE, and notifies waitlisted users via the Observer pattern. To prevent deadlocks when multiple users lock overlapping seat sets, I always acquire locks in a consistent order (sorted by seatId). The entire system is in-memory using `ConcurrentHashMap` for thread-safe show and booking registries. This design cleanly separates concerns — `BookingService` for workflow, `PaymentStrategy` for payment, `SeatAvailabilityService` for queries — and adheres to SOLID principles throughout."

---

## Key Interview Follow-ups

| Question | Answer |
|----------|--------|
| **Why `tryLock(0)` instead of `lock()`?** | `lock()` blocks indefinitely. In a ticket system, we want to tell the user immediately that the seat is taken, not make them wait. |
| **How do you prevent deadlocks?** | Always acquire seat locks in sorted order (by seatId). Two threads locking {Seat-3, Seat-5} will both try Seat-3 first, then Seat-5 — no circular wait. |
| **What if the scheduler thread crashes?** | In production, use a distributed scheduler (Quartz, Redis TTL). For in-memory, the `ScheduledExecutorService` with a thread pool handles single-thread failure gracefully. |
| **How would you scale this to distributed?** | Replace `ReentrantLock` with Redis distributed locks (Redisson `RLock`), seat status in Redis with TTL for auto-expiry, and an event bus (Kafka) for observer notifications. |
| **Why not `synchronized`?** | `synchronized` doesn't support timeout or try-lock semantics. It blocks indefinitely and doesn't allow fail-fast behavior. |
