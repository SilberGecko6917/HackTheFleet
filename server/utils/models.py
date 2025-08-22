from typing import Any

from pydantic import BaseModel

BORD_X = 10
BORD_Y = 10


class LobbyPlayer(BaseModel):
    id: str
    board: list[list[str]] = [["." for _ in range(BORD_Y)] for _ in range(BORD_X)]


class Lobby(BaseModel):
    id: str
    players: list[LobbyPlayer] = []
    game_state: dict = {"state": "waiting", "winner": None, "turn": None}
    isPublic: bool = True
    maxPlayers: int = 2

    def add_player(self, player_id: str):
        if len(self.players) < self.maxPlayers:
            if any(p.id == player_id for p in self.players):
                return False
            player = LobbyPlayer(id=player_id)
            self.players.append(player)
            return True
        return None

    def remove_player(self, player_id: str) -> bool:
        for p in self.players:
            if p.id == player_id:
                self.players.remove(p)
                self.update_game_state()
                return True
        return False

    def get_board(self, player_id: str) -> list[list[str]]:
        for player in self.players:
            if player.id == player_id:
                return player.board
        return []

    def update_game_state(self):
        if len(self.players) < 2:
            self.game_state = {"state": "waiting", "winner": None, "turn": None}
        else:
            self.game_state = {"state": "playing", "winner": None, "turn": self.players[0].id}


class StartMenuOption(BaseModel):
    display_name: str
    id: str
    input: bool = False
    input_placeholder: str = None
    disabled: bool = False


class Player(BaseModel):
    id: str
    websocket: Any
