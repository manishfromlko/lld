"""
Log Analyser
- Strategy Pattern: LogParser (Regex / Delimited)
- Composite Pattern: CompositeFilter (AND / OR)
- Builder Pattern: LogQueryBuilder (fluent API)
- Streaming — reads file line-by-line, never loads entire file
"""

import re
import os
import tempfile
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict
from typing import Iterator


# ──────────────────────────────────────────────
#  LogLevel
# ──────────────────────────────────────────────

class LogLevel(Enum):
    TRACE = 0
    DEBUG = 1
    INFO = 2
    WARN = 3
    ERROR = 4
    FATAL = 5

    def at_least(self, other: "LogLevel") -> bool:
        return self.value >= other.value


# ──────────────────────────────────────────────
#  LogEntry
# ──────────────────────────────────────────────

@dataclass
class LogEntry:
    timestamp: datetime
    level: LogLevel
    thread: str
    source: str
    message: str

    def __str__(self):
        return f"{self.timestamp} [{self.level.name}] [{self.thread}] {self.source} - {self.message}"


# ──────────────────────────────────────────────
#  LogParser (Strategy)
# ──────────────────────────────────────────────

class LogParser(ABC):
    @abstractmethod
    def parse(self, line: str) -> LogEntry | None:
        pass


class RegexLogParser(LogParser):
    """Parses: 2025-03-21 14:30:05 [main] ERROR com.app.Service - Something failed"""

    _PATTERN = re.compile(
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"  # timestamp
        r"\s+\[([^\]]+)\]"                            # thread
        r"\s+(\w+)"                                   # level
        r"\s+(\S+)"                                   # source
        r"\s+-\s+(.*)"                                # message
    )

    def parse(self, line: str) -> LogEntry | None:
        if not line or not line.strip():
            return None
        m = self._PATTERN.match(line.strip())
        if not m:
            return None
        try:
            ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
            level = LogLevel[m.group(3).upper()]
            return LogEntry(ts, level, m.group(2), m.group(4), m.group(5))
        except (ValueError, KeyError):
            return None


# ──────────────────────────────────────────────
#  LogFilter (Strategy + Composite)
# ──────────────────────────────────────────────

class LogFilter(ABC):
    @abstractmethod
    def matches(self, entry: LogEntry) -> bool:
        pass


class DateRangeFilter(LogFilter):
    def __init__(self, from_dt: datetime, to_dt: datetime):
        self.from_dt = from_dt
        self.to_dt = to_dt

    def matches(self, entry: LogEntry) -> bool:
        return self.from_dt <= entry.timestamp <= self.to_dt


class LevelFilter(LogFilter):
    def __init__(self, min_level: LogLevel):
        self.min_level = min_level

    def matches(self, entry: LogEntry) -> bool:
        return entry.level.at_least(self.min_level)


class KeywordFilter(LogFilter):
    def __init__(self, keyword: str, case_sensitive: bool = False):
        self.keyword = keyword if case_sensitive else keyword.lower()
        self.case_sensitive = case_sensitive

    def matches(self, entry: LogEntry) -> bool:
        msg = entry.message if self.case_sensitive else entry.message.lower()
        return self.keyword in msg


class CompositeFilter(LogFilter):
    """Combines multiple filters with AND or OR."""

    def __init__(self, operator: str = "AND"):
        self.operator = operator
        self._filters: list[LogFilter] = []

    def add(self, f: LogFilter) -> "CompositeFilter":
        self._filters.append(f)
        return self

    def matches(self, entry: LogEntry) -> bool:
        if not self._filters:
            return True
        if self.operator == "AND":
            return all(f.matches(entry) for f in self._filters)
        return any(f.matches(entry) for f in self._filters)


# ──────────────────────────────────────────────
#  LogAggregator
# ──────────────────────────────────────────────

class LogAggregator:
    def __init__(self):
        self._level_counts: dict[LogLevel, int] = defaultdict(int)
        self._hour_counts: dict[str, int] = defaultdict(int)
        self._error_messages: dict[str, int] = defaultdict(int)

    def accept(self, entry: LogEntry):
        self._level_counts[entry.level] += 1
        hour_key = entry.timestamp.strftime("%Y-%m-%d %H:00")
        self._hour_counts[hour_key] += 1
        if entry.level.at_least(LogLevel.ERROR):
            self._error_messages[entry.message] += 1

    def count_by_level(self) -> dict:
        return dict(self._level_counts)

    def count_by_hour(self) -> dict:
        return dict(sorted(self._hour_counts.items()))

    def top_errors(self, n: int) -> list[tuple]:
        return sorted(self._error_messages.items(), key=lambda x: x[1], reverse=True)[:n]


# ──────────────────────────────────────────────
#  LogQueryBuilder (Builder / Fluent API)
# ──────────────────────────────────────────────

class LogQueryBuilder:
    def __init__(self):
        self._parser: LogParser = RegexLogParser()
        self._filters: list[LogFilter] = []
        self._operator = "AND"

    def parser(self, p: LogParser) -> "LogQueryBuilder":
        self._parser = p
        return self

    def date_range(self, from_dt: datetime, to_dt: datetime) -> "LogQueryBuilder":
        self._filters.append(DateRangeFilter(from_dt, to_dt))
        return self

    def min_level(self, level: LogLevel) -> "LogQueryBuilder":
        self._filters.append(LevelFilter(level))
        return self

    def keyword(self, kw: str) -> "LogQueryBuilder":
        self._filters.append(KeywordFilter(kw))
        return self

    def operator(self, op: str) -> "LogQueryBuilder":
        self._operator = op
        return self

    def build_filter(self) -> LogFilter:
        if not self._filters:
            return LogFilter.__class__  # pass-all — unused, handled below
        if len(self._filters) == 1:
            return self._filters[0]
        cf = CompositeFilter(self._operator)
        for f in self._filters:
            cf.add(f)
        return cf

    def get_parser(self) -> LogParser:
        return self._parser


# ──────────────────────────────────────────────
#  LogAnalyser (Orchestrator)
# ──────────────────────────────────────────────

class LogAnalyser:
    def __init__(self, parser: LogParser, log_filter: LogFilter, aggregator: LogAggregator):
        self._parser = parser
        self._filter = log_filter
        self._aggregator = aggregator

    def analyse(self, file_path: str, max_results: int = 100) -> list[LogEntry]:
        results = []
        with open(file_path, "r") as f:
            for line in f:
                entry = self._parser.parse(line)
                if entry is None:
                    continue
                if not self._filter.matches(entry):
                    continue
                self._aggregator.accept(entry)
                if len(results) < max_results:
                    results.append(entry)
        return results

    def stream(self, file_path: str) -> Iterator[LogEntry]:
        with open(file_path, "r") as f:
            for line in f:
                entry = self._parser.parse(line)
                if entry and self._filter.matches(entry):
                    self._aggregator.accept(entry)
                    yield entry


# ──────────────────────────────────────────────
#  Helper: generate sample log file
# ──────────────────────────────────────────────

def generate_log_file(num_lines: int = 200) -> str:
    sources = ["com.app.UserService", "com.app.OrderService", "com.app.PaymentService"]
    threads = ["main", "http-exec-1", "scheduler-1"]
    messages = [
        "Request received",
        "Connection timeout to downstream service",
        "Cache miss for key user:99",
        "Payment processed successfully",
        "Database connection pool exhausted",
        "Timeout waiting for response from inventory-service",
        "User authentication failed",
        "NullPointerException in handler",
    ]
    levels = list(LogLevel)
    rng = random.Random(42)
    base = datetime(2025, 3, 21, 8, 0, 0)

    fd, path = tempfile.mkstemp(suffix=".log", prefix="app-")
    with os.fdopen(fd, "w") as f:
        for _ in range(num_lines):
            ts = base + timedelta(minutes=rng.randint(0, 600), seconds=rng.randint(0, 59))
            level = rng.choice(levels)
            thread = rng.choice(threads)
            source = rng.choice(sources)
            msg = rng.choice(messages)
            f.write(f"{ts.strftime('%Y-%m-%d %H:%M:%S')} [{thread}] {level.name} {source} - {msg}\n")
    return path


# ──────────────────────────────────────────────
#  Demo
# ──────────────────────────────────────────────

if __name__ == "__main__":
    log_file = generate_log_file(200)

    query = (LogQueryBuilder()
             .date_range(datetime(2025, 3, 21, 10, 0), datetime(2025, 3, 21, 14, 0))
             .min_level(LogLevel.WARN)
             .keyword("timeout")
             .operator("AND"))

    aggregator = LogAggregator()
    analyser = LogAnalyser(query.get_parser(), query.build_filter(), aggregator)

    print("=== Matching Entries (WARN+ with 'timeout', 10:00–14:00) ===")
    matches = analyser.analyse(log_file, max_results=10)
    for entry in matches:
        print(f"  {entry}")

    print(f"\n  Total matching entries shown: {len(matches)}")

    print("\n=== Count by Level ===")
    for level, count in sorted(aggregator.count_by_level().items(), key=lambda x: x[0].value):
        print(f"  {level.name:<6}: {count}")

    print("\n=== Count by Hour ===")
    for hour, count in aggregator.count_by_hour().items():
        print(f"  {hour}: {count}")

    print("\n=== Top 3 Error Messages ===")
    # Re-analyse with only ERROR+ level
    agg2 = LogAggregator()
    analyser2 = LogAnalyser(RegexLogParser(), LevelFilter(LogLevel.ERROR), agg2)
    analyser2.analyse(log_file)
    for msg, count in agg2.top_errors(3):
        print(f"  [{count}] {msg}")

    os.unlink(log_file)
