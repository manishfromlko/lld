# 03 — Tic-Tac-Toe Game (Python Implementation)

**File:** `tic_tac_toe.py`  
**Tier:** 1 — Highest priority

---

## Problem Statement

Design an extensible N×N Tic-Tac-Toe game with pluggable win strategies and an O(1) win-detection algorithm using running counters.

---

## Design Patterns Used

| Pattern | Where | Why |
|---|---|---|
| **Strategy** | `WinStrategy` ABC → `DefaultWinStrategy` | Swap win-detection logic (e.g., connect-K) without changing `Game` |
| **Factory** | `create_standard_game()` | Encapsulates player + board + strategy wiring |
| **State (Enum)** | `GameStatus` enum drives game-loop | Clean `IN_PROGRESS → WIN / DRAW` transitions |

---

## Class Structure

```
Player(name, symbol, value)       — value = +1 or -1
Move(row, col, player)            — immutable record of one turn
Board(size)                       — char[][] grid + placement validation
WinStrategy (ABC)
└── DefaultWinStrategy            — O(1) counters
Game(board, players, strategy)    — orchestrates turns
create_standard_game()            — factory
```

---

## O(1) Win Check — The Key Insight

Assign each player a numeric value: Player 1 = **+1**, Player 2 = **-1**.  
Maintain four running counters. After each move, check if any counter's absolute value equals N.

```python
# After move at (row, col) by player with value V:
self._row[row]  += V
self._col[col]  += V
if row == col:           self._diag     += V
if row + col == N - 1:  self._anti_diag += V

# Win if any counter hits ±N
return (abs(self._row[row])      == N or
        abs(self._col[col])      == N or
        abs(self._diag)          == N or
        abs(self._anti_diag)     == N)
```

**No board scan needed** — each move touches exactly 2–4 counters. Win check is O(1) per move.

---

## Worked Example (3×3)

```
Move 1: X(+1) at (0,0) → row=[1,0,0] col=[1,0,0] diag=1 anti=0
Move 2: O(-1) at (1,1) → row=[1,-1,0] col=[1,-1,0] diag=0 anti=-1
Move 3: X(+1) at (0,1) → row=[2,-1,0] col=[1,0,0]
Move 4: O(-1) at (2,0) → row=[2,-1,-1] col=[0,0,0]
Move 5: X(+1) at (0,2) → row=[3,-1,-1] → |3| == 3 → X WINS on row 0
```

---

## Python vs Java Key Differences

| Concern | Java | Python |
|---|---|---|
| Interface | `interface WinStrategy` | `ABC` + `@abstractmethod` |
| Enum | `enum GameStatus` | `class GameStatus(Enum)` |
| Record/value object | `record Move(int row, int col, Player player)` | `@dataclass` (or plain class) |
| char array | `char[][] grid` | `list[list[str]]` |

---

## Draw Detection

```python
self._move_count += 1
if self._move_count == self._size ** 2:
    return GameStatus.DRAW
```

Tracked via a simple counter — no need to scan the board.

---

## Extension Points

| Extension | How |
|---|---|
| Connect-K on N×N | New `ConnectKWinStrategy` — use sliding window of size K along rows/cols/diags |
| Undo/Redo | Command pattern — each `Move` stores enough to reverse: subtract `V` from same counters |
| AI player | Minimax with alpha-beta pruning; plug into `Game` as a special `Player` subclass |
| >2 players | Change counters from int to `dict[player_value → int]`; win when any player's counter hits N |

---

## Interview Talking Points

1. **Why +1 / -1 values?** — They let a single integer per row/col/diag represent both players. If two different players both play in the same row, they cancel out and can never reach ±N. One player filling a line reaches N or -N exactly.
2. **Why not `abs(counter) == N` is wrong for >2 players** — With 3 players assigning +1, -1, +2, counters can reach N from mixed values. Extend to per-player counters in that case.
3. **What changes if K < N wins?** — The single-integer counter approach breaks. Maintain a sliding window of the last K cells per row/col/diag and check all-same-player in O(K) per move.
4. **Concurrency for a server** — Synchronise on the `Game` object. Moves are atomic: validate → place → check win → switch turn.
