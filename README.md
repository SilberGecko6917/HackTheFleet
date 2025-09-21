# HackTheFleet — Client

## Description

A terminal TUI client for the HackTheFleet game. Connects to a WebSocket server, manages lobbies, placement, and gameplay.

## Quick start

1. Create and activate a virtualenv (optional):

   ```cmd
   python -m venv .venv
   .venv\Scripts\activate
   ```

2. Install dependencies:

   ```cmd
   python -m pip install -r client\requirements.txt
   ```

3. Run the client:

   ```cmd
   python client\main.py
   ```

## Override server (optional)

- Windows (cmd):

  ```cmd
  python client\main.py
  ```

- Unix/macOS (bash):

  ```bash
  python client/main.py
  ```

## Controls

- Move: arrows or WASD
- Place: Enter or P (placement)
- Remove: R (placement)
- Shoot: Enter (game)
- Start: S (lobby owner)

## Notes

- Run in a normal terminal (cmd/PowerShell/Windows Terminal). The client uses `rich` for TUI and `websockets` for networking.
