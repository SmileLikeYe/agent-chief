"""Implements SPEC §4.5: terminal delivery channel (weakest level, always available)."""

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from delivery.base import DeliveryMessage, render_message


class TerminalChannel:
    name = "terminal"
    max_level = "terminal"

    def __init__(self, console: Console | None = None):
        self.console = console or Console()

    async def send(self, msg: DeliveryMessage, level: str) -> None:
        # Text() renders the (untrusted) body literally — rich markup like
        # "[red]" or "[link=…]" in an event summary is shown, never interpreted.
        body = Text(render_message(msg))
        self.console.print(Panel(body, title="🔔 chief", border_style="cyan"))
