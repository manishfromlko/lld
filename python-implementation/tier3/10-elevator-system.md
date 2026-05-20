# 10 — Elevator System (Python Implementation)

**File:** `elevator_system.py`  
**Tier:** 3

---

## Problem Statement

Design a multi-elevator system where each elevator uses the SCAN algorithm (two-heap implementation) and a pluggable dispatch strategy assigns incoming requests to the most appropriate elevator.

---

## Design Patterns Used

| Pattern | Where | Why |
|---|---|---|
| **Strategy** | `SchedulingStrategy` ABC → `FCFSStrategy`, `ShortestSeekStrategy`, `SCANStrategy` | Swap dispatch logic at runtime without changing the controller |
| **State** | `ElevatorState` enum (`IDLE`, `MOVING_UP`, `MOVING_DOWN`, `DOOR_OPEN`) | Explicit state drives what `run()` does each tick |
| **Singleton** | `ElevatorController.__new__` | One controller dispatches all elevators in the building |

---

## Class Structure

```
Direction (Enum): UP, DOWN, IDLE
ElevatorState (Enum): IDLE, MOVING_UP, MOVING_DOWN, DOOR_OPEN

Request(from_floor, to_floor, direction)

Elevator(Thread)
├── _up_heap   : list (min-heap of floors to visit going up)
├── _down_heap : list (max-heap via negation, floors going down)
├── add_request(floor)
├── run()      → _process_up() / _process_down() every 0.3s
└── _open_door()

SchedulingStrategy (ABC)
├── FCFSStrategy          — fewest pending requests
├── ShortestSeekStrategy  — nearest floor
└── SCANStrategy          — prefer same-direction elevators

ElevatorController (Singleton)  — request_elevator() dispatches to best elevator
Building                        — owns floors, elevators, controller; starts threads
```

---

## SCAN Algorithm — Two Heaps

SCAN (also called the "elevator algorithm") sweeps in one direction, stops at every requested floor, then reverses. Two heaps implement this efficiently:

```
_up_heap   : min-heap → always visit the lowest unvisited floor above current
_down_heap : max-heap (negated) → always visit the highest unvisited floor below current
```

### Moving UP
```python
def _process_up(self):
    if self._up_heap:
        next_floor = self._up_heap[0]       # peek minimum
        if self.current_floor < next_floor:
            self.current_floor += 1          # move one floor up
        if self.current_floor == next_floor:
            heapq.heappop(self._up_heap)     # arrived → open door
            self._open_door()
    elif self._down_heap:
        self.direction = Direction.DOWN      # no more up requests → reverse
        self.state = ElevatorState.MOVING_DOWN
    else:
        self.state = ElevatorState.IDLE      # all done
```

### Adding a Request
```python
def add_request(self, floor: int):
    with self._lock:
        if floor > self.current_floor:
            heapq.heappush(self._up_heap, floor)
        elif floor < self.current_floor:
            heapq.heappush(self._down_heap, -floor)   # negate for max-heap
        else:
            self._open_door()   # already here
```

---

## Max-Heap via Negation

Python only has a min-heap (`heapq`). For the down-queue, floors are stored as negatives:

```
Push floor 5 going down: heapq.heappush(down_heap, -5)
Peek top:  next_floor = -down_heap[0]  → restores 5
Pop:       heapq.heappop(down_heap)
```

The max (highest floor to visit on the way down) becomes the minimum negative — naturally at the top of the min-heap.

---

## Dispatch Strategies

### FCFSStrategy — Fewest pending requests
```python
return min(elevators, key=lambda e: e.pending_count())
```

### ShortestSeekStrategy — Nearest floor
```python
return min(elevators, key=lambda e: abs(e.current_floor - request.from_floor))
```

### SCANStrategy — Prefer same-direction elevators
```python
def score(e):
    dist = abs(e.current_floor - request.from_floor)
    if e.state == ElevatorState.IDLE:
        return dist
    same_dir = (
        (e.direction == Direction.UP and request.from_floor >= e.current_floor) or
        (e.direction == Direction.DOWN and request.from_floor <= e.current_floor)
    )
    return dist if same_dir else dist + 1000   # heavy penalty for wrong direction

return min(elevators, key=score)
```

An elevator moving toward the request floor gets a much lower score than one moving away.

---

## Threading Model

Each `Elevator` is a `threading.Thread`. The `run()` loop ticks every 0.3 seconds:

```python
def run(self):
    while self._running:
        with self._lock:
            if self.state == ElevatorState.MOVING_UP:
                self._process_up()
            elif self.state == ElevatorState.MOVING_DOWN:
                self._process_down()
        time.sleep(0.3)   # floor-to-floor travel time
```

The lock protects `_up_heap`, `_down_heap`, `current_floor`, and `state` from races between the `run()` thread and the `add_request()` caller thread.

---

## Python vs Java Key Differences

| Concern | Java | Python |
|---|---|---|
| Thread | `extends Thread` | `threading.Thread` subclass, override `run()` |
| Priority queue | `PriorityQueue` | `heapq` (manual negation for max-heap) |
| Daemon thread | `setDaemon(true)` | `daemon=True` in constructor |
| Singleton | DCL + `volatile` | `__new__` + `threading.Lock` |

---

## Interview Talking Points

1. **Why two heaps instead of one sorted list?** — A sorted list requires O(N) insertion. Heaps give O(log N) insert and O(1) peek. More importantly, two heaps encode direction: the up-heap is for floors above the current position, the down-heap for below.
2. **SCAN vs FCFS vs ShortestSeek** — SCAN minimises total travel distance across all requests (like a disk seek). FCFS is fair but can be slow. ShortestSeek is fast for individual requests but starves distant floors.
3. **What happens on direction reversal?** — When `_up_heap` is empty, switch to `MOVING_DOWN` and drain `_down_heap`. If both are empty, go `IDLE`. The state machine makes these transitions explicit and safe.
4. **The +1000 penalty in SCAN dispatch** — A magic constant, but the key idea is that an elevator moving away is almost always worse than a slightly farther elevator moving toward the request. The interviewer may ask you to justify or parameterise this.
