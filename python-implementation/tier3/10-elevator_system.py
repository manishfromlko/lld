"""
Elevator System — SCAN Algorithm
- State Pattern: IDLE / MOVING_UP / MOVING_DOWN / DOOR_OPEN
- Strategy Pattern: SchedulingStrategy (FCFS / SCAN / ShortestSeek)
- Each Elevator runs as its own thread
- Two heaps per elevator: min-heap for UP, max-heap for DOWN
"""

import heapq
import threading
import time
from abc import ABC, abstractmethod
from enum import Enum


# ──────────────────────────────────────────────
#  Enums
# ──────────────────────────────────────────────

class Direction(Enum):
    UP = "UP"
    DOWN = "DOWN"
    IDLE = "IDLE"


class ElevatorState(Enum):
    IDLE = "IDLE"
    MOVING_UP = "MOVING_UP"
    MOVING_DOWN = "MOVING_DOWN"
    DOOR_OPEN = "DOOR_OPEN"


# ──────────────────────────────────────────────
#  Request
# ──────────────────────────────────────────────

class Request:
    def __init__(self, from_floor: int, to_floor: int):
        self.from_floor = from_floor
        self.to_floor = to_floor
        self.direction = Direction.UP if to_floor > from_floor else Direction.DOWN

    def __str__(self):
        return f"Request({self.from_floor} → {self.to_floor} [{self.direction.value}])"


# ──────────────────────────────────────────────
#  Elevator (SCAN algorithm with two heaps)
# ──────────────────────────────────────────────

class Elevator(threading.Thread):
    def __init__(self, elevator_id: int, max_floor: int):
        super().__init__(name=f"Elevator-{elevator_id}", daemon=True)
        self.elevator_id = elevator_id
        self.max_floor = max_floor
        self.current_floor = 0
        self.direction = Direction.IDLE
        self.state = ElevatorState.IDLE

        self._up_heap: list[int] = []    # min-heap for UP requests
        self._down_heap: list[int] = []  # max-heap (store as negatives)
        self._lock = threading.Lock()
        self._running = True

    def add_request(self, floor: int):
        with self._lock:
            if floor > self.current_floor:
                heapq.heappush(self._up_heap, floor)
            elif floor < self.current_floor:
                heapq.heappush(self._down_heap, -floor)  # negate for max-heap
            else:
                self._open_door()
                return

            if self.state == ElevatorState.IDLE:
                if floor > self.current_floor:
                    self.direction = Direction.UP
                    self.state = ElevatorState.MOVING_UP
                else:
                    self.direction = Direction.DOWN
                    self.state = ElevatorState.MOVING_DOWN

    def pending_count(self) -> int:
        with self._lock:
            return len(self._up_heap) + len(self._down_heap)

    def shutdown(self):
        self._running = False

    def run(self):
        while self._running:
            with self._lock:
                if self.state == ElevatorState.MOVING_UP:
                    self._process_up()
                elif self.state == ElevatorState.MOVING_DOWN:
                    self._process_down()
            time.sleep(0.3)  # simulate floor-to-floor travel time

    def _process_up(self):
        if self._up_heap:
            next_floor = self._up_heap[0]
            if self.current_floor < next_floor:
                self.current_floor += 1
                print(f"  Elevator {self.elevator_id} ▲ floor {self.current_floor}")
            if self.current_floor == next_floor:
                heapq.heappop(self._up_heap)
                self._open_door()
        elif self._down_heap:
            self.direction = Direction.DOWN
            self.state = ElevatorState.MOVING_DOWN
        else:
            self.direction = Direction.IDLE
            self.state = ElevatorState.IDLE

    def _process_down(self):
        if self._down_heap:
            next_floor = -self._down_heap[0]  # restore positive value
            if self.current_floor > next_floor:
                self.current_floor -= 1
                print(f"  Elevator {self.elevator_id} ▼ floor {self.current_floor}")
            if self.current_floor == next_floor:
                heapq.heappop(self._down_heap)
                self._open_door()
        elif self._up_heap:
            self.direction = Direction.UP
            self.state = ElevatorState.MOVING_UP
        else:
            self.direction = Direction.IDLE
            self.state = ElevatorState.IDLE

    def _open_door(self):
        prev_state = self.state
        self.state = ElevatorState.DOOR_OPEN
        print(f"  Elevator {self.elevator_id} ■ DOOR OPEN at floor {self.current_floor}")
        time.sleep(0.5)  # dwell time
        self.state = prev_state
        print(f"  Elevator {self.elevator_id} ■ DOOR CLOSED at floor {self.current_floor}")

    def __str__(self):
        return (f"Elevator{{id={self.elevator_id}, floor={self.current_floor}, "
                f"dir={self.direction.value}, state={self.state.value}, "
                f"pending={self.pending_count()}}}")


# ──────────────────────────────────────────────
#  Scheduling Strategy (Strategy Pattern)
# ──────────────────────────────────────────────

class SchedulingStrategy(ABC):
    @abstractmethod
    def select(self, elevators: list[Elevator], request: Request) -> Elevator:
        pass


class FCFSStrategy(SchedulingStrategy):
    """Pick the elevator with fewest pending requests."""
    def select(self, elevators: list[Elevator], request: Request) -> Elevator:
        return min(elevators, key=lambda e: e.pending_count())


class ShortestSeekStrategy(SchedulingStrategy):
    """Pick the nearest elevator regardless of direction."""
    def select(self, elevators: list[Elevator], request: Request) -> Elevator:
        return min(elevators, key=lambda e: abs(e.current_floor - request.from_floor))


class SCANStrategy(SchedulingStrategy):
    """
    SCAN: prefer idle elevators or elevators moving toward the request.
    Penalise elevators moving away.
    """
    def select(self, elevators: list[Elevator], request: Request) -> Elevator:
        def score(e: Elevator) -> int:
            dist = abs(e.current_floor - request.from_floor)
            if e.state == ElevatorState.IDLE:
                return dist
            same_dir = (
                (e.direction == Direction.UP and request.from_floor >= e.current_floor)
                or (e.direction == Direction.DOWN and request.from_floor <= e.current_floor)
            )
            return dist if same_dir else dist + 1000

        return min(elevators, key=score)


# ──────────────────────────────────────────────
#  Elevator Controller (Singleton)
# ──────────────────────────────────────────────

class ElevatorController:
    _instance: "ElevatorController | None" = None
    _init_lock = threading.Lock()

    def __new__(cls, elevators=None, strategy=None):
        with cls._init_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._elevators = elevators or []
                cls._instance._strategy = strategy or SCANStrategy()
                cls._instance._dispatch_lock = threading.Lock()
        return cls._instance

    def request_elevator(self, request: Request):
        with self._dispatch_lock:
            print(f"\n  >>> New request: {request}")
            selected = self._strategy.select(self._elevators, request)
            print(f"  >>> Assigned to Elevator {selected.elevator_id}")
            selected.add_request(request.from_floor)
            selected.add_request(request.to_floor)

    def set_strategy(self, strategy: SchedulingStrategy):
        self._strategy = strategy

    def print_status(self):
        print("\n  === Elevator Status ===")
        for e in self._elevators:
            print(f"  {e}")
        print()


# ──────────────────────────────────────────────
#  Building
# ──────────────────────────────────────────────

class Building:
    def __init__(self, total_floors: int, num_elevators: int,
                 strategy: SchedulingStrategy = None):
        self.total_floors = total_floors
        ElevatorController._instance = None  # reset for demo
        elevators = [Elevator(i, total_floors) for i in range(1, num_elevators + 1)]
        self._controller = ElevatorController(elevators, strategy or SCANStrategy())
        self._elevators = elevators

    def start(self):
        for e in self._elevators:
            e.start()
        print(f"  Building started: {len(self._elevators)} elevators, {self.total_floors} floors\n")

    def request(self, from_floor: int, to_floor: int):
        self._controller.request_elevator(Request(from_floor, to_floor))

    def status(self):
        self._controller.print_status()

    def shutdown(self):
        for e in self._elevators:
            e.shutdown()


# ──────────────────────────────────────────────
#  Demo
# ──────────────────────────────────────────────

if __name__ == "__main__":
    building = Building(total_floors=15, num_elevators=2, strategy=SCANStrategy())
    building.start()

    # Simulate several requests
    requests = [(1, 8), (5, 2), (3, 12), (10, 4)]
    for from_f, to_f in requests:
        building.request(from_f, to_f)
        time.sleep(0.1)

    building.status()
    time.sleep(8)  # let elevators run
    building.status()
    building.shutdown()
    print("  Elevator system shut down.")
