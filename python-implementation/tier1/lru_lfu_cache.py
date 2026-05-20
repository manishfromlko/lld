"""
LRU and LFU Cache
- LRU: HashMap + Doubly Linked List → O(1) get/put
- LFU: HashMap + FreqMap + DLL per frequency → O(1) get/put
Strategy Pattern via a common Cache interface.
"""

import threading
from abc import ABC, abstractmethod


# ──────────────────────────────────────────────
#  Doubly Linked List Node
# ──────────────────────────────────────────────

class Node:
    def __init__(self, key=None, val=None):
        self.key = key
        self.val = val
        self.freq = 1
        self.prev = None
        self.next = None


class DoublyLinkedList:
    """Head = most recent / most frequent. Tail = eviction candidate."""

    def __init__(self):
        self.head = Node()  # sentinel
        self.tail = Node()  # sentinel
        self.head.next = self.tail
        self.tail.prev = self.head
        self.size = 0

    def add_to_head(self, node: Node):
        node.next = self.head.next
        node.prev = self.head
        self.head.next.prev = node
        self.head.next = node
        self.size += 1

    def detach(self, node: Node):
        node.prev.next = node.next
        node.next.prev = node.prev
        node.prev = node.next = None
        self.size -= 1

    def remove_tail(self) -> Node | None:
        if self.size == 0:
            return None
        last = self.tail.prev
        self.detach(last)
        return last

    def is_empty(self) -> bool:
        return self.size == 0


# ──────────────────────────────────────────────
#  Cache Interface
# ──────────────────────────────────────────────

class Cache(ABC):
    @abstractmethod
    def get(self, key):
        pass

    @abstractmethod
    def put(self, key, value):
        pass

    @abstractmethod
    def size(self) -> int:
        pass


# ──────────────────────────────────────────────
#  LRU Cache
# ──────────────────────────────────────────────

class LRUCache(Cache):
    def __init__(self, capacity: int):
        self.capacity = capacity
        self._map: dict = {}          # key → Node
        self._dll = DoublyLinkedList()
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            if key not in self._map:
                return None
            node = self._map[key]
            self._move_to_head(node)
            return node.val

    def put(self, key, value):
        with self._lock:
            if key in self._map:
                node = self._map[key]
                node.val = value
                self._move_to_head(node)
                return

            if len(self._map) >= self.capacity:
                evicted = self._dll.remove_tail()
                if evicted:
                    del self._map[evicted.key]

            new_node = Node(key, value)
            self._dll.add_to_head(new_node)
            self._map[key] = new_node

    def _move_to_head(self, node: Node):
        self._dll.detach(node)
        self._dll.add_to_head(node)

    def size(self) -> int:
        return len(self._map)


# ──────────────────────────────────────────────
#  LFU Cache
# ──────────────────────────────────────────────

class LFUCache(Cache):
    def __init__(self, capacity: int):
        self.capacity = capacity
        self._map: dict = {}           # key → Node
        self._freq_map: dict = {}      # freq → DoublyLinkedList
        self._min_freq = 0
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            if key not in self._map:
                return None
            node = self._map[key]
            self._increase_freq(node)
            return node.val

    def put(self, key, value):
        with self._lock:
            if self.capacity == 0:
                return

            if key in self._map:
                node = self._map[key]
                node.val = value
                self._increase_freq(node)
                return

            if len(self._map) >= self.capacity:
                dll = self._freq_map.get(self._min_freq)
                if dll:
                    evicted = dll.remove_tail()
                    if evicted:
                        del self._map[evicted.key]

            new_node = Node(key, value)
            new_node.freq = 1
            self._min_freq = 1
            if 1 not in self._freq_map:
                self._freq_map[1] = DoublyLinkedList()
            self._freq_map[1].add_to_head(new_node)
            self._map[key] = new_node

    def _increase_freq(self, node: Node):
        old_freq = node.freq
        old_dll = self._freq_map.get(old_freq)
        if old_dll:
            old_dll.detach(node)
            if old_dll.is_empty():
                del self._freq_map[old_freq]
                if self._min_freq == old_freq:
                    self._min_freq += 1

        node.freq += 1
        if node.freq not in self._freq_map:
            self._freq_map[node.freq] = DoublyLinkedList()
        self._freq_map[node.freq].add_to_head(node)

    def size(self) -> int:
        return len(self._map)


# ──────────────────────────────────────────────
#  Factory
# ──────────────────────────────────────────────

def create_cache(policy: str, capacity: int) -> Cache:
    if policy == "LRU":
        return LRUCache(capacity)
    elif policy == "LFU":
        return LFUCache(capacity)
    raise ValueError(f"Unknown policy: {policy}")


# ──────────────────────────────────────────────
#  Demo
# ──────────────────────────────────────────────

if __name__ == "__main__":
    print("=== LRU Cache (capacity=3) ===")
    cache = create_cache("LRU", 3)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)
    print(f"  get('a') = {cache.get('a')}")   # 1, moves 'a' to MRU
    cache.put("d", 4)                          # evicts 'b' (LRU)
    print(f"  get('b') = {cache.get('b')}")   # None — evicted
    print(f"  get('c') = {cache.get('c')}")   # 3
    print(f"  get('d') = {cache.get('d')}")   # 4

    print("\n=== LFU Cache (capacity=3) ===")
    lfu = create_cache("LFU", 3)
    lfu.put("x", 10)
    lfu.put("y", 20)
    lfu.put("z", 30)
    lfu.get("x")  # freq[x]=2
    lfu.get("x")  # freq[x]=3
    lfu.get("y")  # freq[y]=2
    lfu.put("w", 40)  # evicts 'z' (freq=1, LRU among freq-1)
    print(f"  get('z') = {lfu.get('z')}")  # None — evicted
    print(f"  get('x') = {lfu.get('x')}")  # 10
    print(f"  get('y') = {lfu.get('y')}")  # 20
    print(f"  get('w') = {lfu.get('w')}")  # 40
