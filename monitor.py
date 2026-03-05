"""
Terminal dashboard for the home security system.
Uses a module-level Stats singleton so any component can update it via import.

Layout (full-screen, scales to terminal size):
  ┌─ header ──────────────────────────────────────────────────┐
  │ left (cameras / llm / alerts)  │  right (logs, scrollable)│
  └─ footer (key hints) ──────────────────────────────────────┘

Arrow keys ↑↓ scroll the log panel.
"""

import atexit
import logging
import logging.handlers
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# ── Shared stats ──────────────────────────────────────────────────────────────

@dataclass
class CameraStats:
    status: str = "connecting"   # connecting | connected | disconnected
    fps: float = 0.0
    motion_score: int = 0
    motion_events: int = 0
    last_motion: str = "—"


@dataclass
class LLMStats:
    model: str = "claude-sonnet-4-6"
    total_calls: int = 0
    suspicious_hits: int = 0
    last_call_ts: float = 0.0
    cooldown_seconds: int = 30


@dataclass
class AlertStats:
    total_sent: int = 0
    log: list[tuple[str, str, str]] = field(default_factory=list)  # (time, camera, reason)


_LOG_STYLES: dict[str, str] = {
    "INFO":   "dim",
    "CAMERA": "cyan",
    "MOTION": "yellow",
    "LLM":    "magenta",
    "ALERT":  "bold red",
    "ERROR":  "red",
}

MAX_LOG_LINES = 500


class Stats:
    def __init__(self):
        self._lock = threading.Lock()
        self.cameras: dict[str, CameraStats] = {}
        self.llm = LLMStats()
        self.alerts = AlertStats()
        self.start_time = time.monotonic()
        self.web_url = ""
        self._log_entries: list[tuple[str, str, str]] = []  # (time, level, message)

    def camera(self, camera_id: str) -> CameraStats:
        with self._lock:
            if camera_id not in self.cameras:
                self.cameras[camera_id] = CameraStats()
            return self.cameras[camera_id]

    def record_alert(self, camera_id: str, reason: str):
        with self._lock:
            ts = datetime.now().strftime("%H:%M:%S")
            self.alerts.total_sent += 1
            self.alerts.log.append((ts, camera_id, reason))
            if len(self.alerts.log) > 10:
                self.alerts.log.pop(0)

    def log(self, message: str, level: str = "INFO"):
        with self._lock:
            ts = datetime.now().strftime("%H:%M:%S")
            self._log_entries.append((ts, level.upper(), message))
            if len(self._log_entries) > MAX_LOG_LINES:
                self._log_entries.pop(0)

    def get_all_log(self) -> list[tuple[str, str, str]]:
        with self._lock:
            return list(self._log_entries)


# Module-level singleton
stats = Stats()


# ── File logger (rotating) ────────────────────────────────────────────────────

class _TruncatingFileHandler(logging.handlers.RotatingFileHandler):
    """On rollover, truncate the file instead of keeping backups."""
    def doRollover(self):
        if self.stream:
            self.stream.close()
            self.stream = None
        self.stream = open(self.baseFilename, "w", encoding=self.encoding)


def _make_file_logger() -> logging.Logger | None:
    import config as _config
    if not _config.LOG_FILE:
        return None
    os.makedirs(os.path.dirname(_config.LOG_FILE) or ".", exist_ok=True)
    logger = logging.getLogger("security")
    logger.setLevel(logging.DEBUG)
    handler = _TruncatingFileHandler(
        _config.LOG_FILE,
        maxBytes=_config.LOG_MAX_BYTES,
        backupCount=0,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(handler)
    return logger

_file_logger: logging.Logger | None = _make_file_logger()


def log(message: str, level: str = "INFO"):
    """Shortcut: monitor.log('msg', 'CAMERA')"""
    stats.log(message, level)
    if _file_logger:
        _file_logger.log(logging.getLevelName(level) if level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL") else logging.INFO, message)


# ── Scroll state ──────────────────────────────────────────────────────────────

_scroll_offset = 0   # 0 = pinned to newest; positive = scrolled up into history
_scroll_lock = threading.Lock()
_scroll_event = threading.Event()


def _adjust_scroll(delta: int):
    global _scroll_offset
    with _scroll_lock:
        _scroll_offset = max(0, _scroll_offset + delta)
    _scroll_event.set()  # wake the render loop immediately


def _get_scroll() -> int:
    with _scroll_lock:
        return _scroll_offset


# ── Panel builders ────────────────────────────────────────────────────────────

def _uptime() -> str:
    secs = int(time.monotonic() - stats.start_time)
    h, r = divmod(secs, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _header_panel() -> Panel:
    t = Text()
    t.append("Home Security Monitor", style="bold white")
    t.append("  |  ", style="dim")
    t.append(f"uptime {_uptime()}", style="dim")
    if stats.web_url:
        t.append("  |  ", style="dim")
        t.append(stats.web_url, style="blue underline")
    return Panel(t, border_style="dim", padding=(0, 1))


def _cameras_panel(left_width: int = 999) -> Panel:
    # Column labels shrink as the left panel narrows
    # left_width is the usable character width of the left column
    if left_width >= 60:
        h_status, h_fps, h_motion, h_events, h_last = "Status", "FPS", "Motion px", "Events", "Last motion"
    elif left_width >= 44:
        h_status, h_fps, h_motion, h_events, h_last = "Status", "FPS", "Mpx", "Ev", "Last"
    else:
        h_status, h_fps, h_motion, h_events, h_last = "St", "FPS", "Mpx", "Ev", "Last"

    table = Table(box=None, padding=(0, 1), show_header=True, header_style="bold cyan")
    table.add_column("ID", style="bold")
    table.add_column(h_status)
    table.add_column(h_fps, justify="right")
    table.add_column(h_motion, justify="right")
    table.add_column(h_events, justify="right")
    table.add_column(h_last)

    for cam_id, cam in stats.cameras.items():
        if cam.status == "connected":
            status = Text("● connected" if left_width >= 44 else "●", style="green")
        elif cam.status == "disconnected":
            status = Text("● disconnected" if left_width >= 44 else "✕", style="red")
        else:
            status = Text("◌ connecting" if left_width >= 44 else "◌", style="yellow")
        table.add_row(
            cam_id, status,
            f"{cam.fps:.1f}", f"{cam.motion_score:,}",
            str(cam.motion_events), cam.last_motion,
        )

    if not stats.cameras:
        table.add_row("—", Text("no cameras", style="dim"), "—", "—", "—", "—")

    return Panel(table, title="[bold]Cameras", border_style="cyan")


def _llm_panel() -> Panel:
    llm = stats.llm
    now = time.monotonic()
    since_last = now - llm.last_call_ts if llm.last_call_ts else None
    last_str = "never" if since_last is None else f"{int(since_last)}s ago"
    if since_last is None:
        cd_str = "—"
    else:
        remaining = max(0.0, llm.cooldown_seconds - since_last)
        cd_str = f"{remaining:.0f}s" if remaining > 0 else "[green]ready[/]"

    table = Table(box=None, padding=(0, 1), show_header=False)
    table.add_column("Key", style="dim", width=18)
    table.add_column("Value", style="bold")
    table.add_row("Model", f"[cyan]{llm.model}[/]")
    table.add_row("API calls", str(llm.total_calls))
    table.add_row("Suspicious hits", f"[red]{llm.suspicious_hits}[/]" if llm.suspicious_hits else "0")
    table.add_row("Last call", last_str)
    table.add_row("Cooldown", cd_str)

    return Panel(table, title="[bold]LLM Analyzer", border_style="magenta")


def _alerts_panel() -> Panel:
    table = Table(box=None, padding=(0, 1), show_header=True, header_style="bold red")
    table.add_column("Time", style="dim", width=10)
    table.add_column("Camera", width=8)
    table.add_column("Reason")

    entries = stats.alerts.log[-5:]
    for ts, cam, reason in reversed(entries):
        table.add_row(ts, cam, reason)
    if not entries:
        table.add_row("—", "—", Text("no alerts yet", style="dim"))

    sent = stats.alerts.total_sent
    title = f"[bold]Alerts[/] — [red]{sent} sent[/]" if sent else "[bold]Alerts[/]"
    return Panel(table, title=title, border_style="red")


def _log_panel(visible_lines: int) -> Panel:
    all_entries = stats.get_all_log()
    total = len(all_entries)

    offset = _get_scroll()
    # Auto-scroll to bottom when offset is 0; clamp when scrolled up
    max_offset = max(0, total - visible_lines)
    offset = min(offset, max_offset)

    end = total - offset
    start = max(0, end - visible_lines)
    shown = all_entries[start:end]

    text = Text()
    for ts, level, message in shown:
        style = _LOG_STYLES.get(level, "dim")
        text.append(f"{ts} ", style="dim")
        text.append(f"[{level:<6}]", style=style)
        text.append(f" {message}\n")

    if not all_entries:
        text.append("no log entries yet", style="dim")

    # Scroll indicator
    if total > visible_lines and offset > 0:
        scroll_info = f" ↑ {offset} lines below newest"
        title = f"[bold]Logs[/] [dim]{scroll_info}[/]"
    elif total > visible_lines:
        title = "[bold]Logs[/] [dim](live)[/]"
    else:
        title = "[bold]Logs[/]"

    return Panel(text, title=title, border_style="dim")


def _footer_text() -> Text:
    t = Text(justify="center")
    t.append("↑↓", style="bold")
    t.append(" scroll logs  ", style="dim")
    t.append("Ctrl+C", style="bold")
    t.append(" quit", style="dim")
    return t


# ── Layout ────────────────────────────────────────────────────────────────────

def _make_layout() -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=1),
    )
    layout["body"].split_row(
        Layout(name="left", ratio=2),
        Layout(name="logs", ratio=3),
    )
    layout["left"].split_column(
        Layout(name="cameras"),
        Layout(name="llm", size=9),
        Layout(name="alerts"),
    )
    return layout


def _update_layout(layout: Layout, console: Console):
    # Log panel height = body height minus panel borders (2 lines)
    log_lines = max(4, console.height - 3 - 1 - 2)  # total - header - footer - borders

    # Left panel takes 2/5 of terminal width; subtract 4 for panel borders/padding
    left_width = max(0, (console.width * 2 // 5) - 4)

    layout["header"].update(_header_panel())
    layout["left"]["cameras"].update(_cameras_panel(left_width))
    layout["left"]["llm"].update(_llm_panel())
    layout["left"]["alerts"].update(_alerts_panel())
    layout["logs"].update(_log_panel(log_lines))
    layout["footer"].update(_footer_text())


# ── Keyboard listener ─────────────────────────────────────────────────────────

def _keyboard_listener():
    """Daemon thread: reads arrow keys from stdin to scroll the log panel."""
    if not sys.stdin.isatty():
        return

    if sys.platform == "win32":
        _keyboard_listener_windows()
    else:
        _keyboard_listener_unix()


def _keyboard_listener_windows():
    import msvcrt
    while True:
        if msvcrt.kbhit():
            ch = msvcrt.getch()
            if ch == b"\xe0":  # extended key prefix (arrow keys)
                ch2 = msvcrt.getch()
                if ch2 == b"H":    # ↑
                    _adjust_scroll(3)
                elif ch2 == b"P":  # ↓
                    _adjust_scroll(-3)
        time.sleep(0.05)


def _keyboard_listener_unix():
    import select
    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    atexit.register(termios.tcsetattr, fd, termios.TCSADRAIN, old_settings)

    try:
        tty.setcbreak(fd)  # cbreak: no line buffering, but signals (Ctrl+C) still work
        while True:
            ready, _, _ = select.select([sys.stdin], [], [], 0.05)
            if not ready:
                continue
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                # Arrow keys arrive as ESC [ A/B — wait briefly for the rest
                ready2, _, _ = select.select([sys.stdin], [], [], 0.05)
                if ready2:
                    rest = sys.stdin.read(2)
                    if rest == "[A":    # ↑ — scroll toward older entries
                        _adjust_scroll(3)
                    elif rest == "[B":  # ↓ — scroll toward newer entries
                        _adjust_scroll(-3)
    except Exception:
        pass
    finally:
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        except Exception:
            pass


# ── Dashboard runner ──────────────────────────────────────────────────────────

def start():
    """Start the full-screen live dashboard and keyboard listener in daemon threads."""
    import config as _config
    refresh_rate = _config.DASHBOARD_REFRESH_RATE

    console = Console()
    layout = _make_layout()

    def _run():
        interval = 1.0 / refresh_rate
        with Live(layout, console=console, screen=True, refresh_per_second=refresh_rate):
            while True:
                _update_layout(layout, console)
                _scroll_event.wait(timeout=interval)
                _scroll_event.clear()

    threading.Thread(target=_keyboard_listener, daemon=True).start()
    threading.Thread(target=_run, daemon=True).start()
