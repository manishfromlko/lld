# 06 — Log Analyser / Parser

**Priority:** TIER 2 — specifically reported at Netcore/Unbxd

---

## Problem Statement

Design a log analyser system that can parse large log files, filter logs by various criteria (date range, severity level, keyword), and aggregate statistics. The system must handle large files efficiently without loading the entire file into memory, support multiple log formats, and allow flexible composition of filters.

---

## Clarification Questions

| # | Question | Why It Matters |
|---|----------|---------------|
| 1 | **What is the log format?** Fixed format (e.g., `timestamp level [thread] message`) or mixed? | Determines parser strategy — regex vs. delimited vs. JSON |
| 2 | **How large are the files?** MBs, GBs, or TBs? | Decides streaming vs. in-memory, memory budget |
| 3 | **Real-time or batch processing?** Are we tailing a live file or analysing historical logs? | Affects architecture — polling/watch vs. one-shot parse |
| 4 | **What filter types are needed?** Date range, severity, keyword, regex, source/thread? | Drives the filter interface and strategy implementations |
| 5 | **What aggregations are required?** Count by level, count by hour, top-N errors, percentiles? | Shapes the aggregator design |
| 6 | **What is the output format?** Console, JSON, CSV, dashboard? | Determines result rendering |
| 7 | **In-memory or streaming?** Can we hold all matching entries in memory, or must we stream results? | Critical for GBs+ — drives the iterator/stream approach |

---

## Entities

```
LogAnalyser (orchestrator)
 ├── LogParser (interface) ─── Strategy
 │    ├── RegexLogParser
 │    └── DelimitedLogParser
 ├── LogFilter (interface) ─── Strategy
 │    ├── DateRangeFilter
 │    ├── LevelFilter
 │    ├── KeywordFilter
 │    └── CompositeFilter ─── Composite (AND / OR)
 ├── LogAggregator
 │    ├── countByLevel()
 │    ├── countByHour()
 │    └── topErrors()
 └── LogQueryBuilder ─── Builder (fluent API)

LogEntry (timestamp, level, message, source, threadName)
LogLevel  (TRACE, DEBUG, INFO, WARN, ERROR, FATAL)
```

---

## Design Patterns

| Pattern | Where | Why |
|---------|-------|-----|
| **Strategy** | `LogFilter`, `LogParser` | Swap parsing/filtering algorithms at runtime without changing the orchestrator |
| **Composite** | `CompositeFilter` | Combine multiple filters with AND/OR logic; clients treat single and compound filters uniformly |
| **Chain of Responsibility** | Filter pipeline (date → level → keyword) | Each filter decides pass/reject independently; chain is extensible without modifying existing filters |
| **Builder** | `LogQueryBuilder` | Fluent API to construct complex queries step-by-step; avoids telescoping constructors |
| **Iterator** | Stream-based file processing | Process arbitrarily large files line-by-line without loading everything into memory |

---

## SOLID Principles

| Principle | How It's Applied |
|-----------|-----------------|
| **S — Single Responsibility** | `LogParser` only parses; `LogFilter` only filters; `LogAggregator` only aggregates; `LogAnalyser` orchestrates |
| **O — Open/Closed** | New filters (`RegexFilter`, `SourceFilter`) are added by implementing `LogFilter` — no existing code changes |
| **L — Liskov Substitution** | Any `LogFilter` implementation can replace another wherever `LogFilter` is expected |
| **I — Interface Segregation** | `LogFilter` and `LogParser` are small, focused interfaces — no fat interfaces |
| **D — Dependency Inversion** | `LogAnalyser` depends on `LogFilter` and `LogParser` abstractions, not concrete classes |

---

## Core Algorithm

```
1. OPEN file with BufferedReader (streaming — never load entire file)
2. FOR each line:
   a. PARSE line → LogEntry  (via configured LogParser strategy)
   b. APPLY filter chain      (date → level → keyword → ...)
   c. IF passes all filters → FEED to LogAggregator
3. RETURN aggregated results
```

### Optimisation for Sorted Log Files

If logs are sorted by timestamp (the common case):

- **Binary search** to find the start position of a date range — `O(log N)` instead of `O(N)`.
- Use `RandomAccessFile` to seek to the midpoint, find the next newline, parse the timestamp, and narrow the window.

### TreeMap for Range Queries

```java
TreeMap<LocalDateTime, List<LogEntry>> index = new TreeMap<>();
// Efficient sub-range extraction:
SortedMap<LocalDateTime, List<LogEntry>> range =
    index.subMap(fromDate, true, toDate, true);
```

`subMap` gives `O(log N)` access to the start plus `O(K)` iteration over `K` matching keys.

---

## Data Structure Choices

| Structure | Purpose | Complexity |
|-----------|---------|------------|
| `BufferedReader` | Streaming file reads, line-by-line | O(1) memory per line |
| `TreeMap<LocalDateTime, List<LogEntry>>` | Time-range queries via `subMap()` | O(log N) lookup |
| `HashMap<LogLevel, AtomicInteger>` | Thread-safe level counting | O(1) per increment |
| `Pattern` (compiled regex) | Parsing log lines | Compile once, match O(L) per line |
| `BlockingQueue<LogEntry>` | Producer-consumer pipeline | O(1) put/take |

---

## Concurrency (Optional but Worth Mentioning)

### Producer-Consumer Model

```
┌──────────┐     BlockingQueue     ┌────────────────┐
│  Reader   │ ──── LogEntry ─────► │  Worker Pool    │
│ (1 thread)│                      │ (N threads)     │
└──────────┘                       │ filter+aggregate│
                                   └────────────────┘
```

- **One reader thread** parses the file and enqueues `LogEntry` objects.
- **N worker threads** dequeue, apply filters, and aggregate (using `AtomicInteger` / `ConcurrentHashMap`).

### Parallel Streams Alternative

```java
Files.lines(path)
     .parallel()
     .map(parser::parse)
     .filter(compositeFilter::matches)
     .forEach(aggregator::accept);
```

Simple but less control over back-pressure and ordering.

---

## Java Implementation

### LogLevel Enum

```java
public enum LogLevel {
    TRACE(0), DEBUG(1), INFO(2), WARN(3), ERROR(4), FATAL(5);

    private final int severity;

    LogLevel(int severity) {
        this.severity = severity;
    }

    public int getSeverity() {
        return severity;
    }

    public boolean isAtLeast(LogLevel other) {
        return this.severity >= other.severity;
    }
}
```

### LogEntry

```java
import java.time.LocalDateTime;

public class LogEntry {
    private final LocalDateTime timestamp;
    private final LogLevel level;
    private final String message;
    private final String source;
    private final String threadName;

    public LogEntry(LocalDateTime timestamp, LogLevel level, String message,
                    String source, String threadName) {
        this.timestamp = timestamp;
        this.level = level;
        this.message = message;
        this.source = source;
        this.threadName = threadName;
    }

    public LocalDateTime getTimestamp() { return timestamp; }
    public LogLevel getLevel()         { return level; }
    public String getMessage()         { return message; }
    public String getSource()          { return source; }
    public String getThreadName()      { return threadName; }

    @Override
    public String toString() {
        return String.format("%s [%s] [%s] %s - %s",
                timestamp, level, threadName, source, message);
    }
}
```

### LogFilter Interface + Implementations

```java
import java.time.LocalDateTime;
import java.util.List;

// --- Strategy interface ---
public interface LogFilter {
    boolean matches(LogEntry entry);
}
```

```java
public class DateRangeFilter implements LogFilter {
    private final LocalDateTime from;
    private final LocalDateTime to;

    public DateRangeFilter(LocalDateTime from, LocalDateTime to) {
        this.from = from;
        this.to = to;
    }

    @Override
    public boolean matches(LogEntry entry) {
        LocalDateTime ts = entry.getTimestamp();
        return !ts.isBefore(from) && !ts.isAfter(to);
    }
}
```

```java
public class LevelFilter implements LogFilter {
    private final LogLevel minimumLevel;

    public LevelFilter(LogLevel minimumLevel) {
        this.minimumLevel = minimumLevel;
    }

    @Override
    public boolean matches(LogEntry entry) {
        return entry.getLevel().isAtLeast(minimumLevel);
    }
}
```

```java
public class KeywordFilter implements LogFilter {
    private final String keyword;
    private final boolean caseSensitive;

    public KeywordFilter(String keyword, boolean caseSensitive) {
        this.keyword = caseSensitive ? keyword : keyword.toLowerCase();
        this.caseSensitive = caseSensitive;
    }

    public KeywordFilter(String keyword) {
        this(keyword, false);
    }

    @Override
    public boolean matches(LogEntry entry) {
        String msg = caseSensitive ? entry.getMessage() : entry.getMessage().toLowerCase();
        return msg.contains(keyword);
    }
}
```

```java
import java.util.ArrayList;
import java.util.List;

public class CompositeFilter implements LogFilter {

    public enum Operator { AND, OR }

    private final List<LogFilter> filters = new ArrayList<>();
    private final Operator operator;

    public CompositeFilter(Operator operator) {
        this.operator = operator;
    }

    public CompositeFilter add(LogFilter filter) {
        filters.add(filter);
        return this;
    }

    @Override
    public boolean matches(LogEntry entry) {
        if (filters.isEmpty()) return true;

        return switch (operator) {
            case AND -> filters.stream().allMatch(f -> f.matches(entry));
            case OR  -> filters.stream().anyMatch(f -> f.matches(entry));
        };
    }
}
```

### LogParser Interface + RegexLogParser

```java
import java.util.Optional;

public interface LogParser {
    Optional<LogEntry> parse(String line);
}
```

```java
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Optional;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Parses lines matching:
 *   2025-03-21 14:30:05 [main] ERROR com.app.Service - Something failed
 */
public class RegexLogParser implements LogParser {

    private static final DateTimeFormatter FORMATTER =
            DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    private static final Pattern LOG_PATTERN = Pattern.compile(
            "^(\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2})" + // group 1: timestamp
            "\\s+\\[([^]]+)]"  +                               // group 2: thread
            "\\s+(\\w+)"       +                               // group 3: level
            "\\s+(\\S+)"      +                               // group 4: source
            "\\s+-\\s+(.*)"                                    // group 5: message
    );

    @Override
    public Optional<LogEntry> parse(String line) {
        if (line == null || line.isBlank()) return Optional.empty();

        Matcher matcher = LOG_PATTERN.matcher(line);
        if (!matcher.matches()) return Optional.empty();

        try {
            LocalDateTime timestamp = LocalDateTime.parse(matcher.group(1), FORMATTER);
            LogLevel level          = LogLevel.valueOf(matcher.group(3).toUpperCase());
            String threadName       = matcher.group(2);
            String source           = matcher.group(4);
            String message          = matcher.group(5);

            return Optional.of(new LogEntry(timestamp, level, message, source, threadName));
        } catch (Exception e) {
            return Optional.empty();
        }
    }
}
```

### LogAggregator

```java
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Collectors;

public class LogAggregator {

    private final Map<LogLevel, AtomicInteger> levelCounts = new ConcurrentHashMap<>();
    private final Map<String, AtomicInteger> hourlyCounts = new ConcurrentHashMap<>();
    private final Map<String, AtomicInteger> errorMessages = new ConcurrentHashMap<>();

    private static final DateTimeFormatter HOUR_FORMAT =
            DateTimeFormatter.ofPattern("yyyy-MM-dd HH:00");

    public void accept(LogEntry entry) {
        levelCounts.computeIfAbsent(entry.getLevel(), k -> new AtomicInteger())
                   .incrementAndGet();

        String hourKey = entry.getTimestamp().format(HOUR_FORMAT);
        hourlyCounts.computeIfAbsent(hourKey, k -> new AtomicInteger())
                    .incrementAndGet();

        if (entry.getLevel().isAtLeast(LogLevel.ERROR)) {
            errorMessages.computeIfAbsent(entry.getMessage(), k -> new AtomicInteger())
                         .incrementAndGet();
        }
    }

    public Map<LogLevel, Integer> countByLevel() {
        return levelCounts.entrySet().stream()
                .collect(Collectors.toMap(Map.Entry::getKey, e -> e.getValue().get()));
    }

    public Map<String, Integer> countByHour() {
        return hourlyCounts.entrySet().stream()
                .sorted(Map.Entry.comparingByKey())
                .collect(Collectors.toMap(
                        Map.Entry::getKey, e -> e.getValue().get(),
                        (a, b) -> a, LinkedHashMap::new));
    }

    public List<Map.Entry<String, Integer>> topErrors(int n) {
        return errorMessages.entrySet().stream()
                .map(e -> Map.entry(e.getKey(), e.getValue().get()))
                .sorted(Map.Entry.<String, Integer>comparingByValue().reversed())
                .limit(n)
                .collect(Collectors.toList());
    }

    public void reset() {
        levelCounts.clear();
        hourlyCounts.clear();
        errorMessages.clear();
    }
}
```

### LogQueryBuilder (Fluent API)

```java
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

public class LogQueryBuilder {

    private LogParser parser;
    private final List<LogFilter> filters = new ArrayList<>();
    private CompositeFilter.Operator operator = CompositeFilter.Operator.AND;

    public LogQueryBuilder parser(LogParser parser) {
        this.parser = parser;
        return this;
    }

    public LogQueryBuilder dateRange(LocalDateTime from, LocalDateTime to) {
        filters.add(new DateRangeFilter(from, to));
        return this;
    }

    public LogQueryBuilder minLevel(LogLevel level) {
        filters.add(new LevelFilter(level));
        return this;
    }

    public LogQueryBuilder keyword(String keyword) {
        filters.add(new KeywordFilter(keyword));
        return this;
    }

    public LogQueryBuilder keyword(String keyword, boolean caseSensitive) {
        filters.add(new KeywordFilter(keyword, caseSensitive));
        return this;
    }

    public LogQueryBuilder filterOperator(CompositeFilter.Operator op) {
        this.operator = op;
        return this;
    }

    public LogFilter buildFilter() {
        if (filters.isEmpty()) return entry -> true;
        if (filters.size() == 1) return filters.get(0);

        CompositeFilter composite = new CompositeFilter(operator);
        filters.forEach(composite::add);
        return composite;
    }

    public LogParser getParser() {
        return parser != null ? parser : new RegexLogParser();
    }
}
```

### LogAnalyser (Orchestrator)

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.stream.Stream;

public class LogAnalyser {

    private final LogParser parser;
    private final LogFilter filter;
    private final LogAggregator aggregator;

    public LogAnalyser(LogParser parser, LogFilter filter, LogAggregator aggregator) {
        this.parser = parser;
        this.filter = filter;
        this.aggregator = aggregator;
    }

    /**
     * Streaming analysis — reads file line-by-line, never loads entire file.
     * Returns matching entries (capped to avoid OOM for huge result sets).
     */
    public List<LogEntry> analyse(Path filePath, int maxResults) throws IOException {
        List<LogEntry> results = new ArrayList<>();

        try (BufferedReader reader = Files.newBufferedReader(filePath)) {
            String line;
            while ((line = reader.readLine()) != null) {
                Optional<LogEntry> parsed = parser.parse(line);
                if (parsed.isEmpty()) continue;

                LogEntry entry = parsed.get();
                if (!filter.matches(entry)) continue;

                aggregator.accept(entry);
                if (results.size() < maxResults) {
                    results.add(entry);
                }
            }
        }
        return results;
    }

    /**
     * Stream-based variant — returns a lazy stream for further composition.
     */
    public Stream<LogEntry> analyseAsStream(Path filePath) throws IOException {
        BufferedReader reader = Files.newBufferedReader(filePath);
        return reader.lines()
                .map(parser::parse)
                .filter(Optional::isPresent)
                .map(Optional::get)
                .filter(filter::matches)
                .peek(aggregator::accept)
                .onClose(() -> {
                    try { reader.close(); } catch (IOException ignored) {}
                });
    }

    public LogAggregator getAggregator() {
        return aggregator;
    }
}
```

### Main — Demo

```java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Map;
import java.util.Random;

public class LogAnalyserDemo {

    private static final DateTimeFormatter FMT =
            DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    public static void main(String[] args) throws IOException {
        Path logFile = generateSampleLogFile();

        // Build a query using the fluent builder
        LogQueryBuilder query = new LogQueryBuilder()
                .parser(new RegexLogParser())
                .dateRange(
                        LocalDateTime.of(2025, 3, 21, 10, 0),
                        LocalDateTime.of(2025, 3, 21, 14, 0))
                .minLevel(LogLevel.WARN)
                .keyword("timeout")
                .filterOperator(CompositeFilter.Operator.AND);

        LogAggregator aggregator = new LogAggregator();
        LogAnalyser analyser = new LogAnalyser(
                query.getParser(), query.buildFilter(), aggregator);

        // Run streaming analysis
        List<LogEntry> matches = analyser.analyse(logFile, 100);

        // Print matching entries
        System.out.println("=== Matching Log Entries ===");
        matches.forEach(System.out::println);

        // Print aggregation results
        System.out.println("\n=== Count by Level ===");
        aggregator.countByLevel().forEach((level, count) ->
                System.out.printf("  %-6s : %d%n", level, count));

        System.out.println("\n=== Count by Hour ===");
        aggregator.countByHour().forEach((hour, count) ->
                System.out.printf("  %s : %d%n", hour, count));

        System.out.println("\n=== Top 5 Errors ===");
        aggregator.topErrors(5).forEach(e ->
                System.out.printf("  [%d] %s%n", e.getValue(), e.getKey()));

        // Demonstrate stream-based analysis with a fresh aggregator
        System.out.println("\n=== Stream-Based: All ERROR+ entries ===");
        LogAggregator streamAgg = new LogAggregator();
        LogAnalyser streamAnalyser = new LogAnalyser(
                new RegexLogParser(), new LevelFilter(LogLevel.ERROR), streamAgg);

        try (var stream = streamAnalyser.analyseAsStream(logFile)) {
            stream.limit(10).forEach(System.out::println);
        }

        System.out.println("\nStream aggregation — count by level:");
        streamAgg.countByLevel().forEach((level, count) ->
                System.out.printf("  %-6s : %d%n", level, count));

        Files.deleteIfExists(logFile);
    }

    private static Path generateSampleLogFile() throws IOException {
        Path path = Files.createTempFile("app-", ".log");
        String[] sources = {"com.app.UserService", "com.app.OrderService",
                            "com.app.PaymentService", "com.app.CacheManager"};
        String[] threads = {"main", "http-nio-8080-exec-1", "scheduler-1", "async-pool-3"};
        String[] messages = {
                "Request received", "Processing order #12345",
                "Connection timeout to downstream service",
                "Cache miss for key user:99", "Payment processed successfully",
                "Database connection pool exhausted",
                "Timeout waiting for response from inventory-service",
                "User authentication failed", "Retrying after timeout",
                "NullPointerException in handler"
        };

        Random rng = new Random(42);
        LogLevel[] levels = LogLevel.values();

        try (BufferedWriter writer = Files.newBufferedWriter(path)) {
            LocalDateTime base = LocalDateTime.of(2025, 3, 21, 8, 0, 0);
            for (int i = 0; i < 500; i++) {
                LocalDateTime ts = base.plusMinutes(rng.nextInt(600)).plusSeconds(rng.nextInt(60));
                LogLevel level = levels[rng.nextInt(levels.length)];
                String thread = threads[rng.nextInt(threads.length)];
                String source = sources[rng.nextInt(sources.length)];
                String message = messages[rng.nextInt(messages.length)];

                writer.write(String.format("%s [%s] %s %s - %s%n",
                        ts.format(FMT), thread, level, source, message));
            }
        }
        return path;
    }
}
```

---

## Scalability Discussion

| Challenge | Solution |
|-----------|----------|
| **File doesn't fit in RAM** | Stream line-by-line with `BufferedReader`. Never hold more than one line + current aggregation state. Producer-consumer pattern to decouple reading from processing. |
| **Logs spread across multiple servers** | **MapReduce-style aggregation.** Map phase: each server filters and produces local aggregates. Reduce phase: merge aggregates centrally. Tools like Apache Spark, Flink, or a custom reducer over Kafka topics. |
| **Millions of small log files** | Use a thread pool with `ExecutorService`; each task processes one file. Merge aggregators at the end using `ConcurrentHashMap`. |
| **Real-time log tailing** | `WatchService` + `RandomAccessFile` to resume from last-read offset. Push matching entries into a streaming pipeline (Kafka / Redis Streams). |
| **Need full-text search** | Ingest into Elasticsearch / OpenSearch. The in-memory analyser works for ad-hoc queries; a search engine handles indexed queries at scale. |

### Memory Budget Example

For a 10 GB file with 100-byte average lines → ~100 million lines. Streaming approach uses `O(1)` memory for reading plus `O(A)` for aggregation state (typically a few KB). No problem on a 512 MB heap.

---

## Class Diagram (ASCII)

```
┌──────────────────┐       ┌──────────────────┐
│  LogQueryBuilder │       │   LogAnalyser     │
│  ─────────────── │       │   ────────────    │
│  +parser()       │       │  -parser: LogParser│
│  +dateRange()    │──────►│  -filter: LogFilter│
│  +minLevel()     │       │  -aggregator      │
│  +keyword()      │       │  +analyse()       │
│  +buildFilter()  │       │  +analyseAsStream()│
└──────────────────┘       └────────┬─────────┘
                                    │ uses
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
          ┌─────────────┐  ┌──────────────┐  ┌──────────────┐
          │ «interface»  │  │ «interface»   │  │LogAggregator │
          │  LogParser   │  │  LogFilter    │  │──────────────│
          │──────────────│  │──────────────│  │+accept()     │
          │+parse(line)  │  │+matches(entry)│ │+countByLevel()│
          └──────┬───────┘  └──────┬───────┘  │+countByHour()│
                 │                 │           │+topErrors()  │
          ┌──────┴───────┐   ┌────┴─────┬─────────┬──────────┐
          │RegexLogParser│   │DateRange │Level    │Keyword   │Composite
          │              │   │Filter    │Filter   │Filter    │Filter
          └──────────────┘   └──────────┴─────────┴──────────┘
```

---

## Interview-Ready Answer

> "I would design the log analyser around a **streaming pipeline** so it never loads the full file into memory. A `LogParser` interface (Strategy pattern) converts raw lines into `LogEntry` objects — we can swap between regex-based, delimited, or JSON parsers. Filters implement a `LogFilter` interface and are composed via a `CompositeFilter` (Composite pattern) supporting AND/OR semantics, which makes complex queries trivial to build with a fluent `LogQueryBuilder`. The orchestrator reads lines with a `BufferedReader`, parses, filters, and feeds matching entries into a `LogAggregator` that maintains thread-safe counters (`ConcurrentHashMap` + `AtomicInteger`) for count-by-level, count-by-hour, and top-N error tracking. For sorted log files, I'd use binary search over `RandomAccessFile` to jump to the start of a date range in O(log N). If the file is too large for a single machine, I'd use a MapReduce-style approach: each node filters and aggregates locally, then a reducer merges the partial results. The whole design is SOLID — new filters and parsers are added by implementing an interface, nothing existing changes."

---

*End of LLD — Log Analyser / Parser*
