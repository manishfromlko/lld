"""
Tic-Tac-Toe — Simple version (interview-friendly)
- Strategy Pattern: WinStrategy — pluggable win detection
- Win check: straightforward board scan (O(N) per move, easy to read)
- No +1/-1 counter trick — just check rows, cols, and diagonals directly
"""

from abc import ABC, abstractmethod
from enum import Enum


# ──────────────────────────────────────────────
#  Enums & Classes
# ──────────────────────────────────────────────

class GameStatus(Enum):
    IN_PROGRESS = "IN_PROGRESS"
    WIN         = "WIN"
    DRAW        = "DRAW"


class Player:
    def __init__(self, name: str, symbol: str):
        self.name = name
        self.symbol = symbol

    def __str__(self):
        return f"{self.name}({self.symbol})"


class Move:
    def __init__(self, row: int, col: int, player: Player):
        self.row = row
        self.col = col
        self.player = player


# ──────────────────────────────────────────────
#  Board
# ──────────────────────────────────────────────

class Board:
    def __init__(self, size: int):
        self.size = size
        self._grid = [['.' for _ in range(size)] for _ in range(size)]
        self._filled = 0

    def place_move(self, move: Move) -> bool:
        r, c = move.row, move.col
        if not (0 <= r < self.size and 0 <= c < self.size):
            return False
        if self._grid[r][c] != '.':
            return False
        self._grid[r][c] = move.player.symbol
        self._filled += 1
        return True

    def get(self, row: int, col: int) -> str:
        return self._grid[row][col]

    def is_full(self) -> bool:
        return self._filled == self.size * self.size

    def display(self):
        for i, row in enumerate(self._grid):
            print("  " + " | ".join(row))
            if i < self.size - 1:
                print("  " + "-+-".join(["-"] * self.size))
        print()


# ──────────────────────────────────────────────
#  Win Strategy (Strategy Pattern)
# ──────────────────────────────────────────────

class WinStrategy(ABC):
    @abstractmethod
    def check_win(self, board: Board, move: Move) -> bool:
        pass


class BoardScanWinStrategy(WinStrategy):
    """
    Simple board scan: after each move, check only the row, column,
    and diagonals that the last move touched.
    O(N) per move — easy to read and explain.
    """

    def check_win(self, board: Board, move: Move) -> bool:
        r, c, sym = move.row, move.col, move.player.symbol
        n = board.size

        # Check the row that was just played
        if all(board.get(r, col) == sym for col in range(n)):
            return True

        # Check the column that was just played
        if all(board.get(row, c) == sym for row in range(n)):
            return True

        # Check main diagonal (only if move is on it)
        if r == c:
            if all(board.get(i, i) == sym for i in range(n)):
                return True

        # Check anti-diagonal (only if move is on it)
        if r + c == n - 1:
            if all(board.get(i, n - 1 - i) == sym for i in range(n)):
                return True

        return False


# ──────────────────────────────────────────────
#  Game
# ──────────────────────────────────────────────

class Game:
    def __init__(self, board: Board, players: list[Player], win_strategy: WinStrategy):
        self._board = board
        self._players = players
        self._win_strategy = win_strategy
        self._current_idx = 0
        self._status = GameStatus.IN_PROGRESS

    def make_move(self, row: int, col: int) -> GameStatus:
        if self._status != GameStatus.IN_PROGRESS:
            raise RuntimeError(f"Game already over: {self._status.value}")

        player = self._players[self._current_idx]
        move = Move(row, col, player)

        if not self._board.place_move(move):
            raise ValueError(f"Invalid move at ({row}, {col})")

        if self._win_strategy.check_win(self._board, move):
            self._status = GameStatus.WIN
            print(f"  >>> {player} WINS! <<<")
        elif self._board.is_full():
            self._status = GameStatus.DRAW
            print("  >>> DRAW <<<")
        else:
            self._current_idx = (self._current_idx + 1) % len(self._players)

        return self._status

    @property
    def current_player(self) -> Player:
        return self._players[self._current_idx]

    @property
    def status(self) -> GameStatus:
        return self._status

    @property
    def board(self) -> Board:
        return self._board


# ──────────────────────────────────────────────
#  Factory
# ──────────────────────────────────────────────

def create_standard_game() -> Game:
    size = 3
    board = Board(size)
    players = [Player("Alice", "X"), Player("Bob", "O")]
    strategy = BoardScanWinStrategy()
    return Game(board, players, strategy)


# ──────────────────────────────────────────────
#  Demo
# ──────────────────────────────────────────────

if __name__ == "__main__":
    game = create_standard_game()
    print("=== Tic-Tac-Toe Demo (X wins on row 0) ===\n")
    game.board.display()

    moves = [(0, 0), (1, 0), (0, 1), (1, 1), (0, 2)]
    for row, col in moves:
        player = game.current_player
        print(f"  {player} plays ({row}, {col})")
        game.make_move(row, col)
        game.board.display()
        if game.status != GameStatus.IN_PROGRESS:
            break

    print(f"Final status: {game.status.value}")

    print("\n=== Draw demo ===\n")
    game2 = create_standard_game()
    # Board fills up with no winner
    #  X O X
    #  X X O
    #  O X O  — no full row/col/diag for either player
    draw_moves = [(0, 0), (0, 1), (0, 2), (1, 2), (1, 0), (2, 0), (1, 1), (2, 2), (2, 1)]
    for row, col in draw_moves:
        player = game2.current_player
        print(f"  {player} plays ({row}, {col})")
        game2.make_move(row, col)
        game2.board.display()
        if game2.status != GameStatus.IN_PROGRESS:
            break
