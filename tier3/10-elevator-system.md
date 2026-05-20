# 10 — Elevator System

**Priority:** TIER 3 — tests state machine, scheduling algorithm, heaps

---

## Problem Statement

Design an elevator system for a building with **N elevators** serving **M floors**. The system must:

- Accept pickup requests from any floor (external hall buttons) and destination requests from inside an elevator (internal panel buttons).
- Dispatch the optimal elevator for each request using a pluggable scheduling algorithm.
- Handle concurrent requests efficiently without starvation.
- Model elevator state transitions (idle, moving up, moving down, door open) as a proper state machine.
- Optimize for minimizing average wait time and total travel distance.

**Real-world parallels:** This problem maps directly to the **SCAN disk-scheduling algorithm** — the elevator moves in one direction servicing all requests, then reverses. It is a classic interview question because it tests heaps, state machines, concurrency, and strategy pattern simultaneously.

---

## Clarification Questions

| # | Question | Why It Matters |
|---|----------|---------------|
| 1 | How many elevators are in the building? | Determines dispatch complexity — single elevator is trivial; multiple requires a scheduling strategy. |
| 2 | How many floors does the building have? | Affects data structure sizing and edge-case handling (ground floor, top floor). |
| 3 | Which scheduling algorithm should we use (FCFS, SCAN, Shortest Seek)? | Core algorithmic decision — SCAN is the default "elevator algorithm" and the expected answer. |
| 4 | What is the maximum capacity of each elevator? | Determines whether we need to model passenger count and reject requests when full. |
| 5 | Are there priority/VIP requests (e.g., fire emergency, VIP floors)? | Requires a separate priority queue or interrupt mechanism. |
| 6 | Should we prefer elevators already moving in the same direction? | Directional affinity is a key optimization in real elevator systems. |
| 7 | Do we need to handle door open/close timing and dwell time? | Adds realism but increases state machine complexity. |

---

## Entities

```
┌─────────────────────────────────────────────────────────────────┐
│                          Building                               │
│  - totalFloors: int                                             │
│  - elevators: List<Elevator>                                    │
│  - controller: ElevatorController                               │
├─────────────────────────────────────────────────────────────────┤
│                          Elevator                               │
│  - id: int                                                      │
│  - currentFloor: int                                            │
│  - direction: Direction                                         │
│  - state: ElevatorState                                         │
│  - upQueue: PriorityQueue<Integer>       (min-heap)             │
│  - downQueue: PriorityQueue<Integer>     (max-heap)             │
│  - capacity: int                                                │
│  - currentLoad: int                                             │
├─────────────────────────────────────────────────────────────────┤
│                     ElevatorState (enum)                        │
│  IDLE, MOVING_UP, MOVING_DOWN, DOOR_OPEN                       │
├─────────────────────────────────────────────────────────────────┤
│                      Direction (enum)                           │
│  UP, DOWN, IDLE                                                 │
├─────────────────────────────────────────────────────────────────┤
│                         Request                                 │
│  - fromFloor: int                                               │
│  - toFloor: int                                                 │
│  - direction: Direction                                         │
│  - timestamp: long                                              │
├─────────────────────────────────────────────────────────────────┤
│                   ElevatorController                            │
│  - elevators: List<Elevator>                                    │
│  - strategy: SchedulingStrategy                                 │
│  + requestElevator(Request): void                               │
│  + assignElevator(Request): Elevator                            │
├─────────────────────────────────────────────────────────────────┤
│              SchedulingStrategy (interface)                      │
│  + selectElevator(List<Elevator>, Request): Elevator            │
│                                                                 │
│  Implementations:                                               │
│    ├── FCFSStrategy          (first come first served)          │
│    ├── SCANStrategy          (elevator / SCAN algorithm)        │
│    └── ShortestSeekStrategy  (nearest elevator first)           │
└─────────────────────────────────────────────────────────────────┘
```

---

## Design Patterns

### 1. Strategy Pattern — `SchedulingStrategy`

The scheduling algorithm is decoupled behind an interface so it can be swapped at runtime without modifying `ElevatorController`.

```
ElevatorController ──uses──▶ «interface» SchedulingStrategy
                                    ▲
                    ┌───────────────┼───────────────┐
                    │               │               │
              FCFSStrategy    SCANStrategy    ShortestSeekStrategy
```

**Why:** Different buildings have different traffic patterns. A hospital may need FCFS for fairness; a skyscraper may need SCAN for throughput. Strategy lets us switch without touching dispatch logic.

### 2. State Pattern — Elevator States

The elevator transitions between well-defined states. Each state dictates what actions are valid.

```
         ┌──────────┐
         │   IDLE   │◀──────────────────────────┐
         └────┬─────┘                            │
              │ request received                 │ no pending requests
              ▼                                  │
     ┌────────────────┐     reached top    ┌─────┴──────────┐
     │   MOVING_UP    │──────────────────▶│  MOVING_DOWN   │
     └───────┬────────┘                    └───────┬────────┘
              │ arrived at target floor            │ arrived at target floor
              ▼                                    ▼
         ┌──────────┐                         ┌──────────┐
         │ DOOR_OPEN│                         │ DOOR_OPEN│
         └──────────┘                         └──────────┘
```

**Transitions:**
- `IDLE` → `MOVING_UP` / `MOVING_DOWN` (on new request)
- `MOVING_UP` → `DOOR_OPEN` (arrived at a serviced floor)
- `MOVING_DOWN` → `DOOR_OPEN` (arrived at a serviced floor)
- `DOOR_OPEN` → `MOVING_UP` / `MOVING_DOWN` / `IDLE` (after dwell time)

### 3. Observer Pattern — Floor Display Boards

Each floor has a display showing the nearest elevator's position and direction. When an elevator moves, it notifies all registered observers.

```
Elevator (Subject) ──notifies──▶ FloorDisplay (Observer)
                    ──notifies──▶ InternalPanel (Observer)
```

### 4. Singleton Pattern — `ElevatorController`

Only one controller manages the entire building. Ensures a single point of dispatch and avoids conflicting assignments.

---

## SOLID Principles

| Principle | Application |
|-----------|------------|
| **S — Single Responsibility** | `Elevator` handles movement and state; `ElevatorController` handles dispatch; `SchedulingStrategy` handles algorithm logic. No class does more than one job. |
| **O — Open/Closed** | New scheduling algorithms (e.g., `LookStrategy`, `ZonedStrategy`) are added by implementing `SchedulingStrategy` — no modification to `ElevatorController`. |
| **L — Liskov Substitution** | Any `SchedulingStrategy` implementation can replace another without breaking `ElevatorController`. `FCFSStrategy`, `SCANStrategy`, and `ShortestSeekStrategy` are all interchangeable. |
| **I — Interface Segregation** | `SchedulingStrategy` has a single method `selectElevator()`. Observers implement only `update()`. No fat interfaces. |
| **D — Dependency Inversion** | `ElevatorController` depends on the `SchedulingStrategy` abstraction, not on any concrete algorithm. Strategy is injected, not instantiated internally. |

---

## Core Algorithm — SCAN (Elevator Algorithm)

The **SCAN algorithm** (also called the **elevator algorithm**) is the key to this design. It works identically to disk-arm scheduling:

### How It Works

1. The elevator moves in its **current direction**, serving all requests along the way.
2. When there are **no more requests** in the current direction, it **reverses**.
3. Use a **min-heap** for UP requests — serve the lowest floor first while going up.
4. Use a **max-heap** for DOWN requests — serve the highest floor first while going down.

### Walkthrough

```
Elevator at floor 5, going UP

UP queue   (min-heap): [7, 9, 12]
DOWN queue (max-heap): [3, 1]

Step 1: Moving UP
  → Floor 5 → 6 → 7 (STOP — serve request) → 8 → 9 (STOP) → 10 → 11 → 12 (STOP)
  → UP queue is now empty

Step 2: Reverse direction → now going DOWN
  → Floor 12 → 11 → ... → 3 (STOP — serve request) → 2 → 1 (STOP)
  → DOWN queue is now empty

Step 3: No more requests → state = IDLE
```

### Why Two Heaps?

| Direction | Heap Type | Reasoning |
|-----------|-----------|-----------|
| UP | Min-Heap (`PriorityQueue<Integer>`) | Going up, serve the nearest (smallest) floor first |
| DOWN | Max-Heap (`PriorityQueue<>(reverseOrder())`) | Going down, serve the nearest (largest) floor first |

### Time Complexity

| Operation | Complexity |
|-----------|-----------|
| Add request to heap | O(log n) |
| Get next floor to serve | O(log n) |
| Process all requests | O(n log n) |

---

## Data Structure Choices

| Data Structure | Usage | Justification |
|---------------|-------|--------------|
| `PriorityQueue<Integer>` (min-heap) | UP request queue per elevator | Serves the nearest floor going up in O(log n). Natural ordering. |
| `PriorityQueue<Integer>` (max-heap) | DOWN request queue per elevator | Serves the nearest floor going down in O(log n). Reverse comparator. |
| `TreeSet<Integer>` (alternative) | UP/DOWN queues | No duplicates + ordered iteration. `ceiling()` and `floor()` in O(log n) for directional lookups. |
| `ConcurrentLinkedQueue<Request>` | Pending requests in controller | Thread-safe queue for incoming requests before dispatch. |
| `ReentrantLock` per elevator | Protecting per-elevator heap access | Finer granularity than `synchronized` — allows `tryLock()` for non-blocking dispatch. |

### Why PriorityQueue over TreeSet?

- `PriorityQueue` allows duplicates (two passengers requesting the same floor).
- `TreeSet` silently drops duplicates — problematic if two people on different elevators press floor 7.
- Use `TreeSet` only if your model guarantees unique floor stops per elevator.

---

## Concurrency Strategy

```
┌──────────────┐        ┌──────────────────────┐
│   Main App   │───────▶│  ElevatorController   │
│  (Requests)  │        │  (synchronized dispatch│
└──────────────┘        │   + ReentrantLock)     │
                        └──────┬───┬───┬────────┘
                               │   │   │
                    ┌──────────┘   │   └──────────┐
                    ▼              ▼               ▼
             ┌───────────┐ ┌───────────┐  ┌───────────┐
             │ Elevator 1│ │ Elevator 2│  │ Elevator 3│
             │ (Thread)  │ │ (Thread)  │  │ (Thread)  │
             └───────────┘ └───────────┘  └───────────┘
```

- **Each `Elevator` runs as its own `Thread`** (implements `Runnable`), continuously processing its request queues.
- **`ElevatorController`** uses `synchronized` blocks when assigning requests to avoid race conditions.
- **`ReentrantLock`** per elevator guards the up/down heaps — the controller locks an elevator's queue to add a request while the elevator thread locks it to poll the next floor.
- **`Thread.sleep()`** simulates floor-to-floor travel time.

---

## Java Implementation

### Direction Enum

```java
public enum Direction {
    UP,
    DOWN,
    IDLE
}
```

### ElevatorState Enum

```java
public enum ElevatorState {
    IDLE,
    MOVING_UP,
    MOVING_DOWN,
    DOOR_OPEN
}
```

### Request Class

```java
public class Request {
    private final int fromFloor;
    private final int toFloor;
    private final Direction direction;
    private final long timestamp;

    public Request(int fromFloor, int toFloor) {
        this.fromFloor = fromFloor;
        this.toFloor = toFloor;
        this.direction = toFloor > fromFloor ? Direction.UP : Direction.DOWN;
        this.timestamp = System.currentTimeMillis();
    }

    public int getFromFloor() { return fromFloor; }
    public int getToFloor() { return toFloor; }
    public Direction getDirection() { return direction; }
    public long getTimestamp() { return timestamp; }

    @Override
    public String toString() {
        return "Request{" + fromFloor + " → " + toFloor + " (" + direction + ")}";
    }
}
```

### Elevator Class

```java
import java.util.Collections;
import java.util.PriorityQueue;
import java.util.concurrent.locks.ReentrantLock;

public class Elevator implements Runnable {
    private final int id;
    private int currentFloor;
    private Direction direction;
    private ElevatorState state;
    private final int maxFloor;

    private final PriorityQueue<Integer> upQueue;
    private final PriorityQueue<Integer> downQueue;
    private final ReentrantLock lock;

    private volatile boolean running = true;

    public Elevator(int id, int maxFloor) {
        this.id = id;
        this.currentFloor = 0;
        this.direction = Direction.IDLE;
        this.state = ElevatorState.IDLE;
        this.maxFloor = maxFloor;
        this.upQueue = new PriorityQueue<>();
        this.downQueue = new PriorityQueue<>(Collections.reverseOrder());
        this.lock = new ReentrantLock();
    }

    public void addRequest(int floor) {
        lock.lock();
        try {
            if (floor > currentFloor) {
                upQueue.offer(floor);
            } else if (floor < currentFloor) {
                downQueue.offer(floor);
            } else {
                openDoor();
                return;
            }

            if (state == ElevatorState.IDLE) {
                direction = (floor > currentFloor) ? Direction.UP : Direction.DOWN;
                state = (direction == Direction.UP)
                        ? ElevatorState.MOVING_UP
                        : ElevatorState.MOVING_DOWN;
            }
        } finally {
            lock.unlock();
        }
    }

    @Override
    public void run() {
        while (running) {
            lock.lock();
            try {
                if (state == ElevatorState.MOVING_UP) {
                    processUpRequests();
                } else if (state == ElevatorState.MOVING_DOWN) {
                    processDownRequests();
                }
            } finally {
                lock.unlock();
            }

            try {
                Thread.sleep(500);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                break;
            }
        }
    }

    private void processUpRequests() {
        if (!upQueue.isEmpty()) {
            int nextFloor = upQueue.peek();
            if (currentFloor < nextFloor) {
                currentFloor++;
                System.out.println("Elevator " + id + " ▲ floor " + currentFloor);
            }
            if (currentFloor == nextFloor) {
                upQueue.poll();
                openDoor();
            }
        } else if (!downQueue.isEmpty()) {
            direction = Direction.DOWN;
            state = ElevatorState.MOVING_DOWN;
        } else {
            direction = Direction.IDLE;
            state = ElevatorState.IDLE;
        }
    }

    private void processDownRequests() {
        if (!downQueue.isEmpty()) {
            int nextFloor = downQueue.peek();
            if (currentFloor > nextFloor) {
                currentFloor--;
                System.out.println("Elevator " + id + " ▼ floor " + currentFloor);
            }
            if (currentFloor == nextFloor) {
                downQueue.poll();
                openDoor();
            }
        } else if (!upQueue.isEmpty()) {
            direction = Direction.UP;
            state = ElevatorState.MOVING_UP;
        } else {
            direction = Direction.IDLE;
            state = ElevatorState.IDLE;
        }
    }

    private void openDoor() {
        ElevatorState previousState = state;
        state = ElevatorState.DOOR_OPEN;
        System.out.println("Elevator " + id + " ■ DOOR OPEN at floor " + currentFloor);

        try {
            Thread.sleep(1000);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }

        state = previousState;
        System.out.println("Elevator " + id + " ■ DOOR CLOSED at floor " + currentFloor);
    }

    public int getId() { return id; }
    public int getCurrentFloor() { return currentFloor; }
    public Direction getDirection() { return direction; }
    public ElevatorState getState() { return state; }

    public int getPendingRequests() {
        lock.lock();
        try {
            return upQueue.size() + downQueue.size();
        } finally {
            lock.unlock();
        }
    }

    public void shutdown() {
        running = false;
    }

    @Override
    public String toString() {
        return "Elevator{id=" + id
                + ", floor=" + currentFloor
                + ", dir=" + direction
                + ", state=" + state
                + ", pending=" + getPendingRequests() + "}";
    }
}
```

### SchedulingStrategy Interface

```java
import java.util.List;

public interface SchedulingStrategy {
    Elevator selectElevator(List<Elevator> elevators, Request request);
}
```

### FCFSStrategy

```java
import java.util.List;

public class FCFSStrategy implements SchedulingStrategy {

    @Override
    public Elevator selectElevator(List<Elevator> elevators, Request request) {
        int minPending = Integer.MAX_VALUE;
        Elevator selected = elevators.get(0);

        for (Elevator elevator : elevators) {
            if (elevator.getPendingRequests() < minPending) {
                minPending = elevator.getPendingRequests();
                selected = elevator;
            }
        }
        return selected;
    }
}
```

### SCANStrategy (Elevator Algorithm)

```java
import java.util.List;

public class SCANStrategy implements SchedulingStrategy {

    @Override
    public Elevator selectElevator(List<Elevator> elevators, Request request) {
        Elevator best = null;
        int bestScore = Integer.MAX_VALUE;

        for (Elevator elevator : elevators) {
            int score = calculateScore(elevator, request);
            if (score < bestScore) {
                bestScore = score;
                best = elevator;
            }
        }
        return best != null ? best : elevators.get(0);
    }

    private int calculateScore(Elevator elevator, Request request) {
        int distance = Math.abs(elevator.getCurrentFloor() - request.getFromFloor());

        if (elevator.getState() == ElevatorState.IDLE) {
            return distance;
        }

        boolean sameDirection =
                (elevator.getDirection() == Direction.UP && request.getFromFloor() >= elevator.getCurrentFloor())
             || (elevator.getDirection() == Direction.DOWN && request.getFromFloor() <= elevator.getCurrentFloor());

        if (sameDirection) {
            return distance;
        }

        // Penalize elevators moving away — they must reverse first
        return distance + 1000;
    }
}
```

### ShortestSeekStrategy

```java
import java.util.List;

public class ShortestSeekStrategy implements SchedulingStrategy {

    @Override
    public Elevator selectElevator(List<Elevator> elevators, Request request) {
        Elevator closest = elevators.get(0);
        int minDistance = Integer.MAX_VALUE;

        for (Elevator elevator : elevators) {
            int distance = Math.abs(elevator.getCurrentFloor() - request.getFromFloor());
            if (distance < minDistance) {
                minDistance = distance;
                closest = elevator;
            }
        }
        return closest;
    }
}
```

### ElevatorController (Singleton)

```java
import java.util.List;

public class ElevatorController {

    private static volatile ElevatorController instance;

    private final List<Elevator> elevators;
    private SchedulingStrategy strategy;

    private ElevatorController(List<Elevator> elevators, SchedulingStrategy strategy) {
        this.elevators = elevators;
        this.strategy = strategy;
    }

    public static ElevatorController getInstance(List<Elevator> elevators, SchedulingStrategy strategy) {
        if (instance == null) {
            synchronized (ElevatorController.class) {
                if (instance == null) {
                    instance = new ElevatorController(elevators, strategy);
                }
            }
        }
        return instance;
    }

    public synchronized void requestElevator(Request request) {
        System.out.println("\n>>> New request: " + request);

        Elevator selected = strategy.selectElevator(elevators, request);
        System.out.println(">>> Assigned to Elevator " + selected.getId());

        selected.addRequest(request.getFromFloor());
        selected.addRequest(request.getToFloor());
    }

    public void setStrategy(SchedulingStrategy strategy) {
        this.strategy = strategy;
    }

    public void printStatus() {
        System.out.println("\n=== Elevator Status ===");
        for (Elevator elevator : elevators) {
            System.out.println(elevator);
        }
        System.out.println("=======================\n");
    }
}
```

### Building Class

```java
import java.util.ArrayList;
import java.util.List;

public class Building {
    private final int totalFloors;
    private final List<Elevator> elevators;
    private final ElevatorController controller;
    private final List<Thread> elevatorThreads;

    public Building(int totalFloors, int numElevators, SchedulingStrategy strategy) {
        this.totalFloors = totalFloors;
        this.elevators = new ArrayList<>();
        this.elevatorThreads = new ArrayList<>();

        for (int i = 1; i <= numElevators; i++) {
            elevators.add(new Elevator(i, totalFloors));
        }

        this.controller = ElevatorController.getInstance(elevators, strategy);
    }

    public void start() {
        for (Elevator elevator : elevators) {
            Thread thread = new Thread(elevator, "Elevator-" + elevator.getId());
            thread.setDaemon(true);
            elevatorThreads.add(thread);
            thread.start();
        }
        System.out.println("Building started with " + elevators.size()
                + " elevators and " + totalFloors + " floors.\n");
    }

    public void requestElevator(int fromFloor, int toFloor) {
        controller.requestElevator(new Request(fromFloor, toFloor));
    }

    public void printStatus() {
        controller.printStatus();
    }

    public void shutdown() {
        for (Elevator elevator : elevators) {
            elevator.shutdown();
        }
    }
}
```

### Main Class — Demo

```java
public class ElevatorSystemDemo {
    public static void main(String[] args) throws InterruptedException {
        SchedulingStrategy strategy = new SCANStrategy();
        Building building = new Building(20, 3, strategy);
        building.start();

        // Simulate concurrent requests from different floors
        building.requestElevator(3, 10);   // Person at floor 3, wants to go to 10
        Thread.sleep(200);

        building.requestElevator(7, 2);    // Person at floor 7, wants to go to 2
        Thread.sleep(200);

        building.requestElevator(1, 15);   // Person at floor 1, wants to go to 15
        Thread.sleep(200);

        building.requestElevator(12, 5);   // Person at floor 12, wants to go to 5
        Thread.sleep(200);

        building.requestElevator(9, 18);   // Person at floor 9, wants to go to 18
        Thread.sleep(200);

        building.printStatus();

        // Let elevators process for a while
        Thread.sleep(15000);

        building.printStatus();
        building.shutdown();

        System.out.println("Elevator system shut down.");
    }
}
```

### Sample Output

```
Building started with 3 elevators and 20 floors.

>>> New request: Request{3 → 10 (UP)}
>>> Assigned to Elevator 1

>>> New request: Request{7 → 2 (DOWN)}
>>> Assigned to Elevator 2

>>> New request: Request{1 → 15 (UP)}
>>> Assigned to Elevator 3

Elevator 1 ▲ floor 1
Elevator 2 ▲ floor 1
Elevator 3 ▲ floor 1
Elevator 1 ▲ floor 2
Elevator 2 ▲ floor 2
Elevator 1 ▲ floor 3
Elevator 1 ■ DOOR OPEN at floor 3
Elevator 1 ■ DOOR CLOSED at floor 3
Elevator 1 ▲ floor 4
...
Elevator 1 ▲ floor 10
Elevator 1 ■ DOOR OPEN at floor 10
Elevator 1 ■ DOOR CLOSED at floor 10
```

---

## Class Diagram

```
┌────────────────────────────────────────────────────────────────────────┐
│                              Building                                  │
│  - totalFloors: int                                                    │
│  - elevators: List<Elevator>                                           │
│  - controller: ElevatorController                                      │
│  + start(): void                                                       │
│  + requestElevator(from, to): void                                     │
│  + shutdown(): void                                                    │
└──────────────────────┬─────────────────────────────────────────────────┘
                       │ has-a
                       ▼
┌──────────────────────────────────────────┐
│          ElevatorController              │     ┌──────────────────────────┐
│  «singleton»                             │────▶│ «interface»              │
│  - elevators: List<Elevator>             │     │  SchedulingStrategy      │
│  - strategy: SchedulingStrategy          │     │  + selectElevator(       │
│  + requestElevator(Request): void        │     │      elevators, request) │
│  + printStatus(): void                   │     │    : Elevator            │
└──────────────────┬───────────────────────┘     └──────────┬───────────────┘
                   │ manages                         ▲      ▲       ▲
                   ▼                                 │      │       │
┌──────────────────────────────────────┐     ┌──────┴┐ ┌───┴──┐ ┌──┴───────────┐
│             Elevator                 │     │ FCFS  │ │ SCAN │ │ShortestSeek  │
│  «Runnable»                          │     │Strategy│ │Strat.│ │Strategy      │
│  - id: int                           │     └───────┘ └──────┘ └──────────────┘
│  - currentFloor: int                 │
│  - direction: Direction              │
│  - state: ElevatorState              │
│  - upQueue: PriorityQueue (min-heap) │
│  - downQueue: PriorityQueue (max-heap)│
│  - lock: ReentrantLock               │
│  + addRequest(floor): void           │
│  + run(): void                       │
│  + shutdown(): void                  │
└──────────────────────────────────────┘
          │ uses              │ uses
          ▼                   ▼
┌──────────────┐    ┌───────────────┐
│  Direction   │    │ ElevatorState │
│  UP          │    │ IDLE          │
│  DOWN        │    │ MOVING_UP     │
│  IDLE        │    │ MOVING_DOWN   │
└──────────────┘    │ DOOR_OPEN     │
                    └───────────────┘

┌──────────────────────────────┐
│           Request            │
│  - fromFloor: int            │
│  - toFloor: int              │
│  - direction: Direction      │
│  - timestamp: long           │
└──────────────────────────────┘
```

---

## Interview-Ready Answer

> "I would design the elevator system with a **Building** that contains multiple **Elevator** instances managed by a **singleton ElevatorController**. Each elevator runs as its own thread and maintains two priority queues — a **min-heap for UP requests** and a **max-heap for DOWN requests** — implementing the **SCAN (elevator) algorithm**: the elevator moves in one direction serving all pending floors, then reverses. The controller uses the **Strategy pattern** to select the best elevator for each request, allowing pluggable algorithms like FCFS, SCAN-based scoring, or Shortest Seek. I model elevator states — IDLE, MOVING_UP, MOVING_DOWN, DOOR_OPEN — as an explicit **state machine** with well-defined transitions. For concurrency, each elevator's request queues are guarded by a **ReentrantLock**, and the controller dispatches with synchronized access. The design follows SOLID: strategies are injectable (OCP, DIP), each class has a single responsibility, and the scheduling interface is minimal (ISP). This approach optimizes for low average wait time, prevents starvation by eventually reversing direction, and scales to N elevators by simply adding more threads."

---

## Key Interview Talking Points

| Topic | What to Say |
|-------|------------|
| **Why SCAN over FCFS?** | FCFS causes the elevator to ping-pong between distant floors. SCAN serves all requests in one direction, minimizing total travel — the same principle behind disk-arm scheduling. |
| **Why two heaps?** | A single sorted collection cannot efficiently serve both directions. Min-heap gives O(log n) access to the nearest UP floor; max-heap gives O(log n) access to the nearest DOWN floor. |
| **How to prevent starvation?** | SCAN inherently prevents starvation — every floor in the current direction is served before reversal, so no request waits more than two full sweeps. |
| **Scaling to 50+ elevators?** | Zone the building (floors 1-10, 11-20, etc.) with dedicated elevator groups. Reduces dispatch search space and mimics real-world express/local elevator banks. |
| **Thread safety?** | Per-elevator `ReentrantLock` is finer-grained than a global lock. The controller only holds the lock briefly during dispatch, not during elevator movement. |
| **TreeSet vs PriorityQueue?** | PriorityQueue allows duplicate floor stops (two people requesting the same floor). TreeSet is cleaner if duplicates are impossible. Both give O(log n). |
