# Nicotine+ API — SPEC.md

## Overview

A REST API that wraps pynicotine (the Soulseek client library) to enable programmatic search and download operations. This allows any agent or script to search for albums, queue downloads, and check status — enabling automated music discovery pipelines.

**Use case:** Last.fm recommendations → Soulseek download → beets auto-import → playlist integration.

---

## Architecture

- **Port**: 3090 (configurable via `PORT` env var)
- **Runtime**: Node.js + Express (lightweight HTTP layer) + Python bridge (pynicotine)
- **Soulseek client**: pynicotine (Nicotine+ library)
- **Config**: reads from existing Nicotine+ config (`~/.config/nicotine+/config`)
- **Download output**: configured in Nicotine+ config; fallback via `SLSK_DOWNLOAD_DIR` env var
- **TUI client**: Textual-based terminal UI included in `slsk_tui/`

---

## API Endpoints

### `GET /status`
Returns current connection status and basic stats.

```json
{
  "connected": true,
  "username": "your-username",
  "server": "server.slsknet.org:2242",
  "listening_port": 2234,
  "shares_count": 6,
  "downloads_dir": "/home/user/Downloads/slsk"
}
```

### `POST /search`
Search Soulseek for a query. Returns matching files with user/source info.

```json
{ "query": "artist album" }
```

### `POST /download`
Queue a file for download.

```json
{ "user": "username", "file": "/path/to/file.mp3" }
```

### `GET /downloads`
List active and queued downloads.

### `DELETE /download/:id`
Cancel a download by transfer ID.

### `GET /shares`
List configured shared folders.

### `POST /rescan-shares`
Trigger a rescan of shared folders.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `3090` | API server port |
| `SLSK_DOWNLOAD_DIR` | `~/Downloads/slsk` | Fallback download directory |
| `SLSK_API_URL` | `http://localhost:3090` | TUI client API URL |

---

## Setup

### Prerequisites

- Node.js 18+
- Python 3.12+ with pynicotine installed
- Nicotine+ configured with credentials (`~/.config/nicotine+/config`)

### Install

```bash
npm install
pip install -r requirements-tui.txt  # optional, for TUI client
```

### Run

```bash
node index.js
```

### TUI Client

```bash
python -m slsk_tui
# or with custom API URL:
SLSK_API_URL=http://myhost:3090 python -m slsk_tui
```

---

## Systemd

See `nicotine-api.service` for a template. Adjust `WorkingDirectory` and log paths for your setup.