"""
Tic-Tac-Toe — N×N board, multiple players, O(1) win check.
Strategy Pattern: WinStrategy interface for pluggable win detection.
Key insight: assign +1 / -1 per player; win when |row/col/diag sum| == N.
"""

from enum import Enum
from abc import ABC, abstractmethod
from dataclasses import dataclass


# ──────────────────────────────────────────────
#  Enums & Data Classes
# ──────────────────────────────────────────────

class GameStatus(Enum):
    IN_PROGRESS = "IN_PROGRESS"
    WIN = "WIN"
    DRAW = "DRAW"


@dataclass
class Player:
    name: str
    symbol: str
    value: int  # +1 for player 1, -1 for player 2

    def __str__(self):
        return f"{self.name}({self.symbol})"


@dataclass
class Move:
    row: int
    col: int
    player: Player


# ──────────────────────────────────────────────
#  Win Strategy Interface (Strategy Pattern)
# ──────────────────────────────────────────────

class WinStrategy(ABC):
    @abstractmethod
    def check_win(self, move: Move, board_size: int) -> bool:
        pass

    @abstractmethod
    def reset(self, board_size: int):
        pass


class DefaultWinStrategy(WinStrategy):
    """O(1) win check using running row/col/diagonal counters."""

    def __init__(self, board_size: int):
        self.reset(board_size)

    def reset(self, board_size: int):
        self._n = board_size
        self._row = [0] * board_size
        self._col = [0] * board_size
        self._diag = 0
        self._anti_diag = 0

    def check_win(self, move: Move, board_size: int) -> bool:
        r, c, v = move.row, move.col, move.player.value
        self._row[r] += v
        self._col[c] += v
        if r == c:
            self._diag += v
        if r + c == board_size - 1:
            self._anti_diag += v

        n = board_size
        return (abs(self._row[r]) == n or abs(self._col[c]) == n
                or abs(self._diag) == n or abs(self._anti_diag) == n)


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

    def is_full(self) -> bool:
        return self._filled == self.size * self.size

    def display(self):
        for i, row in enumerate(self._grid):
            print("  " + " | ".join(row))
            if i < self.size - 1:
                print("  " + "-+-".join(["-"] * self.size))
        print()


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
        self._history: list[Move] = []

    def make_move(self, row: int, col: int) -> GameStatus:
        if self._status != GameStatus.IN_PROGRESS:
            raise RuntimeError(f"Game already over: {self._status}")

        player = self._players[self._current_idx]
        move = Move(row, col, player)

        if not self._board.place_move(move):
            raise ValueError(f"Invalid move at ({row}, {col})")

        self._history.append(move)

        if self._win_strategy.check_win(move, self._board.size):
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
    players = [Player("Alice", "X", +1), Player("Bob", "O", -1)]
    strategy = DefaultWinStrategy(size)
    return Game(board, players, strategy)


# ──────────────────────────────────────────────
#  Demo
# ──────────────────────────────────────────────

if __name__ == "__main__":
    game = create_standard_game()
    print("=== Tic-Tac-Toe Demo (X wins on row 0) ===\n")
    game.board.display()

    # X wins on the top row
    moves = [(0, 0), (1, 0), (0, 1), (1, 1), (0, 2)]
    for row, col in moves:
        player = game.current_player
        print(f"  {player} plays ({row}, {col})")
        game.make_move(row, col)
        game.board.display()
        if game.status != GameStatus.IN_PROGRESS:
            break

    print(f"Final status: {game.status.value}")

    print("\n=== Custom 4x4 Game ===")
    size = 4
    board4 = Board(size)
    players4 = [Player("P1", "X", +1), Player("P2", "O", -1)]
    strategy4 = DefaultWinStrategy(size)
    game4 = Game(board4, players4, strategy4)

    # P1 fills column 0
    col_moves = [(0, 0), (0, 1), (1, 0), (1, 1), (2, 0), (2, 1), (3, 0)]
    for row, col in col_moves:
        p = game4.current_player
        game4.make_move(row, col)
        if game4.status != GameStatus.IN_PROGRESS:
            print(f"  {p} wins by filling column 0!")
            break
    game4.board.display()
