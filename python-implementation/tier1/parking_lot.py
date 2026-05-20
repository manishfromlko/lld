"""
Parking Lot System
- Singleton ParkingLot
- Strategy Pattern: FeeStrategy (Hourly / FlatRate)
- Per-spot thread-safe atomic occupation
"""

import threading
import time
import uuid
from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass, field
from collections import defaultdict
from queue import Queue


# ──────────────────────────────────────────────
#  Enums
# ──────────────────────────────────────────────

class VehicleType(Enum):
    BIKE = "BIKE"
    CAR = "CAR"
    TRUCK = "TRUCK"


class SpotType(Enum):
    COMPACT = "COMPACT"
    REGULAR = "REGULAR"
    LARGE = "LARGE"

    @staticmethod
    def from_vehicle(vtype: VehicleType) -> "SpotType":
        mapping = {
            VehicleType.BIKE: SpotType.COMPACT,
            VehicleType.CAR: SpotType.REGULAR,
            VehicleType.TRUCK: SpotType.LARGE,
        }
        return mapping[vtype]


# ──────────────────────────────────────────────
#  Vehicle
# ──────────────────────────────────────────────

@dataclass
class Vehicle:
    license_plate: str
    vehicle_type: VehicleType

    def __str__(self):
        return f"{self.vehicle_type.value}[{self.license_plate}]"


# ──────────────────────────────────────────────
#  Parking Spot (thread-safe via threading.Lock)
# ──────────────────────────────────────────────

class ParkingSpot:
    def __init__(self, spot_id: str, spot_type: SpotType):
        self.spot_id = spot_id
        self.spot_type = spot_type
        self._vehicle: Vehicle | None = None
        self._lock = threading.Lock()

    def occupy(self, vehicle: Vehicle) -> bool:
        with self._lock:
            if self._vehicle is not None:
                return False
            self._vehicle = vehicle
            return True

    def release(self) -> Vehicle | None:
        with self._lock:
            v = self._vehicle
            self._vehicle = None
            return v

    @property
    def is_available(self) -> bool:
        return self._vehicle is None

    def __str__(self):
        status = "FREE" if self.is_available else str(self._vehicle)
        return f"{self.spot_type.value}-{self.spot_id}[{status}]"


# ──────────────────────────────────────────────
#  Parking Floor
# ──────────────────────────────────────────────

class ParkingFloor:
    def __init__(self, floor_num: int, compact: int, regular: int, large: int):
        self.floor_num = floor_num
        self._available: dict[SpotType, Queue] = {t: Queue() for t in SpotType}
        self._all_spots: list[ParkingSpot] = []

        for spot_type, count in [(SpotType.COMPACT, compact),
                                  (SpotType.REGULAR, regular),
                                  (SpotType.LARGE, large)]:
            for i in range(1, count + 1):
                sid = f"F{floor_num}-{spot_type.value[0]}{i}"
                spot = ParkingSpot(sid, spot_type)
                self._available[spot_type].put(spot)
                self._all_spots.append(spot)

    def allocate(self, spot_type: SpotType, vehicle: Vehicle) -> ParkingSpot | None:
        q = self._available[spot_type]
        while not q.empty():
            spot = q.get()
            if spot.occupy(vehicle):
                return spot
            # Lost the race — spot was taken; don't re-queue (it's occupied)
        return None

    def release(self, spot: ParkingSpot):
        spot.release()
        self._available[spot.spot_type].put(spot)

    def available_count(self, spot_type: SpotType) -> int:
        return self._available[spot_type].qsize()

    def status(self) -> str:
        parts = [f"Floor {self.floor_num}:"]
        for t in SpotType:
            parts.append(f"{t.value}={self.available_count(t)}")
        return " ".join(parts)


# ──────────────────────────────────────────────
#  Ticket
# ──────────────────────────────────────────────

@dataclass
class Ticket:
    ticket_id: str
    vehicle: Vehicle
    spot: ParkingSpot
    entry_time: float = field(default_factory=time.time)

    def __str__(self):
        return f"Ticket[{self.ticket_id} | {self.vehicle} | {self.spot.spot_id}]"


# ──────────────────────────────────────────────
#  Fee Strategy (Strategy Pattern)
# ──────────────────────────────────────────────

class FeeStrategy(ABC):
    @abstractmethod
    def calculate(self, entry_time: float, exit_time: float) -> float:
        pass


class HourlyFeeStrategy(FeeStrategy):
    def __init__(self, rate_per_hour: float):
        self.rate = rate_per_hour

    def calculate(self, entry_time: float, exit_time: float) -> float:
        import math
        hours = math.ceil((exit_time - entry_time) / 3600)
        return max(1, hours) * self.rate


class FlatRateFeeStrategy(FeeStrategy):
    def __init__(self, flat_rate: float):
        self.flat_rate = flat_rate

    def calculate(self, entry_time: float, exit_time: float) -> float:
        return self.flat_rate


# ──────────────────────────────────────────────
#  Parking Lot (Singleton)
# ──────────────────────────────────────────────

class ParkingLot:
    _instance: "ParkingLot | None" = None
    _init_lock = threading.Lock()

    def __new__(cls, name: str = ""):
        with cls._init_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._name = name
                cls._instance._floors: list[ParkingFloor] = []
        return cls._instance

    def add_floor(self, floor: ParkingFloor):
        self._floors.append(floor)

    @property
    def floors(self) -> list[ParkingFloor]:
        return self._floors

    def print_status(self):
        print(f"=== {self._name} ===")
        for floor in self._floors:
            print(f"  {floor.status()}")


# ──────────────────────────────────────────────
#  Parking Service (Facade)
# ──────────────────────────────────────────────

class ParkingService:
    def __init__(self, lot: ParkingLot, fee_strategy: FeeStrategy):
        self._lot = lot
        self._fee_strategy = fee_strategy
        self._active_tickets: dict[str, Ticket] = {}
        self._lock = threading.Lock()

    def set_fee_strategy(self, strategy: FeeStrategy):
        self._fee_strategy = strategy

    def park(self, vehicle: Vehicle) -> Ticket | None:
        required = SpotType.from_vehicle(vehicle.vehicle_type)
        for floor in self._lot.floors:
            spot = floor.allocate(required, vehicle)
            if spot:
                ticket = Ticket(str(uuid.uuid4())[:8].upper(), vehicle, spot)
                with self._lock:
                    self._active_tickets[vehicle.license_plate] = ticket
                print(f"  [PARK]   {vehicle} → {spot.spot_id} | {ticket.ticket_id}")
                return ticket
        print(f"  [FULL]   No {required.value} spot for {vehicle}")
        return None

    def unpark(self, license_plate: str) -> float:
        with self._lock:
            ticket = self._active_tickets.pop(license_plate, None)
        if not ticket:
            print(f"  [ERROR]  No ticket for {license_plate}")
            return -1

        fee = self._fee_strategy.calculate(ticket.entry_time, time.time())
        # Release the spot back to its floor
        for floor in self._lot.floors:
            if ticket.spot.spot_id.startswith(f"F{floor.floor_num}"):
                floor.release(ticket.spot)
                break
        print(f"  [UNPARK] {ticket.vehicle} from {ticket.spot.spot_id} | Fee: ${fee:.2f}")
        return fee


# ──────────────────────────────────────────────
#  Demo
# ──────────────────────────────────────────────

if __name__ == "__main__":
    # Reset singleton for demo
    ParkingLot._instance = None

    lot = ParkingLot("Downtown Garage")
    lot.add_floor(ParkingFloor(1, compact=5, regular=4, large=2))
    lot.add_floor(ParkingFloor(2, compact=5, regular=4, large=2))

    service = ParkingService(lot, HourlyFeeStrategy(10.0))
    lot.print_status()
    print()

    # Park vehicles concurrently
    vehicles = [Vehicle(f"CAR-{i:03d}", VehicleType.CAR) for i in range(1, 7)]
    threads = [threading.Thread(target=service.park, args=(v,)) for v in vehicles]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print()
    lot.print_status()
    print()

    # Bike and truck
    service.park(Vehicle("BIKE-001", VehicleType.BIKE))
    service.park(Vehicle("TRUCK-001", VehicleType.TRUCK))

    print()
    service.unpark("CAR-001")
    service.unpark("BIKE-001")

    # Switch to flat rate
    service.set_fee_strategy(FlatRateFeeStrategy(25.0))
    service.unpark("CAR-002")

    print()
    lot.print_status()
