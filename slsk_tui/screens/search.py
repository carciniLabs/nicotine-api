"""Search screen — query Soulseek and display results in a DataTable."""

from __future__ import annotations

import os
from functools import total_ordering
from humanize import naturalsize

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import DataTable, Input, Select, Static
from textual.message import Message
from textual.worker import Worker, get_current_worker


# -- Column key constants -----------------------------------------------------

COL_FILENAME = "filename"
COL_USER = "user"
COL_SIZE = "size"
COL_BITRATE = "bitrate"
COL_SPEED = "speed"
COL_QUEUE = "queue"

# Set of sortable column keys
SORTABLE_COLUMNS = {COL_FILENAME, COL_SIZE, COL_BITRATE, COL_SPEED, COL_QUEUE}

# Sort indicators
SORT_ASC = "▲"
SORT_DESC = "▼"

# Base column labels (without sort indicators)
BASE_LABELS: dict[str, str] = {
    COL_FILENAME: "Filename",
    COL_USER: "User",
    COL_SIZE: "Size",
    COL_BITRATE: "Bitrate",
    COL_SPEED: "Speed",
    COL_QUEUE: "Queue",
}

# Extension filter options: (label, value) pairs for the Select widget.
# The value "all" means no filter; others are file extensions (lowercase).
EXT_FILTER_OPTIONS = [
    ("All", "all"),
    (".flac", ".flac"),
    (".mp3", ".mp3"),
    (".ogg", ".ogg"),
    (".wav", ".wav"),
]


@total_ordering
class SortableCell:
    """Cell that stores a raw sort value alongside a display string.

    DataTable's sort() compares cell values directly. By wrapping numeric
    values in SortableCell, we get correct numeric sorting while the display
    shows the human-readable formatted string.
    """

    __slots__ = ("raw", "display")

    def __init__(self, raw: int | float | str, display: str) -> None:
        self.raw = raw
        self.display = display

    def __str__(self) -> str:
        return self.display

    def __repr__(self) -> str:
        return f"SortableCell({self.raw!r}, {self.display!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, SortableCell):
            return self.raw == other.raw
        return NotImplemented

    def __lt__(self, other: object) -> bool:
        if isinstance(other, SortableCell):
            # None-like raw values sort last
            if self.raw is None and other.raw is None:
                return False
            if self.raw is None:
                return False  # None sorts last (is greater)
            if other.raw is None:
                return True  # non-None sorts before None
            return self.raw < other.raw
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.raw)


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


def _parse_bitrate_raw(val) -> int:
    """Extract a numeric bitrate for sorting. Non-numeric values sort as 0."""
    if val is None:
        return 0
    try:
        num = int(val)
        if num > 999:
            return num // 1000
        return num
    except (ValueError, TypeError):
        return 0


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
        yield Horizontal(
            Static("Filter:", id="filter-label"),
            Select(
                EXT_FILTER_OPTIONS,
                value="all",
                id="ext-filter",
            ),
            id="filter-bar",
        )
        yield DataTable(id="results-table", cursor_type="row")

    def on_mount(self) -> None:
        table = self.query_one("#results-table", DataTable)
        table.add_columns(
            (BASE_LABELS[COL_FILENAME], COL_FILENAME),
            (BASE_LABELS[COL_USER], COL_USER),
            (BASE_LABELS[COL_SIZE], COL_SIZE),
            (BASE_LABELS[COL_BITRATE], COL_BITRATE),
            (BASE_LABELS[COL_SPEED], COL_SPEED),
            (BASE_LABELS[COL_QUEUE], COL_QUEUE),
        )
        self._row_data: dict[str, dict] = {}
        self._all_results: list[dict] = []  # unfiltered results cache
        self._current_filter: str = "all"  # active extension filter
        self._last_query: str = ""  # last search query for status messages
        self._searching = False
        self._spinner_tick = 0
        self._sort_column: str | None = None
        self._sort_reverse: bool = True  # True = descending
        self.query_one("#search-input", Input).focus()

    # -- key bindings -------------------------------------------------------

    def action_focus_search(self) -> None:
        self.query_one("#search-input", Input).focus()

    def action_clear_results(self) -> None:
        table = self.query_one("#results-table", DataTable)
        table.clear()
        self._row_data.clear()
        self._all_results.clear()
        self._last_query = ""
        self._current_filter = "all"
        # Reset filter widget
        ext_filter = self.query_one("#ext-filter", Select)
        ext_filter.value = "all"
        self.query_one("#search-status", Static).update("")
        # Reset sort state
        self._sort_column = None
        self._sort_reverse = True
        self._update_sort_indicators()
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
        self._all_results.clear()
        self._last_query = query
        # Reset filter to "all" on new search
        self._current_filter = "all"
        ext_filter = self.query_one("#ext-filter", Select)
        ext_filter.value = "all"
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
        """Store raw results and apply current filter."""
        self._stop_spinner()
        self._all_results = results
        self._last_query = query

        if not results:
            status = self.query_one("#search-status", Static)
            status.update(f'No results for "{query}"')
            return

        # Default sort: bitrate descending on fresh results
        self._sort_column = COL_BITRATE
        self._sort_reverse = True
        self._apply_filter()
        self._update_sort_indicators()

    # -- extension filter ----------------------------------------------------

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle extension filter change."""
        if event.select.id != "ext-filter":
            return
        value = str(event.value).lower() if event.value != Select.BLANK else "all"
        self._current_filter = value
        self._apply_filter()

    def _apply_filter(self) -> None:
        """Rebuild the DataTable rows based on the current extension filter."""
        table = self.query_one("#results-table", DataTable)
        status = self.query_one("#search-status", Static)

        # Clear existing rows and row data
        table.clear()
        self._row_data.clear()

        # Filter results
        results = self._all_results
        if self._current_filter != "all":
            ext = self._current_filter.lower()
            results = [
                r for r in self._all_results
                if r.get("filename", "").lower().endswith(ext)
            ]

        # Populate table with filtered results
        for r in results:
            filename = r.get("filename", "")
            # Strip directory prefix for readability
            display_name = os.path.basename(filename) if filename else filename
            user = r.get("user", "")

            size_raw = r.get("size", 0) or 0
            bitrate_raw = _parse_bitrate_raw(r.get("bitrate", ""))
            speed_raw = r.get("speed", 0) or 0
            queue_raw = r.get("queue_length", 0) or 0

            # Create SortableCell wrappers for numeric columns
            size_cell = SortableCell(raw=size_raw, display=_human_size(size_raw))
            bitrate_cell = SortableCell(raw=bitrate_raw, display=_format_bitrate(r.get("bitrate", "")))
            speed_cell = SortableCell(raw=speed_raw, display=(f"{speed_raw} kbps" if speed_raw else ""))
            queue_cell = SortableCell(raw=queue_raw, display=str(queue_raw) if queue_raw is not None else "")

            row_key = table.add_row(display_name, user, size_cell, bitrate_cell, speed_cell, queue_cell)
            self._row_data[str(row_key)] = {
                "filename": filename,
                "user": user,
            }

        # Update status message
        total = len(self._all_results)
        shown = len(results)
        query = self._last_query

        if self._current_filter == "all":
            status.update(f'Found {total} result(s) for "{query}"')
        elif shown == 0:
            ext_display = self._current_filter.lstrip(".")
            status.update(f'No .{ext_display} results ({total} total)')
        else:
            ext_display = self._current_filter.lstrip(".")
            status.update(f'Showing {shown} .{ext_display} result(s) of {total}')

        # Re-apply sort if there's an active sort column
        if self._sort_column:
            self._apply_sort()

    # -- column-header click sorting ------------------------------------------

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        """Handle column-header clicks to toggle sorting."""
        col_key = str(event.column_key)
        if col_key not in SORTABLE_COLUMNS:
            return

        # Toggle direction if same column, otherwise default to descending
        if self._sort_column == col_key:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column = col_key
            self._sort_reverse = True

        self._apply_sort()

    def _apply_sort(self) -> None:
        """Sort the DataTable by the current sort column and direction."""
        if self._sort_column is None:
            return
        table = self.query_one("#results-table", DataTable)
        table.sort(self._sort_column, reverse=self._sort_reverse)
        self._update_sort_indicators()

    def _update_sort_indicators(self) -> None:
        """Update column labels to show ▲/▼ on the active sort column."""
        table = self.query_one("#results-table", DataTable)
        indicator = SORT_DESC if self._sort_reverse else SORT_ASC

        for col_key, column in table.columns.items():
            key_str = str(col_key)
            base = BASE_LABELS.get(key_str, str(col_key))
            if key_str == self._sort_column:
                column.label = f"{base} {indicator}"
            else:
                column.label = base

        table.refresh()

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