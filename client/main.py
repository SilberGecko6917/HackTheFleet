import asyncio
import json
import logging
import os
import platform

import ezcord
import websockets
from InquirerPy import inquirer
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

ezcord.set_log(log_level=logging.DEBUG)

BASE_URI = "localhost:8000"

console = Console()


def clear_console():
    if platform.system() == "Windows":
        os.system("cls")
    else:
        os.system("clear")


async def print_welcome_message():
    clear_console()

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
    clear_console()


async def start_menu(player_id: str, websocket):
    while True:
        clear_console()
        await websocket.send("MENU_start_options")
        data = await websocket.recv()
        if not data.strip():
            print("No data received from server. Retrying...")
            continue

        try:
            options = json.loads(data)["options"]
        except json.JSONDecodeError:
            print(f"Received invalid data: {data}")
            continue

        choice = await inquirer.select(
            message=f"HackTheFleet - Start Menu (Player ID: {player_id})",
            choices=[option["display_name"] for option in options] + ["Exit"],
        ).execute_async()

        if choice == "Exit":
            print("Exiting the game. Goodbye!")
            await websocket.close()
            return

        selected_option = next((opt for opt in options if opt["display_name"] == choice), None)
        if selected_option:
            if selected_option["disabled"]:
                print("This option is currently disabled. Please try again later.")
                await asyncio.sleep(2)
                continue
            if selected_option.get("input", False):
                input_value = await inquirer.text(
                    message=selected_option["input_placeholder"] or "Enter your input:"
                ).execute_async()
                await websocket.send(json.dumps({"option": selected_option["id"], "input": input_value}))
            else:
                await websocket.send(json.dumps({"option": selected_option["id"]}))
            break
        else:
            print("Invalid option selected. Please try again.")


def make_private_lobby_screen(lobby_id: str, players: list[str], logs: list[str]):
    clear_console()

    layout = Layout()

    info_panel = Panel(
        f"[bold cyan]Lobby ID:[/bold cyan] {lobby_id}\n"
        f"[bold cyan]Players:[/bold cyan] {len(players)}/2\n"
        f"[bold yellow]Status:[/bold yellow] {'Waiting' if len(players) < 2 else 'Ready'}\n",
        title="Game Info",
        border_style="blue"
    )
    layout.split_column(Layout(info_panel, name="info", size=6), Layout(name="console"))

    log_table = Table.grid()
    for log in logs[-10:]:
        log_table.add_row(f"[white]{log}")
    layout["console"].update(Panel(log_table, title="Lobby Console", border_style="magenta"))

    return layout


async def render_private_lobby(lobby_id: str, websocket, players: list[str], logs: list[str]):
    with Live(make_private_lobby_screen(lobby_id, players, logs), refresh_per_second=4, console=console) as live:
        while True:
            data = await websocket.recv()

            try:
                event = json.loads(data)
            except Exception:
                if "heartbeat" in data:
                    continue
                logs.append(f"Received invalid message: {data}")
                live.update(make_private_lobby_screen(lobby_id, players, logs))
                continue

            print(event)

            if "lobby_data" in event:
                lobby_id = event["lobby_id"]
                players = event["lobby_data"]["players"]
                logs.extend(event["logs"])
                live.update(make_private_lobby_screen(lobby_id, players, logs))

            elif event.get("type") == "start":
                logs.append("Game starting...")
                live.update(make_private_lobby_screen(lobby_id, players, logs))
                await asyncio.sleep(2)
                break

            elif event.get("type") == "log":
                logs.append(event["message"])
                live.update(make_private_lobby_screen(lobby_id, players, logs))

            else:
                live.update(make_private_lobby_screen(lobby_id, players, logs))


async def send_heartbeat(websocket):
    while True:
        await websocket.send("heartbeat")
        await asyncio.sleep(5)


async def run_client(player_id: str | None = None):
    uri = f"ws://{BASE_URI}/ws"
    try:
        async with websockets.connect(uri) as websocket:
            message = await websocket.recv()
            data = json.loads(message)
            player_id = data.get("player_id", player_id)

            asyncio.create_task(send_heartbeat(websocket))

            print("\n")

            await start_menu(player_id, websocket)

            try:
                while True:
                    response = await websocket.recv()
                    if response == "heartbeat_ack":
                        continue
                    try:
                        data = json.loads(response)

                        if data.get("message") == "Lobby created":
                            lobby_id = data["lobby_id"]
                            players = data["lobby_data"]["players"]
                            logs = data.get("logs", ["Lobby created."])
                            await render_private_lobby(lobby_id, websocket, players, logs)

                        elif data.get("message") == "Joined private game":
                            lobby_id = data["lobby_id"]
                            players = data["lobby_data"]["players"]
                            logs = data["logs"]
                            await render_private_lobby(lobby_id, websocket, players, logs)

                        else:
                            print(f"Response: {response}")
                    except Exception as e:
                        raise e
            except websockets.ConnectionClosedOK:
                ezcord.log.info("Connection closed gracefully.")
    except Exception as exc:
        ezcord.log.error(f"An error occurred", exc_info=exc)
        await asyncio.sleep(1)
        await run_client(player_id)


async def main():
    await print_welcome_message()
    await run_client()


if __name__ == '__main__':
    asyncio.run(main())
