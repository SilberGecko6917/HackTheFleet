import random
import string

from .models import Lobby, Player

MAX_LOBBY_PLAYERS = 2


class LobbyManager:
    def __init__(self):
        self.lobbies: dict[str, Lobby] = {}  # {lobby_id: Lobby instance}
        self.public_queue: list[Player] = []

    def generate_lobby_id(self):
        lobby_id = ''.join(random.choices(string.digits, k=6))
        while lobby_id in self.lobbies:
            lobby_id = ''.join(random.choices(string.digits, k=6))
        return lobby_id

    async def create_lobby(self, player: Player, is_public: bool = True) -> Lobby:
        lobby_id = self.generate_lobby_id()
        lobby = Lobby(id=lobby_id, isPublic=is_public)
        lobby.add_player(player.id)
        lobby.owner_id = player.id
        self.lobbies[lobby_id] = lobby
        return lobby

    async def join_lobby(self, player_id: str, lobby_id: str) -> Lobby | None:
        lobby = self.lobbies.get(lobby_id)
        if not lobby:
            return None
        if lobby.add_player(player_id):
            return lobby
        return None

    async def join_public_game(self, player: Player) -> Lobby | None:
        if not self.public_queue:
            self.public_queue.append(player)
            return None

        opponent = self.public_queue.pop(0)
        lobby = await self.create_lobby(opponent, is_public=True)
        lobby.add_player(player.id)
        return lobby

    async def leave_lobby(self, player_id: str, lobby_id: str) -> bool:
        lobby = self.lobbies.get(lobby_id)
        if not lobby:
            return False
        removed = lobby.remove_player(player_id)
        if removed and not lobby.players:
            del self.lobbies[lobby_id]
        return removed

    async def get_lobby(self, lobby_id: str) -> Lobby | None:
        return self.lobbies.get(lobby_id)

    async def get_lobbies(self) -> list[Lobby]:
        return list(self.lobbies.values())

    async def get_lobby_by_player(self, player_id: str) -> Lobby | None:
        for lobby in self.lobbies.values():
            if any(p.id == player_id for p in lobby.players):
                return lobby
        return None
