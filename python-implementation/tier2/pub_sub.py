"""
In-Memory Pub-Sub / Message Queue
- Topic: append-only message list, synchronized with threading.Condition
- Consumer: independent offset tracking (broadcast — each sees all messages)
- ConsumerGroup: shared offset (round-robin — each message goes to one member)
- Singleton MessageBroker
"""

import threading
import time
import uuid
from dataclasses import dataclass, field


# ──────────────────────────────────────────────
#  Message
# ──────────────────────────────────────────────

_msg_id_lock = threading.Lock()
_msg_id_counter = 0


def _next_id() -> int:
    global _msg_id_counter
    with _msg_id_lock:
        _msg_id_counter += 1
        return _msg_id_counter


@dataclass
class Message:
    payload: str
    msg_id: int = field(default_factory=_next_id)
    timestamp: float = field(default_factory=time.time)

    def __str__(self):
        return f"Message{{id={self.msg_id}, payload='{self.payload}'}}"


# ──────────────────────────────────────────────
#  Topic
# ──────────────────────────────────────────────

class Topic:
    def __init__(self, name: str):
        self.name = name
        self._messages: list[Message] = []
        self._cond = threading.Condition()

    def publish(self, message: Message):
        with self._cond:
            self._messages.append(message)
            self._cond.notify_all()   # wake all waiting consumers

    def consume(self, offset: int) -> Message:
        """Block until a message exists at the given offset, then return it."""
        with self._cond:
            while offset >= len(self._messages):
                self._cond.wait()
            return self._messages[offset]

    def message_count(self) -> int:
        with self._cond:
            return len(self._messages)


# ──────────────────────────────────────────────
#  Independent Consumer (broadcast — sees every message)
# ──────────────────────────────────────────────

class Consumer(threading.Thread):
    def __init__(self, consumer_id: str, topic: Topic):
        super().__init__(name=f"consumer-{consumer_id}", daemon=True)
        self.consumer_id = consumer_id
        self._topic = topic
        self._offset = 0
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        print(f"[Consumer-{self.consumer_id}] started on topic: {self._topic.name}")
        while self._running:
            try:
                msg = self._topic.consume(self._offset)
                print(f"[Consumer-{self.consumer_id}] offset={self._offset} → {msg}")
                self._offset += 1
            except Exception:
                break
        print(f"[Consumer-{self.consumer_id}] stopped")


# ──────────────────────────────────────────────
#  Consumer Group (round-robin — messages partitioned across members)
# ──────────────────────────────────────────────

class ConsumerGroup:
    def __init__(self, group_id: str, topic: Topic):
        self.group_id = group_id
        self._topic = topic
        self._group_offset = 0
        self._offset_lock = threading.Lock()
        self._members: list["GroupConsumer"] = []

    def _claim_next_offset(self) -> int:
        with self._offset_lock:
            offset = self._group_offset
            self._group_offset += 1
            return offset

    def add_member(self, member_id: str) -> "GroupConsumer":
        member = GroupConsumer(member_id, self)
        self._members.append(member)
        return member


class GroupConsumer(threading.Thread):
    def __init__(self, member_id: str, group: ConsumerGroup):
        super().__init__(name=f"group-consumer-{member_id}", daemon=True)
        self.member_id = member_id
        self._group = group
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        print(f"[GroupConsumer-{self.member_id}|{self._group.group_id}] started on {self._group._topic.name}")
        while self._running:
            offset = self._group._claim_next_offset()
            try:
                msg = self._group._topic.consume(offset)
                print(f"[GroupConsumer-{self.member_id}|{self._group.group_id}] offset={offset} → {msg}")
            except Exception:
                break
        print(f"[GroupConsumer-{self.member_id}] stopped")


# ──────────────────────────────────────────────
#  Producer
# ──────────────────────────────────────────────

class Producer(threading.Thread):
    def __init__(self, producer_id: str, topic: Topic, count: int, delay_ms: float = 0):
        super().__init__(name=f"producer-{producer_id}", daemon=True)
        self.producer_id = producer_id
        self._topic = topic
        self._count = count
        self._delay = delay_ms / 1000

    def run(self):
        print(f"[Producer-{self.producer_id}] started on topic: {self._topic.name}")
        for i in range(1, self._count + 1):
            payload = f"P{self.producer_id}-msg-{i}"
            self._topic.publish(Message(payload))
            print(f"[Producer-{self.producer_id}] published: {payload}")
            if self._delay > 0:
                time.sleep(self._delay)
        print(f"[Producer-{self.producer_id}] finished")


# ──────────────────────────────────────────────
#  MessageBroker (Singleton)
# ──────────────────────────────────────────────

class MessageBroker:
    _instance: "MessageBroker | None" = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._topics: dict[str, Topic] = {}
        return cls._instance

    def create_topic(self, name: str) -> Topic:
        if name not in self._topics:
            self._topics[name] = Topic(name)
        return self._topics[name]

    def get_topic(self, name: str) -> Topic:
        if name not in self._topics:
            raise KeyError(f"Topic not found: {name}")
        return self._topics[name]

    def publish(self, topic_name: str, payload: str):
        self.get_topic(topic_name).publish(Message(payload))


# ──────────────────────────────────────────────
#  Demo
# ──────────────────────────────────────────────

if __name__ == "__main__":
    broker = MessageBroker()
    orders_topic = broker.create_topic("orders")

    print("=== Broadcast Demo: 3 consumers each see ALL messages ===\n")
    c1 = Consumer("C1", orders_topic)
    c2 = Consumer("C2", orders_topic)
    c1.start(); c2.start()

    p1 = Producer("A", orders_topic, count=4, delay_ms=100)
    p1.start()
    p1.join()
    time.sleep(0.8)

    c1.stop(); c2.stop()
    c1.interrupt_flag = True
    # Give consumers time to notice the stop
    time.sleep(0.2)

    print("\n=== Consumer Group Demo: 2 members SPLIT messages ===\n")
    payments_topic = broker.create_topic("payments")
    group = ConsumerGroup("payment-processors", payments_topic)
    g1 = group.add_member("G1")
    g2 = group.add_member("G2")
    g1.start(); g2.start()

    p2 = Producer("B", payments_topic, count=6, delay_ms=80)
    p2.start()
    p2.join()
    time.sleep(0.8)

    g1.stop(); g2.stop()
    time.sleep(0.2)

    print("\nDone. orders topic has", orders_topic.message_count(), "messages.")
    print("payments topic has", payments_topic.message_count(), "messages.")
