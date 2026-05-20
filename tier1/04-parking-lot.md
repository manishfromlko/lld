# 04 — Parking Lot System

**Priority:** TIER 1 — classic LLD, reported at multiple companies (Amazon, Google, Microsoft, Uber, Flipkart)

---

## Problem Statement

Design a multi-floor parking lot that supports different vehicle types (car, bike, truck), concurrent entry/exit through multiple gates, and flexible fee calculation. The system must efficiently allocate the nearest available spot matching a vehicle's size, handle high-throughput concurrent access without double-booking, and compute fees using pluggable pricing strategies.

---

## Clarification Questions to Ask the Interviewer

| # | Question | Why It Matters |
|---|----------|----------------|
| 1 | **What vehicle types do we need to support?** (car, bike, truck, electric?) | Determines spot types and size-mapping logic |
| 2 | **How many floors does the lot have, and is the count fixed or dynamic?** | Affects data structure choice and nearest-spot algorithm |
| 3 | **What fee strategy should we use?** (hourly, flat-rate, tiered, per-minute?) | Drives the Strategy pattern implementation |
| 4 | **Are there multiple entry/exit gates? Can a vehicle enter from one and exit from another?** | Impacts ticket lookup and concurrency at gates |
| 5 | **Should we allocate the nearest available spot to the entry gate, or any available spot?** | Determines search algorithm — sequential scan vs. priority queue |
| 6 | **How do we handle concurrent access?** (multiple vehicles arriving simultaneously) | Shapes the entire concurrency strategy |
| 7 | **Do we need display boards showing real-time availability per floor?** | Introduces Observer pattern for live updates |

---

## Entities

```
ParkingLot (1)
 ├── ParkingFloor (N)
 │    ├── ParkingSpot (M per floor)
 │    │    └── Vehicle (0 or 1)
 │    └── DisplayBoard
 ├── EntryGate (E)
 └── ExitGate (X)

Ticket ──references──▶ Vehicle, ParkingSpot, entryTime
FeeStrategy ──used by──▶ FeeService
ParkingService ──orchestrates──▶ ParkingLot, FeeService
```

| Entity | Key Fields | Responsibility |
|--------|-----------|----------------|
| `ParkingLot` | `floors`, `entryGates`, `exitGates` | Singleton root; manages floors |
| `ParkingFloor` | `floorNumber`, `spots`, `availableSpotsByType` | Floor-level spot tracking |
| `ParkingSpot` | `spotId`, `spotType`, `isAvailable`, `vehicle` | Atomic spot state management |
| `Vehicle` | `licensePlate`, `vehicleType` | Immutable value object |
| `VehicleType` | `CAR`, `BIKE`, `TRUCK` | Enum for vehicle classification |
| `SpotType` | `COMPACT`, `REGULAR`, `LARGE` | Enum for spot sizing |
| `Ticket` | `ticketId`, `vehicle`, `spot`, `entryTime` | Proof of parking; used for fee calc |
| `FeeStrategy` | `calculateFee(entryTime, exitTime)` | Strategy interface for pricing |
| `HourlyFeeStrategy` | `ratePerHour` | Charges by the hour |
| `FlatRateFeeStrategy` | `flatRate` | Fixed price regardless of duration |
| `ParkingService` | `park()`, `unpark()`, `calculateFee()` | Orchestration facade |
| `FeeService` | `feeStrategy` | Delegates fee calculation |

---

## Design Patterns

### 1. Strategy Pattern — Fee Calculation

```
         ┌─────────────────┐
         │  <<interface>>   │
         │   FeeStrategy    │
         │ + calculateFee() │
         └────────┬─────────┘
                  │
       ┌──────────┴──────────┐
       ▼                     ▼
┌──────────────┐   ┌──────────────────┐
│ HourlyFee    │   │ FlatRateFee      │
│ Strategy     │   │ Strategy         │
└──────────────┘   └──────────────────┘
```

**Why:** Fee policies change independently of parking logic. New strategies (tiered, per-minute, weekend-discount) can be added without modifying existing code.

### 2. Factory Pattern — Object Creation

- `TicketFactory.createTicket(vehicle, spot)` — centralises ticket ID generation and timestamp assignment.
- Keeps construction logic out of the service layer.

### 3. Singleton Pattern — ParkingLot

- One physical parking lot = one in-memory instance.
- Double-checked locking or enum-based singleton for thread-safety.

### 4. Observer Pattern — Display Boards

```
ParkingFloor (Subject)  ──notifies──▶  DisplayBoard (Observer)
```

When a spot is occupied or released, the floor notifies all registered display boards so availability counts update in real time.

---

## SOLID Principles Applied

| Principle | How It's Applied |
|-----------|-----------------|
| **S — Single Responsibility** | `ParkingSpot` only manages its own state. `FeeService` only calculates fees. `ParkingService` only orchestrates park/unpark. No class does two jobs. |
| **O — Open/Closed** | `FeeStrategy` is open for extension (add `TieredFeeStrategy`) but closed for modification — no `if/else` chain in fee calculation. |
| **L — Liskov Substitution** | Any `FeeStrategy` implementation can replace another without breaking `FeeService`. `HourlyFeeStrategy` and `FlatRateFeeStrategy` are fully interchangeable. |
| **I — Interface Segregation** | `FeeStrategy` exposes only `calculateFee()`. Spots don't implement fee logic. Each interface is narrowly focused on one capability. |
| **D — Dependency Inversion** | `FeeService` depends on the `FeeStrategy` abstraction, not on `HourlyFeeStrategy` directly. High-level modules never depend on low-level concrete classes. |

---

## Core Algorithm

### Finding the Nearest Available Spot

```
findAvailableSpot(vehicleType):
    spotType = mapVehicleToSpotType(vehicleType)
    for each floor in parkingLot.floors (sorted by floorNumber):
        queue = floor.availableSpots.get(spotType)
        if queue is not empty:
            spot = queue.poll()           // ConcurrentLinkedQueue — thread-safe
            if spot.occupy(vehicle):      // synchronized check-and-set
                return spot
            else:
                continue                  // lost race, try next
    throw ParkingFullException
```

**Time Complexity:** O(F) where F = number of floors (amortised O(1) per floor with queue).

### Fee Calculation

```
calculateFee(ticket):
    duration = now() - ticket.entryTime
    return feeStrategy.calculateFee(duration)
```

Entirely delegated to the plugged-in strategy — zero conditional branching.

---

## Data Structure Choices

| Structure | Purpose | Why This Choice |
|-----------|---------|-----------------|
| `ConcurrentHashMap<SpotType, ConcurrentLinkedQueue<ParkingSpot>>` per floor | Track available spots by type | O(1) lookup by type, O(1) poll for next spot, thread-safe without external locking |
| `ConcurrentHashMap<String, Ticket>` | Active tickets keyed by license plate | O(1) lookup on exit, thread-safe reads/writes |
| `AtomicInteger` per `(floor, spotType)` | Available count for display boards | Lock-free counter updates |
| **Alternative:** `TreeMap<Integer, ParkingSpot>` | If nearest-to-gate allocation is needed | Sorted by spot distance, O(log n) first-available |

---

## Concurrency Strategy

### Primary: Semaphore + synchronized per Spot

```
ParkingFloor:
    Semaphore capacitySemaphore = new Semaphore(totalSpots)
    // Controls max vehicles per floor — acts as a gate

ParkingSpot:
    synchronized occupy(vehicle)   // fine-grained lock per spot
    synchronized release()
```

- **Semaphore** limits floor capacity — threads block at `acquire()` when full.
- **synchronized on ParkingSpot** prevents two vehicles from claiming the same spot.
- **AtomicInteger** for available-spot counts (lock-free decrement/increment).

### Alternative 1: ReentrantLock per Spot

```java
private final ReentrantLock lock = new ReentrantLock();

public boolean occupy(Vehicle v) {
    if (lock.tryLock()) {
        try {
            if (isAvailable) { isAvailable = false; vehicle = v; return true; }
        } finally { lock.unlock(); }
    }
    return false;
}
```

**Advantage:** `tryLock()` is non-blocking — thread immediately moves to next spot on failure.

### Alternative 2: CAS on AtomicBoolean

```java
private final AtomicBoolean available = new AtomicBoolean(true);

public boolean occupy(Vehicle v) {
    if (available.compareAndSet(true, false)) {
        this.vehicle = v;
        return true;
    }
    return false;
}
```

**Advantage:** Truly lock-free. No context switching. Best throughput under contention.

### Race Condition Walkthrough

```
Timeline:
    T1 (Car-A) ─────────────────────────────────────────
    T2 (Car-B) ─────────────────────────────────────────

WITHOUT synchronization:
    T1: reads spot.isAvailable → true
    T2: reads spot.isAvailable → true        ← STALE READ
    T1: sets spot.isAvailable = false, assigns Car-A
    T2: sets spot.isAvailable = false, assigns Car-B  ← OVERWRITES Car-A!
    Result: Car-A's ticket points to a spot now holding Car-B. Car-A is lost.

WITH synchronized / CAS:
    T1: enters synchronized block, reads true, sets false, assigns Car-A, exits
    T2: enters synchronized block, reads false → returns false
    T2: moves to next spot → finds another available one
    Result: Both cars get their own spots. No data corruption.
```

---

## Java Implementation

### VehicleType Enum

```java
public enum VehicleType {
    BIKE,
    CAR,
    TRUCK
}
```

### SpotType Enum

```java
public enum SpotType {
    COMPACT,
    REGULAR,
    LARGE;

    public static SpotType fromVehicleType(VehicleType vehicleType) {
        return switch (vehicleType) {
            case BIKE  -> COMPACT;
            case CAR   -> REGULAR;
            case TRUCK -> LARGE;
        };
    }
}
```

### Vehicle Class

```java
public class Vehicle {

    private final String licensePlate;
    private final VehicleType type;

    public Vehicle(String licensePlate, VehicleType type) {
        this.licensePlate = licensePlate;
        this.type = type;
    }

    public String getLicensePlate() { return licensePlate; }
    public VehicleType getType()    { return type; }

    @Override
    public String toString() {
        return type + "[" + licensePlate + "]";
    }
}
```

### ParkingSpot Class

```java
public class ParkingSpot {

    private final String spotId;
    private final SpotType spotType;
    private volatile boolean available = true;
    private Vehicle vehicle;

    public ParkingSpot(String spotId, SpotType spotType) {
        this.spotId = spotId;
        this.spotType = spotType;
    }

    public synchronized boolean occupy(Vehicle vehicle) {
        if (!available) return false;
        this.available = false;
        this.vehicle = vehicle;
        return true;
    }

    public synchronized Vehicle release() {
        if (available) return null;
        Vehicle parked = this.vehicle;
        this.vehicle = null;
        this.available = true;
        return parked;
    }

    public boolean isAvailable()  { return available; }
    public String getSpotId()     { return spotId; }
    public SpotType getSpotType() { return spotType; }
    public Vehicle getVehicle()   { return vehicle; }

    @Override
    public String toString() {
        return spotType + "-" + spotId + (available ? " [FREE]" : " [" + vehicle + "]");
    }
}
```

### ParkingFloor Class

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.atomic.AtomicInteger;

public class ParkingFloor {

    private final int floorNumber;
    private final List<ParkingSpot> allSpots;
    private final Map<SpotType, ConcurrentLinkedQueue<ParkingSpot>> availableSpots;
    private final Map<SpotType, AtomicInteger> availableCounts;

    public ParkingFloor(int floorNumber, int compactCount, int regularCount, int largeCount) {
        this.floorNumber = floorNumber;
        this.allSpots = new ArrayList<>();
        this.availableSpots = new ConcurrentHashMap<>();
        this.availableCounts = new ConcurrentHashMap<>();

        for (SpotType type : SpotType.values()) {
            availableSpots.put(type, new ConcurrentLinkedQueue<>());
            availableCounts.put(type, new AtomicInteger(0));
        }

        initSpots(SpotType.COMPACT, compactCount);
        initSpots(SpotType.REGULAR, regularCount);
        initSpots(SpotType.LARGE, largeCount);
    }

    private void initSpots(SpotType type, int count) {
        for (int i = 1; i <= count; i++) {
            String id = "F" + floorNumber + "-" + type.name().charAt(0) + i;
            ParkingSpot spot = new ParkingSpot(id, type);
            allSpots.add(spot);
            availableSpots.get(type).offer(spot);
            availableCounts.get(type).incrementAndGet();
        }
    }

    public ParkingSpot findAvailableSpot(SpotType type) {
        ConcurrentLinkedQueue<ParkingSpot> queue = availableSpots.get(type);
        while (true) {
            ParkingSpot spot = queue.poll();
            if (spot == null) return null;

            if (spot.occupy(null)) {
                spot.release();
                return spot;
            }
            // spot was grabbed by another thread — try next in queue
        }
    }

    public ParkingSpot allocateSpot(SpotType type, Vehicle vehicle) {
        ConcurrentLinkedQueue<ParkingSpot> queue = availableSpots.get(type);
        while (true) {
            ParkingSpot spot = queue.poll();
            if (spot == null) return null;

            if (spot.occupy(vehicle)) {
                availableCounts.get(type).decrementAndGet();
                return spot;
            }
        }
    }

    public void releaseSpot(ParkingSpot spot) {
        spot.release();
        availableSpots.get(spot.getSpotType()).offer(spot);
        availableCounts.get(spot.getSpotType()).incrementAndGet();
    }

    public int getFloorNumber() { return floorNumber; }

    public int getAvailableCount(SpotType type) {
        return availableCounts.get(type).get();
    }

    public String getStatus() {
        StringBuilder sb = new StringBuilder("Floor " + floorNumber + ": ");
        for (SpotType type : SpotType.values()) {
            sb.append(type).append("=").append(getAvailableCount(type)).append(" ");
        }
        return sb.toString().trim();
    }
}
```

### Ticket Class

```java
import java.time.LocalDateTime;
import java.util.UUID;

public class Ticket {

    private final String ticketId;
    private final Vehicle vehicle;
    private final ParkingSpot spot;
    private final LocalDateTime entryTime;

    public Ticket(Vehicle vehicle, ParkingSpot spot) {
        this.ticketId = UUID.randomUUID().toString().substring(0, 8).toUpperCase();
        this.vehicle = vehicle;
        this.spot = spot;
        this.entryTime = LocalDateTime.now();
    }

    public String getTicketId()        { return ticketId; }
    public Vehicle getVehicle()        { return vehicle; }
    public ParkingSpot getSpot()       { return spot; }
    public LocalDateTime getEntryTime() { return entryTime; }

    @Override
    public String toString() {
        return "Ticket[" + ticketId + " | " + vehicle + " | " + spot.getSpotId() + " | " + entryTime + "]";
    }
}
```

### FeeStrategy Interface + Implementations

```java
import java.time.Duration;
import java.time.LocalDateTime;

public interface FeeStrategy {
    double calculateFee(LocalDateTime entryTime, LocalDateTime exitTime);
}
```

```java
import java.time.Duration;
import java.time.LocalDateTime;

public class HourlyFeeStrategy implements FeeStrategy {

    private final double ratePerHour;

    public HourlyFeeStrategy(double ratePerHour) {
        this.ratePerHour = ratePerHour;
    }

    @Override
    public double calculateFee(LocalDateTime entryTime, LocalDateTime exitTime) {
        long minutes = Duration.between(entryTime, exitTime).toMinutes();
        long hours = (long) Math.ceil(minutes / 60.0);
        return Math.max(1, hours) * ratePerHour;
    }
}
```

```java
import java.time.LocalDateTime;

public class FlatRateFeeStrategy implements FeeStrategy {

    private final double flatRate;

    public FlatRateFeeStrategy(double flatRate) {
        this.flatRate = flatRate;
    }

    @Override
    public double calculateFee(LocalDateTime entryTime, LocalDateTime exitTime) {
        return flatRate;
    }
}
```

### FeeService

```java
public class FeeService {

    private FeeStrategy strategy;

    public FeeService(FeeStrategy strategy) {
        this.strategy = strategy;
    }

    public void setStrategy(FeeStrategy strategy) {
        this.strategy = strategy;
    }

    public double calculate(Ticket ticket) {
        return strategy.calculateFee(ticket.getEntryTime(), java.time.LocalDateTime.now());
    }
}
```

### ParkingLot Class (Singleton)

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ParkingLot {

    private static volatile ParkingLot instance;

    private final String name;
    private final List<ParkingFloor> floors;

    private ParkingLot(String name) {
        this.name = name;
        this.floors = new ArrayList<>();
    }

    public static ParkingLot getInstance(String name) {
        if (instance == null) {
            synchronized (ParkingLot.class) {
                if (instance == null) {
                    instance = new ParkingLot(name);
                }
            }
        }
        return instance;
    }

    public void addFloor(ParkingFloor floor) {
        floors.add(floor);
    }

    public List<ParkingFloor> getFloors() {
        return Collections.unmodifiableList(floors);
    }

    public String getName() { return name; }

    public void printStatus() {
        System.out.println("=== " + name + " Status ===");
        for (ParkingFloor floor : floors) {
            System.out.println("  " + floor.getStatus());
        }
    }
}
```

### ParkingService (Orchestration Facade)

```java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class ParkingService {

    private final ParkingLot parkingLot;
    private final FeeService feeService;
    private final Map<String, Ticket> activeTickets = new ConcurrentHashMap<>();

    public ParkingService(ParkingLot parkingLot, FeeService feeService) {
        this.parkingLot = parkingLot;
        this.feeService = feeService;
    }

    public Ticket park(Vehicle vehicle) {
        SpotType requiredType = SpotType.fromVehicleType(vehicle.getType());

        for (ParkingFloor floor : parkingLot.getFloors()) {
            ParkingSpot spot = floor.allocateSpot(requiredType, vehicle);
            if (spot != null) {
                Ticket ticket = new Ticket(vehicle, spot);
                activeTickets.put(vehicle.getLicensePlate(), ticket);
                System.out.println("[PARK]   " + vehicle + " → " + spot.getSpotId()
                        + " | Ticket: " + ticket.getTicketId());
                return ticket;
            }
        }

        System.out.println("[FULL]   No " + requiredType + " spot available for " + vehicle);
        return null;
    }

    public double unpark(String licensePlate) {
        Ticket ticket = activeTickets.remove(licensePlate);
        if (ticket == null) {
            System.out.println("[ERROR]  No active ticket for " + licensePlate);
            return -1;
        }

        double fee = feeService.calculate(ticket);

        ParkingSpot spot = ticket.getSpot();
        for (ParkingFloor floor : parkingLot.getFloors()) {
            if (spot.getSpotId().startsWith("F" + floor.getFloorNumber())) {
                floor.releaseSpot(spot);
                break;
            }
        }

        System.out.printf("[UNPARK] %s from %s | Fee: $%.2f%n",
                ticket.getVehicle(), spot.getSpotId(), fee);
        return fee;
    }

    public int activeCount() {
        return activeTickets.size();
    }
}
```

### Main — Concurrent Demo

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ParkingLotDemo {

    public static void main(String[] args) throws InterruptedException {

        // --- Setup ---
        ParkingLot lot = ParkingLot.getInstance("Downtown Garage");
        lot.addFloor(new ParkingFloor(1, 5, 10, 3));   // Floor 1: 5 compact, 10 regular, 3 large
        lot.addFloor(new ParkingFloor(2, 5, 10, 3));   // Floor 2: same layout

        FeeService feeService = new FeeService(new HourlyFeeStrategy(10.0));
        ParkingService service = new ParkingService(lot, feeService);

        lot.printStatus();
        System.out.println();

        // --- Concurrent parking: 15 cars racing for 20 regular spots ---
        int carCount = 15;
        ExecutorService executor = Executors.newFixedThreadPool(8);
        CountDownLatch latch = new CountDownLatch(carCount);

        for (int i = 1; i <= carCount; i++) {
            final int id = i;
            executor.submit(() -> {
                try {
                    Vehicle car = new Vehicle("CAR-" + String.format("%03d", id), VehicleType.CAR);
                    service.park(car);
                } finally {
                    latch.countDown();
                }
            });
        }

        latch.await();
        System.out.println();
        lot.printStatus();
        System.out.println("Active tickets: " + service.activeCount());
        System.out.println();

        // --- Park some bikes and a truck ---
        service.park(new Vehicle("BIKE-001", VehicleType.BIKE));
        service.park(new Vehicle("BIKE-002", VehicleType.BIKE));
        service.park(new Vehicle("TRUCK-001", VehicleType.TRUCK));

        System.out.println();
        lot.printStatus();
        System.out.println();

        // --- Unpark a few vehicles ---
        service.unpark("CAR-001");
        service.unpark("BIKE-001");
        service.unpark("TRUCK-001");

        System.out.println();
        lot.printStatus();

        // --- Switch to flat-rate and unpark another ---
        feeService.setStrategy(new FlatRateFeeStrategy(25.0));
        service.unpark("CAR-005");

        executor.shutdown();
    }
}
```

### Sample Output

```
=== Downtown Garage Status ===
  Floor 1: COMPACT=5 REGULAR=10 LARGE=3
  Floor 2: COMPACT=5 REGULAR=10 LARGE=3

[PARK]   CAR[CAR-003] → F1-R1 | Ticket: A3F1B2C8
[PARK]   CAR[CAR-001] → F1-R2 | Ticket: D4E5F6A7
[PARK]   CAR[CAR-007] → F1-R3 | Ticket: B1C2D3E4
...
[PARK]   CAR[CAR-012] → F2-R2 | Ticket: F5A6B7C8

=== Downtown Garage Status ===
  Floor 1: COMPACT=5 REGULAR=0 LARGE=3
  Floor 2: COMPACT=5 REGULAR=5 LARGE=3
Active tickets: 15

[PARK]   BIKE[BIKE-001] → F1-C1 | Ticket: E1F2A3B4
[PARK]   BIKE[BIKE-002] → F1-C2 | Ticket: C5D6E7F8
[PARK]   TRUCK[TRUCK-001] → F1-L1 | Ticket: A9B0C1D2

[UNPARK] CAR[CAR-001] from F1-R2 | Fee: $10.00
[UNPARK] BIKE[BIKE-001] from F1-C1 | Fee: $10.00
[UNPARK] TRUCK[TRUCK-001] from F1-L1 | Fee: $10.00

[UNPARK] CAR[CAR-005] from F1-R5 | Fee: $25.00   ← switched to flat-rate
```

---

## Class Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         ParkingLot «singleton»                  │
│  - name: String                                                 │
│  - floors: List<ParkingFloor>                                   │
│  + getInstance(): ParkingLot                                    │
│  + addFloor(ParkingFloor)                                       │
└────────────────────────┬────────────────────────────────────────┘
                         │ 1..*
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                        ParkingFloor                             │
│  - floorNumber: int                                             │
│  - availableSpots: Map<SpotType, Queue<ParkingSpot>>            │
│  - availableCounts: Map<SpotType, AtomicInteger>                │
│  + allocateSpot(SpotType, Vehicle): ParkingSpot                 │
│  + releaseSpot(ParkingSpot)                                     │
└────────────────────────┬────────────────────────────────────────┘
                         │ 1..*
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                        ParkingSpot                              │
│  - spotId: String                                               │
│  - spotType: SpotType                                           │
│  - available: volatile boolean                                  │
│  - vehicle: Vehicle                                             │
│  + «synchronized» occupy(Vehicle): boolean                      │
│  + «synchronized» release(): Vehicle                            │
└─────────────────────────────────────────────────────────────────┘
            ▲ used by                         ▲ references
┌───────────┴──────────┐           ┌──────────┴───────────┐
│       Ticket         │           │      Vehicle         │
│  - ticketId: String  │           │  - licensePlate      │
│  - entryTime         │           │  - type: VehicleType │
│  - vehicle: Vehicle  │           └──────────────────────┘
│  - spot: ParkingSpot │
└──────────────────────┘

┌──────────────────┐       ┌──────────────────────────────┐
│  ParkingService  │──────▶│  FeeService                  │
│  + park()        │       │  - strategy: FeeStrategy     │
│  + unpark()      │       │  + calculate(Ticket): double │
└──────────────────┘       └──────────┬───────────────────┘
                                      │ uses
                           ┌──────────▼───────────────┐
                           │  «interface» FeeStrategy  │
                           │  + calculateFee(): double │
                           └──────────┬───────────────┘
                                ┌─────┴──────┐
                                ▼            ▼
                        ┌────────────┐ ┌─────────────┐
                        │ HourlyFee  │ │ FlatRateFee │
                        │ Strategy   │ │ Strategy    │
                        └────────────┘ └─────────────┘
```

---

## Interview-Ready Answer

> "I'd design the parking lot as a **Singleton `ParkingLot`** that holds a list of **`ParkingFloor`** objects, each maintaining a **`ConcurrentHashMap<SpotType, ConcurrentLinkedQueue<ParkingSpot>>`** for O(1) nearest-available-spot lookups. Each **`ParkingSpot`** uses **`synchronized` blocks** (or `AtomicBoolean` CAS) on its `occupy`/`release` methods to prevent double-booking under concurrent access. When a vehicle arrives, the **`ParkingService`** iterates floors top-to-bottom, polls the queue for the required `SpotType`, and issues a **`Ticket`** containing the vehicle, spot, and entry timestamp. On exit, the ticket is looked up from a **`ConcurrentHashMap<String, Ticket>`** keyed by license plate, and the fee is computed via the **Strategy pattern** — a `FeeStrategy` interface with `HourlyFeeStrategy` and `FlatRateFeeStrategy` implementations, injected into `FeeService`. This makes pricing fully pluggable without modifying orchestration logic. For capacity gating, I'd use a **`Semaphore`** per floor. The Observer pattern notifies display boards of availability changes. The design adheres to **SOLID**: single responsibility across all classes, open/closed via strategy, Liskov-substitutable fee strategies, segregated interfaces, and dependency inversion through the `FeeStrategy` abstraction."

---

## Common Follow-Up Questions

| Question | Key Talking Points |
|----------|--------------------|
| How would you handle electric vehicle charging spots? | Add `ELECTRIC` to `SpotType`, extend `ParkingSpot` with `ChargingSpot` subclass, add surcharge fee strategy decorator |
| How do you scale this to multiple lots? | Remove Singleton, introduce `ParkingLotRegistry`, each lot is independent, routing layer picks the closest lot |
| What if we need reservation / pre-booking? | Add `ReservationService` with time-slotted spot locking, use `ScheduledExecutorService` to release expired reservations |
| How would you persist this? | `ParkingSpot` → DB row with optimistic locking (`version` column), `Ticket` → separate table, fee calculated at query time |
| What about an event-driven approach? | Emit `SpotOccupied`/`SpotReleased` events, consumers update displays, analytics, and billing asynchronously |
