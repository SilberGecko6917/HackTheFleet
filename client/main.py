import asyncio
import json
import logging
import os
import platform
import threading
import sys

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


def format_board(board: list[list[str]]) -> str:
    lines = []
    for row in board:
        lines.append(" ".join(row))
    return "\n".join(lines)


def format_board_with_cursor(board: list[list[str]] | None, cursor_x: int, cursor_y: int) -> str:
    board = board or []
    lines = []
    for y, row in enumerate(board):
        cells = []
        for x, cell in enumerate(row):
            if x == cursor_x and y == cursor_y:
                cells.append(f"[reverse]{cell}[/reverse]")
            else:
                cells.append(cell)
        lines.append(" ".join(cells))
    return "\n".join(lines)


def make_private_lobby_screen(lobby_id: str, players: list[str], logs: list[str], owner_id: str, me: str,
                              game_started: bool = False, placing_phase: bool = False,
                              placement_time_left: int | None = None,
                              board: list[list[str]] | None = None,
                              opponent_view: list[list[str]] | None = None,
                              cursor_x: int = 0, cursor_y: int = 0,
                              game_state: dict | None = None):
    """Render the lobby UI using rich Layouts.

    Notes:
    - Rich.Live performs incremental updates; avoid clearing the console each render (that causes flicker).
    - `placement_time_left` is the remaining seconds for the placement phase. The client
      uses the value provided by the server when available, and falls back to 45 seconds when
      the placement is triggered locally by the owner.
    """
    layout = Layout()

    log_table = Table.grid()
    max_logs = 8 if game_started else 12
    for log in logs[-max_logs:]:
        log_table.add_row(f"[white]{log}")

    turn_line = ""
    if game_state and isinstance(game_state, dict):
        turn_id = game_state.get("turn")
        if turn_id:
            turn_line = f"[bold cyan]Turn:[/bold cyan] {'You' if turn_id == me else turn_id}\n"

    if not game_started and not placing_phase:
        info_panel = Panel(
            f"[bold cyan]Lobby ID:[/bold cyan] {lobby_id}\n"
            f"[bold cyan]Owner:[/bold cyan] {owner_id}\n"
            f"[bold cyan]Players:[/bold cyan] {len(players)}/2\n"
            f"[bold yellow]Status:[/bold yellow] {'Waiting' if len(players) < 2 else 'Ready'}\n"
            f"{turn_line}"
            f"[green]{'Owner: press S to start when ready' if me == owner_id and len(players) == 2 else ''}[/green]",
            title="Lobby Info",
            border_style="blue"
        )
        layout.split_row(
            Layout(info_panel, name="left", size=40),
            Layout(Panel(log_table, title="Console", border_style="magenta"), name="right")
        )
    elif placing_phase:
        board_text = format_board_with_cursor(board or [], cursor_x, cursor_y)
        timer_text = f"Placement time left: {placement_time_left}s" if placement_time_left is not None else ""
        info_panel = Panel(
            f"[bold cyan]Lobby ID:[/bold cyan] {lobby_id}\n"
            f"[bold cyan]Owner:[/bold cyan] {owner_id}\n"
            f"[bold cyan]Players:[/bold cyan] {len(players)}/2\n"
            f"{turn_line}"
            f"[bold cyan]Cursor:[/bold cyan] ({cursor_x},{cursor_y})\n"
            f"[bold yellow]{timer_text}[/bold yellow]\n"
            f"[green]Controls: WASD or arrows to move, P or Enter to place, R to remove, S to start (owner)[/green]",
            title="Placement",
            border_style="blue"
        )
        board_panel = Panel(
            f"[bold cyan]Your Board (place ships):[/bold cyan]\n\n{board_text}",
            title="Your Board",
            border_style="green"
        )
        layout.split_row(
            Layout(board_panel, name="left", size=50),
            Layout(name="right")
        )
        layout["right"].split_column(
            Layout(info_panel, name="info", size=4),
            Layout(Panel(log_table, title="Console", border_style="magenta"), name="console")
        )
    else:
        board_text = format_board(board or [])
        opponent_text = format_board_with_cursor(opponent_view or [], cursor_x, cursor_y)
        game_panel = Panel(
            f"[bold cyan]You:[/bold cyan] {me}\n"
            f"[bold cyan]Owner:[/bold cyan] {owner_id}\n"
            f"{turn_line}\n"
            f"{board_text}",
            title="Your Board",
            border_style="green"
        )
        opponent_panel = Panel(
            f"[bold cyan]Opponent View (select with WASD or arrows, Enter to shoot):[/bold cyan]\n\n{opponent_text}",
            title="Opponent",
            border_style="red"
        )
        layout.split_row(
            Layout(name="left", size=40),
            Layout(opponent_panel, name="right")
        )
        layout["left"].split_column(
            Layout(game_panel, name="game", size=12),
            Layout(Panel(log_table, title="Console", border_style="magenta"), name="console")
        )

    return layout


async def render_private_lobby(lobby_id: str, websocket, players: list[str], logs: list[str],
                                owner_id: str | None = None, me: str | None = None,
                                initial_board: list[list[str]] | None = None,
                                initial_opponent_view: list[list[str]] | None = None):
    game_started = False
    current_board = initial_board
    opponent_view = initial_opponent_view
    placing_phase = False
    placement_time_left: int | None = None
    cursor_x = 0
    cursor_y = 0
    game_state: dict | None = None
    loop = asyncio.get_event_loop()  # capture the running event loop so background threads can schedule coroutines

    # single-key reader (cross-platform) - choose implementation depending on platform
    if platform.system() == "Windows":
        import msvcrt

        def _get_key():
            ch = msvcrt.getwch()
            if ch in ('\x00', '\xe0'):
                ch2 = msvcrt.getwch()
                return ('ARROW', ch2)
            return ("CHAR", ch)
    else:
        import tty
        import termios

        fd = sys.stdin.fileno()

        def _get_key():
            old = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                ch = sys.stdin.read(1)
                if ch == '\x1b':
                    seq = sys.stdin.read(2)
                    return ('ARROW', seq)
                return ("CHAR", ch)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)

    def start_key_listener(live):
        def run():
            nonlocal cursor_x, cursor_y, game_started, placing_phase, placement_time_left, current_board, opponent_view, game_state

            while running:
                kind, key = _get_key()
                if kind == 'ARROW':

                    direction = None
                    try:
                        if isinstance(key, str):
                            if key in ('H', '[A'):
                                direction = 'UP'
                            elif key in ('P', '[B'):
                                direction = 'DOWN'
                            elif key in ('K', '[D'):
                                direction = 'LEFT'
                            elif key in ('M', '[C'):
                                direction = 'RIGHT'
                    except Exception:
                        direction = None

                    if direction == 'LEFT':
                        cursor_x = max(0, cursor_x - 1)
                    elif direction == 'RIGHT':
                        if placing_phase or not game_started:
                            max_x = (len(current_board[0]) - 1) if current_board else 4
                        else:
                            max_x = (len(opponent_view[0]) - 1) if opponent_view else 4
                        cursor_x = min(max_x, cursor_x + 1)
                    elif direction == 'UP':
                        cursor_y = max(0, cursor_y - 1)
                    elif direction == 'DOWN':
                        if placing_phase or not game_started:
                            max_y = (len(current_board) - 1) if current_board else 4
                        else:
                            max_y = (len(opponent_view) - 1) if opponent_view else 4
                        cursor_y = min(max_y, cursor_y + 1)

                    try:
                        live.update(make_private_lobby_screen(lobby_id, players, logs, owner_id, me, game_started,
                                                              placing_phase, placement_time_left,
                                                              current_board, opponent_view, cursor_x, cursor_y, game_state))
                    except Exception:
                        pass
                    continue

                ch = key
                if isinstance(ch, str) and ch.lower() == 's' and me == owner_id and not game_started and len(players) == 2 and not placing_phase:
                    asyncio.run_coroutine_threadsafe(websocket.send(json.dumps({"action": "start_game"})),
                                                     loop)
                    logs.append("[green]Placement phase started (local)[/green]")
                    placing_phase = True
                    placement_time_left = 45
                    if current_board is None:
                        current_board = [["~"] * 5 for _ in range(5)]
                    try:
                        live.update(make_private_lobby_screen(lobby_id, players, logs, owner_id, me, game_started,
                                                              placing_phase, placement_time_left,
                                                              current_board, opponent_view, cursor_x, cursor_y, game_state))
                    except Exception:
                        pass
                    continue

                lk = ch.lower() if isinstance(ch, str) else ch
                if lk in ('w', 'a', 's', 'd'):
                    if lk == 'a':
                        cursor_x = max(0, cursor_x - 1)
                    elif lk == 'd':
                        if placing_phase or not game_started:
                            max_x = (len(current_board[0]) - 1) if current_board else 4
                        else:
                            max_x = (len(opponent_view[0]) - 1) if opponent_view else 4
                        cursor_x = min(max_x, cursor_x + 1)
                    elif lk == 'w':
                        cursor_y = max(0, cursor_y - 1)
                    elif lk == 's':
                        if placing_phase or not game_started:
                            max_y = (len(current_board) - 1) if current_board else 4
                        else:
                            max_y = (len(opponent_view) - 1) if opponent_view else 4
                        cursor_y = min(max_y, cursor_y + 1)
                    try:
                        live.update(make_private_lobby_screen(lobby_id, players, logs, owner_id, me, game_started,
                                                              placing_phase, placement_time_left,
                                                              current_board, opponent_view, cursor_x, cursor_y, game_state))
                    except Exception:
                        pass
                    continue

                ch = key
                try:
                    is_enter = ch in ('\r', '\n')
                except Exception:
                    is_enter = False

                if is_enter:
                    if not game_started or placing_phase:
                        asyncio.run_coroutine_threadsafe(
                            websocket.send(json.dumps({"action": "place_ship", "x": cursor_x, "y": cursor_y})),
                            loop
                        )
                        logs.append(f"Sent place_ship at ({cursor_x},{cursor_y})")
                        try:
                            live.update(make_private_lobby_screen(lobby_id, players, logs, owner_id, me, game_started,
                                                                  placing_phase, placement_time_left,
                                                                  current_board, opponent_view, cursor_x, cursor_y))
                        except Exception:
                            pass
                    else:
                        asyncio.run_coroutine_threadsafe(
                            websocket.send(json.dumps({"action": "shoot", "x": cursor_x, "y": cursor_y})),
                            loop
                        )
                        logs.append(f"Sent shoot at ({cursor_x},{cursor_y})")
                        try:
                            live.update(make_private_lobby_screen(lobby_id, players, logs, owner_id, me, game_started,
                                                                  placing_phase, placement_time_left,
                                                                  current_board, opponent_view, cursor_x, cursor_y))
                        except Exception:
                            pass
                else:
                    if isinstance(ch, str):
                        lk = ch.lower()
                        if lk == 's' and me == owner_id and not game_started and len(players) == 2:
                            asyncio.run_coroutine_threadsafe(websocket.send(json.dumps({"action": "start_game"})),
                                                             loop)
                            logs.append("Sent start_game")
                            try:
                                live.update(make_private_lobby_screen(lobby_id, players, logs, owner_id, me, game_started,
                                                                      placing_phase, placement_time_left,
                                                                      current_board, opponent_view, cursor_x, cursor_y))
                            except Exception:
                                pass
                        elif lk == 'p' and (not game_started or placing_phase):
                            asyncio.run_coroutine_threadsafe(
                                websocket.send(json.dumps({"action": "place_ship", "x": cursor_x, "y": cursor_y})),
                                loop
                            )
                            logs.append(f"Sent place_ship at ({cursor_x},{cursor_y})")
                            try:
                                live.update(make_private_lobby_screen(lobby_id, players, logs, owner_id, me, game_started,
                                                                      placing_phase, placement_time_left,
                                                                      current_board, opponent_view, cursor_x, cursor_y))
                            except Exception:
                                pass
                        elif lk == 'r' and (not game_started or placing_phase):
                            asyncio.run_coroutine_threadsafe(
                                websocket.send(json.dumps({"action": "remove_ship", "x": cursor_x, "y": cursor_y})),
                                loop
                            )
                            logs.append(f"Sent remove_ship at ({cursor_x},{cursor_y})")
                            try:
                                live.update(make_private_lobby_screen(lobby_id, players, logs, owner_id, me, game_started,
                                                                      placing_phase, placement_time_left,
                                                                      current_board, opponent_view, cursor_x, cursor_y))
                            except Exception:
                                pass

        t = threading.Thread(target=run, daemon=True)
        t.start()

    with Live(make_private_lobby_screen(lobby_id, players, logs, owner_id, me, game_started,
                                       placing_phase, placement_time_left,
                                       current_board, opponent_view, cursor_x, cursor_y),
              refresh_per_second=4, console=console) as live:
        running = True

        def stop_running():
            nonlocal running
            running = False

        start_key_listener(live)

        while True:
            try:
                data = await websocket.recv()
            except websockets.ConnectionClosedOK:
                break

            try:
                event = json.loads(data)
            except Exception:
                if "heartbeat" in data:
                    continue
                logs.append(f"Received invalid message: {data}")
                live.update(
                    make_private_lobby_screen(lobby_id, players, logs, owner_id, me, game_started, placing_phase,
                                              placement_time_left, current_board, opponent_view, cursor_x, cursor_y, game_state))
                continue

            if isinstance(event, dict) and "state" in event:
                game_state = event.get("state")

            if "lobby_data" in event:
                lobby_id = event["lobby_id"]
                players = event["lobby_data"]["players"]
                owner_id = event.get("owner_id", owner_id)
                if "board" in event:
                    current_board = event.get("board")
                if "opponent_view" in event:
                    opponent_view = event.get("opponent_view")
                logs.extend(event.get("logs", []))
                live.update(
                    make_private_lobby_screen(lobby_id, players, logs, owner_id, me, game_started, placing_phase,
                                              placement_time_left, current_board, opponent_view, cursor_x, cursor_y, game_state))

            elif event.get("type") == "placing":
                placing_phase = True
                placement_time_left = int(event.get("placement_time", 45))
                current_board = event.get("board")
                opponent_view = event.get("opponent_view")
                owner_id = event.get("owner_id", owner_id)
                game_state = event.get("state", game_state)
                logs.extend(event.get("logs", []))

                async def placement_countdown():
                    nonlocal placement_time_left, placing_phase
                    while placement_time_left is not None and placement_time_left > 0 and placing_phase:
                        await asyncio.sleep(1)
                        placement_time_left -= 1
                        try:
                            live.update(make_private_lobby_screen(lobby_id, players, logs, owner_id, me,
                                                                  game_started, placing_phase, placement_time_left,
                                                                  current_board, opponent_view, cursor_x, cursor_y))
                        except Exception:
                            pass

                asyncio.create_task(placement_countdown())
                live.update(
                    make_private_lobby_screen(lobby_id, players, logs, owner_id, me, game_started, placing_phase,
                                              placement_time_left, current_board, opponent_view, cursor_x, cursor_y, game_state))

            elif event.get("type") == "start":
                placing_phase = False
                game_started = True
                current_board = event.get("board")
                opponent_view = event.get("opponent_view")
                owner_id = event.get("owner_id", owner_id)
                game_state = event.get("state", game_state)
                logs.append("Game started!")
                live.update(
                    make_private_lobby_screen(lobby_id, players, logs, owner_id, me, game_started, placing_phase,
                                              placement_time_left, current_board, opponent_view, cursor_x, cursor_y, game_state))

            elif event.get("type") == "update":
                current_board = event.get("board")
                opponent_view = event.get("opponent_view")
                game_state = event.get("state", game_state)
                live.update(
                    make_private_lobby_screen(lobby_id, players, logs, owner_id, me, game_started, placing_phase,
                                              placement_time_left, current_board, opponent_view, cursor_x, cursor_y, game_state))

            elif event.get("type") == "log":
                logs.append(event["message"])
                if "state" in event:
                    game_state = event.get("state")
                live.update(
                    make_private_lobby_screen(lobby_id, players, logs, owner_id, me, game_started, placing_phase,
                                              placement_time_left, current_board, opponent_view, cursor_x, cursor_y, game_state))

            else:
                logs.append(f"Received unknown event: {event}")
                live.update(
                    make_private_lobby_screen(lobby_id, players, logs, owner_id, me, game_started, placing_phase,
                                              placement_time_left, current_board, opponent_view, cursor_x, cursor_y, game_state))

            if game_state and isinstance(game_state, dict) and game_state.get("state") == "finished":
                winner = game_state.get("winner")
                won = (winner == me)
                result_title = "You Win!" if won else "You Lose!"
                result_color = "green" if won else "red"
                board_text = format_board(current_board or [])
                opponent_text = format_board(opponent_view or [])
                result_panel = Panel(
                    f"[bold {result_color}]{result_title}[/bold {result_color}]\n\n"
                    f"Winner: {winner}\n\n"
                    f"[bold cyan]Your Board:[/bold cyan]\n{board_text}\n\n"
                    f"[bold cyan]Opponent View:[/bold cyan]\n{opponent_text}",
                    title="Game Over",
                    border_style=result_color
                )
                live.update(Layout(result_panel))

                console.print("Press any key to return to menu...")
                try:
                    _ = _get_key()
                except Exception:
                    pass
                return


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
                            await render_private_lobby(
                                data["lobby_id"], websocket,
                                data["lobby_data"]["players"],
                                data.get("logs", []),
                                owner_id=data.get("owner_id"),
                                me=player_id,
                                initial_board=data.get("board"),
                                initial_opponent_view=data.get("opponent_view"),
                                )

                        elif data.get("message") == "Joined private game":
                            await render_private_lobby(
                                data["lobby_id"], websocket,
                                data["lobby_data"]["players"],
                                data.get("logs", []),
                                owner_id=data.get("owner_id"),
                                me=player_id,
                                initial_board=data.get("board"),
                                initial_opponent_view=data.get("opponent_view"),
                            )
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
