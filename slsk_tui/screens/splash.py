"""Splash screen — animated ASCII art title with particle effects."""

from __future__ import annotations

import math
import random

from rich.text import Text
from rich.style import Style

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static

# ── ASCII art banner ──────────────────────────────────────────────────────────
# Clean block-letter "SLSK" banner, ~60 cols wide, 6 rows.

_SLSK_BANNER_LINES = [
    " ███████╗██╗     ██████╗ ██████╗ ███████╗███████╗███████╗██╗     ██████╗ ",
    " ██╔════╝██║     ██╔══██╗██╔══██╗██╔════╝██╔════╝██╔════╝██║     ██╔══██╗ ",
    " ███████╗██║     ██████╔╝██║  ██║█████╗  ███████╗█████╗  ██║     ██║  ██║ ",
    " ╚════██║██║     ██╔═══╝ ██║  ██║██╔══╝  ╚════██║██╔══╝  ██║     ██║  ██║ ",
    " ███████║███████╗██║     ██████╔╝███████╗███████║███████╗███████╗██████╔╝ ",
    " ╚══════╝╚══════╝╚═╝     ╚═════╝ ╚══════╝╚══════╝╚══════╝╚══════╝╚═════╝ ",
]

_SLSK_SUBTITLE = "soulseek tui"

# ── Particle system ──────────────────────────────────────────────────────────

_PARTICLE_CHARS = list("░▒▓█▄▀·∙○●♪♫")

_COLOR_NAMES = [
    "cyan",
    "deep_sky_blue",
    "dodger_blue",
    "steel_blue",
    "dark_cyan",
    "turquoise",
]

# Dim fallback colors (256-color compatible)
_DIM_COLORS = [
    "grey37",
    "grey42",
    "grey50",
]

# How many new particles to spawn per tick
_SPAWN_PER_TICK = 2

# Duration before auto-fade starts (seconds)
_SPLASH_DURATION = 2.5

# Fade-out duration (seconds)
_FADE_DURATION = 0.3

# Tick interval (seconds) — ~20fps
_TICK_INTERVAL = 0.05

# Max particles (performance cap)
_MAX_PARTICLES = 80


class _Particle:
    """Lightweight particle with position, velocity, and lifetime."""

    __slots__ = ("x", "y", "char", "color", "velocity", "lifetime", "age", "wave_offset")

    def __init__(
        self,
        x: float,
        y: float,
        char: str,
        color: str,
        velocity: float,
        lifetime: float,
        wave_offset: float,
    ) -> None:
        self.x = x
        self.y = y
        self.char = char
        self.color = color
        self.velocity = velocity
        self.lifetime = lifetime
        self.age = 0.0
        self.wave_offset = wave_offset

    @property
    def alive(self) -> bool:
        return self.age < self.lifetime

    def brightness(self, fade_multiplier: float = 1.0) -> float:
        """Return brightness 0.0..1.0 based on age and global fade."""
        ratio = self.age / self.lifetime if self.lifetime > 0 else 1.0
        # Fade in during first 10%, full brightness in middle, fade out in last 30%
        if ratio < 0.1:
            b = ratio / 0.1
        elif ratio > 0.7:
            b = max(0.0, (1.0 - ratio) / 0.3)
        else:
            b = 1.0
        return b * fade_multiplier


class SplashScreen(Screen):
    """Full-screen splash with ASCII art title and particle rain animation."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._particles: list[_Particle] = []
        self._fading = False
        self._fade_start_time: float = 0.0
        self._dismissed = False
        self._age: float = 0.0
        self._tick_timer = None

    def compose(self) -> ComposeResult:
        yield Static("", id="splash-title")
        yield Static("", id="splash-canvas")

    def on_mount(self) -> None:
        """Set up timers and render initial state."""
        # Render ASCII art title
        self._render_title()

        # Start animation loop (~20fps)
        self._tick_timer = self.set_interval(_TICK_INTERVAL, self._tick)

        # Auto-dismiss timer
        self.set_timer(_SPLASH_DURATION, self._start_fade)

    def on_unmount(self) -> None:
        """Clean up timers."""
        if self._tick_timer is not None:
            self._tick_timer.stop()
            self._tick_timer = None

    # ── Dismiss on any input ─────────────────────────────────────────────

    def on_key(self, event) -> None:
        """Any key press dismisses the splash."""
        event.prevent_default()
        event.stop()
        self._start_fade()

    def on_click(self, event) -> None:
        """Any mouse click dismisses the splash."""
        event.prevent_default()
        event.stop()
        self._start_fade()

    # ── Fade-out logic ────────────────────────────────────────────────────

    def _start_fade(self) -> None:
        """Begin the fade-out animation."""
        if self._fading or self._dismissed:
            return
        self._fading = True
        self._fade_start_time = self._age

    def _force_dismiss(self) -> None:
        """Guarantee dismissal even if fade doesn't complete naturally."""
        if self._dismissed:
            return
        self._dismissed = True
        if self._tick_timer is not None:
            self._tick_timer.stop()
            self._tick_timer = None
        try:
            self.dismiss()
        except Exception:
            pass

    # ── Animation tick ─────────────────────────────────────────────────────

    def _tick(self) -> None:
        """Per-frame update: spawn, move, and render particles."""
        dt = _TICK_INTERVAL
        self._age += dt

        # Calculate global fade multiplier (1.0 = full brightness, 0.0 = invisible)
        fade_multiplier = 1.0
        if self._fading:
            fade_elapsed = self._age - self._fade_start_time
            fade_multiplier = max(0.0, 1.0 - fade_elapsed / _FADE_DURATION)

        # Spawn new particles (skip during fade)
        if not self._fading and len(self._particles) < _MAX_PARTICLES:
            for _ in range(_SPAWN_PER_TICK):
                self._spawn_particle()

        # Update existing particles
        alive: list[_Particle] = []
        for p in self._particles:
            p.age += dt
            if not p.alive:
                continue

            # Move: drift downward with sine-wave horizontal wobble
            p.y += p.velocity * dt * 8.0
            p.x += math.sin(p.age * 2.5 + p.wave_offset) * 0.25

            # Remove if off bottom of a 200-row bound (we clip to visible area during render)
            if p.y > 200:
                continue

            alive.append(p)

        self._particles = alive

        # If fading and all particles gone, dismiss now
        if self._fading:
            fade_elapsed = self._age - self._fade_start_time
            if not self._particles or fade_elapsed > _FADE_DURATION + 0.05:
                self._force_dismiss()
                return

        # Render
        self._render_particles(fade_multiplier)

    def _spawn_particle(self) -> None:
        """Create a new particle near the top of the screen."""
        # Use a reasonable default if screen size not yet available
        width = max(self.size.width, 40) if self.size else 80
        p = _Particle(
            x=random.uniform(0, width),
            y=random.uniform(-2, 1),
            char=random.choice(_PARTICLE_CHARS),
            color=random.choice(_COLOR_NAMES),
            velocity=random.uniform(1.5, 3.5),
            lifetime=random.uniform(2.0, 4.0),
            wave_offset=random.uniform(0, 2 * math.pi),
        )
        self._particles.append(p)

    # ── Title rendering ────────────────────────────────────────────────────

    def _render_title(self) -> None:
        """Render the ASCII art title with Rich Text."""
        try:
            title_widget = self.query_one("#splash-title", Static)
        except Exception:
            return

        text = Text()
        for i, line in enumerate(_SLSK_BANNER_LINES):
            text.append(line, style=Style(color="cyan", bold=True))
            if i < len(_SLSK_BANNER_LINES) - 1:
                text.append("\n")
        # Subtitle
        text.append("\n")
        text.append(_SLSK_SUBTITLE, style=Style(color="deep_sky_blue", italic=True))

        title_widget.update(text)

    # ── Particle rendering ─────────────────────────────────────────────────

    def _render_particles(self, fade_multiplier: float) -> None:
        """Build a Rich Text frame buffer and update the canvas widget."""
        try:
            canvas_widget = self.query_one("#splash-canvas", Static)
        except Exception:
            return

        # Get canvas dimensions
        region = canvas_widget.size
        width = max(region.width, 1)
        height = max(region.height, 1)

        if self._fading and not self._particles:
            # Clear canvas during final frame of fade
            canvas_widget.update("")
            return

        # Build grid: list of (col, row, char, brightness, color)
        # then render using Rich Text for proper styling
        text = Text()

        # Create a 2D grid tracking which cells have particles
        # For efficiency, we iterate particles and place them directly
        placed: dict[tuple[int, int], tuple[str, float, str]] = {}
        for p in self._particles:
            col = int(p.x)
            row = int(p.y)
            if 0 <= col < width and 0 <= row < height:
                b = p.brightness(fade_multiplier)
                if b > 0.08:  # skip invisible particles
                    # If multiple particles overlap, keep the brighter one
                    if (col, row) not in placed or b > placed[(col, row)][1]:
                        placed[(col, row)] = (p.char, b, p.color)

        # Build rows as Rich Text
        for row_idx in range(height):
            col_idx = 0
            while col_idx < width:
                if (col_idx, row_idx) in placed:
                    char, brightness, color_name = placed[(col_idx, row_idx)]
                    # Map brightness to style
                    if brightness < 0.35:
                        style = Style(color="grey37")
                    elif brightness < 0.6:
                        style = Style(color=color_name, dim=True)
                    else:
                        style = Style(color=color_name, bold=True)
                    text.append(char, style=style)
                else:
                    text.append(" ")
                col_idx += 1
            if row_idx < height - 1:
                text.append("\n")

        canvas_widget.update(text)