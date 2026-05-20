# 02 — LRU / LFU Cache (Python Implementation)

**File:** `lru_lfu_cache.py`  
**Tier:** 1 — Highest priority

---

## Problem Statement

Design an in-memory cache with configurable eviction policy (LRU or LFU). `get` and `put` must both be O(1). Handle concurrent reads and writes safely.

---

## Design Patterns Used

| Pattern | Where | Why |
|---|---|---|
| **Strategy** | `CachePolicy` enum selects eviction logic at creation time | Add new policies (FIFO, TTL) without changing the cache skeleton |
| **Factory** | `create_cache(policy, capacity)` | Hides which concrete class to instantiate |

---

## Class Structure

```
Node                          — doubly linked list node (key, val, freq, prev, next)
DoublyLinkedList              — O(1) add_to_head / detach / remove_tail

LRUCache                      — dict[key→Node] + single DLL
LFUCache                      — dict[key→Node] + dict[freq→DLL] + min_freq

create_cache("LRU"|"LFU", capacity) → LRUCache | LFUCache
```

---

## Data Structures

### LRU — HashMap + one DLL

```
HashMap<key → Node>   → O(1) lookup
DoublyLinkedList      → head = most-recent, tail = least-recent

HEAD ←→ [most recent] ←→ ... ←→ [least recent] ←→ TAIL
                                        ↑ evict this on overflow
```

### LFU — HashMap + FrequencyMap + DLL per frequency

```
HashMap<key → Node>            → O(1) lookup
HashMap<freq → DoublyLinkedList> → each freq bucket, LRU-ordered inside
int min_freq                   → which bucket to evict from

freq=1: [C] ←→ [D]   ← min_freq=1, evict tail
freq=2: [B]
freq=5: [A]
```

---

## Python vs Java Key Differences

| Concern | Java | Python |
|---|---|---|
| Interface | `Cache<K,V>` interface | No generics at runtime; type hints for clarity |
| Lock | `ReentrantReadWriteLock` | Single `threading.Lock` (LRU `get` modifies order, so a read lock would be wrong anyway) |
| Null sentinel | `null` | `None` |
| Inner class | `private static class Node` | Top-level `Node` class (Python has no access modifiers) |

---

## Core Algorithms

### LRU — GET
```
1. key not in map → return None
2. detach node from current position in DLL
3. add_to_head(node)   ← mark as most-recently used
4. return node.val
```

### LRU — PUT
```
1. key exists → update val, move to head, return
2. at capacity → evict remove_tail(), remove from map
3. create new Node, add_to_head, insert into map
```

### LFU — GET
```
1. key not in map → return None
2. remove node from freq_map[node.freq]
3. if that bucket empty AND node.freq == min_freq → min_freq++
4. node.freq++
5. add node to head of freq_map[node.freq]
6. return node.val
```

### LFU — PUT
```
1. key exists → update val, same promotion as GET
2. at capacity → evict remove_tail() from freq_map[min_freq]
3. create Node(freq=1), add to freq_map[1], set min_freq=1
```

---

## Concurrency

Both caches use a single `threading.Lock` that wraps every `get` and `put`:

```python
def get(self, key):
    with self._lock:
        ...  # safe to read AND reorder DLL

def put(self, key, val):
    with self._lock:
        ...
```

`get` in LRU **modifies** the DLL (moves node to head), so a pure read lock would be incorrect — a full write lock is the safe choice.

---

## O(1) Proof

| Operation | Data structure used | Why O(1) |
|---|---|---|
| `get` lookup | `dict` | Hash table lookup |
| Move to head | `DLL.detach + add_to_head` | Pointer surgery only, no traversal |
| Evict LRU | `DLL.remove_tail` | Tail pointer is always available |
| Evict LFU | `freq_map[min_freq].remove_tail` | `min_freq` tracked explicitly |
| Promote freq | Remove from old DLL, add to new DLL | O(1) pointer surgery |

---

## Interview Talking Points

1. **Why not use `collections.OrderedDict`?** — It works, but interviewers want to see the DLL + HashMap built explicitly to demonstrate understanding of the data structure.
2. **Why does `get` need a write lock in LRU?** — Because it modifies the DLL order (moves the accessed node to head). A read lock would allow a data race on `prev`/`next` pointers.
3. **LFU edge case: min_freq update** — `min_freq` only needs to increment (to `old_freq + 1`) on promotion, because a new item always resets `min_freq = 1`.
4. **LFU tie-breaking** — Among items with the same frequency, we evict the **least recently used** one (the tail of that freq's DLL).
