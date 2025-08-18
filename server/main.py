import random
import string

from fastapi import FastAPI, WebSocket, logger as _logger

app = FastAPI()

logger = _logger.logger

# {USER_ID: WEBSOCKET}
CURRENT_USERS = {}


def generate_player_id():
    player_id = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    while player_id in CURRENT_USERS:
        player_id = ''.join(random.choices(string.ascii_letters + string.digits, k=8))

    return player_id


@app.websocket("/ws")
async def ws_get_id(websocket: WebSocket):
    await websocket.accept()
    player_id = generate_player_id()

    CURRENT_USERS[player_id] = websocket

    await websocket.send_json({"player_id": player_id})
    await websocket.send_text("Welcome to the game! Your player ID is: " + player_id)
