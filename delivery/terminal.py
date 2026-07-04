"""Implements SPEC §4.5: terminal delivery channel (weakest level, always available)."""

from rich.console import Console
from rich.panel import Panel

from delivery.base import DeliveryMessage, render_message


class TerminalChannel:
    name = "terminal"
    max_level = "terminal"

    def __init__(self, console: Console | None = None):
        self.console = console or Console()

    async def send(self, msg: DeliveryMessage, level: str) -> None:
        self.console.print(Panel(render_message(msg), title="🔔 chief", border_style="cyan"))
