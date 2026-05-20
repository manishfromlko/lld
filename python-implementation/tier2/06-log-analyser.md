# 06 — Log Analyser (Python Implementation)

**File:** `log_analyser.py`  
**Tier:** 2

---

## Problem Statement

Design a streaming log analyser that reads large log files line-by-line (never loading the whole file into memory), applies composable filters, and aggregates statistics (level counts, top errors, hourly distribution).

---

## Design Patterns Used

| Pattern | Where | Why |
|---|---|---|
| **Chain of Responsibility** | `CompositeFilter(AND/OR)` composed of `LogFilter` instances | Combine filters dynamically without giant if-else chains |
| **Builder** | `LogQueryBuilder` fluent API | Readable, step-by-step filter construction |
| **Strategy** | `LogParser` ABC → `RegexLogParser` | Swap parsers for different log formats without changing analyser logic |

---

## Class Structure

```
LogLevel (Enum): DEBUG < INFO < WARN < ERROR < FATAL
LogEntry(timestamp, thread, level, source, message)

LogParser (ABC)
└── RegexLogParser           — single compiled regex, parses one line → LogEntry

LogFilter (ABC)
├── DateRangeFilter
├── LevelFilter              — min_level comparison
├── KeywordFilter            — substring search in message
└── CompositeFilter(op, filters) — AND / OR of sub-filters

LogAggregator                — collects stats: level counts, top errors, hourly buckets
LogQueryBuilder              — fluent builder → produces CompositeFilter
LogAnalyser                  — orchestrates: parse → filter → aggregate (streaming)
```

---

## Streaming Design — Never Load the Full File

```python
def analyse(self, filepath: str) -> LogAggregator:
    agg = LogAggregator()
    with open(filepath, encoding="utf-8") as f:
        for line in f:                      # line-by-line, O(1) memory
            entry = self._parser.parse(line)
            if entry and self._filter.matches(entry):
                agg.add(entry)
    return agg
```

Python's file iterator is lazy — each `for line in f` call reads one line. Memory usage stays at O(1) regardless of file size.

---

## Regex Parser — Compiled Once

```python
_LOG_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"  # timestamp
    r"\s+\[([^\]]+)\]"                           # [thread]
    r"\s+(\w+)"                                  # LEVEL
    r"\s+([^\s]+)"                               # source
    r"\s+-\s+(.*)"                               # message
)
```

Compiling the regex **once at class/module level** avoids recompiling on every log line — critical for performance on millions of lines.

---

## Composite Filter (Chain of Responsibility)

```python
class CompositeFilter(LogFilter):
    def __init__(self, op: FilterOp, filters: list[LogFilter]):
        self._op = op
        self._filters = filters

    def matches(self, entry: LogEntry) -> bool:
        if self._op == FilterOp.AND:
            return all(f.matches(entry) for f in self._filters)
        return any(f.matches(entry) for f in self._filters)
```

Filters compose like boolean expressions. Nesting is unlimited.

---

## Builder — Fluent Query Construction

```python
filter_ = (LogQueryBuilder()
    .date_range(start, end)
    .min_level(LogLevel.WARN)
    .keyword("timeout")
    .build_filter())           # returns CompositeFilter(AND, [...])
```

Each `.method()` appends a filter to an internal list; `.build_filter()` wraps them in `CompositeFilter(AND)`.

---

## Aggregator

```python
class LogAggregator:
    def add(self, entry: LogEntry):
        self._level_counts[entry.level] += 1      # defaultdict
        hour_key = entry.timestamp.strftime("%Y-%m-%d %H:00")
        self._hourly_counts[hour_key] += 1
        if entry.level in (LogLevel.ERROR, LogLevel.FATAL):
            self._error_messages[entry.message] += 1

    def top_errors(self, n=5) -> list[tuple[str, int]]:
        return sorted(self._error_messages.items(),
                      key=lambda x: -x[1])[:n]
```

`collections.defaultdict(int)` eliminates missing-key checks.

---

## Python vs Java Key Differences

| Concern | Java | Python |
|---|---|---|
| File streaming | `BufferedReader` / `Files.lines()` | `open()` + `for line in f` |
| Regex | `Pattern.compile()` | `re.compile()` |
| Default map | `getOrDefault(k, 0)` | `defaultdict(int)` |
| Enum ordering | Enum ordinal comparison | Explicit `_ORDER` dict or `IntEnum` |

---

## Level Ordering

`LogLevel` values are assigned integers so `LevelFilter` can do a simple `>=` comparison:

```python
class LogLevel(Enum):
    DEBUG = 1; INFO = 2; WARN = 3; ERROR = 4; FATAL = 5

class LevelFilter(LogFilter):
    def matches(self, entry: LogEntry) -> bool:
        return entry.level.value >= self._min_level.value
```

---

## Interview Talking Points

1. **Why streaming instead of loading into a list?** — Log files can be gigabytes. Loading into a list would OOM the process. Streaming keeps memory at O(1) and lets analysis start immediately.
2. **Why compile the regex once?** — `re.compile` is expensive. Recompiling on every line of a 10 M-line file would be the dominant cost.
3. **Composite filter extensibility** — Adding a `ThreadFilter` or `SourceFilter` requires only implementing `LogFilter.matches()`. The `CompositeFilter` and builder require zero changes.
4. **Top-N errors** — `sorted(..., key=lambda x: -x[1])[:n]` is O(N log N). For very large error dictionaries, use `heapq.nlargest(n, ..., key=...)` for O(N log n).
