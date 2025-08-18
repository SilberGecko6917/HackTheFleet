import asyncio
import json
import logging
import os
import platform

import ezcord
import websockets
from InquirerPy import inquirer

ezcord.set_log(log_level=logging.DEBUG)

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


async def start_menu(player_id: str, websocket):
    await websocket.send("MENU_start_options")
    data = await websocket.recv()
    options = json.loads(data)["options"]

    choice = await inquirer.select(
        message=f"HackTheFleet - Start Menu (Player ID: {player_id})",
        choices=[option["display_name"] for option in options] + ["Exit"],
        pointer=">>",
    ).execute_async()

    if choice == "Exit":
        print("Exiting the game. Goodbye!")
        await websocket.close()
        return

    selected_option = next((opt for opt in options if opt["display_name"] == choice), None)
    if selected_option:
        ezcord.log.debug(selected_option)
        if selected_option.get("input", False):
            input_value = await inquirer.text(
                message=selected_option["input_placeholder"] or "Enter your input:"
            ).execute_async()
            await websocket.send(json.dumps({"option": selected_option["id"], "input": input_value}))
        else:
            await websocket.send(json.dumps({"option": selected_option["id"]}))
    else:
        print("Invalid option selected. Please try again.")


async def send_heartbeat(websocket):
    while True:
        await websocket.send("heartbeat")
        await asyncio.sleep(5)


async def run_client(player_id: str | None = None):
    uri = f"ws://{BASE_URI}/ws"
    try:
        async with websockets.connect(uri) as websocket:
            ezcord.log.debug("CONNECTED")

            message = await websocket.recv()
            data = json.loads(message)
            player_id = data.get("player_id", player_id)
            ezcord.log.debug(f"PLAYER_ID: {player_id}")

            asyncio.create_task(send_heartbeat(websocket))

            print("\n\n")

            await start_menu(player_id, websocket)

            while True:
                response = await websocket.recv()
                if response == "heartbeat_ack":
                    return
                print(f"Response: {response}")
    except Exception as exc:
        ezcord.log.error(f"An error occurred", exc_info=exc)
        await asyncio.sleep(1)
        await run_client(player_id)


async def main():
    await print_welcome_message()
    await run_client()


if __name__ == '__main__':
    asyncio.run(main())
