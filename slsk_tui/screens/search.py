"""Search screen — query Soulseek and display results in a DataTable."""

from __future__ import annotations

import os
from humanize import naturalsize

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Input, Static
from textual.message import Message
from textual.worker import Worker, get_current_worker


def _human_size(size: int | float) -> str:
    """Return human-readable file size, e.g. '4.2 MB'."""
    try:
        return naturalsize(size, binary=True)
    except Exception:
        return str(size)


def _format_bitrate(val) -> str:
    """Return a clean bitrate string.

    The API may return numeric (e.g. 320, 1411) or string (e.g. 'FLAC') values.
    Numeric values that are >= 1000 and look like raw Kbps are shown as-is;
    very large numbers likely represent bits-per-second so divide by 1000.
    """
    if not val and val != 0:
        return ""
    try:
        num = int(val)
        # Values over ~999 are probably in bps, not kbps — convert
        if num > 999:
            return f"{num // 1000}"
        return str(num)
    except (ValueError, TypeError):
        # Non-numeric values like "FLAC", "VBR", etc.
        return str(val)


_SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class SearchScreen(Screen):
    """Main search screen with query input and results table."""

    BINDINGS = [
        Binding("s", "focus_search", "Search", show=True),
        Binding("escape", "clear_results", "Clear", show=True),
    ]

    class DownloadQueued(Message):
        """Posted when a user queues a download from a result row."""

        def __init__(self, filename: str, user: str) -> None:
            self.filename = filename
            self.user = user
            super().__init__()

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Search Soulseek…", id="search-input")
        yield Static("", id="search-status")
        yield DataTable(id="results-table")

    def on_mount(self) -> None:
        table = self.query_one("#results-table", DataTable)
        table.add_columns("Filename", "User", "Size", "Bitrate", "Speed", "Queue")
        self._row_data: dict[str, dict] = {}
        self._searching = False
        self._spinner_tick = 0
        self.query_one("#search-input", Input).focus()

    # -- key bindings -------------------------------------------------------

    def action_focus_search(self) -> None:
        self.query_one("#search-input", Input).focus()

    def action_clear_results(self) -> None:
        table = self.query_one("#results-table", DataTable)
        table.clear()
        self._row_data.clear()
        self.query_one("#search-status", Static).update("")
        # If we were searching, cancel spinner
        self._searching = False

    # -- key pass-through for app bindings ----------------------------------

    def on_key(self, event) -> None:
        """Let app-level bindings (1, 2, q) work even when the Input is focused.

        Textual normally consumes key events in focused Input widgets. We
        intercept the app-level keys here and re-fire them as actions.
        """
        key = event.key
        # App-level keys that should always work
        if key in ("1", "2", "q"):
            event.prevent_default()
            action_map = {"1": "show_search", "2": "show_downloads", "q": "quit"}
            action_name = action_map[key]
            # Fire on the app which owns those bindings
            self.app.run_action(action_name)

    # -- search trigger ------------------------------------------------------

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "search-input":
            return
        query = event.value.strip()
        if not query:
            return
        self._do_search(query)

    def _do_search(self, query: str) -> None:
        """Kick off a search worker so the UI stays responsive."""
        status = self.query_one("#search-status", Static)
        table = self.query_one("#results-table", DataTable)
        table.clear()
        self._row_data.clear()
        status.update("[italic]⠋ Searching…[/italic]")
        self._searching = True
        self._spinner_tick = 0
        self._spinner_timer = self.set_interval(0.15, self._update_spinner)
        self.run_worker(self._search_worker(query), name=f"search-{query}", exclusive=True)

    def _update_spinner(self) -> None:
        """Animate the spinner while searching."""
        if not self._searching:
            return
        self._spinner_tick = (self._spinner_tick + 1) % len(_SPINNER_FRAMES)
        frame = _SPINNER_FRAMES[self._spinner_tick]
        try:
            status = self.query_one("#search-status", Static)
            status.update(f"[italic]{frame} Searching…[/italic]")
        except Exception:
            pass

    def _stop_spinner(self) -> None:
        """Stop the spinner animation."""
        self._searching = False
        try:
            self._spinner_timer.stop()
        except Exception:
            pass

    async def _search_worker(self, query: str) -> None:
        """Background worker: call API and populate table on success."""
        try:
            resp = self.app.client.search(query, max_results=100)  # type: ignore[attr-defined]
            results = resp.get("results", [])
            total = resp.get("total_results", len(results))
        except Exception as exc:
            self.call_from_thread(self._show_search_error, exc)
            return

        self.call_from_thread(self._populate_results, query, results, total)

    def _show_search_error(self, exc: Exception) -> None:
        self._stop_spinner()
        status = self.query_one("#search-status", Static)
        status.update(f"[red]Search failed: {exc}[/red]")

    def _populate_results(self, query: str, results: list[dict], total: int) -> None:
        """Populate the DataTable with search results (called on main thread)."""
        self._stop_spinner()
        status = self.query_one("#search-status", Static)
        table = self.query_one("#results-table", DataTable)

        if not results:
            status.update(f'No results for "{query}"')
            return

        for r in results:
            filename = r.get("filename", "")
            # Strip directory prefix for readability
            display_name = os.path.basename(filename) if filename else filename
            user = r.get("user", "")
            size = _human_size(r.get("size", 0))
            bitrate = _format_bitrate(r.get("bitrate", ""))
            speed = str(r.get("speed", "")) + " kbps" if r.get("speed") else ""
            queue = str(r.get("queue_length", ""))

            row_key = table.add_row(display_name, user, size, bitrate, speed, queue)
            self._row_data[str(row_key)] = {
                "filename": filename,
                "user": user,
            }

        status.update(f'Found {total} result(s) for "{query}"')

    # -- download on row selection ------------------------------------------

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Queue a download when the user selects a result row."""
        key = str(event.row_key.value) if event.row_key.value is not None else str(event.row_key)
        data = self._row_data.get(key)
        if not data:
            return

        filename = data["filename"]
        user = data["user"]

        try:
            self.app.client.download(user=user, file=filename, filename=filename)  # type: ignore[attr-defined]
            self.post_message(self.DownloadQueued(filename=filename, user=user))
            self.app.notify(f"Queued: {os.path.basename(filename)}")
        except Exception as exc:
            self.app.notify(f"Download failed: {exc}", severity="error")