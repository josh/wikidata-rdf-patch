import logging
import os
from typing import Literal


def _actions_log_level(levelno: int) -> Literal["debug", "notice", "error", "warning"]:
    if levelno >= 40:
        return "error"
    elif levelno >= 30:
        return "warning"
    elif levelno >= 20:
        return "notice"
    else:
        return "debug"


class Formatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        levelname = _actions_log_level(record.levelno)
        title = f"{record.module}.{record.funcName}"
        message = record.getMessage()
        return f"::{levelname} file={record.filename},line={record.lineno},title={title}::{message}"


handler = logging.StreamHandler()
handler.setFormatter(Formatter())

_setup = False


def setup() -> None:
    global _setup
    if _setup:
        return

    _logger = logging.getLogger("")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        _logger.addHandler(handler)
    if os.environ.get("RUNNER_DEBUG") == "1":
        _logger.setLevel(logging.DEBUG)

    _setup = True
