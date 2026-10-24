"""Breadcrumb logger — every step is visible so you can follow the agent's decisions."""

import logging
from rich.logging import RichHandler
from .config import cfg

logging.basicConfig(
    level=getattr(logging, cfg.LOG_LEVEL, logging.INFO),
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
)

log = logging.getLogger("trapdoor")
