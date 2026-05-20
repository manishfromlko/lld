# 12 — In-Memory Spreadsheet with Formula Engine

**Priority:** TIER 3 — tests dependency graph, topological sort, observer pattern

---

## Problem Statement

Design an in-memory spreadsheet that supports:

- **Cells with raw values or formulas** (e.g., `=A1+B2*3`)
- **Automatic recalculation** when any dependency changes — updating `A1` must cascade through every cell that transitively depends on it
- **Circular dependency detection** — reject formulas that would create a cycle (e.g., `A1=B1`, `B1=A1`)
- **O(1) cell lookup** by standard A1 notation
- **Topological-order evaluation** so that every cell sees up-to-date inputs before it is evaluated

---

## Clarification Questions

| # | Question | Why It Matters |
|---|----------|---------------|
| 1 | **Which formulas are supported?** Only arithmetic (+, -, *, /) or also functions like SUM, AVG, IF? | Determines parser/evaluator complexity |
| 2 | **What cell types exist?** Number, String, Boolean, Error? | Affects the `CellValue` abstraction |
| 3 | **What is the formula syntax?** Always starts with `=`? Are parentheses supported? | Drives the tokenizer and parser grammar |
| 4 | **How should circular dependencies be handled?** Reject the formula, show `#CIRC!` error, or break the cycle? | Impacts the dependency graph contract |
| 5 | **Is undo/redo required?** If yes, what granularity — per cell or per batch? | Requires a command/memento stack |
| 6 | **What is the maximum sheet size?** Unbounded or fixed (e.g., 1 000 × 1 000)? | Affects storage strategy (sparse vs dense) |
| 7 | **Is import/export needed?** CSV, JSON, or a custom format? | May need a serialization layer |

---

## Entities

| Entity | Responsibility |
|--------|---------------|
| **Spreadsheet** | Top-level grid — owns all cells, dependency graph, and the recalculation engine |
| **Cell** | Holds a cell ID, raw value, optional formula, and tracks its dependents & dependencies |
| **CellId** | Value object — parses `"A1"` into `(row=0, col=0)`, provides equality and hashing |
| **Formula** | Immutable record — stores the original expression string and the list of parsed tokens |
| **FormulaParser** | Stateless service — tokenizes `"=A1+B2*3"` into a stream of operands & operators |
| **FormulaEvaluator** | Stateless service — walks the token list, resolves cell references, and computes a numeric result |
| **DependencyGraph** | Directed graph — `A1 → {C1, C2}` means "if A1 changes, C1 and C2 must be recalculated" |

---

## Design Patterns

### 1. Observer Pattern

When a cell's value changes, it **notifies all its dependents** (observers) to recalculate.

```
Cell (Subject)
  └── dependents: Set<Cell>   ← observers
        ├── C1.recalculate()
        └── D1.recalculate()
```

### 2. Composite Pattern

A cell's content is polymorphic — it is either a **raw value** or a **formula**. Both implement a common `CellContent` interface so the spreadsheet can treat them uniformly.

```
CellContent (interface)
  ├── RawValue   → returns stored double
  └── FormulaValue → evaluates expression, returns computed double
```

### 3. Strategy Pattern

Different `EvaluationStrategy` implementations handle different formula complexity levels (basic arithmetic, functions, array formulas) without changing the evaluator's control flow.

### 4. Builder Pattern

`CellBuilder` provides a fluent API for constructing cells with optional formula, formatting, and metadata — avoids telescoping constructors.

---

## SOLID Principles

| Principle | Application in This Design |
|-----------|---------------------------|
| **S — Single Responsibility** | `FormulaParser` only parses; `FormulaEvaluator` only evaluates; `DependencyGraph` only tracks edges and detects cycles |
| **O — Open/Closed** | New formula functions (SUM, AVG) are added as new `EvaluationStrategy` implementations — existing evaluator code is untouched |
| **L — Liskov Substitution** | `RawValue` and `FormulaValue` both implement `CellContent`; any code expecting `CellContent` works with either |
| **I — Interface Segregation** | `CellContent` exposes only `evaluate()`; `DependencyGraph` exposes only `addEdge / removeEdge / hasCycle / topologicalSort` — no fat interfaces |
| **D — Dependency Inversion** | `Spreadsheet` depends on the `CellContent` abstraction, not on concrete `RawValue` or `FormulaValue` classes; `FormulaEvaluator` receives a `CellValueResolver` function, not a concrete `Spreadsheet` |

---

## Core Algorithm

### Step-by-step flow when `setCell("C1", "=A1+B1")` is called:

```
1. PARSE      → FormulaParser tokenizes "=A1+B1"
                 tokens: [CellRef(A1), PLUS, CellRef(B1)]

2. EXTRACT    → dependencies = {A1, B1}

3. CYCLE CHECK → DFS from C1 through new dependency edges
                  If A1 or B1 transitively depends on C1 → REJECT (CircularDependencyException)

4. UPDATE GRAPH → Remove old edges for C1
                   Add edges: A1 → C1, B1 → C1

5. EVALUATE   → FormulaEvaluator resolves A1=5, B1=10 → result = 15
                 Store 15 as C1's computed value

6. CASCADE    → Topological sort of all cells reachable from C1
                 For each cell in topo order → re-evaluate formula
```

### Topological Sort Guarantees Correct Order

```
A1 = 5
B1 = 10
C1 = =A1 + B1       → depends on {A1, B1}
D1 = =C1 * 2        → depends on {C1}
E1 = =D1 + A1       → depends on {D1, A1}

Topological order after A1 changes:
  A1 → C1 → D1 → E1

C1 sees updated A1 ✓
D1 sees updated C1 ✓
E1 sees updated D1 and A1 ✓
```

### Circular Dependency Detection (DFS)

```
Before accepting "C1 = =A1 + B1":
  - Start DFS from C1's new dependencies (A1, B1)
  - Walk their dependency chains
  - If any path leads back to C1 → cycle detected → reject formula

Example cycle:
  A1 = =B1
  B1 = =A1   ← DFS from B1 reaches A1 which reaches B1 → CYCLE
```

---

## Data Structure Choices

| Structure | Used For | Complexity |
|-----------|----------|------------|
| `HashMap<String, Cell>` | Cell storage — O(1) lookup by `"A1"` key | Get/Put: O(1) avg |
| `HashMap<String, Set<String>>` | Adjacency list for dependency graph — `A1 → {C1, D1}` | Add/Remove edge: O(1) avg |
| `HashMap<String, Set<String>>` | Reverse adjacency list (dependencies) — `C1 → {A1, B1}` | Needed for cleanup on formula change |
| `ArrayDeque` (as Stack) | DFS-based cycle detection | O(V + E) |
| `ArrayDeque` (as Queue) | Kahn's algorithm for topological sort | O(V + E) |
| `Deque<Command>` | Undo/redo stack (command pattern) | Push/Pop: O(1) |

---

## Concurrency

For a **single-user, in-memory spreadsheet** concurrency is generally unnecessary — all operations are synchronous and single-threaded.

If extended to **multi-user**:

| Concern | Solution |
|---------|----------|
| Concurrent reads while one user writes | `ReadWriteLock` on the spreadsheet — multiple readers, exclusive writer |
| Concurrent cell edits | Lock at cell granularity with `ConcurrentHashMap` + per-cell `ReentrantLock` |
| Recalculation during edits | Snapshot the dependency graph before recalculating; apply results atomically |

---

## Java Implementation

### CellId — A1 Notation Parser

```java
public class CellId {
    private final int row;
    private final int col;
    private final String id;

    public CellId(String id) {
        this.id = id.toUpperCase();
        int i = 0;
        int c = 0;
        while (i < id.length() && Character.isLetter(id.charAt(i))) {
            c = c * 26 + (Character.toUpperCase(id.charAt(i)) - 'A');
            i++;
        }
        this.col = c;
        this.row = Integer.parseInt(id.substring(i)) - 1;
    }

    public int getRow() { return row; }
    public int getCol() { return col; }
    public String getId() { return id; }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (!(o instanceof CellId)) return false;
        CellId other = (CellId) o;
        return row == other.row && col == other.col;
    }

    @Override
    public int hashCode() {
        return 31 * row + col;
    }

    @Override
    public String toString() { return id; }
}
```

### Cell

```java
public class Cell {
    private final String id;
    private double value;
    private String formula;            // null if raw value
    private Set<String> dependencies;  // cells this cell depends on
    private Set<String> dependents;    // cells that depend on this cell

    public Cell(String id) {
        this.id = id.toUpperCase();
        this.dependencies = new HashSet<>();
        this.dependents = new HashSet<>();
    }

    public String getId() { return id; }

    public double getValue() { return value; }
    public void setValue(double value) {
        this.value = value;
        this.formula = null;
        this.dependencies.clear();
    }

    public String getFormula() { return formula; }
    public void setFormula(String formula) { this.formula = formula; }

    public Set<String> getDependencies() { return dependencies; }
    public void setDependencies(Set<String> deps) { this.dependencies = deps; }

    public Set<String> getDependents() { return dependents; }
    public void addDependent(String cellId) { dependents.add(cellId); }
    public void removeDependent(String cellId) { dependents.remove(cellId); }

    public boolean hasFormula() { return formula != null; }

    @Override
    public String toString() {
        return hasFormula()
            ? String.format("Cell[%s, formula=%s, value=%.2f]", id, formula, value)
            : String.format("Cell[%s, value=%.2f]", id, value);
    }
}
```

### FormulaParser

```java
import java.util.*;
import java.util.regex.*;

public class FormulaParser {

    public enum TokenType { NUMBER, CELL_REF, OPERATOR, LPAREN, RPAREN }

    public static class Token {
        public final TokenType type;
        public final String value;

        public Token(TokenType type, String value) {
            this.type = type;
            this.value = value;
        }

        @Override
        public String toString() { return type + "(" + value + ")"; }
    }

    private static final Pattern TOKEN_PATTERN = Pattern.compile(
        "([A-Za-z]+\\d+)" +       // cell reference like A1, BC23
        "|(\\d+\\.?\\d*)" +       // number literal
        "|([+\\-*/])" +           // arithmetic operator
        "|(\\()" +                // left paren
        "|(\\))"                  // right paren
    );

    public List<Token> parse(String formula) {
        if (formula == null || !formula.startsWith("=")) {
            throw new IllegalArgumentException("Formula must start with '='");
        }

        String expr = formula.substring(1).replaceAll("\\s+", "");
        List<Token> tokens = new ArrayList<>();
        Matcher matcher = TOKEN_PATTERN.matcher(expr);

        while (matcher.find()) {
            if (matcher.group(1) != null) {
                tokens.add(new Token(TokenType.CELL_REF, matcher.group(1).toUpperCase()));
            } else if (matcher.group(2) != null) {
                tokens.add(new Token(TokenType.NUMBER, matcher.group(2)));
            } else if (matcher.group(3) != null) {
                tokens.add(new Token(TokenType.OPERATOR, matcher.group(3)));
            } else if (matcher.group(4) != null) {
                tokens.add(new Token(TokenType.LPAREN, "("));
            } else if (matcher.group(5) != null) {
                tokens.add(new Token(TokenType.RPAREN, ")"));
            }
        }
        return tokens;
    }

    public Set<String> extractDependencies(String formula) {
        Set<String> deps = new HashSet<>();
        for (Token token : parse(formula)) {
            if (token.type == TokenType.CELL_REF) {
                deps.add(token.value);
            }
        }
        return deps;
    }
}
```

### FormulaEvaluator

Evaluates a formula using a simple recursive-descent approach that respects operator precedence (`*`, `/` before `+`, `-`).

```java
import java.util.*;
import java.util.function.Function;

public class FormulaEvaluator {

    private final Function<String, Double> cellValueResolver;
    private List<FormulaParser.Token> tokens;
    private int pos;

    public FormulaEvaluator(Function<String, Double> cellValueResolver) {
        this.cellValueResolver = cellValueResolver;
    }

    public double evaluate(String formula) {
        FormulaParser parser = new FormulaParser();
        this.tokens = parser.parse(formula);
        this.pos = 0;
        double result = parseExpression();
        if (pos != tokens.size()) {
            throw new IllegalArgumentException("Unexpected token at position " + pos);
        }
        return result;
    }

    // expression = term (('+' | '-') term)*
    private double parseExpression() {
        double result = parseTerm();
        while (pos < tokens.size() && isAddSub(tokens.get(pos))) {
            String op = tokens.get(pos++).value;
            double right = parseTerm();
            result = op.equals("+") ? result + right : result - right;
        }
        return result;
    }

    // term = factor (('*' | '/') factor)*
    private double parseTerm() {
        double result = parseFactor();
        while (pos < tokens.size() && isMulDiv(tokens.get(pos))) {
            String op = tokens.get(pos++).value;
            double right = parseFactor();
            if (op.equals("*")) result *= right;
            else {
                if (right == 0) throw new ArithmeticException("Division by zero");
                result /= right;
            }
        }
        return result;
    }

    // factor = NUMBER | CELL_REF | '(' expression ')'
    private double parseFactor() {
        if (pos >= tokens.size()) {
            throw new IllegalArgumentException("Unexpected end of formula");
        }
        FormulaParser.Token token = tokens.get(pos);

        if (token.type == FormulaParser.TokenType.NUMBER) {
            pos++;
            return Double.parseDouble(token.value);
        }
        if (token.type == FormulaParser.TokenType.CELL_REF) {
            pos++;
            return cellValueResolver.apply(token.value);
        }
        if (token.type == FormulaParser.TokenType.LPAREN) {
            pos++;
            double result = parseExpression();
            if (pos >= tokens.size()
                    || tokens.get(pos).type != FormulaParser.TokenType.RPAREN) {
                throw new IllegalArgumentException("Missing closing parenthesis");
            }
            pos++;
            return result;
        }
        throw new IllegalArgumentException("Unexpected token: " + token);
    }

    private boolean isAddSub(FormulaParser.Token t) {
        return t.type == FormulaParser.TokenType.OPERATOR
                && (t.value.equals("+") || t.value.equals("-"));
    }

    private boolean isMulDiv(FormulaParser.Token t) {
        return t.type == FormulaParser.TokenType.OPERATOR
                && (t.value.equals("*") || t.value.equals("/"));
    }
}
```

### DependencyGraph

```java
import java.util.*;

public class DependencyGraph {

    // dependents: A1 → {C1, D1} means "C1 and D1 depend on A1"
    private final Map<String, Set<String>> dependents = new HashMap<>();
    // dependencies: C1 → {A1, B1} means "C1 depends on A1 and B1"
    private final Map<String, Set<String>> dependencies = new HashMap<>();

    public void addDependency(String cell, String dependsOn) {
        dependencies.computeIfAbsent(cell, k -> new HashSet<>()).add(dependsOn);
        dependents.computeIfAbsent(dependsOn, k -> new HashSet<>()).add(cell);
    }

    public void removeDependenciesFor(String cell) {
        Set<String> deps = dependencies.remove(cell);
        if (deps != null) {
            for (String dep : deps) {
                Set<String> set = dependents.get(dep);
                if (set != null) {
                    set.remove(cell);
                    if (set.isEmpty()) dependents.remove(dep);
                }
            }
        }
    }

    public Set<String> getDependents(String cell) {
        return dependents.getOrDefault(cell, Collections.emptySet());
    }

    public Set<String> getDependencies(String cell) {
        return dependencies.getOrDefault(cell, Collections.emptySet());
    }

    /**
     * Detects if adding the given dependencies for {@code cell} would create a cycle.
     * Uses DFS: starting from each new dependency, checks if any path leads back to cell.
     */
    public boolean hasCycle(String cell, Set<String> newDeps) {
        Set<String> visited = new HashSet<>();
        for (String dep : newDeps) {
            if (dfsDetectCycle(dep, cell, visited)) {
                return true;
            }
        }
        return false;
    }

    private boolean dfsDetectCycle(String current, String target, Set<String> visited) {
        if (current.equals(target)) return true;
        if (!visited.add(current)) return false;

        for (String dep : dependencies.getOrDefault(current, Collections.emptySet())) {
            if (dfsDetectCycle(dep, target, visited)) return true;
        }
        return false;
    }

    /**
     * Returns a topological ordering of all cells that need recalculation
     * when {@code startCell} changes. Uses BFS (Kahn's algorithm) over the
     * subgraph of affected cells.
     */
    public List<String> topologicalSort(String startCell) {
        // Collect all affected cells via BFS on the dependents graph
        Set<String> affected = new LinkedHashSet<>();
        Queue<String> queue = new ArrayDeque<>();
        for (String dep : getDependents(startCell)) {
            queue.add(dep);
        }
        while (!queue.isEmpty()) {
            String cell = queue.poll();
            if (affected.add(cell)) {
                for (String next : getDependents(cell)) {
                    queue.add(next);
                }
            }
        }

        // Kahn's algorithm on the affected subgraph
        Map<String, Integer> inDegree = new HashMap<>();
        for (String cell : affected) {
            inDegree.put(cell, 0);
        }
        for (String cell : affected) {
            for (String dep : getDependencies(cell)) {
                if (affected.contains(dep)) {
                    inDegree.merge(cell, 1, Integer::sum);
                }
            }
        }

        Queue<String> ready = new ArrayDeque<>();
        for (Map.Entry<String, Integer> entry : inDegree.entrySet()) {
            if (entry.getValue() == 0) ready.add(entry.getKey());
        }

        List<String> order = new ArrayList<>();
        while (!ready.isEmpty()) {
            String cell = ready.poll();
            order.add(cell);
            for (String dependent : getDependents(cell)) {
                if (affected.contains(dependent)) {
                    int newDeg = inDegree.merge(dependent, -1, Integer::sum);
                    if (newDeg == 0) ready.add(dependent);
                }
            }
        }
        return order;
    }
}
```

### Spreadsheet — Main Orchestrator

```java
import java.util.*;

public class Spreadsheet {

    private final Map<String, Cell> cells = new HashMap<>();
    private final DependencyGraph graph = new DependencyGraph();
    private final FormulaParser parser = new FormulaParser();

    public void setCellValue(String cellId, double value) {
        cellId = cellId.toUpperCase();
        Cell cell = getOrCreateCell(cellId);

        // Remove old formula dependencies
        graph.removeDependenciesFor(cellId);

        cell.setValue(value);
        recalculateDependents(cellId);
    }

    public void setCellFormula(String cellId, String formula) {
        cellId = cellId.toUpperCase();
        Cell cell = getOrCreateCell(cellId);

        Set<String> newDeps = parser.extractDependencies(formula);

        // Circular dependency check
        if (newDeps.contains(cellId) || graph.hasCycle(cellId, newDeps)) {
            throw new IllegalArgumentException(
                "Circular dependency detected for " + cellId + " with formula " + formula);
        }

        // Remove old dependencies
        graph.removeDependenciesFor(cellId);

        // Add new dependencies
        cell.setFormula(formula);
        cell.setDependencies(newDeps);
        for (String dep : newDeps) {
            getOrCreateCell(dep);
            graph.addDependency(cellId, dep);
        }

        // Evaluate this cell
        evaluateCell(cell);

        // Cascade recalculation
        recalculateDependents(cellId);
    }

    public double getCellValue(String cellId) {
        cellId = cellId.toUpperCase();
        Cell cell = cells.get(cellId);
        return cell != null ? cell.getValue() : 0.0;
    }

    public Cell getCell(String cellId) {
        return cells.get(cellId.toUpperCase());
    }

    private Cell getOrCreateCell(String cellId) {
        return cells.computeIfAbsent(cellId, Cell::new);
    }

    private void evaluateCell(Cell cell) {
        if (!cell.hasFormula()) return;

        FormulaEvaluator evaluator = new FormulaEvaluator(this::getCellValue);
        double result = evaluator.evaluate(cell.getFormula());
        cell.setValue(result);
        cell.setFormula(cell.getFormula()); // restore formula (setValue clears it)
        cell.setDependencies(parser.extractDependencies(cell.getFormula()));
    }

    private void recalculateDependents(String cellId) {
        List<String> order = graph.topologicalSort(cellId);
        for (String depCellId : order) {
            Cell depCell = cells.get(depCellId);
            if (depCell != null && depCell.hasFormula()) {
                evaluateCell(depCell);
            }
        }
    }

    public void printSheet() {
        System.out.println("=== Spreadsheet State ===");
        cells.entrySet().stream()
            .sorted(Map.Entry.comparingByKey())
            .forEach(e -> System.out.println("  " + e.getValue()));
        System.out.println();
    }
}
```

### Main — Demo

```java
public class SpreadsheetDemo {
    public static void main(String[] args) {
        Spreadsheet sheet = new Spreadsheet();

        // Set raw values
        sheet.setCellValue("A1", 5);
        sheet.setCellValue("B1", 10);
        System.out.println("--- After setting A1=5, B1=10 ---");
        sheet.printSheet();

        // Set formula C1 = A1 + B1
        sheet.setCellFormula("C1", "=A1+B1");
        System.out.println("--- After setting C1=A1+B1 ---");
        sheet.printSheet();
        System.out.println("C1 = " + sheet.getCellValue("C1")); // 15.0

        // Set formula D1 = C1 * 2
        sheet.setCellFormula("D1", "=C1*2");
        System.out.println("--- After setting D1=C1*2 ---");
        sheet.printSheet();
        System.out.println("D1 = " + sheet.getCellValue("D1")); // 30.0

        // Now change A1 to 20 — C1 and D1 should auto-update
        sheet.setCellValue("A1", 20);
        System.out.println("--- After changing A1 to 20 ---");
        sheet.printSheet();
        System.out.println("C1 = " + sheet.getCellValue("C1")); // 30.0  (20 + 10)
        System.out.println("D1 = " + sheet.getCellValue("D1")); // 60.0  (30 * 2)

        // Circular dependency detection
        try {
            sheet.setCellFormula("A1", "=D1+1");
            System.out.println("ERROR: Should have thrown!");
        } catch (IllegalArgumentException e) {
            System.out.println("Caught expected error: " + e.getMessage());
        }

        // Parentheses and complex expressions
        sheet.setCellFormula("E1", "=(A1+B1)*(C1-10)");
        System.out.println("--- After setting E1=(A1+B1)*(C1-10) ---");
        sheet.printSheet();
        System.out.println("E1 = " + sheet.getCellValue("E1")); // (20+10)*(30-10) = 600.0
    }
}
```

### Expected Output

```
--- After setting A1=5, B1=10 ---
=== Spreadsheet State ===
  Cell[A1, value=5.00]
  Cell[B1, value=10.00]

--- After setting C1=A1+B1 ---
=== Spreadsheet State ===
  Cell[A1, value=5.00]
  Cell[B1, value=10.00]
  Cell[C1, formula==A1+B1, value=15.00]

C1 = 15.0
--- After setting D1=C1*2 ---
=== Spreadsheet State ===
  Cell[A1, value=5.00]
  Cell[B1, value=10.00]
  Cell[C1, formula==A1+B1, value=15.00]
  Cell[D1, formula==C1*2, value=30.00]

D1 = 30.0
--- After changing A1 to 20 ---
=== Spreadsheet State ===
  Cell[A1, value=20.00]
  Cell[B1, value=10.00]
  Cell[C1, formula==A1+B1, value=30.00]
  Cell[D1, formula==C1*2, value=60.00]

C1 = 30.0
D1 = 60.0
Caught expected error: Circular dependency detected for A1 with formula =D1+1
--- After setting E1=(A1+B1)*(C1-10) ---
=== Spreadsheet State ===
  Cell[A1, value=20.00]
  Cell[B1, value=10.00]
  Cell[C1, formula==A1+B1, value=30.00]
  Cell[D1, formula==C1*2, value=60.00]
  Cell[E1, formula==(A1+B1)*(C1-10), value=600.00]

E1 = 600.0
```

---

## Class Diagram

```
┌─────────────────────┐       ┌────────────────────┐
│    Spreadsheet      │       │  DependencyGraph   │
├─────────────────────┤       ├────────────────────┤
│ cells: Map<Str,Cell>│──────▶│ dependents: Map    │
│ graph: DepGraph     │       │ dependencies: Map  │
│ parser: FormParser  │       ├────────────────────┤
├─────────────────────┤       │ addDependency()    │
│ setCellValue()      │       │ removeDepsFor()    │
│ setCellFormula()    │       │ hasCycle()         │
│ getCellValue()      │       │ topologicalSort()  │
│ recalcDependents()  │       └────────────────────┘
└────────┬────────────┘
         │ uses
         ▼
┌─────────────────────┐       ┌────────────────────┐
│       Cell          │       │   FormulaParser    │
├─────────────────────┤       ├────────────────────┤
│ id: String          │       │ parse(formula)     │
│ value: double       │       │ extractDeps(form)  │
│ formula: String     │       └────────┬───────────┘
│ dependencies: Set   │                │ produces
│ dependents: Set     │                ▼
├─────────────────────┤       ┌────────────────────┐
│ getValue/setValue() │       │  FormulaEvaluator  │
│ hasFormula()        │       ├────────────────────┤
└─────────────────────┘       │ evaluate(formula)  │
                              │ parseExpression()  │
┌─────────────────────┐       │ parseTerm()        │
│      CellId         │       │ parseFactor()      │
├─────────────────────┤       └────────────────────┘
│ row: int            │
│ col: int            │
│ parse("A1")→(0,0)  │
└─────────────────────┘
```

---

## Complexity Analysis

| Operation | Time Complexity | Notes |
|-----------|----------------|-------|
| Set cell value | O(1) | HashMap put |
| Set cell formula | O(F + V + E) | F = formula tokens, V+E = cycle check |
| Get cell value | O(1) | HashMap get |
| Cycle detection | O(V + E) | DFS on dependency subgraph |
| Recalculation | O(V + E + F·V) | Topological sort + evaluate each affected cell |
| Parse formula | O(F) | F = number of tokens |

Where V = number of affected cells, E = number of dependency edges, F = formula length.

---

## Interview-Ready Answer

> "I would model the spreadsheet as a `HashMap<String, Cell>` for O(1) cell lookup by A1 notation. Each cell holds either a raw numeric value or a formula string. When a formula like `=A1+B1` is set, I parse it with a regex-based tokenizer to extract cell references as dependencies, then build a directed dependency graph using adjacency lists. Before accepting any formula, I run a DFS cycle detection to prevent circular references — if adding the formula would create a cycle, I reject it immediately. Once accepted, I evaluate the formula using a recursive-descent evaluator that respects operator precedence and resolves cell references through the spreadsheet. When any cell's value changes, I perform a topological sort (Kahn's algorithm) on the subgraph of transitively affected dependents, then re-evaluate each cell in that order. This guarantees every cell sees up-to-date inputs before it computes its own value. The Observer pattern ensures dependents are notified of changes, the Composite pattern lets raw values and formulas share a common interface, and the Strategy pattern makes it easy to add new formula functions without modifying the evaluator. For concurrency in a multi-user scenario, I would add a `ReadWriteLock` at the spreadsheet level."

---

## Common Interview Follow-ups

| Question | Key Points |
|----------|-----------|
| **How do you handle ranges like SUM(A1:A10)?** | Expand the range into individual cell references during parsing; add each as a dependency |
| **How would you support undo/redo?** | Command pattern — each `setCell` creates a `Command` object stored on an undo `Deque`; undo reverses the command and pushes to redo stack |
| **What if the sheet is huge (millions of cells)?** | Sparse storage (only store non-empty cells); lazy evaluation (only compute when a cell is read); partition the dependency graph |
| **How to handle string values in cells?** | Make `CellContent` generic — `NumberValue`, `StringValue`, `FormulaValue`; formulas that reference string cells throw a `#VALUE!` error |
| **How to persist the spreadsheet?** | Serialize to JSON/CSV — store each cell's id, raw value or formula; on load, replay formulas in topological order |
