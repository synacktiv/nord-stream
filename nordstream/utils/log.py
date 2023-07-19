"""
custom logging module.
"""

import logging
import os
from typing import Any, cast

from rich.console import Console
from rich.logging import RichHandler

# Blablabla "roll your own logging handler"
# https://github.com/Textualize/rich/issues/2647#issuecomment-1335017733
class WhitespaceStrippingConsole(Console):
    def _render_buffer(self, *args, **kwargs):
        rendered = super()._render_buffer(*args, **kwargs)
        newline_char = "\n" if rendered[-1] == "\n" else ""
        return "\n".join(line.rstrip() for line in rendered.splitlines()) + newline_char


class NordStreamLog(logging.Logger):
    # New logging level
    SUCCESS: int = 25
    VERBOSE: int = 15

    @staticmethod
    def setVerbosity(verbose: int, quiet: bool = False):
        """Set logging level accordingly to the verbose count or with quiet enable."""
        if quiet:
            logger.setLevel(logging.CRITICAL)
        elif verbose == 1:
            logger.setLevel(NordStreamLog.VERBOSE)
        elif verbose >= 2:
            logger.setLevel(logging.DEBUG)
        else:
            # Default INFO
            logger.setLevel(logging.INFO)

    def debug(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        """Change default debug text format with rich color support"""
        super(NordStreamLog, self).debug("{}[D]{} {}".format("[bold yellow3]", "[/bold yellow3]", msg), *args, **kwargs)

    def verbose(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        """Add verbose logging method with text format / rich color support"""
        if self.isEnabledFor(NordStreamLog.VERBOSE):
            self._log(NordStreamLog.VERBOSE, "{}[V]{} {}".format("[bold blue]", "[/bold blue]", msg), args, **kwargs)

    def raw(
        self,
        msg: Any,
        level=VERBOSE,
        markup=False,
        highlight=False,
        emoji=False,
        rich_parsing=False,
    ) -> None:
        """Add raw text logging, used for stream printing."""
        if rich_parsing:
            markup = True
            highlight = True
            emoji = True
        if self.isEnabledFor(level):
            if type(msg) is bytes:
                msg = msg.decode("utf-8", errors="ignore")
            # Raw message are print directly to the console bypassing logging system and auto formatting
            console.print(msg, end="", markup=markup, highlight=highlight, emoji=emoji)

    def info(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        """Change default info text format with rich color support"""
        super(NordStreamLog, self).info("{}[*]{} {}".format("[bold blue]", "[/bold blue]", msg), *args, **kwargs)

    def warning(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        """Change default warning text format with rich color support"""
        super(NordStreamLog, self).warning(
            "{}[!]{} {}".format("[bold orange3]", "[/bold orange3]", msg), *args, **kwargs
        )

    def error(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        """Change default error text format with rich color support"""
        super(NordStreamLog, self).error("{}[-]{} {}".format("[bold red]", "[/bold red]", msg), *args, **kwargs)

    def exception(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        """Change default exception text format with rich color support"""
        super(NordStreamLog, self).exception("{}[x]{} {}".format("[bold red]", "[/bold red]", msg), *args, **kwargs)

    def critical(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        """Change default critical text format with rich color support
        Add auto exit."""
        super(NordStreamLog, self).critical("{}[!]{} {}".format("[bold red]", "[/bold red]", msg), *args, **kwargs)
        exit(1)

    def success(self, msg: Any, *args: Any, **kwargs: Any) -> None:
        """Add success logging method with text format / rich color support"""
        if self.isEnabledFor(NordStreamLog.SUCCESS):
            self._log(NordStreamLog.SUCCESS, "{}[+]{} {}".format("[bold green]", "[/bold green]", msg), args, **kwargs)

    def empty_line(self, log_level: int = logging.INFO) -> None:
        """Print an empty line."""
        self.raw(os.linesep, level=log_level)


# Global rich console object
console: Console = WhitespaceStrippingConsole()

# Main logging default config
# Set default Logger class as NordStreamLog
logging.setLoggerClass(NordStreamLog)

# Add new level to the logging config
logging.addLevelName(NordStreamLog.VERBOSE, "VERBOSE")
logging.addLevelName(NordStreamLog.SUCCESS, "SUCCESS")

# Logging setup using RichHandler and minimalist text format
logging.basicConfig(
    format="%(message)s",
    handlers=[
        RichHandler(
            rich_tracebacks=True,
            show_time=False,
            markup=True,
            show_level=False,
            show_path=False,
            console=console,
        )
    ],
)

# Global logger object
logger: NordStreamLog = cast(NordStreamLog, logging.getLogger("main"))
# Default log level
logger.setLevel(logging.INFO)
