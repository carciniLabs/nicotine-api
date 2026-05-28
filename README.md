# nicotine-api

REST API wrapping [pynicotine](https://github.com/nicotine-plus/nicotine-plus) for programmatic Soulseek search and download.

Includes a Textual TUI client for interactive use.

## Quick Start

```bash
# Install dependencies
npm install
pip install -r requirements-tui.txt  # optional, for TUI

# Configure Nicotine+ credentials
# (edit ~/.config/nicotine+/config or launch Nicotine+ GUI once)

# Start the API server
node index.js

# Or use the TUI
python -m slsk_tui
```

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/status` | Connection status and stats |
| POST | `/search` | Search Soulseek (`{"query": "..."}`) |
| POST | `/download` | Queue download (`{"user":"...", "file":"..."}`) |
| GET | `/downloads` | List active downloads |
| DELETE | `/download/:id` | Cancel a download |
| GET | `/shares` | List shared folders |
| POST | `/rescan-shares` | Rescan shared folders |

## Environment Variables

- `PORT` — API port (default: 3090)
- `SLSK_DOWNLOAD_DIR` — Fallback download path (default: `~/Downloads/slsk`)
- `SLSK_API_URL` — TUI connection URL (default: `http://localhost:3090`)

## License

MIT