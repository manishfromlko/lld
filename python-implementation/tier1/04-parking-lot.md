# 04 — Parking Lot System (Python Implementation)

**File:** `parking_lot.py`  
**Tier:** 1 — Highest priority

---

## Problem Statement

Design a multi-floor parking lot that supports different vehicle types (bike, car, truck), concurrent entry/exit, and pluggable fee strategies. No two vehicles should be assigned the same spot simultaneously.

---

## Design Patterns Used

| Pattern | Where | Why |
|---|---|---|
| **Strategy** | `FeeStrategy` ABC → `HourlyFeeStrategy`, `FlatRateFeeStrategy` | Swap pricing without changing `ParkingService` |
| **Singleton** | `ParkingLot.__new__` with class-level lock | One lot instance per process, thread-safe creation |
| **Factory method** | `SpotType.from_vehicle(VehicleType)` | Maps vehicle type to required spot type in one place |

---

## Class Structure

```
VehicleType (Enum): BIKE, CAR, TRUCK
SpotType    (Enum): SMALL, MEDIUM, LARGE
                    .from_vehicle(VehicleType) → SpotType

Vehicle(vehicle_id, vehicle_type)
ParkingSpot(spot_id, spot_type, floor)   — owns threading.Lock
ParkingFloor(floor_id)                  — dict[SpotType → Queue[ParkingSpot]]
ParkingLot  (Singleton)                 — list[ParkingFloor]

FeeStrategy (ABC)
├── HourlyFeeStrategy
└── FlatRateFeeStrategy

Ticket(ticket_id, vehicle, spot, entry_time)
ParkingService(lot, fee_strategy)        — park() / unpark()
```

---

## Concurrency — Per-Spot Locking

Each `ParkingSpot` owns a `threading.Lock`. `occupy()` acquires the lock and checks availability atomically:

```python
def occupy(self, vehicle: Vehicle) -> bool:
    with self._lock:
        if not self.is_available:
            return False
        self.vehicle = vehicle
        self.is_available = False
        return True
```

This prevents double-booking: two threads for the same spot race, one wins the lock, the loser sees `is_available = False` and retries with the next spot.

---

## Spot Allocation — Queue per SpotType per Floor

Each floor maintains a `deque` (used as a queue) per spot type:

```python
# ParkingFloor internal structure
_available: dict[SpotType, deque[ParkingSpot]]

# Finding a spot
def find_spot(self, spot_type) -> ParkingSpot | None:
    queue = self._available.get(spot_type)
    if queue:
        return queue.popleft()   # O(1)
    return None
```

On `unpark`, the spot is pushed back to the right end of the queue.

---

## Singleton Pattern

```python
class ParkingLot:
    _instance = None
    _class_lock = threading.Lock()

    def __new__(cls, ...):
        with cls._class_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                # initialise floors, spots
        return cls._instance
```

Python's `__new__` is the equivalent of Java's double-checked locking pattern.

---

## Fee Calculation

```python
class HourlyFeeStrategy(FeeStrategy):
    def calculate(self, ticket: Ticket, exit_time: datetime) -> float:
        hours = ceil((exit_time - ticket.entry_time).seconds / 3600)
        return hours * self._rate_per_hour

class FlatRateFeeStrategy(FeeStrategy):
    def calculate(self, ticket: Ticket, exit_time: datetime) -> float:
        return self._flat_rate
```

`ParkingService` holds a reference to `FeeStrategy` and can swap it at runtime — the Open/Closed principle in action.

---

## Python vs Java Key Differences

| Concern | Java | Python |
|---|---|---|
| Singleton | Double-checked locking with `volatile` | `__new__` + class-level `Lock` |
| Queue | `LinkedList` / `ArrayDeque` | `collections.deque` |
| Enum method | `SpotType.fromVehicle(VehicleType)` static method | `@classmethod` on `SpotType` |
| `synchronized` | `synchronized(spot) { ... }` | `with spot._lock:` |

---

## Vehicle → Spot Type Mapping

```
BIKE  → SMALL
CAR   → MEDIUM
TRUCK → LARGE
```

`SpotType.from_vehicle()` centralises this mapping. Adding `ELECTRIC → MEDIUM_WITH_CHARGER` requires touching only this one method.

---

## Interview Talking Points

1. **Why per-spot lock instead of per-floor?** — Per-floor would serialise every vehicle entering the same floor. Per-spot allows two vehicles on the same floor to park concurrently as long as they pick different spots.
2. **Why a queue (FIFO) for available spots?** — Gives consistent nearest-first ordering and O(1) allocation. A priority queue could be used for strict "nearest to gate" ordering.
3. **Singleton trade-off** — Singleton is convenient but makes testing harder (hard to reset state). A better approach for tests is dependency injection — pass the lot to `ParkingService`.
4. **Fee strategy swap** — `ParkingService.set_fee_strategy(new_strategy)` lets the lot switch between hourly and flat-rate pricing at runtime without restarting.
