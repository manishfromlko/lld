# 12 — In-Memory Spreadsheet with Formula Engine (Python Implementation)

**File:** `spreadsheet.py`  
**Tier:** 3

---

## Problem Statement

Design an in-memory spreadsheet where cells hold raw values or formulas that reference other cells. When a cell changes, all dependent cells must be automatically recalculated in topological order. Circular dependencies must be detected and rejected.

---

## Design Patterns Used

| Pattern | Where | Why |
|---|---|---|
| **Interpreter** | `FormulaParser` + `FormulaEvaluator` | Tokenise and evaluate arbitrary arithmetic expressions with cell references |
| **Observer** (implicit) | `_recalculate_dependents()` propagates changes | Changing one cell triggers recalculation of all downstream cells |
| **Dependency Graph** | `DependencyGraph` | Tracks which cells depend on which, enabling topological evaluation order |

---

## Class Structure

```
TokenType (Enum): NUMBER, CELL_REF, PLUS, MINUS, STAR, SLASH, LPAREN, RPAREN
Token(ttype, value)

FormulaParser             — regex tokenizer: "=A1+B2*3" → list[Token]
FormulaEvaluator          — recursive-descent evaluator (expr → term → factor)

Cell(cell_id, value, formula, dependencies, dependents)
DependencyGraph           — add_dependency / remove_dependencies / has_cycle / topological_order
Spreadsheet               — set_value / set_formula / get_value / _recalculate_dependents
```

---

## Formula Parser — Regex Tokenizer

A single compiled regex tokenises the formula expression in one pass:

```python
_TOKEN_RE = re.compile(
    r"([A-Z]+\d+)"         # CELL_REF  e.g. A1, BC12
    r"|(\d+(?:\.\d*)?)"    # NUMBER    e.g. 42, 3.14
    r"|(\+)|(-)|(\*)|(/)"
    r"|(\()|(\))"
)
```

Called once per formula string — O(len(formula)) tokenisation. Strips spaces before matching.

---

## Formula Evaluator — Recursive Descent

Implements a classic recursive-descent parser respecting standard operator precedence (`*`/`/` before `+`/`-`):

```
Grammar:
  expr   → term   (('+' | '-') term)*
  term   → factor (('*' | '/') factor)*
  factor → NUMBER | CELL_REF | '(' expr ')'
```

```python
def _expr(self) -> float:
    left = self._term()
    while self._peek() and self._peek().ttype in (PLUS, MINUS):
        op = self._consume().ttype
        right = self._term()
        left = left + right if op == PLUS else left - right
    return left

def _factor(self) -> float:
    tok = self._peek()
    if tok.ttype == NUMBER:    return float(self._consume().value)
    if tok.ttype == CELL_REF: return self._resolve(self._consume().value)
    if tok.ttype == LPAREN:
        self._consume()
        val = self._expr()
        self._consume()   # RPAREN
        return val
```

`_resolve` is a callable injected at construction — `Spreadsheet.get_value`. This keeps `FormulaEvaluator` independent of `Spreadsheet`.

---

## Dependency Graph

### Structure
```python
_deps:      dict[str, set[str]]   # cell → cells it reads from
_dependents: dict[str, set[str]] # cell → cells that read it
```

### Cycle Detection — DFS

Before adding new dependencies for `cell_id`, check if any new dependency can reach `cell_id` via existing `_deps`:

```python
def has_cycle(self, start: str, new_deps: set[str]) -> bool:
    visited = set()
    def dfs(node):
        if node == start: return True    # found a path back to start → cycle!
        if node in visited: return False
        visited.add(node)
        return any(dfs(dep) for dep in self._deps.get(node, set()))

    return any(dep == start or dfs(dep) for dep in new_deps)
```

**Key:** DFS follows `_deps` edges (what each cell depends on), not `_dependents`. If we can reach `start` from any `new_dep` by following dependencies, adding the edge would create a cycle.

### Topological Order — Kahn's BFS

When cell `X` changes, find all cells that (transitively) depend on `X` and order them so no cell is recalculated before its dependencies:

```python
def topological_order(self, start: str) -> list[str]:
    # 1. Collect all reachable cells via _dependents (BFS)
    reachable = {all cells reachable from start via _dependents}

    # 2. Build in-degree map restricted to reachable subgraph
    in_degree = {n: count of n's deps that are also reachable}

    # 3. Kahn's: process zero-in-degree nodes first
    ready = deque(n for n in reachable if in_degree[n] == 0)
    order = []
    while ready:
        node = ready.popleft()
        order.append(node)
        for dep in _dependents[node]:
            in_degree[dep] -= 1
            if in_degree[dep] == 0:
                ready.append(dep)
    return order
```

---

## Cascaded Recalculation Flow

```
set_value("A1", 20)
  → remove A1's old formula deps (none for raw value)
  → A1.value = 20
  → _recalculate_dependents("A1")
       → topological_order("A1") = ["C1", "D1"]  (C1 = A1+B1; D1 = C1*2)
       → C1: re-evaluate "=A1+B1" → 20+10 = 30
       → D1: re-evaluate "=C1*2"  → 30*2 = 60
```

Order matters: D1 must be recalculated **after** C1, not before.

---

## Circular Dependency Rejection

```python
sheet.set_formula("X1", "=Y1+1")   # X1 depends on Y1 ✓
sheet.set_formula("Y1", "=X1+1")   # Y1 depends on X1 → X1 → Y1 → cycle!
# → raises ValueError: Circular dependency detected
```

`has_cycle("Y1", {"X1"})`:
- DFS from X1 following `_deps["X1"] = {"Y1"}`
- reaches Y1 = start → returns True → exception raised, formula not applied.

---

## Python vs Java Key Differences

| Concern | Java | Python |
|---|---|---|
| Regex | `Pattern.compile` + `Matcher` | `re.compile` + `finditer` |
| TreeMap for cells | `TreeMap<String, Cell>` for sorted order | `dict` (insertion-ordered 3.7+), sort on `display()` |
| Topological sort | `Kahn's with LinkedList queue` | `collections.deque` as BFS queue |
| Interface injection | Constructor DI with interface type | Callable (function reference) passed to `FormulaEvaluator` |

---

## Interview Talking Points

1. **Why recursive descent instead of a library?** — For an interview, recursive descent proves you understand grammar, operator precedence, and parsing. It's also ~50 lines — concise enough to write in a session.
2. **Why Kahn's (BFS) instead of DFS topological sort?** — Kahn's naturally detects remaining cycles (nodes with in-degree > 0 after BFS). DFS topo-sort requires a separate cycle check. Since we already check for cycles before adding the formula, Kahn's is slightly simpler here.
3. **What if a formula references a non-existent cell?** — `_get_or_create` initialises missing cells with value `0.0`. This matches Excel behaviour (blank cell = 0).
4. **Concurrency** — The current implementation is single-threaded. For concurrent access, add a `threading.RWLock`: reads (`get_value`) can share, writes (`set_value`, `set_formula`) need exclusive access. The entire recalculation cascade must happen under the write lock to prevent partial reads.
