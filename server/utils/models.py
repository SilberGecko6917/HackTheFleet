from dataclasses import field, dataclass
from typing import Any
import random

from pydantic import BaseModel

BORD_X = 10
BORD_Y = 10


@dataclass
class PlayerRef:
    id: str


@dataclass()
class Lobby:
    id: str
    isPublic: bool
    owner_id: str | None = None
    players: list[PlayerRef] = field(default_factory=list)
    game_state: dict = field(default_factory=lambda: {"state": "waiting", "turn": None, "winner": None})
    board_size: int = 5
    boards: dict[str, list[list[str]]] = field(default_factory=dict)
    ships_required: int = 3

    def add_player(self, player_id: str) -> bool:
        if any(p.id == player_id for p in self.players):
            return True
        if len(self.players) >= 2:
            return False
        self.players.append(PlayerRef(id=player_id))
        if not self.owner_id:
            self.owner_id = player_id
        if player_id not in self.boards:
            self.boards[player_id] = [["~"] * self.board_size for _ in range(self.board_size)]
        return True

    def remove_player(self, player_id: str) -> bool:
        before = len(self.players)
        self.players = [p for p in self.players if p.id != player_id]
        if self.owner_id == player_id:
            self.owner_id = self.players[0].id if self.players else None
        return len(self.players) != before

    def get_board(self, player_id: str) -> list[list[str]]:
        return self.boards.get(player_id, [])

    def update_game_state(self):
        if len(self.players) < 2:
            self.game_state = {"state": "waiting", "winner": None, "turn": None}
        else:
            self.game_state = {"state": "playing", "winner": None, "turn": self.players[0].id}

    def place_ships_randomly(self, player_id: str, num_ships: int | None = None):
        """Place single-cell ships marked with 'S' randomly on the player's board.

        If `num_ships` is None, place up to `self.ships_required` ships. Existing ships are not
        removed; placement only fills free '~' cells.
        """
        if num_ships is None:
            num_ships = self.ships_required
        board = self.boards.get(player_id)
        if not board:
            return
        free_cells = [(x, y) for x in range(self.board_size) for y in range(self.board_size) if board[y][x] == "~"]
        random.shuffle(free_cells)
        for i in range(min(num_ships, len(free_cells))):
            x, y = free_cells[i]
            board[y][x] = "S"

    def ships_placed(self, player_id: str) -> int:
        board = self.boards.get(player_id)
        if not board:
            return 0
        return sum(1 for row in board for cell in row if cell == "S")

    def place_ship(self, player_id: str, x: int, y: int) -> dict:
        """Place a single-cell ship at (x, y) if within bounds, not occupied, and under limit.

        Returns a dict containing either an 'error' key or 'ok': True and 'placed' count.
        """
        if x < 0 or y < 0 or x >= self.board_size or y >= self.board_size:
            return {"error": "Out of bounds"}
        board = self.boards.get(player_id)
        if board is None:
            return {"error": "Board not found"}
        if board[y][x] == "S":
            return {"error": "Already ship"}
        placed = self.ships_placed(player_id)
        if placed >= self.ships_required:
            return {"error": "Max ships placed"}
        board[y][x] = "S"
        return {"ok": True, "placed": placed + 1}

    def remove_ship(self, player_id: str, x: int, y: int) -> dict:
        if x < 0 or y < 0 or x >= self.board_size or y >= self.board_size:
            return {"error": "Out of bounds"}
        board = self.boards.get(player_id)
        if board is None:
            return {"error": "Board not found"}
        if board[y][x] != "S":
            return {"error": "No ship at position"}
        board[y][x] = "~"
        return {"ok": True, "placed": self.ships_placed(player_id)}

    def start_game(self) -> dict:
        """Start the game if both players have placed the required number of ships.

        Sets the initial turn to the first player in `self.players` and updates `self.game_state`.
        Returns a dict with 'ok': True on success or an 'error' key on failure.
        """
        if len(self.players) < 2:
            return {"error": "Not enough players"}
        for p in self.players:
            if self.ships_placed(p.id) < self.ships_required:
                return {"error": f"Player {p.id} has not placed enough ships"}
        first = self.players[0].id if self.players else None
        self.game_state = {"state": "playing", "turn": first, "winner": None}
        return {"ok": True}

    def _opponent_id(self, player_id: str) -> str | None:
        for p in self.players:
            if p.id != player_id:
                return p.id
        return None

    def shoot(self, shooter_id: str, x: int, y: int) -> dict:
        """Handle a shot from `shooter_id` at coordinates (x, y).

        Returns a dict with keys:
        - 'hit': bool
        - 'already': bool (if that cell was already shot)
        - 'winner': optional id of winner when the shot finishes the game

        This implementation switches the turn to the opponent after each shot (even on hit).
        """
        opponent_id = self._opponent_id(shooter_id)
        if not opponent_id:
            return {"error": "No opponent"}
        if self.game_state.get("turn") != shooter_id:
            return {"error": "Not your turn"}
        board = self.boards.get(opponent_id)
        if not board:
            return {"error": "Opponent board not found"}
        if x < 0 or y < 0 or x >= self.board_size or y >= self.board_size:
            return {"error": "Out of bounds"}

        cell = board[y][x]
        if cell in ("X", "O"):
            return {"hit": cell == "X", "already": True}

        hit = False
        if cell == "S":
            board[y][x] = "X"
            hit = True
        else:
            board[y][x] = "O"

        # switch turn to opponent
        self.game_state["turn"] = opponent_id

        # check whether opponent has any ships left
        opponent_board = board
        ships_left = any(cell == "S" for row in opponent_board for cell in row)
        if not ships_left:
            self.game_state["state"] = "finished"
            self.game_state["winner"] = shooter_id

        return {"hit": hit, "already": False, "winner": self.game_state.get("winner")}

    def get_opponent_view(self, player_id: str) -> list[list[str]]:
        """Return a view of the opponent's board where ships are hidden; only X and O are visible.

        If there is no opponent, return a blank board view.
        """
        opponent_id = self._opponent_id(player_id)
        if not opponent_id:
            return [["~"] * self.board_size for _ in range(self.board_size)]
        board = self.boards.get(opponent_id, [["~"] * self.board_size for _ in range(self.board_size)])
        view = [[(cell if cell in ("X", "O") else "~") for cell in row] for row in board]
        return view


class StartMenuOption(BaseModel):
    display_name: str
    id: str
    input: bool = False
    input_placeholder: str = None
    disabled: bool = False


class Player(BaseModel):
    id: str
    websocket: Any
