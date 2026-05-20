"""
In-Memory Spreadsheet with Formula Engine
- Cell: stores raw value or formula, tracks dependencies / dependents
- FormulaParser: regex tokenizer → token list
- FormulaEvaluator: recursive-descent (expression → term → factor) for operator precedence
- DependencyGraph: Kahn's topological sort for cascaded recalculation; DFS cycle detection
"""

import re
from dataclasses import dataclass, field
from collections import deque
from enum import Enum
from typing import Optional


# ──────────────────────────────────────────────
#  Token
# ──────────────────────────────────────────────

class TokenType(Enum):
    NUMBER   = "NUMBER"
    CELL_REF = "CELL_REF"
    PLUS     = "PLUS"
    MINUS    = "MINUS"
    STAR     = "STAR"
    SLASH    = "SLASH"
    LPAREN   = "LPAREN"
    RPAREN   = "RPAREN"


@dataclass
class Token:
    ttype: TokenType
    value: str


# ──────────────────────────────────────────────
#  FormulaParser — tokenizes "=A1+B2*3"
# ──────────────────────────────────────────────

_TOKEN_RE = re.compile(
    r"([A-Z]+\d+)"       # CELL_REF  e.g. A1, BC12
    r"|(\d+(?:\.\d*)?)"  # NUMBER    e.g. 42, 3.14
    r"|(\+)|(-)|(\*)|(/)"
    r"|(\()|(\))"
)


class FormulaParser:
    def parse(self, formula: str) -> list[Token]:
        """formula must start with '='"""
        expr = formula.lstrip("=").replace(" ", "")
        tokens: list[Token] = []
        for m in _TOKEN_RE.finditer(expr):
            cell, num, plus, minus, star, slash, lp, rp = m.groups()
            if cell:
                tokens.append(Token(TokenType.CELL_REF, cell))
            elif num:
                tokens.append(Token(TokenType.NUMBER, num))
            elif plus:
                tokens.append(Token(TokenType.PLUS, "+"))
            elif minus:
                tokens.append(Token(TokenType.MINUS, "-"))
            elif star:
                tokens.append(Token(TokenType.STAR, "*"))
            elif slash:
                tokens.append(Token(TokenType.SLASH, "/"))
            elif lp:
                tokens.append(Token(TokenType.LPAREN, "("))
            elif rp:
                tokens.append(Token(TokenType.RPAREN, ")"))
        return tokens


# ──────────────────────────────────────────────
#  FormulaEvaluator — recursive-descent
#  Grammar:
#    expr   → term   (('+' | '-') term)*
#    term   → factor (('*' | '/') factor)*
#    factor → NUMBER | CELL_REF | '(' expr ')'
# ──────────────────────────────────────────────

class FormulaEvaluator:
    def __init__(self, cell_resolver):
        # cell_resolver: callable(cell_id: str) -> float
        self._resolve = cell_resolver

    def evaluate(self, tokens: list[Token]) -> float:
        self._tokens = tokens
        self._pos = 0
        result = self._expr()
        return result

    def _peek(self) -> Optional[Token]:
        return self._tokens[self._pos] if self._pos < len(self._tokens) else None

    def _consume(self) -> Token:
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def _expr(self) -> float:
        left = self._term()
        while self._peek() and self._peek().ttype in (TokenType.PLUS, TokenType.MINUS):
            op = self._consume().ttype
            right = self._term()
            left = left + right if op == TokenType.PLUS else left - right
        return left

    def _term(self) -> float:
        left = self._factor()
        while self._peek() and self._peek().ttype in (TokenType.STAR, TokenType.SLASH):
            op = self._consume().ttype
            right = self._factor()
            left = left * right if op == TokenType.STAR else left / right
        return left

    def _factor(self) -> float:
        tok = self._peek()
        if tok is None:
            raise ValueError("Unexpected end of formula")

        if tok.ttype == TokenType.NUMBER:
            self._consume()
            return float(tok.value)

        if tok.ttype == TokenType.CELL_REF:
            self._consume()
            return self._resolve(tok.value)

        if tok.ttype == TokenType.LPAREN:
            self._consume()
            val = self._expr()
            if not self._peek() or self._peek().ttype != TokenType.RPAREN:
                raise ValueError("Missing closing parenthesis")
            self._consume()
            return val

        raise ValueError(f"Unexpected token: {tok}")


# ──────────────────────────────────────────────
#  Cell
# ──────────────────────────────────────────────

@dataclass
class Cell:
    cell_id: str
    value: float = 0.0
    formula: Optional[str] = None
    dependencies: set[str] = field(default_factory=set)   # cells this cell reads
    dependents: set[str] = field(default_factory=set)     # cells that read this cell

    def __str__(self):
        if self.formula:
            return f"{self.cell_id}={self.formula}({self.value})"
        return f"{self.cell_id}={self.value}"


# ──────────────────────────────────────────────
#  DependencyGraph
# ──────────────────────────────────────────────

class DependencyGraph:
    def __init__(self):
        self._deps: dict[str, set[str]] = {}      # cell → cells it depends on
        self._dependents: dict[str, set[str]] = {} # cell → cells that depend on it

    def add_dependency(self, cell_id: str, depends_on: str):
        self._deps.setdefault(cell_id, set()).add(depends_on)
        self._dependents.setdefault(depends_on, set()).add(cell_id)

    def remove_dependencies(self, cell_id: str):
        for dep in self._deps.pop(cell_id, set()):
            self._dependents.get(dep, set()).discard(cell_id)

    def get_dependents(self, cell_id: str) -> set[str]:
        return self._dependents.get(cell_id, set())

    def has_cycle(self, start: str, new_deps: set[str]) -> bool:
        """Check if adding new_deps for start would create a cycle (DFS).
        A cycle exists if any new dep can reach `start` via existing _deps."""
        visited: set[str] = set()

        def dfs(node: str) -> bool:
            if node == start:
                return True
            if node in visited:
                return False
            visited.add(node)
            for dep in self._deps.get(node, set()):
                if dfs(dep):
                    return True
            return False

        for dep in new_deps:
            if dep == start or dfs(dep):
                return True
        return False

    def topological_order(self, start: str) -> list[str]:
        """
        Kahn's BFS: return all dependents of `start` in evaluation order
        (cells that have no unresolved dependencies come first).
        """
        # Collect all nodes reachable from `start` via dependents
        reachable: set[str] = set()
        queue: deque[str] = deque([start])
        while queue:
            node = queue.popleft()
            for dep in self._dependents.get(node, set()):
                if dep not in reachable:
                    reachable.add(dep)
                    queue.append(dep)

        # Build in-degree map restricted to the reachable subgraph
        in_degree: dict[str, int] = {n: 0 for n in reachable}
        for node in reachable:
            for d in self._deps.get(node, set()):
                if d in reachable:
                    in_degree[node] = in_degree.get(node, 0) + 1

        ready: deque[str] = deque(n for n in reachable if in_degree[n] == 0)
        order: list[str] = []
        while ready:
            node = ready.popleft()
            order.append(node)
            for dep in self._dependents.get(node, set()):
                if dep in in_degree:
                    in_degree[dep] -= 1
                    if in_degree[dep] == 0:
                        ready.append(dep)
        return order


# ──────────────────────────────────────────────
#  Spreadsheet
# ──────────────────────────────────────────────

class Spreadsheet:
    def __init__(self):
        self._cells: dict[str, Cell] = {}
        self._graph = DependencyGraph()
        self._parser = FormulaParser()

    def _get_or_create(self, cell_id: str) -> Cell:
        if cell_id not in self._cells:
            self._cells[cell_id] = Cell(cell_id)
        return self._cells[cell_id]

    def set_value(self, cell_id: str, value: float):
        cell = self._get_or_create(cell_id)
        # Remove old formula dependencies
        self._graph.remove_dependencies(cell_id)
        cell.dependencies.clear()
        cell.formula = None
        cell.value = value
        self._recalculate_dependents(cell_id)

    def set_formula(self, cell_id: str, formula: str):
        tokens = self._parser.parse(formula)
        new_deps = {t.value for t in tokens if t.ttype == TokenType.CELL_REF}

        if self._graph.has_cycle(cell_id, new_deps):
            raise ValueError(f"Circular dependency detected for {cell_id} with formula {formula}")

        cell = self._get_or_create(cell_id)
        # Remove old dependencies, register new ones
        self._graph.remove_dependencies(cell_id)
        cell.dependencies.clear()

        for dep_id in new_deps:
            self._get_or_create(dep_id)
            self._graph.add_dependency(cell_id, dep_id)
            cell.dependencies.add(dep_id)

        cell.formula = formula
        cell.value = self._evaluate_formula(tokens)
        self._recalculate_dependents(cell_id)

    def get_value(self, cell_id: str) -> float:
        return self._cells[cell_id].value if cell_id in self._cells else 0.0

    def _evaluate_formula(self, tokens: list[Token]) -> float:
        evaluator = FormulaEvaluator(self.get_value)
        return evaluator.evaluate(tokens)

    def _recalculate_dependents(self, cell_id: str):
        order = self._graph.topological_order(cell_id)
        for cid in order:
            cell = self._cells.get(cid)
            if cell and cell.formula:
                tokens = self._parser.parse(cell.formula)
                cell.value = self._evaluate_formula(tokens)
                print(f"    ↻ recalculated {cell.cell_id} = {cell.value}")

    def display(self):
        for cid in sorted(self._cells):
            c = self._cells[cid]
            if c.formula:
                print(f"  {cid}: {c.formula} = {c.value}")
            else:
                print(f"  {cid}: {c.value}")


# ──────────────────────────────────────────────
#  Demo
# ──────────────────────────────────────────────

if __name__ == "__main__":
    sheet = Spreadsheet()

    print("=== Set raw values ===")
    sheet.set_value("A1", 5)
    sheet.set_value("B1", 10)
    sheet.display()

    print("\n=== Set formula: C1 = A1 + B1 ===")
    sheet.set_formula("C1", "=A1+B1")
    sheet.display()

    print("\n=== Set formula: D1 = C1 * 2 ===")
    sheet.set_formula("D1", "=C1*2")
    sheet.display()

    print("\n=== Change A1 = 20 → cascaded recalculation ===")
    sheet.set_value("A1", 20)
    sheet.display()

    print("\n=== Complex formula: E1 = (A1 + B1) * 3 ===")
    sheet.set_formula("E1", "=(A1+B1)*3")
    sheet.display()

    print("\n=== Circular dependency detection ===")
    sheet.set_formula("X1", "=Y1+1")
    try:
        sheet.set_formula("Y1", "=X1+1")
        print("  ERROR: should have raised ValueError")
    except ValueError as e:
        print(f"  ✓ Caught: {e}")

    print("\n=== Final state ===")
    sheet.display()
