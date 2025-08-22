import asyncio
import json
import logging
import random
import string
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket

from .utils import StartMenuOption, LobbyManager
from .utils.models import Player


@asynccontextmanager
async def on_startup(_: FastAPI):
    asyncio.create_task(heartbeat_checker())
    yield


app = FastAPI(redoc_url=None, lifespan=on_startup)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("server")

lobby_manager = LobbyManager()

CURRENT_USERS = {}  # {player_id: websocket}
USER_HEARTBEATS = {}  # {player_id: last_heartbeat_timestamp}
HEARTBEAT_TIMEOUT = 10  # seconds

START_MENU_OPTIONS = [
    StartMenuOption(display_name="Join Public Game", id="join_public_game", disabled=True),
    StartMenuOption(display_name="Join Private Game", id="join_private_game", input=True,
                    input_placeholder="Enter the game ID"),
    StartMenuOption(display_name="Create Private Game", id="create_private_game"),
]


def generate_player_id():
    player_id = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    while player_id in CURRENT_USERS:
        player_id = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    return player_id


async def heartbeat_checker():
    while True:
        now = time.time()
        to_remove = []
        for player_id, last_beat in USER_HEARTBEATS.items():
            if now - last_beat > HEARTBEAT_TIMEOUT:
                logger.info(f"Player {player_id} timed out (no heartbeat).")
                to_remove.append(player_id)
        for player_id in to_remove:
            USER_HEARTBEATS.pop(player_id, None)
            ws = CURRENT_USERS.pop(player_id, None)
            if ws:
                await ws.close()
        await asyncio.sleep(HEARTBEAT_TIMEOUT // 2)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    player = Player(id=generate_player_id(), websocket=websocket)
    CURRENT_USERS[player.id] = websocket
    USER_HEARTBEATS[player.id] = time.time()

    await websocket.send_json({"player_id": player.id})

    while True:
        try:
            data = await websocket.receive_text()
            logger.info(f"Received message from {player.id}: {data}")

            if data == "heartbeat":
                USER_HEARTBEATS[player.id] = time.time()
                await websocket.send_text("heartbeat_ack")
            elif data == "MENU_start_options":
                options = [option.model_dump() for option in START_MENU_OPTIONS]
                await websocket.send_json({"options": options})
            else:
                try:
                    msg = json.loads(data)
                    if msg.get("option") == "create_private_game":
                        lobby = await lobby_manager.create_lobby(player, is_public=False)
                        lobby_data = {"players": [p.id for p in lobby.players]}
                        await websocket.send_json({
                            "lobby_id": lobby.id,
                            "state": lobby.game_state,
                            "message": "Lobby created",
                            "lobby_data": lobby_data,
                            "logs": ["Lobby created.", "Waiting for players..."]
                        })
                        logger.info(f"Created private lobby {lobby.id}")

                    elif msg.get("option") == "join_public_game":
                        lobby = await lobby_manager.join_public_game(player)
                        if not lobby:
                            await websocket.send_json({"message": "Waiting for opponent..."})
                        else:
                            await websocket.send_json({
                                "lobby_id": lobby.id,
                                "board": lobby.get_board(player.id),
                                "state": lobby.game_state,
                                "message": "Joined public game"
                            })
                            logger.info(f"Player {player.id} joined public game {lobby.id}")

                    elif msg.get("option") == "join_private_game":
                        lobby_id = msg.get("input")
                        if not lobby_id:
                            await websocket.send_json({"error": "Lobby ID is required"})
                            continue

                        lobby = await lobby_manager.get_lobby(lobby_id)
                        if not lobby:
                            await websocket.send_json({"error": "Lobby not found"})
                            continue

                        if not await lobby_manager.join_lobby(player.id, lobby_id):
                            await websocket.send_json({"error": "Failed to join lobby"})
                            continue

                        lobby_data = {"players": [p.id for p in lobby.players]}

                        await websocket.send_json({
                            "lobby_id": lobby.id,
                            "state": lobby.game_state,
                            "message": "Joined private game",
                            "lobby_data": lobby_data,
                            "logs": ["Joining Lobby..."]
                        })

                        for p in lobby.players:
                            ws = CURRENT_USERS.get(p.id)
                            if ws:
                                await ws.send_json({
                                    "lobby_id": lobby.id,
                                    "state": lobby.game_state,
                                    "message": "Lobby update",
                                    "lobby_data": lobby_data,
                                    "logs": [f"Player {player.id} joined the lobby."]
                                })

                        logger.info(f"Player {player.id} joined private game {lobby.id}")

                except Exception as exc:
                    logger.error(f"An error occurred: {exc}")

        except Exception as e:
            logger.error(f"Error with player {player.id}: {e}")
            break

    USER_HEARTBEATS.pop(player.id, None)
    CURRENT_USERS.pop(player.id, None)
    lobby = await lobby_manager.get_lobby_by_player(player.id)
    if lobby:
        await lobby_manager.leave_lobby(player.id, lobby.id)
        logger.info(f"Player {player.id} left lobby {lobby.id}.")
    else:
        logger.info(f"Player {player.id} was not in any lobby.")
    logger.info(f"Player {player.id} disconnected.")
