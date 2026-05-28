# nicotine-api

REST API and TUI for Soulseek, built on [pynicotine](https://github.com/nicotine-plus/nicotine-plus).

Search, download, and manage shares on the Soulseek network through an HTTP interface — or use the included terminal UI client.

## Architecture

```
┌──────────────┐     JSON over stdio     ┌──────────────┐     pynicotine     ┌──────────────┐
│   index.js   │ ◄──────────────────────► │   bridge.py  │ ◄────────────────► │   Soulseek   │
│  (Express)   │     Node ◄──► Python     │ (subprocess) │                    │   Network    │
│  port 3090    │                          │              │                    │              │
└──────┬───────┘                          └──────────────┘                    └──────────────┘
       │ HTTP
       ▼
┌──────────────┐
│  slsk_tui/   │  (Textual TUI — python -m slsk_tui)
└──────────────┘
```

- **Node.js layer** (`index.js`) — Express HTTP server on port 3090. Spawns `bridge.py` as a child process and communicates via newline-delimited JSON on stdin/stdout. Routes map 1:1 to Python commands.
- **Python bridge** (`bridge.py`) — Runs pynicotine's headless core. Receives JSON commands from Node, emits events back. Handles login, search, downloads, shares, and rescan operations.
- **TUI client** (`slsk_tui/`) — Textual-based terminal UI. Talks to the API over HTTP. Screens: Search, Downloads.

## Prerequisites

- **Node.js** 18+
- **Python** 3.11+
- **pynicotine** — install with `pip install pynicotine`

## Installation

**API server:**

```bash
npm install
pip install pynicotine
```

**TUI client:**

```bash
pip install -r requirements-tui.txt
```

## Running the API

```bash
node index.js
```

The server listens on port 3090 by default.

## Running the TUI

```bash
python -m slsk_tui
```

The TUI connects to the API server at `http://localhost:3090` by default (override with `SLSK_API_URL`).

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `3090` | API server port (note: currently hardcoded in index.js, not yet configurable via env) |
| `SLSK_DOWNLOAD_DIR` | (from pynicotine config) | Download output directory |
| `SLSK_API_URL` | `http://localhost:3090` | API URL for the TUI client |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/status` | Connection status, username, server, shares count, uptime |
| `POST` | `/search` | Search Soulseek. Body: `{"query": "...", "max_results": 50, "timeout": 20000}` |
| `POST` | `/download` | Queue a download. Body: `{"user": "...", "file": "...", "filename": "..."}` |
| `GET` | `/downloads` | List active/completed downloads with progress |
| `DELETE` | `/download/:id` | Cancel a download by transfer ID |
| `GET` | `/shares` | List configured shared folders |
| `POST` | `/rescan-shares` | Trigger a rescan of shared folders |

## Systemd Service

A service file (`nicotine-api.service`) is included for running the API as a user-level systemd service.

```bash
# Copy the service file and adjust WorkingDirectory/ExecStart paths as needed
cp nicotine-api.service ~/.config/systemd/user/

# Enable and start
systemctl --user enable --now nicotine-api

# View logs
journalctl --user -u nicotine-api -f
```

The service runs with `Restart=always` and writes output to `~/nicotine-api.log`.

## Project Structure

```
nicotine-api/
├── index.js                   # Express HTTP server (Node.js entry point)
├── bridge.py                  # pynicotine bridge (Python subprocess)
├── package.json               # Node.js dependencies
├── slsk_tui/                  # Textual TUI client
│   ├── __main__.py            #   TUI entry point
│   ├── app.py                 #   Textual App class
│   ├── client.py              #   HTTP client for the API
│   ├── screens/
│   │   ├── search.py          #     Search screen
│   │   └── downloads.py       #     Downloads screen
│   ├── widgets/
│   │   └── status_bar.py      #     Status bar widget
│   └── styles.tcss            #   Textual CSS
├── nicotine-api.service        # systemd user service file
├── requirements-tui.txt       # Python deps for TUI
├── SPEC.md                    # Internal implementation notes
└── .gitignore
```