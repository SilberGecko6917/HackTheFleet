import asyncio
import logging
import random
import string
import time

from fastapi import FastAPI, WebSocket
from pydantic import BaseModel

app = FastAPI()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("server")

CURRENT_USERS = {}  # {player_id: websocket}
USER_HEARTBEATS = {}  # {player_id: last_heartbeat_timestamp}
HEARTBEAT_TIMEOUT = 10  # seconds


class StartMenuOption(BaseModel):
    display_name: str
    id: str
    input: bool = False
    input_placeholder: str = None


START_MENU_OPTIONS = [
    StartMenuOption(display_name="Join Public Game", id="join_public_game"),
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


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(heartbeat_checker())


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    player_id = generate_player_id()
    CURRENT_USERS[player_id] = websocket
    USER_HEARTBEATS[player_id] = time.time()

    await websocket.send_json({"player_id": player_id})

    while True:
        try:
            data = await websocket.receive_text()
            logger.info(f"Received message from {player_id}: {data}")

            if data == "heartbeat":
                USER_HEARTBEATS[player_id] = time.time()
                await websocket.send_text("heartbeat_ack")
            elif data == "MENU_start_options":
                options = [option.dict() for option in START_MENU_OPTIONS]
                await websocket.send_json({"options": options})
        except Exception as e:
            logger.error(f"Error with player {player_id}: {e}")
            break
    USER_HEARTBEATS.pop(player_id, None)
    CURRENT_USERS.pop(player_id, None)
