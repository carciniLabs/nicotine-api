# Soulseek TUI

A terminal UI for [slsk-api](https://github.com/mathewhalpern/slsk-api), built with [Textual](https://textual.textualize.io/).

## Quickstart

```bash
pip install -r requirements-tui.txt
python -m slsk_tui
```

The app connects to `http://archbox:3090` by default. Override with the `SLSK_API_URL` environment variable:

```bash
SLSK_API_URL=http://myhost:3090 python -m slsk_tui
```

## Features

- Search Soulseek and browse results in a scrollable table
- Queue downloads from search results
- Monitor active and completed downloads with auto-refresh
- Cancel downloads with confirmation
- Trigger share rescans
- View connection status at a glance
- Full keyboard navigation

## Keybindings

### Global (available on all screens)

| Key | Action |
|-----|--------|
| `1` | Switch to Search screen |
| `2` | Switch to Downloads screen |
| `q` | Quit the app |
| `Ctrl+C` | Quit the app |

### Search screen

| Key | Action |
|-----|--------|
| `Enter` | Submit search query / Select result row |
| `s` | Focus the search input |
| `Escape` | Clear search results |

### Downloads screen

| Key | Action |
|-----|--------|
| `c` | Cancel the selected download (with confirmation) |
| `r` | Trigger a share rescan |
| `Escape` | Go back to Search screen |

### Confirmation modal

| Key | Action |
|-----|--------|
| `y` | Confirm |
| `n` / `Escape` | Cancel |

## Screenshots

<!-- TODO: Add screenshots here -->

## Architecture

```
slsk_tui/
  __init__.py          # Package version
  __main__.py          # Entry point (python -m slsk_tui)
  app.py               # Textual App class with screen navigation
  client.py            # HTTP client wrapping slsk-api REST endpoints
  styles.tcss          # Textual CSS (dark theme)
  widgets/
    __init__.py
    status_bar.py       # Connection status bar
  screens/
    __init__.py
    search.py          # Search input + results table
    downloads.py       # Downloads table + confirm modal
```

## Requirements

- Python 3.11+
- textual >= 0.40
- httpx
- humanize