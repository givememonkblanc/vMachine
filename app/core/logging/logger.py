import json
import logging
import logging.handlers
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOG_DIR = Path(__file__).resolve().parent.parent.parent.parent / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers.clear()

    console_handler = logging.StreamHandler(sys.stdout)
    console_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    console_handler.setFormatter(logging.Formatter(console_format, datefmt="%Y-%m-%d %H:%M:%S"))
    console_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    root_logger.addHandler(console_handler)

    file_handler = logging.handlers.RotatingFileHandler(
        filename=str(_LOG_DIR / "okastro.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(JsonFormatter())
    file_handler.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)

    error_handler = logging.handlers.RotatingFileHandler(
        filename=str(_LOG_DIR / "error.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    error_handler.setFormatter(JsonFormatter())
    error_handler.setLevel(logging.ERROR)
    root_logger.addHandler(error_handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
