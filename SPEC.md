# Nicotine+ API — SPEC.md

## Overview

A REST API that wraps pynicotine (the Soulseek client library) to enable programmatic search and download operations on archbox. This allows Igor to search for albums, queue downloads, and check status — enabling automated music discovery pipelines.

**Context:** Soulseek has the best selection of rare/obscure music. This API enables automation: Last.fm recommendations → Soulseek download → beets auto-import → playlist integration.

---

## Architecture

- **Host**: archbox (192.168.1.x or archbox.terra.crab-aesthetics.com)
- **Port**: 3090
- **Runtime**: Node.js + Express (lightweight, familiar pattern)
- **Soulseek client**: pynicotine (Nicotine+ library, already installed)
- **Config**: reads from existing `~/.config/nicotine+/config`
- **Download output**: `/mnt/fangorn/Audio/Music/Unsorted/SLSK/` (same as archpad)

---

## API Endpoints

### `GET /status`
Returns current connection status and basic stats.

```json
{
  "connected": true,
  "username": "crab-aesthetics",
  "server": "server.slsknet.org:2242",
  "listening_port": 2234,
  "shares_count": 6,
  "downloads_dir": "/mnt/fangorn/Audio/Music/Unsorted/SLSK"
}
```

### `POST /search`
Search Soulseek for a query. Returns matching files with user/source info.

**Request:**
```json
{
  "query": "Warlung Vultures Paradise",
  "max_results": 10
}
```

**Response:**
```json
{
  "query": "Warlung Vultures Paradise",
  "results": [
    {
      "filename": "Warlung - Vultures Paradise (2025).flac",
      "user": "SomeUser123",
      "speed": 1560,
      "queue_length": 0,
      "size": 289456789,
      "bitrate": "FLAC",
      "duration": 2345
    }
  ],
  "total_results": 1
}
```

### `POST /download`
Queue a file for download.

**Request:**
```json
{
  "user": "SomeUser123",
  "file": "/Warlung/Vultures Paradise/01 Vultures Paradise.flac",
  "filename": "Warlung - Vultures Paradise (2025).flac"
}
```

**Response:**
```json
{
  "success": true,
  "transfer_id": "abc123",
  "status": "queued"
}
```

### `GET /downloads`
List active downloads and their status.

```json
{
  "downloads": [
    {
      "id": "abc123",
      "filename": "Warlung - Vultures Paradise (2025).flac",
      "user": "SomeUser123",
      "status": "downloading",
      "progress": 45,
      "size": 289456789,
      "speed_kbps": 1240
    }
  ]
}
```

### `DELETE /download/:id`
Cancel a download by transfer ID.

### `GET /shares`
List configured shared folders (read-only).

### `POST /rescan-shares`
Trigger a rescan of shared folders.

---

## Implementation Notes

- **pynicotine core**: Use `pynicotine.core.Core` — the non-GUI engine. It handles the protocol and can be instantiated without GTK.
  ```python
  from pynicotine.core import Core
  core = Core()  # reads config from ~/.config/nicotine+/ by default
  ```
- **Search**: `core.search.do_search(query)` — returns results via callback
- **Downloads**: `core.transfers.queue_download(user, file, filename)`
- **Events**: Core emits events via `pynicotine.events` — hook into these for status updates
- **Config path**: Can pass `--user-data ~/.config/nicotine+` to override

### Alternative: spawn nicotine with --command flag
Check if Nicotine+ has a command mode or FIFO pipe for headless control. Look at `--help` for any command interface.

---

## Process Management

- API server runs as systemd service `nicotine-api.service`
- Port 3090 (not 80/443 — not running as root)
- Restart policy: always
- Log to `/home/crab/nicotine-api.log`

---

## Testing Checklist

- [ ] `GET /status` returns connected state
- [ ] `POST /search` returns real results from Soulseek
- [ ] `POST /download` queues a file and it appears in downloads list
- [ ] File lands in `/mnt/fangorn/Audio/Music/Unsorted/SLSK/`
- [ ] `GET /downloads` reflects active transfers
- [ ] `DELETE /download/:id` cancels a queued download

---

## Todo

- [ ] Build initial Express server scaffold
- [ ] Integrate pynicotine core
- [ ] Implement `/search` endpoint
- [ ] Implement `/download` endpoint
- [ ] Implement `/downloads` list
- [ ] Write systemd service file
- [ ] Test full pipeline: search → queue → download → file lands on disk
- [ ] Document Last.fm integration point