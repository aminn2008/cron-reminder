import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"

_HANDLER_FLAG = "_cronreminder_file"


def setup_logging() -> None:
    LOGS_DIR.mkdir(exist_ok=True)
    root = logging.getLogger()
    if any(getattr(h, _HANDLER_FLAG, False) for h in root.handlers):
        return

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    fh = RotatingFileHandler(
        LOGS_DIR / "app.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    fh.setLevel(logging.INFO)
    setattr(fh, _HANDLER_FLAG, True)
    root.addHandler(fh)
    root.setLevel(logging.INFO)


    logging.getLogger("uvicorn.access").propagate = False
    logging.getLogger("uvicorn.error").propagate = False
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
