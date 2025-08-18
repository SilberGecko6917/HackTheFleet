import asyncio
import json
import os
import platform

import websockets

PLAYER_ID = ""

BASE_URI = "localhost:8000"


async def print_welcome_message():
    if platform.system() == "Windows":
        os.system("cls")
    else:
        os.system("clear")

    logo = """
.##.....##....###.....######..##....##       
.##.....##...##.##...##....##.##...##.       
.##.....##..##...##..##.......##..##..       
.#########.##.....##.##.......#####...       
.##.....##.#########.##.......##..##..       
.##.....##.##.....##.##....##.##...##.       
.##.....##.##.....##..######..##....##       
.########.##.....##.########                 
....##....##.....##.##......                 
....##....##.....##.##......                 
....##....#########.######..                 
....##....##.....##.##......                 
....##....##.....##.##......                 
....##....##.....##.########                 
.########.##.......########.########.########
.##.......##.......##.......##..........##...
.##.......##.......##.......##..........##...
.######...##.......######...######......##...
.##.......##.......##.......##..........##...
.##.......##.......##.......##..........##...
.##.......########.########.########....##...
"""

    print(logo)
    await asyncio.sleep(1)
    if platform.system() == "Windows":
        os.system("cls")
    else:
        os.system("clear")


async def run_client(player_id: str | None = None):
    uri = f"ws://{BASE_URI}/ws"
    try:
        async with websockets.connect(uri) as websocket:
            print("[INFO] CONNECTED")

            message = await websocket.recv()
            data = json.loads(message)
            print("[INFO] PLAYER_ID: " + data.get("player_id"))
            await websocket.send("Hello")
            while True:
                response = await websocket.recv()
                print(f"Response: {response}")
    except Exception as exc:
        print(f"An error occurred: {exc}")
        await asyncio.sleep(1)
        await run_client(player_id)


async def main():
    await print_welcome_message()
    await run_client()


if __name__ == '__main__':
    asyncio.run(main())
