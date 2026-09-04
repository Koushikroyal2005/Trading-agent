import sys
from functools import lru_cache
from pathlib import Path

from loguru import logger

from backend.utils.config import get_settings


@lru_cache(maxsize=1)
def configure_logging():
    settings = get_settings()
    log_dir = Path(settings.hdd_storage_path) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(sys.stderr, level=settings.log_level, serialize=True)
    logger.add(log_dir / "vector_{time:YYYY-MM-DD}.log", rotation="00:00", retention="7 days", compression="gz", serialize=True, enqueue=True)
    return logger

