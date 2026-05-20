# 07 — Pub-Sub / In-Memory Message Queue

**Priority:** TIER 2 — tests producer-consumer, Observer pattern, concurrency

---

## Problem Statement

Design an in-memory publish-subscribe message queue that supports:

- **Topics** — logical channels that decouple producers from consumers.
- **Multiple producers** — any number of threads can publish to a topic concurrently.
- **Multiple consumers** — each consumer independently tracks its own offset.
- **Consumer groups** — a set of consumers that share a single logical offset so that messages are partitioned across group members (parallel consumption).
- **Message persistence (in-memory)** — messages are stored in an append-only list and survive for the lifetime of the process (or until a configurable TTL expires).
- **Offset-based consumption** — consumers pull messages starting from a stored offset, enabling replay and at-least-once delivery.
- **Parallel consumers** — consumer groups distribute messages round-robin across members for horizontal throughput.

---

## Clarification Questions

| # | Question | Why It Matters |
|---|----------|---------------|
| 1 | How many topics do we expect? Are they created up-front or dynamically? | Determines whether we need a concurrent topic registry. |
| 2 | Is message ordering per-topic guaranteed? | Drives the choice between a single lock per topic vs. partitioned structures. |
| 3 | What delivery semantics — **at-least-once** or **at-most-once**? | Affects whether we commit offset before or after processing. |
| 4 | Do we need **consumer groups** (Kafka-style) where only one member in the group gets each message? | Changes from broadcast to round-robin dispatch. |
| 5 | Who tracks offsets — the broker or the consumer? | Determines state ownership and crash-recovery behavior. |
| 6 | Should messages persist forever or have a **TTL / max-size**? | Impacts memory management and cleanup threads. |
| 7 | Is **backpressure** needed — should producers block when consumers are too far behind? | Decides whether we cap the message list or apply flow control. |

---

## Entities

```
┌──────────────┐        publishes to        ┌──────────┐
│   Producer   │ ──────────────────────────► │  Topic   │
└──────────────┘                             │          │
                                             │ messages │
┌──────────────┐   polls (offset-based)      │ subs     │
│   Consumer   │ ◄────────────────────────── │          │
└──────────────┘                             └──────────┘
       │ belongs to                                │
       ▼                                           │ managed by
┌───────────────┐                            ┌──────────────┐
│ ConsumerGroup │                            │ MessageBroker│
└───────────────┘                            └──────────────┘
```

| Entity | Key Fields |
|--------|-----------|
| **Topic** | `name`, `List<Message> messages`, `List<ConsumerGroup> subscriberGroups` |
| **Message** | `id` (auto-increment), `payload` (String), `timestamp` |
| **Producer** | reference to `MessageBroker`, target `topicName` |
| **Consumer** | `consumerId`, subscribed `topicName`, `AtomicInteger offset` |
| **ConsumerGroup** | `groupId`, `List<Consumer> members`, shared `AtomicInteger groupOffset` |
| **MessageBroker** | `ConcurrentHashMap<String, Topic> topics` — central registry (Singleton) |

---

## Design Patterns

### 1. Observer Pattern — Topic → Subscribers

When a producer publishes a message, the topic calls `notifyAll()` inside a `synchronized` block. All consumers that are blocked in `wait()` wake up and pull from their offset.

```
Producer.publish(msg)
  └─► Topic.addMessage(msg)
        └─► synchronized(this) { messages.add(msg); notifyAll(); }
              └─► Consumer threads wake from wait(), read from offset
```

### 2. Strategy Pattern — DeliveryStrategy

The broker delegates message delivery to a pluggable strategy:

| Strategy | Behavior |
|----------|----------|
| `BROADCAST` | Every consumer (or every group) receives every message. |
| `ROUND_ROBIN` | Within a consumer group, messages are distributed one-per-consumer in rotation. |

This makes the dispatch mechanism open for extension without modifying Topic.

### 3. Factory Pattern — TopicFactory / ConsumerFactory

`TopicFactory.create(name)` encapsulates topic creation with default settings (TTL, max-size). `ConsumerFactory.create(groupId, topicName)` wires the consumer to the correct group and topic.

### 4. Singleton Pattern — MessageBroker

A single `MessageBroker` instance coordinates all topic creation, lookup, and lifecycle management. Implemented via a private constructor + static holder for thread-safe lazy initialization.

---

## SOLID Principles

| Principle | How It Applies |
|-----------|---------------|
| **S — Single Responsibility** | `Topic` stores messages; `Consumer` tracks offset and reads; `MessageBroker` manages routing. No class does more than one job. |
| **O — Open/Closed** | New delivery strategies (`BROADCAST`, `ROUND_ROBIN`, `PRIORITY`) are added by implementing `DeliveryStrategy` — no existing code changes. |
| **L — Liskov Substitution** | Any `DeliveryStrategy` implementation can replace another without breaking `Topic` or `ConsumerGroup`. |
| **I — Interface Segregation** | `Publisher` interface exposes only `publish()`; `Subscriber` interface exposes only `poll()` / `consume()`. Consumers don't see publish methods and vice-versa. |
| **D — Dependency Inversion** | `MessageBroker` depends on the `DeliveryStrategy` abstraction, not on concrete `BroadcastStrategy` or `RoundRobinStrategy`. Strategies are injected at topic creation. |

---

## Core Algorithm

### Publish Flow

```
1. Producer calls broker.publish(topicName, payload)
2. Broker looks up Topic in ConcurrentHashMap
3. Topic acquires synchronized(this)
4. Message created with auto-incremented ID + timestamp
5. Message appended to topic.messages (ArrayList — append-only)
6. topic.notifyAll()  →  wake all waiting consumers
7. Lock released
```

### Consume Flow (per consumer, offset-based)

```
1. Consumer calls topic.consume(offset)
2. synchronized(topic):
     while (offset >= topic.messages.size()):
         topic.wait()          // block until new messages
3. Read messages[offset .. messages.size()-1]
4. Advance consumer's AtomicInteger offset
5. Return batch to caller
```

### Consumer Group — Parallel Consumption

```
1. ConsumerGroup maintains a shared groupOffset (AtomicInteger)
2. On each consume cycle:
     a. groupOffset.getAndIncrement() to claim the next message index
     b. If index < messages.size(), that consumer processes it
     c. If index >= messages.size(), consumer waits (wait/notify)
3. Result: messages are partitioned across group members without duplication
```

---

## Data Structure Choices

| Structure | Purpose | Why This Choice |
|-----------|---------|----------------|
| `ConcurrentHashMap<String, Topic>` | Topic registry | O(1) lookup, thread-safe without external lock, allows concurrent topic creation |
| `ArrayList<Message>` | Per-topic message store | Append-only, O(1) amortized add, O(1) random access by offset index |
| `AtomicInteger` | Message IDs, consumer offsets | Lock-free atomic increment, avoids synchronizing just for ID generation |
| `synchronized + wait/notify` | Consumer blocking | Classic producer-consumer; no extra dependencies |
| `BlockingQueue` (alternative) | Consumer blocking | Cleaner API (`take()` blocks automatically), but interviewer may disallow |

### If Interviewer Says "Don't Use BlockingQueue"

Use `ArrayList` + `AtomicInteger` offset + `synchronized` + `wait/notify`:

```java
// Consumer — blocking read
synchronized (topic) {
    while (offset.get() >= topic.getMessageCount()) {
        topic.wait();  // no new messages → block
    }
    Message msg = topic.getMessage(offset.getAndIncrement());
    // process msg
}

// Producer — publish
synchronized (topic) {
    topic.addMessage(message);
    topic.notifyAll();  // wake up all waiting consumers
}
```

### Alternative: AtomicBoolean + CAS Spin-Wait (No Built-In Locks)

If the interviewer disallows `synchronized` entirely:

```java
private final AtomicBoolean lock = new AtomicBoolean(false);

// Acquire
while (!lock.compareAndSet(false, true)) {
    Thread.onSpinWait();  // hint to JVM — reduce power in tight loop
}
try {
    // critical section: read/write messages
} finally {
    lock.set(false);  // release
}
```

> **Trade-off:** spin-wait burns CPU; only appropriate for very short critical sections with low contention.

---

## Concurrency Strategy

| Approach | Mechanism | When to Use |
|----------|-----------|-------------|
| **Primary** | `synchronized` + `wait/notify` on `Topic` | Default — simple, well-understood, sufficient for in-memory queues |
| **Alternative 1** | `LinkedBlockingQueue` | When the interviewer is fine with `java.util.concurrent` — cleaner API, built-in blocking |
| **Alternative 2** | `AtomicBoolean` + CAS spin-wait | When interviewer says "no synchronized" — demonstrates lock-free knowledge |
| **Alternative 3** | `ReentrantLock` + `Condition` | When you need multiple conditions (e.g., separate "not-empty" and "not-full" conditions for backpressure) |

### ReentrantLock + Condition Example

```java
private final ReentrantLock lock = new ReentrantLock();
private final Condition notEmpty = lock.newCondition();

// Publish
lock.lock();
try {
    messages.add(message);
    notEmpty.signalAll();
} finally {
    lock.unlock();
}

// Consume
lock.lock();
try {
    while (offset >= messages.size()) {
        notEmpty.await();
    }
    Message msg = messages.get(offset++);
} finally {
    lock.unlock();
}
```

---

## Java Implementation

### Message

```java
public class Message {

    private static final AtomicInteger ID_GEN = new AtomicInteger(0);

    private final int id;
    private final String payload;
    private final long timestamp;

    public Message(String payload) {
        this.id = ID_GEN.incrementAndGet();
        this.payload = payload;
        this.timestamp = System.currentTimeMillis();
    }

    public int getId() {
        return id;
    }

    public String getPayload() {
        return payload;
    }

    public long getTimestamp() {
        return timestamp;
    }

    @Override
    public String toString() {
        return "Message{id=" + id + ", payload='" + payload + "'}";
    }
}
```

### DeliveryStrategy

```java
public enum DeliveryStrategy {
    BROADCAST,
    ROUND_ROBIN
}
```

### Topic

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

public class Topic {

    private final String name;
    private final List<Message> messages;
    private final List<ConsumerGroup> subscriberGroups;

    public Topic(String name) {
        this.name = name;
        this.messages = new ArrayList<>();
        this.subscriberGroups = new CopyOnWriteArrayList<>();
    }

    public String getName() {
        return name;
    }

    public synchronized void publish(Message message) {
        messages.add(message);
        notifyAll();
    }

    public synchronized Message consume(int offset) throws InterruptedException {
        while (offset >= messages.size()) {
            wait();
        }
        return messages.get(offset);
    }

    public synchronized List<Message> consumeBatch(int fromOffset, int maxBatch) throws InterruptedException {
        while (fromOffset >= messages.size()) {
            wait();
        }
        int toIndex = Math.min(messages.size(), fromOffset + maxBatch);
        return Collections.unmodifiableList(new ArrayList<>(messages.subList(fromOffset, toIndex)));
    }

    public synchronized int getMessageCount() {
        return messages.size();
    }

    public void addSubscriberGroup(ConsumerGroup group) {
        subscriberGroups.add(group);
    }

    public List<ConsumerGroup> getSubscriberGroups() {
        return Collections.unmodifiableList(subscriberGroups);
    }
}
```

### Consumer

```java
import java.util.concurrent.atomic.AtomicInteger;

public class Consumer implements Runnable {

    private final String consumerId;
    private final Topic topic;
    private final AtomicInteger offset;
    private volatile boolean running;

    public Consumer(String consumerId, Topic topic) {
        this.consumerId = consumerId;
        this.topic = topic;
        this.offset = new AtomicInteger(0);
        this.running = true;
    }

    public String getConsumerId() {
        return consumerId;
    }

    public void stop() {
        this.running = false;
    }

    @Override
    public void run() {
        System.out.println("[Consumer-" + consumerId + "] started on topic: " + topic.getName());
        while (running) {
            try {
                int currentOffset = offset.get();
                Message msg = topic.consume(currentOffset);
                offset.incrementAndGet();
                System.out.println("[Consumer-" + consumerId + "] offset=" + currentOffset
                        + " → " + msg);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                break;
            }
        }
        System.out.println("[Consumer-" + consumerId + "] stopped.");
    }
}
```

### ConsumerGroup

```java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;

public class ConsumerGroup {

    private final String groupId;
    private final Topic topic;
    private final List<GroupConsumer> members;
    private final AtomicInteger groupOffset;

    public ConsumerGroup(String groupId, Topic topic) {
        this.groupId = groupId;
        this.topic = topic;
        this.members = new CopyOnWriteArrayList<>();
        this.groupOffset = new AtomicInteger(0);
        topic.addSubscriberGroup(this);
    }

    public String getGroupId() {
        return groupId;
    }

    public GroupConsumer addMember(String memberId) {
        GroupConsumer member = new GroupConsumer(memberId, this);
        members.add(member);
        return member;
    }

    public Topic getTopic() {
        return topic;
    }

    public AtomicInteger getGroupOffset() {
        return groupOffset;
    }

    /**
     * A consumer that belongs to a group. It claims the next unprocessed
     * message via the shared groupOffset, ensuring each message is
     * delivered to exactly one member in the group (round-robin effect).
     */
    public static class GroupConsumer implements Runnable {

        private final String memberId;
        private final ConsumerGroup group;
        private volatile boolean running;

        public GroupConsumer(String memberId, ConsumerGroup group) {
            this.memberId = memberId;
            this.group = group;
            this.running = true;
        }

        public void stop() {
            this.running = false;
        }

        @Override
        public void run() {
            Topic topic = group.getTopic();
            AtomicInteger sharedOffset = group.getGroupOffset();
            System.out.println("[GroupConsumer-" + memberId + " | group=" + group.getGroupId()
                    + "] started on topic: " + topic.getName());

            while (running) {
                int claimedOffset = sharedOffset.getAndIncrement();
                try {
                    Message msg = topic.consume(claimedOffset);
                    System.out.println("[GroupConsumer-" + memberId + " | group="
                            + group.getGroupId() + "] offset=" + claimedOffset + " → " + msg);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    break;
                }
            }
            System.out.println("[GroupConsumer-" + memberId + "] stopped.");
        }
    }
}
```

### Producer

```java
public class Producer implements Runnable {

    private final String producerId;
    private final Topic topic;
    private final int messageCount;
    private final long delayMs;

    public Producer(String producerId, Topic topic, int messageCount, long delayMs) {
        this.producerId = producerId;
        this.topic = topic;
        this.messageCount = messageCount;
        this.delayMs = delayMs;
    }

    @Override
    public void run() {
        System.out.println("[Producer-" + producerId + "] started on topic: " + topic.getName());
        for (int i = 1; i <= messageCount; i++) {
            String payload = "P" + producerId + "-msg-" + i;
            topic.publish(new Message(payload));
            System.out.println("[Producer-" + producerId + "] published: " + payload);
            if (delayMs > 0) {
                try {
                    Thread.sleep(delayMs);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    break;
                }
            }
        }
        System.out.println("[Producer-" + producerId + "] finished.");
    }
}
```

### MessageBroker (Singleton)

```java
import java.util.concurrent.ConcurrentHashMap;

public class MessageBroker {

    private static volatile MessageBroker instance;
    private final ConcurrentHashMap<String, Topic> topics;

    private MessageBroker() {
        this.topics = new ConcurrentHashMap<>();
    }

    public static MessageBroker getInstance() {
        if (instance == null) {
            synchronized (MessageBroker.class) {
                if (instance == null) {
                    instance = new MessageBroker();
                }
            }
        }
        return instance;
    }

    public Topic createTopic(String name) {
        return topics.computeIfAbsent(name, Topic::new);
    }

    public Topic getTopic(String name) {
        Topic topic = topics.get(name);
        if (topic == null) {
            throw new IllegalArgumentException("Topic not found: " + name);
        }
        return topic;
    }

    public void publish(String topicName, String payload) {
        Topic topic = getTopic(topicName);
        topic.publish(new Message(payload));
    }

    public void removeTopic(String name) {
        topics.remove(name);
    }

    public boolean hasTopic(String name) {
        return topics.containsKey(name);
    }

    /** Reset for testing — not for production use. */
    public void clear() {
        topics.clear();
    }
}
```

### Main — Full Demo

```java
public class PubSubDemo {

    public static void main(String[] args) throws InterruptedException {

        MessageBroker broker = MessageBroker.getInstance();
        Topic orderTopic = broker.createTopic("orders");

        // ── Independent Consumers (BROADCAST-style: each sees ALL messages) ──

        Consumer consumer1 = new Consumer("C1", orderTopic);
        Consumer consumer2 = new Consumer("C2", orderTopic);
        Consumer consumer3 = new Consumer("C3", orderTopic);

        Thread ct1 = new Thread(consumer1, "consumer-C1");
        Thread ct2 = new Thread(consumer2, "consumer-C2");
        Thread ct3 = new Thread(consumer3, "consumer-C3");
        ct1.start();
        ct2.start();
        ct3.start();

        // ── Producers ──

        Producer producerA = new Producer("A", orderTopic, 5, 100);
        Producer producerB = new Producer("B", orderTopic, 5, 150);

        Thread pt1 = new Thread(producerA, "producer-A");
        Thread pt2 = new Thread(producerB, "producer-B");
        pt1.start();
        pt2.start();

        // Wait for producers to finish
        pt1.join();
        pt2.join();

        // Give consumers time to drain remaining messages
        Thread.sleep(2000);

        // Stop consumers
        consumer1.stop();
        consumer2.stop();
        consumer3.stop();

        // Interrupt waiting consumers so they exit cleanly
        ct1.interrupt();
        ct2.interrupt();
        ct3.interrupt();

        ct1.join();
        ct2.join();
        ct3.join();

        System.out.println("\n=== Consumer Group Demo (ROUND_ROBIN) ===\n");

        // ── Consumer Group (ROUND_ROBIN: each message goes to ONE member) ──

        Topic paymentTopic = broker.createTopic("payments");

        ConsumerGroup group = new ConsumerGroup("payment-processors", paymentTopic);
        ConsumerGroup.GroupConsumer gc1 = group.addMember("G1");
        ConsumerGroup.GroupConsumer gc2 = group.addMember("G2");

        Thread gt1 = new Thread(gc1, "group-consumer-G1");
        Thread gt2 = new Thread(gc2, "group-consumer-G2");
        gt1.start();
        gt2.start();

        Producer producerC = new Producer("C", paymentTopic, 10, 50);
        Thread pt3 = new Thread(producerC, "producer-C");
        pt3.start();
        pt3.join();

        Thread.sleep(2000);

        gc1.stop();
        gc2.stop();
        gt1.interrupt();
        gt2.interrupt();
        gt1.join();
        gt2.join();

        System.out.println("\nAll threads completed. Broker has topics: orders, payments");
    }
}
```

### Expected Output (abbreviated)

```
[Consumer-C1] started on topic: orders
[Consumer-C2] started on topic: orders
[Consumer-C3] started on topic: orders
[Producer-A] started on topic: orders
[Producer-A] published: PA-msg-1
[Consumer-C1] offset=0 → Message{id=1, payload='PA-msg-1'}
[Consumer-C2] offset=0 → Message{id=1, payload='PA-msg-1'}
[Consumer-C3] offset=0 → Message{id=1, payload='PA-msg-1'}
[Producer-B] published: PB-msg-1
[Consumer-C1] offset=1 → Message{id=2, payload='PB-msg-1'}
...
=== Consumer Group Demo (ROUND_ROBIN) ===
[GroupConsumer-G1 | group=payment-processors] offset=0 → Message{id=11, payload='PC-msg-1'}
[GroupConsumer-G2 | group=payment-processors] offset=1 → Message{id=12, payload='PC-msg-2'}
[GroupConsumer-G1 | group=payment-processors] offset=2 → Message{id=13, payload='PC-msg-3'}
...
```

**Key observation:** In broadcast mode all three consumers see every message (offsets 0–9). In the consumer group, G1 and G2 split the messages — no duplication.

---

## Class Diagram

```
┌─────────────────────────────────────────────────────────┐
│                   MessageBroker «Singleton»              │
│─────────────────────────────────────────────────────────│
│ - topics: ConcurrentHashMap<String, Topic>              │
│─────────────────────────────────────────────────────────│
│ + getInstance(): MessageBroker                          │
│ + createTopic(name): Topic                              │
│ + getTopic(name): Topic                                 │
│ + publish(topicName, payload): void                     │
└──────────────────────┬──────────────────────────────────┘
                       │ manages 1..*
                       ▼
┌─────────────────────────────────────────────────────────┐
│                        Topic                             │
│─────────────────────────────────────────────────────────│
│ - name: String                                          │
│ - messages: ArrayList<Message>                          │
│ - subscriberGroups: List<ConsumerGroup>                 │
│─────────────────────────────────────────────────────────│
│ + publish(msg): void  «synchronized, notifyAll»         │
│ + consume(offset): Message  «synchronized, wait»        │
│ + consumeBatch(offset, max): List<Message>              │
└─────────┬───────────────────────────┬───────────────────┘
          │ stores 0..*              │ subscribed by 0..*
          ▼                          ▼
┌──────────────────┐    ┌─────────────────────────────────┐
│     Message      │    │        ConsumerGroup             │
│──────────────────│    │─────────────────────────────────│
│ - id: int        │    │ - groupId: String               │
│ - payload: String│    │ - members: List<GroupConsumer>   │
│ - timestamp: long│    │ - groupOffset: AtomicInteger     │
└──────────────────┘    │─────────────────────────────────│
                        │ + addMember(id): GroupConsumer   │
                        └──────────┬──────────────────────┘
                                   │ contains 1..*
                                   ▼
┌──────────────────┐    ┌─────────────────────────────────┐
│    Producer       │    │    GroupConsumer «Runnable»      │
│──────────────────│    │─────────────────────────────────│
│ - producerId     │    │ - memberId: String              │
│ - topic: Topic   │    │ + run(): void                   │
│ + run(): void    │    └─────────────────────────────────┘
└──────────────────┘
                        ┌─────────────────────────────────┐
                        │    Consumer «Runnable»           │
                        │─────────────────────────────────│
                        │ - consumerId: String             │
                        │ - offset: AtomicInteger          │
                        │ + run(): void                    │
                        └─────────────────────────────────┘
```

---

## Complexity Analysis

| Operation | Time Complexity | Notes |
|-----------|----------------|-------|
| Publish (append) | O(1) amortized | `ArrayList.add()` at end |
| Consume by offset | O(1) | `ArrayList.get(index)` — random access |
| Topic lookup | O(1) average | `ConcurrentHashMap.get()` |
| Consumer group claim | O(1) | `AtomicInteger.getAndIncrement()` — CAS |
| Create topic | O(1) average | `computeIfAbsent` |

**Space:** O(T × M) where T = number of topics and M = average messages per topic.

---

## Interview-Ready Answer

> "I'd design the in-memory pub-sub queue around a **MessageBroker singleton** that manages a `ConcurrentHashMap<String, Topic>`. Each **Topic** holds an append-only `ArrayList<Message>` and uses `synchronized` with `wait/notify` for the classic producer-consumer pattern — producers call `notifyAll()` after appending, and consumers `wait()` when their offset reaches the end of the list. Every **Consumer** independently tracks its own `AtomicInteger` offset, enabling replay and at-least-once semantics. For parallel consumption I introduce a **ConsumerGroup** whose members share a single `AtomicInteger` group offset; each member atomically claims the next message via `getAndIncrement()`, achieving Kafka-style round-robin partitioning without explicit partition assignment. If the interviewer restricts `synchronized`, I can swap in `ReentrantLock` with `Condition` for finer-grained signaling (separate not-empty / not-full conditions for backpressure), or demonstrate a lock-free spin-wait using `AtomicBoolean` with CAS. The design follows SOLID — `Topic` stores, `Consumer` reads, `MessageBroker` routes — and the **Observer** pattern decouples producers from consumers via `wait/notify` signaling. This gives us O(1) publish, O(1) offset-based read, thread-safe concurrent access, and a clear path to adding features like TTL-based cleanup, dead-letter queues, or persistent storage behind the same interface."

---

## Follow-Up Questions & Answers

| Question | Answer |
|----------|--------|
| How would you add **message TTL / cleanup**? | Background `ScheduledExecutorService` that periodically trims messages older than TTL from the head of the list. Adjust consumer offsets accordingly. |
| How would you implement **at-least-once** delivery? | Consumer commits offset only after successful processing. On failure, the consumer re-reads from the last committed offset. |
| How would you add **backpressure**? | Cap `messages.size()` at a max. Producers `wait()` when full. Use `ReentrantLock` + two `Condition`s: `notFull` and `notEmpty`. |
| How would you make this **distributed**? | Replace in-memory list with a distributed log (Kafka). Replace `ConcurrentHashMap` with a service registry. Offset tracking moves to an external store (e.g., ZooKeeper, Redis). |
| How would you support **message filtering**? | Add a `Predicate<Message>` filter per consumer/subscription. Filter applied at consume time to skip non-matching messages. |
| How would you handle **poison messages** (always fail)? | Implement a retry counter per message-consumer pair. After N failures, route to a dead-letter topic. |
