# 001 — Tic-Tac-Toe (Simple Version)

**File:** `001-tic-tac-toe.py`  
**Use this version in an interview** — straightforward board scan, no counter tricks.

> For the O(1) counter-based version see `03-tic_tac_toe.py` / `03-tic_tac_toe.md`.

---

## Problem Statement

Design an N×N Tic-Tac-Toe game with a pluggable win-detection strategy. Two players take turns placing their symbol; the first to fill a complete row, column, or diagonal wins.

---

## Design Patterns Used

| Pattern | Where | Why |
|---|---|---|
| **Strategy** | `WinStrategy` ABC → `BoardScanWinStrategy` | Swap win-detection logic without changing `Game` |
| **Factory** | `create_standard_game()` | Wires board + players + strategy in one place |
| **State (Enum)** | `GameStatus` | Explicit `IN_PROGRESS → WIN / DRAW` transitions |

---

## Class Structure

```
Player(name, symbol)          — just name and symbol, no numeric value
Move(row, col, player)        — what was played and by whom
Board(size)                   — N×N grid, place_move(), is_full(), display()

WinStrategy (ABC)
└── BoardScanWinStrategy      — scans only the affected row/col/diag after each move

Game(board, players, strategy)
└── make_move(row, col) → GameStatus

create_standard_game() → Game   — factory
```

---

## Win Strategy — Simple Board Scan

After each move, check only the **row, column, and diagonals that the move touched**. No need to scan the entire board.

```python
class BoardScanWinStrategy(WinStrategy):
    def check_win(self, board: Board, move: Move) -> bool:
        r, c, sym = move.row, move.col, move.player.symbol
        n = board.size

        # Row that was just played
        if all(board.get(r, col) == sym for col in range(n)):
            return True

        # Column that was just played
        if all(board.get(row, c) == sym for row in range(n)):
            return True

        # Main diagonal — only relevant if move is ON the diagonal (row == col)
        if r == c:
            if all(board.get(i, i) == sym for i in range(n)):
                return True

        # Anti-diagonal — only relevant if move is on it (row + col == n-1)
        if r + c == n - 1:
            if all(board.get(i, n - 1 - i) == sym for i in range(n)):
                return True

        return False
```

**Why only affected row/col/diag?** — Cells in other rows/columns haven't changed, so they can't have newly formed a winning line. Checking them every move would be wasted work.

---

## Complexity

| | Simple scan (this version) | O(1) counter version |
|---|---|---|
| Per-move win check | O(N) | O(1) |
| Extra space | None | O(N) for counter arrays |
| Easy to explain? | **Yes** | Needs +1/-1 insight |

For a 3×3 board, O(N) = O(3) — no practical difference. The simple version is preferred in an interview unless the interviewer specifically asks for O(1).

---

## Game Flow

```
Game.__init__   → board, players, strategy, current_idx=0, status=IN_PROGRESS

make_move(r, c):
  1. Validate game is still IN_PROGRESS
  2. Get current player
  3. board.place_move(move)  — validates bounds + cell not occupied
  4. strategy.check_win(board, move)  → WIN?
  5. board.is_full() → DRAW?
  6. Advance current_idx = (current_idx + 1) % len(players)
```

---

## Plugging in a Different Strategy

To use a different win rule (e.g., Connect-K where K < N), just implement `WinStrategy`:

```python
class ConnectKWinStrategy(WinStrategy):
    def __init__(self, k: int):
        self._k = k

    def check_win(self, board: Board, move: Move) -> bool:
        # Check runs of length k in row/col/diag through (move.row, move.col)
        ...

# Use it:
game = Game(Board(6), players, ConnectKWinStrategy(4))  # Connect-4 on a 6×6 board
```

`Game` and `Board` require zero changes.

---

## Differences from the O(1) Version (`03-tic_tac_toe.py`)

| Aspect | This version (001) | O(1) version (03) |
|---|---|---|
| `Player` fields | `name`, `symbol` | `name`, `symbol`, `value` (+1/-1) |
| `WinStrategy.check_win` args | `(board, move)` — needs the board | `(move, board_size)` — only counters |
| Win detection | Scans row/col/diag in grid | Increments integer counters |
| Easiest to write in 30 min | **Yes** | Needs more thought |

---

## Interview Talking Points

1. **Why Strategy pattern for win detection?** — Decouples the game loop from the win rule. Adding Connect-K, or a custom "corners win" rule, only requires a new class implementing `WinStrategy` — `Game` and `Board` are untouched.
2. **Why check only the affected row/col/diag?** — After a move at `(r, c)`, only lines through that cell can be newly completed. All other lines are unchanged since the previous move.
3. **When to mention the O(1) version?** — Proactively: *"This is O(N) per move. If the interviewer needs O(1), I can maintain running row/col/diag counters using a +1/-1 per-player trick that eliminates the scan entirely."*
4. **Diagonal guard conditions** — `r == c` checks the main diagonal; `r + c == n - 1` checks the anti-diagonal. A move not on a diagonal doesn't need to trigger a diagonal check at all.
