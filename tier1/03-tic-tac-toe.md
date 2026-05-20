# 03 — Tic-Tac-Toe Game

**Priority:** TIER 1 — reported at Netcore specifically

---

## Problem Statement

Design an extensible Tic-Tac-Toe game that supports N×N boards, multiple players, and pluggable winning strategies. The solution must demonstrate clean object-oriented design, Strategy pattern for win detection, and an O(1) win-check algorithm using running counters instead of brute-force board scanning.

---

## Clarification Questions to Ask the Interviewer

1. **Board size** — Is the board always 3×3, or should the design support arbitrary N×N boards?
2. **Number of players** — Is the game strictly 2-player, or could there be more players on larger boards?
3. **Win condition** — Is the win condition always N-in-a-row (full row/col/diagonal), or could it be a configurable K-in-a-row (e.g., connect-4 style on a 6×7 grid)?
4. **Undo/Redo** — Should the game support undo and redo of moves?
5. **AI player** — Should the system support a computer-controlled player (Minimax, random move, etc.)?
6. **Persistence** — Do we need to save/load game state, or is this purely in-memory?
7. **Concurrency** — Is this a local single-instance game, or will multiple games run concurrently on a server?

---

## Entities

```
┌─────────────┐      ┌──────────────┐
│    Game      │─────▶│    Board     │
│              │      │  (N×N grid)  │
│  players[]   │      └──────────────┘
│  currentIdx  │
│  status      │      ┌──────────────┐
│  winStrategy─┼─────▶│ WinStrategy  │  ◀── Strategy Pattern
│              │      │  (interface) │
└─────────────┘      └──────┬───────┘
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
     ┌────────────┐ ┌────────────┐ ┌──────────────┐
     │DefaultWin  │ │CustomWin   │ │ConnectKWin   │
     │Strategy    │ │Strategy    │ │Strategy      │
     └────────────┘ └────────────┘ └──────────────┘

┌──────────┐       ┌──────────┐       ┌────────────────┐
│  Player  │       │   Move   │       │   GameStatus   │
│  name    │       │  row     │       │  IN_PROGRESS   │
│  symbol  │       │  col     │       │  WIN           │
│  value   │       │  player  │       │  DRAW          │
└──────────┘       └──────────┘       └────────────────┘
```

| Entity | Responsibility |
|---|---|
| **Board** | Holds the N×N grid, validates placement, displays the board |
| **Player** | Represents a player with a name, display symbol, and numeric value for O(1) counting |
| **Move** | Immutable record of a single move: row, column, and who played |
| **Game** | Orchestrates gameplay: turn management, move validation, win/draw checks |
| **WinStrategy** | Interface for pluggable win-detection algorithms |
| **DefaultWinStrategy** | O(1) win check using running row/col/diagonal counters |
| **GameStatus** | Enum representing the current state of the game |

---

## Design Patterns

| Pattern | Where Applied | Why |
|---|---|---|
| **Strategy** | `WinStrategy` interface with `DefaultWinStrategy`, `CustomWinStrategy` | Decouple win-detection logic from `Game`; easily swap algorithms without changing game code |
| **Factory** | `GameFactory` | Encapsulate complex `Game` construction (board size, players, strategy selection) |
| **State (via Enum)** | `GameStatus` enum drives game-loop behavior | Clean transitions: `IN_PROGRESS → WIN / DRAW` |
| **Command** *(extension)* | `Move` as command objects for undo/redo | Each move is encapsulated and reversible |

---

## SOLID Principles Applied

| Principle | How It's Applied |
|---|---|
| **S — Single Responsibility** | `Board` only manages the grid. `Game` only orchestrates turns. `WinStrategy` only checks wins. Each class has exactly one reason to change. |
| **O — Open/Closed** | New win strategies (e.g., `ConnectKWinStrategy`) can be added by implementing `WinStrategy` — no modification to `Game` or `Board` needed. |
| **L — Liskov Substitution** | Any `WinStrategy` implementation can be substituted without breaking `Game`. `DefaultWinStrategy` and `CustomWinStrategy` are interchangeable via the interface. |
| **I — Interface Segregation** | `WinStrategy` has a single method `checkWin()`. Players don't depend on board internals. Interfaces are narrow and focused. |
| **D — Dependency Inversion** | `Game` depends on the `WinStrategy` abstraction, not on any concrete strategy. Strategy is injected at construction time. |

---

## Core Algorithm — O(1) Win Check

### The Problem with Brute Force

After every move, a naive approach scans the entire board — O(N²) per move. For a 3×3 board this is fine, but for larger boards it becomes wasteful.

### The O(1) Insight

Maintain running counters. Assign each player a numeric value: Player 1 = **+1**, Player 2 = **-1**. After each move, update exactly the relevant counters and check if any counter has reached ±N.

### Data Structures

```
int[] rowCount    = new int[N]   // sum of player values in each row
int[] colCount    = new int[N]   // sum of player values in each column
int   diagCount   = 0            // sum for main diagonal (row == col)
int   antiDiagCount = 0          // sum for anti-diagonal (row + col == N-1)
int   totalMoves  = 0            // to detect draw (totalMoves == N*N)
```

### Algorithm

```
Player X = +1, Player O = -1

After move at (row, col) by player with value V:

    rowCount[row]  += V
    colCount[col]  += V

    if (row == col)
        diagCount += V

    if (row + col == N - 1)
        antiDiagCount += V

    totalMoves++

    // Win check — O(1)
    if |rowCount[row]| == N
    || |colCount[col]| == N
    || |diagCount|     == N
    || |antiDiagCount| == N
        → CURRENT PLAYER WINS

    // Draw check
    if totalMoves == N * N
        → DRAW
```

### Worked Example (3×3)

```
Move 1: X plays (0,0)  → rowCount=[1,0,0] colCount=[1,0,0] diag=1 anti=0
Move 2: O plays (1,1)  → rowCount=[1,-1,0] colCount=[1,-1,0] diag=0 anti=-1
Move 3: X plays (0,1)  → rowCount=[2,-1,0] colCount=[1,0,0] diag=0 anti=-1
Move 4: O plays (2,0)  → rowCount=[2,-1,-1] colCount=[0,0,0] diag=0 anti=-2
Move 5: X plays (0,2)  → rowCount=[3,-1,-1] ← |3| == N → X WINS on row 0!
```

### Complexity

| Operation | Brute Force | O(1) Counter |
|---|---|---|
| Per-move win check | O(N) | **O(1)** |
| Space overhead | None | O(N) for row/col arrays |
| Total for full game | O(N² × N) | **O(N²)** |

---

## Data Structure Choices

| Data Structure | Used For | Why This Choice |
|---|---|---|
| `char[][] grid` | Board representation | Simple, cache-friendly, O(1) access by (row, col). `char` is human-readable for display. |
| `int[] rowCount` | Running row sums | O(1) win check per move. Index maps directly to row number. |
| `int[] colCount` | Running column sums | Same as above for columns. |
| `int diagCount` | Main diagonal sum | Only one main diagonal → single int suffices. |
| `int antiDiagCount` | Anti-diagonal sum | Only one anti-diagonal → single int suffices. |
| `List<Player>` | Player roster | Ordered, allows easy round-robin via index modulo. Supports >2 players for extensions. |
| `List<Move>` | Move history | Preserves order for undo/redo, replay, and auditing. |

---

## Concurrency Considerations

For a **single local game**, concurrency is not needed — the game loop is sequential.

For a **multiplayer server** scenario, consider:

| Concern | Approach |
|---|---|
| Multiple games in parallel | Each `Game` instance is independent — no shared state. Use a `ConcurrentHashMap<String, Game>` to manage game sessions. |
| Two players on same game via network | Synchronize on the `Game` object: `synchronized(game) { game.makeMove(...) }`. |
| Thread-safe board access | Board mutations only happen through `Game.makeMove()`, which acts as a single entry point — easy to synchronize. |
| Optimistic approach | Use `AtomicInteger` for counters and CAS operations for lock-free updates (over-engineering for an interview). |

---

## Java Implementation

### GameStatus.java

```java
public enum GameStatus {
    IN_PROGRESS,
    WIN,
    DRAW
}
```

### Player.java

```java
public class Player {
    private final String name;
    private final char symbol;
    private final int value; // +1 for player 1, -1 for player 2

    public Player(String name, char symbol, int value) {
        this.name = name;
        this.symbol = symbol;
        this.value = value;
    }

    public String getName()  { return name; }
    public char getSymbol()  { return symbol; }
    public int getValue()    { return value; }

    @Override
    public String toString() {
        return name + " (" + symbol + ")";
    }
}
```

### Move.java

```java
public class Move {
    private final int row;
    private final int col;
    private final Player player;

    public Move(int row, int col, Player player) {
        this.row = row;
        this.col = col;
        this.player = player;
    }

    public int getRow()       { return row; }
    public int getCol()       { return col; }
    public Player getPlayer() { return player; }
}
```

### WinStrategy.java — Strategy Pattern Interface

```java
public interface WinStrategy {

    /**
     * Called after every move. Returns true if the move results in a win.
     */
    boolean checkWin(Board board, Move move, int boardSize);

    /**
     * Resets internal state (for new game or undo).
     */
    void reset(int boardSize);
}
```

### DefaultWinStrategy.java — O(1) Win Check

```java
public class DefaultWinStrategy implements WinStrategy {

    private int[] rowCount;
    private int[] colCount;
    private int diagCount;
    private int antiDiagCount;

    public DefaultWinStrategy(int boardSize) {
        reset(boardSize);
    }

    @Override
    public void reset(int boardSize) {
        this.rowCount = new int[boardSize];
        this.colCount = new int[boardSize];
        this.diagCount = 0;
        this.antiDiagCount = 0;
    }

    @Override
    public boolean checkWin(Board board, Move move, int boardSize) {
        int row = move.getRow();
        int col = move.getCol();
        int val = move.getPlayer().getValue();

        rowCount[row] += val;
        colCount[col] += val;

        if (row == col) {
            diagCount += val;
        }

        if (row + col == boardSize - 1) {
            antiDiagCount += val;
        }

        return Math.abs(rowCount[row]) == boardSize
            || Math.abs(colCount[col]) == boardSize
            || Math.abs(diagCount) == boardSize
            || Math.abs(antiDiagCount) == boardSize;
    }
}
```

### Board.java

```java
public class Board {
    private final int size;
    private final char[][] grid;
    private int filledCells;

    public Board(int size) {
        this.size = size;
        this.grid = new char[size][size];
        this.filledCells = 0;
        initializeGrid();
    }

    private void initializeGrid() {
        for (int i = 0; i < size; i++) {
            for (int j = 0; j < size; j++) {
                grid[i][j] = '-';
            }
        }
    }

    public boolean placeMove(Move move) {
        int r = move.getRow();
        int c = move.getCol();

        if (r < 0 || r >= size || c < 0 || c >= size) {
            return false;
        }
        if (grid[r][c] != '-') {
            return false;
        }

        grid[r][c] = move.getPlayer().getSymbol();
        filledCells++;
        return true;
    }

    public boolean isFull() {
        return filledCells == size * size;
    }

    public int getSize() {
        return size;
    }

    public char getCell(int row, int col) {
        return grid[row][col];
    }

    public void display() {
        for (int i = 0; i < size; i++) {
            for (int j = 0; j < size; j++) {
                System.out.print(" " + grid[i][j]);
                if (j < size - 1) System.out.print(" |");
            }
            System.out.println();
            if (i < size - 1) {
                System.out.println("-".repeat(size * 4 - 1));
            }
        }
        System.out.println();
    }
}
```

### Game.java — Core Orchestrator

```java
import java.util.ArrayList;
import java.util.List;

public class Game {
    private final Board board;
    private final List<Player> players;
    private final WinStrategy winStrategy;
    private final List<Move> moveHistory;

    private int currentPlayerIndex;
    private GameStatus status;

    public Game(Board board, List<Player> players, WinStrategy winStrategy) {
        this.board = board;
        this.players = players;
        this.winStrategy = winStrategy;
        this.moveHistory = new ArrayList<>();
        this.currentPlayerIndex = 0;
        this.status = GameStatus.IN_PROGRESS;
    }

    public GameStatus makeMove(int row, int col) {
        if (status != GameStatus.IN_PROGRESS) {
            throw new IllegalStateException("Game is already over: " + status);
        }

        Player current = players.get(currentPlayerIndex);
        Move move = new Move(row, col, current);

        if (!board.placeMove(move)) {
            throw new IllegalArgumentException(
                "Invalid move at (" + row + ", " + col + "). Cell occupied or out of bounds."
            );
        }

        moveHistory.add(move);

        if (winStrategy.checkWin(board, move, board.getSize())) {
            status = GameStatus.WIN;
            System.out.println(">>> " + current + " WINS! <<<");
            return status;
        }

        if (board.isFull()) {
            status = GameStatus.DRAW;
            System.out.println(">>> DRAW <<<");
            return status;
        }

        currentPlayerIndex = (currentPlayerIndex + 1) % players.size();
        return status;
    }

    public Player getCurrentPlayer() {
        return players.get(currentPlayerIndex);
    }

    public GameStatus getStatus() {
        return status;
    }

    public Board getBoard() {
        return board;
    }

    public List<Move> getMoveHistory() {
        return List.copyOf(moveHistory);
    }
}
```

### GameFactory.java

```java
import java.util.List;

public class GameFactory {

    public static Game createStandardGame() {
        int size = 3;
        Board board = new Board(size);
        Player p1 = new Player("Alice", 'X', +1);
        Player p2 = new Player("Bob", 'O', -1);
        WinStrategy strategy = new DefaultWinStrategy(size);
        return new Game(board, List.of(p1, p2), strategy);
    }

    public static Game createCustomGame(int size, List<Player> players, WinStrategy strategy) {
        Board board = new Board(size);
        return new Game(board, players, strategy);
    }
}
```

### Main.java — Demo

```java
import java.util.Scanner;

public class Main {

    public static void main(String[] args) {
        Game game = GameFactory.createStandardGame();
        Scanner scanner = new Scanner(System.in);

        System.out.println("=== Tic-Tac-Toe ===");
        System.out.println("Enter moves as: row col (0-indexed)\n");
        game.getBoard().display();

        while (game.getStatus() == GameStatus.IN_PROGRESS) {
            Player current = game.getCurrentPlayer();
            System.out.print(current + "'s turn → ");

            int row = scanner.nextInt();
            int col = scanner.nextInt();

            try {
                game.makeMove(row, col);
            } catch (IllegalArgumentException e) {
                System.out.println("  ✗ " + e.getMessage());
                continue;
            }

            game.getBoard().display();
        }

        System.out.println("Game over. Status: " + game.getStatus());
        scanner.close();
    }
}
```

### Full Automated Demo (no user input)

```java
public class AutoDemo {

    public static void main(String[] args) {
        Game game = GameFactory.createStandardGame();

        // Pre-scripted moves: X wins on row 0
        int[][] moves = {
            {0, 0}, // X
            {1, 0}, // O
            {0, 1}, // X
            {1, 1}, // O
            {0, 2}, // X wins
        };

        System.out.println("=== Automated Tic-Tac-Toe Demo ===\n");
        game.getBoard().display();

        for (int[] m : moves) {
            Player current = game.getCurrentPlayer();
            System.out.println(current + " plays (" + m[0] + ", " + m[1] + ")");

            game.makeMove(m[0], m[1]);
            game.getBoard().display();

            if (game.getStatus() != GameStatus.IN_PROGRESS) {
                break;
            }
        }

        System.out.println("Final status: " + game.getStatus());
    }
}
```

**Expected Output:**

```
=== Automated Tic-Tac-Toe Demo ===

 - | - | -
-----------
 - | - | -
-----------
 - | - | -

Alice (X) plays (0, 0)
 X | - | -
-----------
 - | - | -
-----------
 - | - | -

Bob (O) plays (1, 0)
 X | - | -
-----------
 O | - | -
-----------
 - | - | -

Alice (X) plays (0, 1)
 X | X | -
-----------
 O | - | -
-----------
 - | - | -

Bob (O) plays (1, 1)
 X | X | -
-----------
 O | O | -
-----------
 - | - | -

Alice (X) plays (0, 2)
>>> Alice (X) WINS! <<<
 X | X | X
-----------
 O | O | -
-----------
 - | - | -

Final status: WIN
```

---

## Class Diagram (Text)

```
┌──────────────────────────────────────────────────────────┐
│                        Game                              │
│──────────────────────────────────────────────────────────│
│ - board: Board                                           │
│ - players: List<Player>                                  │
│ - winStrategy: WinStrategy        ◀── injected           │
│ - moveHistory: List<Move>                                │
│ - currentPlayerIndex: int                                │
│ - status: GameStatus                                     │
│──────────────────────────────────────────────────────────│
│ + makeMove(row, col): GameStatus                         │
│ + getCurrentPlayer(): Player                             │
│ + getStatus(): GameStatus                                │
│ + getBoard(): Board                                      │
│ + getMoveHistory(): List<Move>                           │
└──────────────────────────────────────────────────────────┘
         │ uses              │ uses
         ▼                   ▼
┌─────────────────┐   ┌──────────────────────────────────┐
│     Board       │   │    «interface» WinStrategy       │
│─────────────────│   │──────────────────────────────────│
│ - size: int     │   │ + checkWin(Board, Move, int):    │
│ - grid: char[][]│   │       boolean                    │
│ - filledCells   │   │ + reset(int): void               │
│─────────────────│   └──────────────┬───────────────────┘
│ + placeMove()   │                  │ implements
│ + isFull()      │                  ▼
│ + display()     │   ┌──────────────────────────────────┐
│ + getCell()     │   │     DefaultWinStrategy           │
└─────────────────┘   │──────────────────────────────────│
                      │ - rowCount: int[]                │
┌─────────────────┐   │ - colCount: int[]                │
│     Player      │   │ - diagCount: int                 │
│─────────────────│   │ - antiDiagCount: int             │
│ - name: String  │   │──────────────────────────────────│
│ - symbol: char  │   │ + checkWin(): boolean   ← O(1)  │
│ - value: int    │   │ + reset(): void                  │
└─────────────────┘   └──────────────────────────────────┘

┌─────────────────┐   ┌─────────────────┐
│      Move       │   │   GameStatus    │
│─────────────────│   │─────────────────│
│ - row: int      │   │ IN_PROGRESS     │
│ - col: int      │   │ WIN             │
│ - player: Player│   │ DRAW            │
└─────────────────┘   └─────────────────┘
```

---

## Extensions to Mention in the Interview

### 1. Undo/Redo — Command Pattern

```java
public interface GameCommand {
    void execute();
    void undo();
}

public class MakeMoveCommand implements GameCommand {
    private final Game game;
    private final int row, col;

    public MakeMoveCommand(Game game, int row, int col) {
        this.game = game;
        this.row = row;
        this.col = col;
    }

    @Override
    public void execute() { game.makeMove(row, col); }

    @Override
    public void undo() { game.undoLastMove(); }  // Board restores cell, strategy reverses counter
}
```

- Maintain a `Deque<GameCommand>` as the undo stack and a separate redo stack.
- `DefaultWinStrategy.undoMove()` would subtract the player's value from the same counters.

### 2. AI Player — Minimax Algorithm

```java
public class AIPlayer extends Player {

    public AIPlayer(String name, char symbol, int value) {
        super(name, symbol, value);
    }

    public Move computeBestMove(Board board) {
        // Minimax with alpha-beta pruning
        // For 3×3: searches all states (max 9! = 362,880 leaves)
        // Returns the move with the highest minimax score
    }
}
```

- Minimax time complexity: O(b^d) where b = branching factor, d = depth.
- Alpha-beta pruning cuts this roughly in half.
- For larger boards, use heuristic evaluation with depth limits.

### 3. Network Multiplayer

- Wrap `Game` in a REST or WebSocket service.
- Each game has a unique session ID.
- `POST /games` — create a new game.
- `POST /games/{id}/move` — make a move (validates it's that player's turn).
- `GET /games/{id}` — get current board state.
- Use `synchronized` or `ReentrantLock` on the `Game` object per session.

### 4. Tournament Mode

- `TournamentManager` runs round-robin or bracket-style matches.
- Tracks player stats (wins, losses, draws).
- Uses `GameFactory` to spin up each match.

---

## Interview-Ready Answer

> "I would design the Tic-Tac-Toe game around four core entities: `Board`, `Player`, `Move`, and `Game`. The `Board` manages an N×N `char[][]` grid with placement validation. The `Game` class orchestrates turn management and delegates win detection to a `WinStrategy` interface — this is the **Strategy Pattern** — so we can swap algorithms without touching the game logic. The default strategy uses an **O(1) win check**: I maintain `int[]` counters for each row and column plus two integers for the diagonals. Player 1 adds +1 and Player 2 adds -1 on every move. If any counter's absolute value reaches N, that player has won — no need to scan the board. This makes each move O(1) for win detection instead of O(N). For extensibility, new strategies can be plugged in by implementing `WinStrategy`. I'd use a `GameFactory` to encapsulate creation and could extend with undo/redo via the Command pattern, an AI player via Minimax with alpha-beta pruning, or network multiplayer by wrapping the `Game` in a REST API with per-session synchronization."

---

## Common Interview Follow-ups

| Question | Key Points |
|---|---|
| "How would you handle a 100×100 board?" | O(1) counter approach scales perfectly — same 4 checks regardless of board size. Space is O(N) for the counter arrays. |
| "What if we need K-in-a-row on an N×N board (K < N)?" | Counter approach no longer works directly. Use a sliding window on rows/cols/diags — O(N) per move. Implement as a new `ConnectKWinStrategy`. |
| "How do you handle >2 players?" | Counters break with >2 players (can't use ±1). Fall back to storing symbols in counters and checking all-same, or track per-player counts per row/col/diag — `int[playerCount][N]` for rows, etc. |
| "How would you add undo?" | Command pattern. Each `Move` stores enough info to reverse: restore the cell to `'-'`, subtract the player's value from the counters, decrement `filledCells`. |
| "Thread safety?" | Synchronize on the `Game` object. Moves are atomic (validate → place → check win → switch turn). Use `ConcurrentHashMap` for managing multiple game sessions. |
