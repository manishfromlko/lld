# 07 — Pub-Sub / Message Queue (Python Implementation)

**File:** `pub_sub.py`  
**Tier:** 2

---

## Problem Statement

Design an in-memory pub-sub system supporting two consumption models:
- **Broadcast** (independent consumers): every consumer sees every message from its own offset.
- **Consumer Group** (shared offset): messages are partitioned round-robin across group members — each message goes to exactly one member.

---

## Design Patterns Used

| Pattern | Where | Why |
|---|---|---|
| **Singleton** | `MessageBroker.__new__` | One broker per process; topics are registered globally |
| **Observer** | `Consumer` / `GroupConsumer` threads react to `Topic.publish` | Decoupled producers from consumers via condition variable |

---

## Class Structure

```
Message(payload, msg_id, timestamp)

Topic(name)
├── _messages: list[Message]    — append-only log
├── _cond: threading.Condition
├── publish(msg)                — notify_all()
└── consume(offset) → Message   — blocking wait until offset exists

Consumer(Thread)               — independent offset, sees ALL messages
ConsumerGroup
└── GroupConsumer(Thread)      — shared group offset (round-robin)

Producer(Thread)               — publishes N messages to a topic

MessageBroker (Singleton)      — create_topic / get_topic / publish
```

---

## Core Mechanism — `threading.Condition`

The `Topic` uses a `Condition` variable (monitor) as the wait/notify mechanism. This is the Python equivalent of Java's `Object.wait()` / `Object.notifyAll()`.

```python
def publish(self, message: Message):
    with self._cond:
        self._messages.append(message)
        self._cond.notify_all()   # wake ALL waiting consumers

def consume(self, offset: int) -> Message:
    with self._cond:
        while offset >= len(self._messages):
            self._cond.wait()     # releases lock, suspends thread
        return self._messages[offset]
```

- `wait()` atomically releases the condition lock and suspends the thread.
- `notify_all()` wakes every consumer; each then re-checks whether its offset is now available.

---

## Broadcast Model — Independent Consumer

Each `Consumer` thread tracks its own `_offset`:

```python
class Consumer(threading.Thread):
    def run(self):
        while self._running:
            msg = self._topic.consume(self._offset)   # blocks if not ready
            process(msg)
            self._offset += 1
```

Two consumers on the same topic each start at offset 0 and independently advance. Both see every message — like Kafka consumer groups with one member each.

---

## Consumer Group Model — Shared Offset (Round-Robin)

All group members share a single `_group_offset` protected by a lock:

```python
class ConsumerGroup:
    def _claim_next_offset(self) -> int:
        with self._offset_lock:
            offset = self._group_offset
            self._group_offset += 1
            return offset   # this member exclusively processes this offset
```

Each `GroupConsumer` claims the next unclaimed offset atomically. Message N goes to whichever member claims it first — effectively round-robin under equal speed, but correct even under varying speeds.

---

## Message Log — Append-Only

`Topic._messages` is a plain `list`. Messages are **never deleted** — consumers advance their own offset instead. This matches Kafka's log-based design and allows:
- Replay from any offset.
- Independent progress across consumers.

---

## Python vs Java Key Differences

| Concern | Java | Python |
|---|---|---|
| Monitor | `Object.wait()` / `notifyAll()` inside `synchronized` | `threading.Condition.wait()` / `notify_all()` inside `with cond:` |
| Thread class | `extends Thread` or `implements Runnable` | `threading.Thread` subclass, override `run()` |
| Atomic counter | `AtomicInteger` | `threading.Lock` guarding a plain `int` |
| Singleton | DCL with `volatile` | `__new__` + `threading.Lock` |

---

## Threading Model

```
Producer thread  →  Topic.publish()  →  notify_all()
                                              ↓
Consumer-C1 wakes, reads offset 0, C1._offset=1
Consumer-C2 wakes, reads offset 0, C2._offset=1   ← independent, both see msg 0

GroupConsumer-G1 claims offset 0, reads msg 0
GroupConsumer-G2 claims offset 1, reads msg 1      ← split, each gets one
```

---

## Interview Talking Points

1. **`notify_all` vs `notify`** — With multiple consumers, `notify()` would wake only one. If that consumer's offset isn't ready yet (e.g., there are gaps), no consumer makes progress. `notify_all()` is safe here because consumers re-check the condition (`while offset >= len`).
2. **Why append-only log?** — Deletion would invalidate existing consumer offsets. An append-only log lets any consumer replay from any point in time.
3. **Round-robin vs work-stealing** — The `_claim_next_offset` approach is effectively work-stealing: the fastest consumer claims the most messages. True round-robin would pre-assign messages, which is fragile if a consumer is slow.
4. **Persistence** — Extend by writing messages to disk (WAL) before `notify_all`. On restart, reload from disk to rebuild `_messages`.
