# 02 — LRU / LFU Cache with Thread Safety

**Priority:** TIER 1 — HIGHEST (classic senior LLD, tests DS + concurrency + strategy pattern)

---

## Problem Statement

Design a generic in-memory cache with configurable eviction policies (LRU, LFU). Support `get(key)`, `put(key, value)` with O(1) time complexity. Handle concurrent reads/writes safely.

---

## Clarification Questions to Ask the Interviewer

1. **Eviction policy:** LRU only, or should I support multiple (LRU, LFU, FIFO)?
2. **Generic types:** Should the cache be generic `Cache<K, V>` or specific?
3. **Concurrency:** Multiple threads reading/writing? (Expect YES)
4. **Size limit:** Fixed capacity? What happens when full? (Evict least recently/frequently used)
5. **Write policy:** Write-through (write to cache + backing store) or write-back (write to cache, lazy flush)?
6. **TTL:** Should entries expire after a time-to-live?
7. **Null values:** Can we store null values?

---

## Entities

```
Cache<K, V> (interface)
├── get(K key) → V
├── put(K key, V value)
└── size()

EvictionStrategy<K> (interface)  ← Strategy Pattern
├── LRUEvictionStrategy
├── LFUEvictionStrategy
└── FIFOEvictionStrategy

CacheStorage<K, V> (interface)
└── HashMapCacheStorage

CacheNode<K, V>
├── key, value
├── prev, next (for doubly linked list)
└── frequency (for LFU)
```

---

## Design Patterns

| Pattern | Where | Why |
|---|---|---|
| **Strategy** | `EvictionStrategy` — swap LRU/LFU/FIFO | Open/Closed principle — add eviction policies without modifying cache |
| **Factory** | `CacheFactory.create(policy, capacity)` | Create cache with the right eviction strategy |
| **Generic** | `Cache<K, V>` | Reusable for any key-value types |

---

## SOLID Principles Applied

| Principle | How |
|---|---|
| **S** | Cache handles caching; EvictionStrategy handles eviction; Storage handles storage |
| **O** | Add new eviction policies without modifying Cache class |
| **L** | Any EvictionStrategy can replace another |
| **I** | Cache interface is lean: get, put, size |
| **D** | Cache depends on EvictionStrategy interface, not LRU/LFU directly |

---

## Data Structure Choices

### LRU Cache — HashMap + Doubly Linked List

```
Why not just LinkedHashMap?
→ It works for simple cases, but interviewers want to see you build it.
→ Custom DLL gives O(1) detach + move-to-head.

HashMap<K, Node<K,V>>  → O(1) lookup by key
DoublyLinkedList        → O(1) move-to-front (most recent), remove-tail (evict)

Head ←→ [Most Recent] ←→ [Recent] ←→ ... ←→ [Least Recent] ←→ Tail
                                                    ↑
                                              evict this one
```

### LFU Cache — HashMap + FrequencyMap + DLL per frequency

```
HashMap<K, Node<K,V>>              → O(1) lookup
HashMap<Integer, DoublyLinkedList>  → frequency → list of nodes with that frequency
int minFrequency                    → tracks which frequency to evict from

freq=1: [C] ←→ [D]   ← minFreq=1, evict from here (LRU within same freq)
freq=2: [B]
freq=5: [A]
```

---

## Concurrency Strategy

**Primary:** `ReadWriteLock` — many readers, one writer

```java
ReadWriteLock rwLock = new ReentrantReadWriteLock();

V get(K key) {
    rwLock.readLock().lock();    // multiple gets can run in parallel
    try { ... }
    finally { rwLock.readLock().unlock(); }
}

void put(K key, V value) {
    rwLock.writeLock().lock();   // exclusive access
    try { ... }
    finally { rwLock.writeLock().unlock(); }
}
```

**But wait:** `get()` in LRU also MODIFIES the list (moves node to head). So we actually need write lock for get too, OR use lock striping.

**Alternative 1:** `synchronized` on the entire cache (simple but bottleneck)
**Alternative 2:** Lock striping — hash key to a segment, lock only that segment

```java
// Lock striping: key hash determines which lock
int segment = key.hashCode() % NUM_SEGMENTS;
locks[segment].lock();
```

**Alternative 3 (if interviewer says no built-in locks):** Use `AtomicReference` + CAS for the linked list head.

---

## Core Algorithm — LRU

```
GET(key):
  1. If key not in map → return null
  2. Node = map.get(key)
  3. Move node to HEAD of DLL (most recently used)
  4. Return node.value

PUT(key, value):
  1. If key exists → update value, move to HEAD
  2. If cache is full → remove TAIL node (least recently used), remove from map
  3. Create new node, add to HEAD, add to map
```

## Core Algorithm — LFU

```
GET(key):
  1. If key not in map → return null
  2. Node = map.get(key)
  3. Remove node from freqMap[node.freq]
  4. If freqMap[node.freq] is empty AND node.freq == minFreq → minFreq++
  5. node.freq++
  6. Add node to freqMap[node.freq]
  7. Return node.value

PUT(key, value):
  1. If key exists → update value, do same as GET (increase freq)
  2. If cache is full → evict LRU node from freqMap[minFreq] (tail of that list)
  3. Create new node with freq=1, add to freqMap[1], set minFreq=1
```

---

## Java Implementation

### Cache Interface

```java
public interface Cache<K, V> {
    V get(K key);
    void put(K key, V value);
    int size();
}
```

### Eviction Strategy Interface

```java
public interface EvictionStrategy<K> {
    void keyAccessed(K key);
    void keyAdded(K key);
    K evict();
}
```

### CacheNode (Doubly Linked List Node)

```java
public class CacheNode<K, V> {
    K key;
    V value;
    CacheNode<K, V> prev;
    CacheNode<K, V> next;
    int frequency;

    public CacheNode(K key, V value) {
        this.key = key;
        this.value = value;
        this.frequency = 1;
    }
}
```

### DoublyLinkedList

```java
public class DoublyLinkedList<K, V> {
    CacheNode<K, V> head;
    CacheNode<K, V> tail;
    int size;

    public DoublyLinkedList() {
        head = new CacheNode<>(null, null);
        tail = new CacheNode<>(null, null);
        head.next = tail;
        tail.prev = head;
        size = 0;
    }

    public void addToHead(CacheNode<K, V> node) {
        node.next = head.next;
        node.prev = head;
        head.next.prev = node;
        head.next = node;
        size++;
    }

    public void detach(CacheNode<K, V> node) {
        node.prev.next = node.next;
        node.next.prev = node.prev;
        node.prev = null;
        node.next = null;
        size--;
    }

    public CacheNode<K, V> removeTail() {
        if (size == 0) return null;
        CacheNode<K, V> last = tail.prev;
        detach(last);
        return last;
    }

    public boolean isEmpty() { return size == 0; }
}
```

### LRU Cache Implementation

```java
import java.util.*;
import java.util.concurrent.locks.*;

public class LRUCache<K, V> implements Cache<K, V> {
    private final int capacity;
    private final Map<K, CacheNode<K, V>> map;
    private final DoublyLinkedList<K, V> dll;
    private final ReadWriteLock rwLock = new ReentrantReadWriteLock();

    public LRUCache(int capacity) {
        this.capacity = capacity;
        this.map = new HashMap<>();
        this.dll = new DoublyLinkedList<>();
    }

    @Override
    public V get(K key) {
        rwLock.writeLock().lock();  // write lock because get modifies DLL order
        try {
            CacheNode<K, V> node = map.get(key);
            if (node == null) return null;
            moveToHead(node);
            return node.value;
        } finally {
            rwLock.writeLock().unlock();
        }
    }

    @Override
    public void put(K key, V value) {
        rwLock.writeLock().lock();
        try {
            CacheNode<K, V> existing = map.get(key);
            if (existing != null) {
                existing.value = value;
                moveToHead(existing);
                return;
            }
            if (map.size() >= capacity) {
                CacheNode<K, V> evicted = dll.removeTail();
                if (evicted != null) {
                    map.remove(evicted.key);
                }
            }
            CacheNode<K, V> newNode = new CacheNode<>(key, value);
            dll.addToHead(newNode);
            map.put(key, newNode);
        } finally {
            rwLock.writeLock().unlock();
        }
    }

    private void moveToHead(CacheNode<K, V> node) {
        dll.detach(node);
        dll.addToHead(node);
    }

    @Override
    public int size() {
        rwLock.readLock().lock();
        try { return map.size(); }
        finally { rwLock.readLock().unlock(); }
    }
}
```

### LFU Cache Implementation

```java
import java.util.*;
import java.util.concurrent.locks.*;

public class LFUCache<K, V> implements Cache<K, V> {
    private final int capacity;
    private final Map<K, CacheNode<K, V>> map;
    private final Map<Integer, DoublyLinkedList<K, V>> freqMap;
    private int minFreq;
    private final ReadWriteLock rwLock = new ReentrantReadWriteLock();

    public LFUCache(int capacity) {
        this.capacity = capacity;
        this.map = new HashMap<>();
        this.freqMap = new HashMap<>();
        this.minFreq = 0;
    }

    @Override
    public V get(K key) {
        rwLock.writeLock().lock();
        try {
            CacheNode<K, V> node = map.get(key);
            if (node == null) return null;
            increaseFrequency(node);
            return node.value;
        } finally {
            rwLock.writeLock().unlock();
        }
    }

    @Override
    public void put(K key, V value) {
        rwLock.writeLock().lock();
        try {
            if (capacity == 0) return;

            CacheNode<K, V> existing = map.get(key);
            if (existing != null) {
                existing.value = value;
                increaseFrequency(existing);
                return;
            }

            if (map.size() >= capacity) {
                DoublyLinkedList<K, V> minFreqList = freqMap.get(minFreq);
                CacheNode<K, V> evicted = minFreqList.removeTail();
                map.remove(evicted.key);
                if (minFreqList.isEmpty()) freqMap.remove(minFreq);
            }

            CacheNode<K, V> newNode = new CacheNode<>(key, value);
            newNode.frequency = 1;
            minFreq = 1;
            freqMap.computeIfAbsent(1, k -> new DoublyLinkedList<>()).addToHead(newNode);
            map.put(key, newNode);
        } finally {
            rwLock.writeLock().unlock();
        }
    }

    private void increaseFrequency(CacheNode<K, V> node) {
        int oldFreq = node.frequency;
        DoublyLinkedList<K, V> oldList = freqMap.get(oldFreq);
        oldList.detach(node);
        if (oldList.isEmpty()) {
            freqMap.remove(oldFreq);
            if (minFreq == oldFreq) minFreq++;
        }
        node.frequency++;
        freqMap.computeIfAbsent(node.frequency, k -> new DoublyLinkedList<>()).addToHead(node);
    }

    @Override
    public int size() {
        rwLock.readLock().lock();
        try { return map.size(); }
        finally { rwLock.readLock().unlock(); }
    }
}
```

### Cache Factory

```java
public class CacheFactory {
    public enum Policy { LRU, LFU }

    public static <K, V> Cache<K, V> create(Policy policy, int capacity) {
        return switch (policy) {
            case LRU -> new LRUCache<>(capacity);
            case LFU -> new LFUCache<>(capacity);
        };
    }
}
```

### Main Class (Demo)

```java
public class Main {
    public static void main(String[] args) {
        Cache<String, String> cache = CacheFactory.create(CacheFactory.Policy.LRU, 3);

        cache.put("a", "1");
        cache.put("b", "2");
        cache.put("c", "3");
        System.out.println(cache.get("a")); // "1" — moves "a" to most recent

        cache.put("d", "4"); // evicts "b" (least recently used)
        System.out.println(cache.get("b")); // null — evicted

        // Multithreaded test
        for (int i = 0; i < 10; i++) {
            final int idx = i;
            new Thread(() -> {
                cache.put("key-" + idx, "val-" + idx);
                System.out.println(Thread.currentThread().getName() + " put key-" + idx);
            }).start();
        }
    }
}
```

---

## Lock Striping Alternative (If Interviewer Wants More Granular)

```java
public class StripedLRUCache<K, V> implements Cache<K, V> {
    private static final int NUM_SEGMENTS = 16;
    private final LRUCache<K, V>[] segments;

    @SuppressWarnings("unchecked")
    public StripedLRUCache(int totalCapacity) {
        segments = new LRUCache[NUM_SEGMENTS];
        int perSegment = Math.max(1, totalCapacity / NUM_SEGMENTS);
        for (int i = 0; i < NUM_SEGMENTS; i++) {
            segments[i] = new LRUCache<>(perSegment);
        }
    }

    private int segmentFor(K key) {
        return (key.hashCode() & 0x7FFFFFFF) % NUM_SEGMENTS;
    }

    @Override
    public V get(K key) { return segments[segmentFor(key)].get(key); }

    @Override
    public void put(K key, V value) { segments[segmentFor(key)].put(key, value); }

    @Override
    public int size() {
        int total = 0;
        for (LRUCache<K, V> seg : segments) total += seg.size();
        return total;
    }
}
```

Same concept as ConcurrentHashMap per-bucket locking — partition the contention.

---

## Comparison Table

| Aspect | LRU | LFU |
|---|---|---|
| Evicts | Least **recently** used | Least **frequently** used |
| Data structures | HashMap + 1 DLL | HashMap + FreqMap + DLL per freq |
| Complexity | Simpler | More complex |
| Good for | General caching, recency matters | When frequency of access matters |
| Bad for | Scan pollution (one-time items push out frequent items) | Items accessed heavily early but not anymore |

---

## Interview-Ready Answer

> "I'd design the cache using the Strategy pattern with a `Cache<K,V>` interface and swappable eviction strategies. LRU uses a HashMap for O(1) lookup and a Doubly Linked List for O(1) move-to-head and evict-from-tail. LFU extends this with a frequency map where each frequency has its own DLL, and a minFreq tracker for O(1) eviction. For thread safety, I'd use a ReadWriteLock — though in LRU, get also modifies the list order, so it needs a write lock. For higher throughput, I'd use lock striping — partitioning keys into segments, each with its own lock — same principle as ConcurrentHashMap."
