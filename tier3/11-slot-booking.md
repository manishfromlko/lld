# 11 — Slot Booking / Scheduling System

**Priority:** TIER 3 — HealthifyMe domain (health coach slot booking)

---

## Problem Statement

Design a slot booking system where users can book time slots with health coaches. The system must prevent double booking, handle concurrent booking attempts gracefully, support different time zones, and manage the full lifecycle of a slot from availability through booking, completion, or cancellation. Coaches define their working hours, and the system auto-generates bookable slots. When two users attempt to book the same slot simultaneously, exactly one must succeed and the other must receive a clear rejection.

---

## Clarification Questions

| # | Question | Assumed Answer |
|---|----------|----------------|
| 1 | What is the default slot duration? | Fixed 30-minute slots; coaches can opt for 45-min or 60-min |
| 2 | How do coaches define availability? | Coaches set daily working hours (e.g., 9 AM–5 PM) and the system generates slots |
| 3 | Are recurring slots supported? | Yes — coaches can set weekly recurring availability templates |
| 4 | What is the cancellation policy? | Free cancellation up to 2 hours before slot start; late cancel marks as NO_SHOW |
| 5 | Is there a waitlist when slots are full? | Yes — users can join a waitlist and get notified on cancellation |
| 6 | How are time zones handled? | All internal storage in UTC; display converted to user's local timezone |
| 7 | Is there a buffer between consecutive slots? | Yes — configurable buffer (default 5 min) between slots for coach break |

---

## Entities

```
┌──────────────┐       ┌──────────────┐       ┌──────────────────┐
│    Coach      │       │    User       │       │   SlotStatus     │
│──────────────│       │──────────────│       │  (enum)          │
│ id            │       │ id            │       │  AVAILABLE       │
│ name          │       │ name          │       │  LOCKED          │
│ specialization│       │ email         │       │  BOOKED          │
│ workingHours  │       │ timezone      │       │  CANCELLED       │
│ slotDuration  │       │ bookings      │       └──────────────────┘
│ bufferMinutes │       └───────┬───────┘
└───────┬───────┘               │           ┌──────────────────┐
        │                       │           │  BookingStatus    │
        │  1           *        │           │  (enum)          │
        ▼                       │           │  CONFIRMED       │
┌──────────────┐               │           │  CANCELLED       │
│   TimeSlot    │               │           │  COMPLETED       │
│──────────────│               │           │  NO_SHOW         │
│ id            │               │           └──────────────────┘
│ coach         │◄──────────────┘
│ startTime     │       ┌──────────────┐
│ endTime       │       │   Booking     │
│ status        │◄──────│──────────────│
│ version       │       │ id            │
└──────────────┘       │ user          │
                        │ coach         │
                        │ timeSlot      │
                        │ status        │
                        │ bookedAt      │
                        │ cancelledAt   │
                        └──────────────┘
```

**Services:**

| Service | Responsibility |
|---------|---------------|
| `CoachService` | Manage coach profiles, working hours, specialization lookup |
| `SlotService` | Generate slots from working hours, check availability, detect overlaps |
| `BookingService` | Lock → confirm → cancel flow, concurrency handling, waitlist management |
| `NotificationService` | Notify coach on new booking, notify user on cancellation/waitlist promotion |

---

## Design Patterns

### 1. Strategy — Slot Generation

Different coaches may need different slot durations or generation rules.

```
SlotGenerationStrategy (interface)
├── FixedDurationStrategy      — 30-min fixed slots with buffer
├── FlexibleDurationStrategy   — coach picks 30/45/60-min per day
└── RecurringTemplateStrategy  — weekly template auto-generates slots
```

The `SlotService` delegates to the appropriate strategy based on coach configuration, making it trivial to add new generation rules without modifying existing code.

### 2. State — Slot Lifecycle

Slots transition through well-defined states. Invalid transitions are rejected.

```
AVAILABLE ──► LOCKED ──► BOOKED ──► COMPLETED
    ▲            │                      │
    │            │ (timeout)            │
    └────────────┘                      │
    ▲                                   │
    │            CANCELLED ◄────────────┘
    └────────────────┘ (if cancellation policy allows)
```

Each state encapsulates what actions are permitted, preventing illegal transitions at compile time rather than through scattered `if` checks.

### 3. Observer — Booking Notifications

```
BookingEventPublisher
├── notifies → CoachNotificationListener   (coach gets SMS/push on new booking)
├── notifies → UserNotificationListener    (user gets confirmation email)
└── notifies → WaitlistListener            (promotes next waitlisted user on cancel)
```

Decouples the booking logic from notification delivery. Adding a new notification channel (e.g., Slack integration) requires only a new listener.

### 4. Factory — Booking Creation

`BookingFactory` centralizes booking object construction, setting defaults like `bookedAt = now()`, initial status `CONFIRMED`, and generating the booking ID — keeping the service layer free of construction details.

---

## SOLID Principles

| Principle | Application |
|-----------|------------|
| **S — Single Responsibility** | `SlotService` only manages slot generation and availability; `BookingService` only handles the booking lifecycle; `NotificationService` only delivers alerts |
| **O — Open/Closed** | `SlotGenerationStrategy` interface allows adding new generation rules (e.g., recurring, custom) without modifying `SlotService` |
| **L — Liskov Substitution** | Any `SlotGenerationStrategy` implementation can replace another — `SlotService` works identically regardless of which concrete strategy is injected |
| **I — Interface Segregation** | `BookingObserver` is split into fine-grained listeners (`OnBookingCreated`, `OnBookingCancelled`) so implementations only subscribe to events they care about |
| **D — Dependency Inversion** | `BookingService` depends on `SlotRepository` (interface), not a concrete `TreeMapSlotRepository` — can swap to a DB-backed implementation without changing business logic |

---

## Core Algorithm

### Slot Generation

```
Input:  coach working hours (startHour, endHour), slotDuration, bufferMinutes, date
Output: List<TimeSlot>

1. current = date.atTime(startHour)
2. end     = date.atTime(endHour)
3. while current + slotDuration <= end:
      slot = new TimeSlot(current, current + slotDuration, coach, AVAILABLE)
      add slot to list
      current = current + slotDuration + bufferMinutes
4. return list
```

### Booking Flow

```
1. User requests available slots for a coach on a given date
2. SlotService returns slots where status == AVAILABLE
3. User selects a slot
4. BookingService.book(userId, slotId):
   a. Acquire lock on slot (synchronized / ReentrantLock / optimistic version check)
   b. Verify slot.status == AVAILABLE (double-check after lock)
   c. slot.status = LOCKED
   d. Create Booking(user, coach, slot, CONFIRMED)
   e. slot.status = BOOKED
   f. Release lock
   g. Publish BookingCreatedEvent → observers
5. If lock acquisition fails or status != AVAILABLE:
   → return BookingResult.SLOT_UNAVAILABLE
```

### Overlap Detection

Two time intervals overlap if and only if:

```
slot1.start < slot2.end  AND  slot2.start < slot1.end
```

Used in `SlotService.hasOverlap()` to prevent generating or booking overlapping slots for the same coach.

### Concurrent Booking — Race Condition Resolution

```
Thread-1: book(user=Alice, slot=S1)     Thread-2: book(user=Bob, slot=S1)
          │                                        │
          ├─ acquire lock on S1 ✓                  ├─ acquire lock on S1 ✗ (blocked)
          ├─ check: AVAILABLE ✓                    │
          ├─ set LOCKED                            │
          ├─ create Booking                        │
          ├─ set BOOKED                            │
          ├─ release lock                          ├─ acquire lock on S1 ✓ (unblocked)
          │                                        ├─ check: BOOKED ✗ (fail)
          │                                        ├─ release lock
          │                                        └─ return SLOT_UNAVAILABLE
          └─ return SUCCESS
```

---

## Data Structure Choices

| Structure | Purpose | Complexity | Why |
|-----------|---------|-----------|-----|
| `TreeMap<LocalDateTime, TimeSlot>` | Sorted slots per coach | O(log N) insert/lookup, O(log N + K) range query via `subMap` | Natural ordering by time; efficient range queries for "slots between 2 PM and 5 PM" |
| `ConcurrentHashMap<String, TreeMap<LocalDateTime, TimeSlot>>` | Coach → sorted slots map | O(1) coach lookup + O(log N) slot ops | Thread-safe at the coach level; each coach's TreeMap is independently lockable |
| `ReentrantLock` per slot (or `synchronized`) | Slot-level mutual exclusion | O(1) lock/unlock | Prevents two threads from modifying the same slot simultaneously |
| `AtomicInteger` version field (optimistic) | Conflict detection without blocking | O(1) CAS operation | Higher throughput under low contention — retry instead of block |
| `LinkedList<User>` per slot | Waitlist queue | O(1) add to tail, O(1) poll from head | FIFO fairness for waitlisted users |

### Why TreeMap over HashMap?

- Slots are inherently time-ordered; TreeMap maintains this naturally
- `subMap(from, to)` gives O(log N + K) range queries — perfect for "show me available slots between 2 PM and 4 PM"
- `floorEntry()` / `ceilingEntry()` enable finding nearest available slot in O(log N)

---

## Concurrency Strategy

### Primary: `synchronized` on Slot Object (Pessimistic Locking)

```java
synchronized (slot) {
    if (slot.getStatus() != SlotStatus.AVAILABLE) {
        return BookingResult.SLOT_UNAVAILABLE;
    }
    slot.setStatus(SlotStatus.LOCKED);
    // create booking...
    slot.setStatus(SlotStatus.BOOKED);
}
```

**Pros:** Simple, correct, zero chance of lost updates.
**Cons:** Threads block — poor throughput under high contention on the same slot.

### Alternative 1: Optimistic Locking with Version Counter

```java
int currentVersion = slot.getVersion();
if (slot.getStatus() != SlotStatus.AVAILABLE) {
    return BookingResult.SLOT_UNAVAILABLE;
}
boolean updated = slot.compareAndSetVersion(currentVersion, currentVersion + 1);
if (!updated) {
    return BookingResult.CONFLICT_RETRY;
}
slot.setStatus(SlotStatus.BOOKED);
```

**Pros:** Non-blocking, higher throughput when contention is low.
**Cons:** Callers must handle retries; possible starvation under high contention.

### Alternative 2: ReentrantLock with Timeout

```java
if (slot.getLock().tryLock(2, TimeUnit.SECONDS)) {
    try {
        if (slot.getStatus() != SlotStatus.AVAILABLE) {
            return BookingResult.SLOT_UNAVAILABLE;
        }
        slot.setStatus(SlotStatus.BOOKED);
        // create booking...
    } finally {
        slot.getLock().unlock();
    }
} else {
    return BookingResult.TIMEOUT;
}
```

**Pros:** Bounded wait time — no indefinite blocking. More flexible than `synchronized`.
**Cons:** Slightly more complex API; must ensure `unlock()` in `finally`.

### Recommendation for Interview

Use **`synchronized`** as the default answer (simple, correct, easy to reason about), then mention the alternatives to show depth. In a real production system with a database, this becomes `SELECT ... FOR UPDATE` (pessimistic) or a `version` column with optimistic locking — mention this transition to show system design awareness.

---

## Java Implementation

### Enums

```java
public enum SlotStatus {
    AVAILABLE,
    LOCKED,
    BOOKED,
    CANCELLED
}
```

```java
public enum BookingStatus {
    CONFIRMED,
    CANCELLED,
    COMPLETED,
    NO_SHOW
}
```

```java
public enum BookingResult {
    SUCCESS,
    SLOT_UNAVAILABLE,
    CONFLICT_RETRY,
    TIMEOUT,
    INVALID_SLOT
}
```

### Coach

```java
import java.time.LocalTime;

public class Coach {
    private final String id;
    private final String name;
    private final String specialization;
    private final LocalTime workStart;
    private final LocalTime workEnd;
    private final int slotDurationMinutes;
    private final int bufferMinutes;

    public Coach(String id, String name, String specialization,
                 LocalTime workStart, LocalTime workEnd,
                 int slotDurationMinutes, int bufferMinutes) {
        this.id = id;
        this.name = name;
        this.specialization = specialization;
        this.workStart = workStart;
        this.workEnd = workEnd;
        this.slotDurationMinutes = slotDurationMinutes;
        this.bufferMinutes = bufferMinutes;
    }

    public String getId() { return id; }
    public String getName() { return name; }
    public String getSpecialization() { return specialization; }
    public LocalTime getWorkStart() { return workStart; }
    public LocalTime getWorkEnd() { return workEnd; }
    public int getSlotDurationMinutes() { return slotDurationMinutes; }
    public int getBufferMinutes() { return bufferMinutes; }

    @Override
    public String toString() {
        return name + " (" + specialization + ")";
    }
}
```

### User

```java
import java.time.ZoneId;

public class User {
    private final String id;
    private final String name;
    private final ZoneId timezone;

    public User(String id, String name, ZoneId timezone) {
        this.id = id;
        this.name = name;
        this.timezone = timezone;
    }

    public String getId() { return id; }
    public String getName() { return name; }
    public ZoneId getTimezone() { return timezone; }

    @Override
    public String toString() {
        return name + " [" + timezone + "]";
    }
}
```

### TimeSlot

```java
import java.time.LocalDateTime;
import java.util.concurrent.atomic.AtomicInteger;

public class TimeSlot {
    private final String id;
    private final Coach coach;
    private final LocalDateTime startTime;
    private final LocalDateTime endTime;
    private volatile SlotStatus status;
    private final AtomicInteger version;

    public TimeSlot(String id, Coach coach, LocalDateTime startTime, LocalDateTime endTime) {
        this.id = id;
        this.coach = coach;
        this.startTime = startTime;
        this.endTime = endTime;
        this.status = SlotStatus.AVAILABLE;
        this.version = new AtomicInteger(0);
    }

    public String getId() { return id; }
    public Coach getCoach() { return coach; }
    public LocalDateTime getStartTime() { return startTime; }
    public LocalDateTime getEndTime() { return endTime; }

    public SlotStatus getStatus() { return status; }
    public void setStatus(SlotStatus status) { this.status = status; }

    public int getVersion() { return version.get(); }
    public boolean compareAndSetVersion(int expected, int updated) {
        return version.compareAndSet(expected, updated);
    }

    public boolean overlapsWith(LocalDateTime otherStart, LocalDateTime otherEnd) {
        return this.startTime.isBefore(otherEnd) && otherStart.isBefore(this.endTime);
    }

    @Override
    public String toString() {
        return String.format("[%s] %s → %s (%s)", id, startTime.toLocalTime(), endTime.toLocalTime(), status);
    }
}
```

### Booking

```java
import java.time.LocalDateTime;

public class Booking {
    private final String id;
    private final User user;
    private final Coach coach;
    private final TimeSlot timeSlot;
    private BookingStatus status;
    private final LocalDateTime bookedAt;
    private LocalDateTime cancelledAt;

    public Booking(String id, User user, Coach coach, TimeSlot timeSlot) {
        this.id = id;
        this.user = user;
        this.coach = coach;
        this.timeSlot = timeSlot;
        this.status = BookingStatus.CONFIRMED;
        this.bookedAt = LocalDateTime.now();
    }

    public String getId() { return id; }
    public User getUser() { return user; }
    public Coach getCoach() { return coach; }
    public TimeSlot getTimeSlot() { return timeSlot; }
    public BookingStatus getStatus() { return status; }
    public LocalDateTime getBookedAt() { return bookedAt; }
    public LocalDateTime getCancelledAt() { return cancelledAt; }

    public void cancel() {
        this.status = BookingStatus.CANCELLED;
        this.cancelledAt = LocalDateTime.now();
    }

    @Override
    public String toString() {
        return String.format("Booking[%s] %s with %s at %s (%s)",
                id, user.getName(), coach.getName(),
                timeSlot.getStartTime().toLocalTime(), status);
    }
}
```

### SlotGenerationStrategy (Strategy Pattern)

```java
import java.time.LocalDate;
import java.util.List;

public interface SlotGenerationStrategy {
    List<TimeSlot> generateSlots(Coach coach, LocalDate date);
}
```

```java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

public class FixedDurationSlotStrategy implements SlotGenerationStrategy {

    @Override
    public List<TimeSlot> generateSlots(Coach coach, LocalDate date) {
        List<TimeSlot> slots = new ArrayList<>();
        LocalDateTime current = date.atTime(coach.getWorkStart());
        LocalDateTime end = date.atTime(coach.getWorkEnd());

        while (!current.plusMinutes(coach.getSlotDurationMinutes()).isAfter(end)) {
            LocalDateTime slotEnd = current.plusMinutes(coach.getSlotDurationMinutes());
            String slotId = "SLOT-" + UUID.randomUUID().toString().substring(0, 8);
            slots.add(new TimeSlot(slotId, coach, current, slotEnd));
            current = slotEnd.plusMinutes(coach.getBufferMinutes());
        }

        return slots;
    }
}
```

### BookingObserver (Observer Pattern)

```java
public interface BookingObserver {
    void onBookingCreated(Booking booking);
    void onBookingCancelled(Booking booking);
}
```

```java
public class CoachNotificationListener implements BookingObserver {

    @Override
    public void onBookingCreated(Booking booking) {
        System.out.printf("  📩 [Coach Notification] %s, you have a new booking with %s at %s%n",
                booking.getCoach().getName(), booking.getUser().getName(),
                booking.getTimeSlot().getStartTime().toLocalTime());
    }

    @Override
    public void onBookingCancelled(Booking booking) {
        System.out.printf("  📩 [Coach Notification] Booking with %s at %s was cancelled%n",
                booking.getUser().getName(),
                booking.getTimeSlot().getStartTime().toLocalTime());
    }
}
```

```java
public class UserNotificationListener implements BookingObserver {

    @Override
    public void onBookingCreated(Booking booking) {
        System.out.printf("  📩 [User Notification] %s, your booking with %s at %s is confirmed!%n",
                booking.getUser().getName(), booking.getCoach().getName(),
                booking.getTimeSlot().getStartTime().toLocalTime());
    }

    @Override
    public void onBookingCancelled(Booking booking) {
        System.out.printf("  📩 [User Notification] %s, your booking at %s has been cancelled%n",
                booking.getUser().getName(),
                booking.getTimeSlot().getStartTime().toLocalTime());
    }
}
```

### SlotService

```java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

public class SlotService {
    private final ConcurrentHashMap<String, TreeMap<LocalDateTime, TimeSlot>> coachSlots;
    private final SlotGenerationStrategy strategy;

    public SlotService(SlotGenerationStrategy strategy) {
        this.coachSlots = new ConcurrentHashMap<>();
        this.strategy = strategy;
    }

    public List<TimeSlot> generateSlotsForCoach(Coach coach, LocalDate date) {
        List<TimeSlot> slots = strategy.generateSlots(coach, date);
        TreeMap<LocalDateTime, TimeSlot> slotMap = coachSlots.computeIfAbsent(
                coach.getId(), k -> new TreeMap<>());

        for (TimeSlot slot : slots) {
            if (!hasOverlap(coach.getId(), slot.getStartTime(), slot.getEndTime())) {
                slotMap.put(slot.getStartTime(), slot);
            }
        }

        return slots;
    }

    public List<TimeSlot> getAvailableSlots(String coachId) {
        TreeMap<LocalDateTime, TimeSlot> slotMap = coachSlots.get(coachId);
        if (slotMap == null) return Collections.emptyList();

        return slotMap.values().stream()
                .filter(s -> s.getStatus() == SlotStatus.AVAILABLE)
                .collect(Collectors.toList());
    }

    public List<TimeSlot> getAvailableSlotsInRange(String coachId,
                                                    LocalDateTime from,
                                                    LocalDateTime to) {
        TreeMap<LocalDateTime, TimeSlot> slotMap = coachSlots.get(coachId);
        if (slotMap == null) return Collections.emptyList();

        return slotMap.subMap(from, true, to, false).values().stream()
                .filter(s -> s.getStatus() == SlotStatus.AVAILABLE)
                .collect(Collectors.toList());
    }

    public TimeSlot findSlotById(String coachId, String slotId) {
        TreeMap<LocalDateTime, TimeSlot> slotMap = coachSlots.get(coachId);
        if (slotMap == null) return null;

        return slotMap.values().stream()
                .filter(s -> s.getId().equals(slotId))
                .findFirst()
                .orElse(null);
    }

    public boolean hasOverlap(String coachId, LocalDateTime start, LocalDateTime end) {
        TreeMap<LocalDateTime, TimeSlot> slotMap = coachSlots.get(coachId);
        if (slotMap == null) return false;

        LocalDateTime searchFrom = start.minusHours(1);
        LocalDateTime searchTo = end.plusHours(1);

        return slotMap.subMap(searchFrom, true, searchTo, true).values().stream()
                .filter(s -> s.getStatus() == SlotStatus.BOOKED || s.getStatus() == SlotStatus.LOCKED)
                .anyMatch(existing -> existing.overlapsWith(start, end));
    }
}
```

### BookingService

```java
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

public class BookingService {
    private final SlotService slotService;
    private final Map<String, Booking> bookings;
    private final List<BookingObserver> observers;

    public BookingService(SlotService slotService) {
        this.slotService = slotService;
        this.bookings = new ConcurrentHashMap<>();
        this.observers = new ArrayList<>();
    }

    public void addObserver(BookingObserver observer) {
        observers.add(observer);
    }

    /**
     * Thread-safe booking using synchronized on the slot object.
     * Ensures exactly one thread can transition a slot from AVAILABLE → BOOKED.
     */
    public BookingResult book(User user, Coach coach, TimeSlot slot) {
        if (slot == null) {
            return BookingResult.INVALID_SLOT;
        }

        synchronized (slot) {
            if (slot.getStatus() != SlotStatus.AVAILABLE) {
                System.out.printf("  ✗ %s — slot %s is %s (booking denied)%n",
                        user.getName(), slot.getId(), slot.getStatus());
                return BookingResult.SLOT_UNAVAILABLE;
            }

            slot.setStatus(SlotStatus.LOCKED);

            String bookingId = "BKG-" + UUID.randomUUID().toString().substring(0, 8);
            Booking booking = new Booking(bookingId, user, coach, slot);

            slot.setStatus(SlotStatus.BOOKED);
            bookings.put(bookingId, booking);

            System.out.printf("  ✓ %s — booked slot %s → Booking %s%n",
                    user.getName(), slot.getId(), bookingId);

            notifyObservers(booking, true);
            return BookingResult.SUCCESS;
        }
    }

    /**
     * Alternative: Optimistic locking via version CAS.
     */
    public BookingResult bookOptimistic(User user, Coach coach, TimeSlot slot) {
        if (slot == null) return BookingResult.INVALID_SLOT;

        int currentVersion = slot.getVersion();

        if (slot.getStatus() != SlotStatus.AVAILABLE) {
            return BookingResult.SLOT_UNAVAILABLE;
        }

        boolean versionUpdated = slot.compareAndSetVersion(currentVersion, currentVersion + 1);
        if (!versionUpdated) {
            System.out.printf("  ⚡ %s — optimistic conflict on slot %s, retry needed%n",
                    user.getName(), slot.getId());
            return BookingResult.CONFLICT_RETRY;
        }

        slot.setStatus(SlotStatus.BOOKED);
        String bookingId = "BKG-" + UUID.randomUUID().toString().substring(0, 8);
        Booking booking = new Booking(bookingId, user, coach, slot);
        bookings.put(bookingId, booking);

        System.out.printf("  ✓ %s — booked slot %s (optimistic) → Booking %s%n",
                user.getName(), slot.getId(), bookingId);

        notifyObservers(booking, true);
        return BookingResult.SUCCESS;
    }

    public BookingResult cancel(String bookingId) {
        Booking booking = bookings.get(bookingId);
        if (booking == null) return BookingResult.INVALID_SLOT;

        synchronized (booking.getTimeSlot()) {
            booking.cancel();
            booking.getTimeSlot().setStatus(SlotStatus.AVAILABLE);

            System.out.printf("  ↩ Booking %s cancelled — slot %s is now AVAILABLE%n",
                    bookingId, booking.getTimeSlot().getId());

            notifyObservers(booking, false);
            return BookingResult.SUCCESS;
        }
    }

    public Collection<Booking> getAllBookings() {
        return bookings.values();
    }

    private void notifyObservers(Booking booking, boolean isCreated) {
        for (BookingObserver observer : observers) {
            if (isCreated) {
                observer.onBookingCreated(booking);
            } else {
                observer.onBookingCancelled(booking);
            }
        }
    }
}
```

### Main — Demo: Two Users Race for the Same Slot

```java
import java.time.*;
import java.util.List;
import java.util.concurrent.CountDownLatch;

public class SlotBookingDemo {

    public static void main(String[] args) throws InterruptedException {

        // --- Setup ---
        Coach coach = new Coach("C1", "Dr. Priya", "Nutrition",
                LocalTime.of(9, 0), LocalTime.of(17, 0), 30, 5);

        User alice = new User("U1", "Alice", ZoneId.of("Asia/Kolkata"));
        User bob   = new User("U2", "Bob",   ZoneId.of("America/New_York"));

        SlotGenerationStrategy strategy = new FixedDurationSlotStrategy();
        SlotService slotService = new SlotService(strategy);
        BookingService bookingService = new BookingService(slotService);

        bookingService.addObserver(new CoachNotificationListener());
        bookingService.addObserver(new UserNotificationListener());

        // --- Generate Slots ---
        LocalDate today = LocalDate.now();
        List<TimeSlot> slots = slotService.generateSlotsForCoach(coach, today);

        System.out.println("=== Generated Slots for " + coach + " ===");
        slots.forEach(s -> System.out.println("  " + s));

        // --- Concurrent Booking: Alice and Bob race for the SAME slot ---
        TimeSlot targetSlot = slots.get(0);
        System.out.println("\n=== Race Condition Demo: Both users book " + targetSlot.getId() + " ===");

        CountDownLatch startGate = new CountDownLatch(1);
        CountDownLatch doneLatch = new CountDownLatch(2);

        Thread aliceThread = new Thread(() -> {
            try {
                startGate.await();
                BookingResult result = bookingService.book(alice, coach, targetSlot);
                System.out.println("  Alice result: " + result);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                doneLatch.countDown();
            }
        }, "Alice-Thread");

        Thread bobThread = new Thread(() -> {
            try {
                startGate.await();
                BookingResult result = bookingService.book(bob, coach, targetSlot);
                System.out.println("  Bob result: " + result);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                doneLatch.countDown();
            }
        }, "Bob-Thread");

        aliceThread.start();
        bobThread.start();
        startGate.countDown();
        doneLatch.await();

        // --- Verify only one booking exists ---
        System.out.println("\n=== All Bookings ===");
        bookingService.getAllBookings().forEach(b -> System.out.println("  " + b));

        // --- Show slot is no longer available ---
        System.out.println("\n=== Available Slots After Booking ===");
        List<TimeSlot> available = slotService.getAvailableSlots(coach.getId());
        System.out.println("  Available count: " + available.size() + " (was " + slots.size() + ")");

        // --- Sequential booking: Alice books a second slot ---
        System.out.println("\n=== Sequential Booking: Alice books slot #3 ===");
        TimeSlot secondSlot = slots.get(2);
        BookingResult seqResult = bookingService.book(alice, coach, secondSlot);
        System.out.println("  Alice result for slot #3: " + seqResult);

        // --- Cancellation flow ---
        System.out.println("\n=== Cancellation Demo ===");
        String bookingToCancel = bookingService.getAllBookings().iterator().next().getId();
        bookingService.cancel(bookingToCancel);

        System.out.println("\n=== Final State ===");
        System.out.println("  Total bookings: " + bookingService.getAllBookings().size());
        bookingService.getAllBookings().forEach(b -> System.out.println("  " + b));
        System.out.println("  Available slots: " + slotService.getAvailableSlots(coach.getId()).size());
    }
}
```

### Expected Output

```
=== Generated Slots for Dr. Priya (Nutrition) ===
  [SLOT-a1b2c3d4] 09:00 → 09:30 (AVAILABLE)
  [SLOT-e5f6g7h8] 09:35 → 10:05 (AVAILABLE)
  [SLOT-i9j0k1l2] 10:10 → 10:40 (AVAILABLE)
  ... (14 more slots until 17:00)

=== Race Condition Demo: Both users book SLOT-a1b2c3d4 ===
  ✓ Alice — booked slot SLOT-a1b2c3d4 → Booking BKG-m3n4o5p6
  📩 [Coach Notification] Dr. Priya, you have a new booking with Alice at 09:00
  📩 [User Notification] Alice, your booking with Dr. Priya at 09:00 is confirmed!
  Alice result: SUCCESS
  ✗ Bob — slot SLOT-a1b2c3d4 is BOOKED (booking denied)
  Bob result: SLOT_UNAVAILABLE

=== All Bookings ===
  Booking[BKG-m3n4o5p6] Alice with Dr. Priya at 09:00 (CONFIRMED)
```

---

## Interview-Ready Answer

> "I'd design the slot booking system around three core services: **SlotService** generates time slots from a coach's working hours using a **Strategy pattern** for flexible durations, storing them in a **TreeMap** keyed by start time for O(log N) lookups and efficient range queries via `subMap()`. **BookingService** handles the lock-confirm-cancel lifecycle with **pessimistic locking** — I `synchronize` on the slot object so that when two users race for the same slot, exactly one thread enters the critical section, verifies `status == AVAILABLE`, transitions it to `BOOKED`, and creates the booking, while the other thread sees `BOOKED` and gets a clean rejection. Overlap detection uses the interval comparison `slot1.start < slot2.end && slot2.start < slot1.end`. The **State pattern** governs slot transitions (AVAILABLE → LOCKED → BOOKED), and an **Observer pattern** decouples notifications — coach alerts, user confirmations, and waitlist promotions all subscribe independently. All timestamps are stored in UTC and converted to the user's timezone on display. For production, the `synchronized` block translates directly to `SELECT ... FOR UPDATE` in a database, or I'd use optimistic locking with a version column for higher throughput under low contention. The system respects SOLID: SlotService and BookingService have single responsibilities, the strategy interface is open for extension, and services depend on repository interfaces rather than concrete implementations."

---

## Complexity Summary

| Operation | Time | Space |
|-----------|------|-------|
| Generate N slots for a coach | O(N) | O(N) |
| Find available slots | O(N) | O(K) where K = available count |
| Range query (subMap) | O(log N + K) | O(K) |
| Book a slot (synchronized) | O(1) | O(1) |
| Overlap detection (nearby range) | O(log N + K) | O(1) |
| Cancel a booking | O(1) | O(1) |
