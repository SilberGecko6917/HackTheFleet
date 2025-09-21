import asyncio
import json
import logging
import random
import string
import time
from contextlib import asynccontextmanager

import uvicorn
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
                            "owner_id": lobby.owner_id,
                            "board": lobby.get_board(player.id),
                            "opponent_view": lobby.get_opponent_view(player.id),
                            "logs": ["Lobby created.", "[yellow]Waiting for players...[/yellow]"]
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
                                "owner_id": lobby.owner_id,
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

                        for p in lobby.players:
                            ws = CURRENT_USERS.get(p.id)
                            if ws:
                                await ws.send_json({
                                    "lobby_id": lobby.id,
                                    "state": lobby.game_state,
                                    "message": ("Joined private game" if p.id == player.id else "Lobby update"),
                                    "owner_id": lobby.owner_id,
                                    "lobby_data": lobby_data,
                                    "board": lobby.get_board(p.id),
                                    "opponent_view": lobby.get_opponent_view(p.id),
                                    "logs": [f"Player {player.id} joined the lobby."]
                                })

                        logger.info(f"Player {player.id} joined private game {lobby.id}")

                    elif msg.get("action") == "start_game":
                        lobby = await lobby_manager.get_lobby_by_player(player.id)
                        if not lobby:
                            await websocket.send_json({"type": "log", "message": "[red]No lobby found.[/red]"})
                            continue
                        if lobby.owner_id != player.id:
                            await websocket.send_json(
                                {"type": "log", "message": "[red]Only the owner can start the game.[/red]"})
                        if len(lobby.players) < 2:
                            await websocket.send_json({"type": "log",
                                                       "message": "[red]At least 2 players are required to start the game.[/red]"})
                            continue
                        if lobby.game_state.get("state") != "waiting":
                            await websocket.send_json(
                                {"type": "log", "message": "[red]Game has already started.[/red]"})
                            continue

                        for n in range(3, 0, -1):
                            for p in lobby.players:
                                ws = CURRENT_USERS.get(p.id)
                                if ws:
                                    await ws.send_json(
                                        {"type": "log", "message": f"[green]Placement starting in {n}...[/green]"})
                            await asyncio.sleep(1)

                        placement_time = 45
                        lobby.game_state = {"state": "placing", "turn": None, "winner": None}
                        for p in lobby.players:
                            ws = CURRENT_USERS.get(p.id)
                            if ws:
                                await ws.send_json({
                                    "type": "placing",
                                    "lobby_id": lobby.id,
                                    "board": lobby.get_board(p.id),
                                    "opponent_view": lobby.get_opponent_view(p.id),
                                    "you": p.id,
                                    "owner_id": lobby.owner_id,
                                    "placement_time": placement_time,
                                    "state": lobby.game_state,
                                    "logs": ["Placement phase started. Place your ships!  \n[gray](Controls: WASD or arrows to move, P or Enter to place, R to remove)[/gray]"]
                                })

                        async def finalize_placement(lobby_id: str, delay: int):
                            await asyncio.sleep(delay)
                            lobby = await lobby_manager.get_lobby(lobby_id)
                            if not lobby:
                                return
                            if lobby.game_state.get("state") != "placing":
                                return

                            for p in lobby.players:
                                placed = lobby.ships_placed(p.id)
                                if placed < lobby.ships_required:
                                    lobby.place_ships_randomly(p.id, lobby.ships_required - placed)

                            lobby.start_game()

                            for p in lobby.players:
                                ws = CURRENT_USERS.get(p.id)
                                if ws:
                                    await ws.send_json({
                                        "type": "start",
                                        "lobby_id": lobby.id,
                                        "board": lobby.get_board(p.id),
                                        "opponent_view": lobby.get_opponent_view(p.id),
                                        "you": p.id,
                                        "owner_id": lobby.owner_id,
                                        "state": lobby.game_state,
                                        "logs": ["Game started!"]
                                    })

                        asyncio.create_task(finalize_placement(lobby.id, placement_time))

                    elif msg.get("action") == "place_ship":
                        lobby = await lobby_manager.get_lobby_by_player(player.id)
                        if not lobby:
                            await websocket.send_json({"type": "log", "message": "[red]No lobby found.[/red]"})
                            continue
                        x = msg.get("x")
                        y = msg.get("y")
                        try:
                            x = int(x)
                            y = int(y)
                        except Exception:
                            await websocket.send_json({"type": "log", "message": "[red]Invalid coordinates.[/red]"})
                            continue

                        result = lobby.place_ship(player.id, x, y)
                        if result.get("error"):
                            await websocket.send_json({"type": "log", "message": f"[red]{result['error']}[/red]"})
                            continue

                        lobby_data = {"players": [p.id for p in lobby.players]}
                        for p in lobby.players:
                            ws = CURRENT_USERS.get(p.id)
                            if ws:
                                await ws.send_json({
                                    "lobby_id": lobby.id,
                                    "state": lobby.game_state,
                                    "message": "Lobby update",
                                    "owner_id": lobby.owner_id,
                                    "lobby_data": lobby_data,
                                    "board": lobby.get_board(p.id),
                                    "opponent_view": lobby.get_opponent_view(p.id),
                                    "logs": [f"Player {player.id} placed ship ({result.get('placed')}/{lobby.ships_required})"]
                                })

                    elif msg.get("action") == "remove_ship":
                        lobby = await lobby_manager.get_lobby_by_player(player.id)
                        if not lobby:
                            await websocket.send_json({"type": "log", "message": "[red]No lobby found.[/red]"})
                            continue
                        x = msg.get("x")
                        y = msg.get("y")
                        try:
                            x = int(x)
                            y = int(y)
                        except Exception:
                            await websocket.send_json({"type": "log", "message": "[red]Invalid coordinates.[/red]"})
                            continue

                        result = lobby.remove_ship(player.id, x, y)
                        if result.get("error"):
                            await websocket.send_json({"type": "log", "message": f"[red]{result['error']}[/red]"})
                            continue

                        lobby_data = {"players": [p.id for p in lobby.players]}
                        for p in lobby.players:
                            ws = CURRENT_USERS.get(p.id)
                            if ws:
                                await ws.send_json({
                                    "lobby_id": lobby.id,
                                    "state": lobby.game_state,
                                    "message": "Lobby update",
                                    "owner_id": lobby.owner_id,
                                    "lobby_data": lobby_data,
                                    "board": lobby.get_board(p.id),
                                    "opponent_view": lobby.get_opponent_view(p.id),
                                    "logs": [f"Player {player.id} removed a ship ({result.get('placed')}/{lobby.ships_required})"]
                                })

                    elif msg.get("action") == "shoot":
                        lobby = await lobby_manager.get_lobby_by_player(player.id)
                        if not lobby:
                            await websocket.send_json({"type": "log", "message": "[red]No lobby found.[/red]"})
                            continue
                        x = msg.get("x")
                        y = msg.get("y")
                        try:
                            x = int(x)
                            y = int(y)
                        except Exception:
                            await websocket.send_json({"type": "log", "message": "[red]Invalid coordinates.[/red]"})
                            continue

                        result = lobby.shoot(player.id, x, y)
                        if result.get("error"):
                            await websocket.send_json({"type": "log", "message": f"[red]{result['error']}[/red]"})
                            continue

                        for p in lobby.players:
                            ws = CURRENT_USERS.get(p.id)
                            if not ws:
                                continue
                            await ws.send_json({
                                "type": "update",
                                "lobby_id": lobby.id,
                                "board": lobby.get_board(p.id),
                                "opponent_view": lobby.get_opponent_view(p.id),
                                "you": p.id,
                                "state": lobby.game_state,
                                "logs": [f"Player {player.id} shot at ({x},{y}) - {'hit' if result.get('hit') else 'miss'}"]
                            })

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

        lobby_data = {"players": [p.id for p in lobby.players]}
        for p in lobby.players:
            ws = CURRENT_USERS.get(p.id)
            if ws:
                await ws.send_json({
                    "lobby_id": lobby.id,
                    "state": lobby.game_state,
                    "message": "player_left",
                    "owner_id": lobby.owner_id,
                    "lobby_data": lobby_data,
                    "logs": [f"Player {player.id} has left the lobby."]
                })
    else:
        logger.info(f"Player {player.id} was not in any lobby.")
    logger.info(f"Player {player.id} disconnected.")

if __name__ == '__main__':
    uvicorn.run(app, host="0.0.0.0", port=8000)
