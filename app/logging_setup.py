import logging
import sys

from loguru import logger

from app.config import settings


class InterceptHandler(logging.Handler):
    def emit(self, record):
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        logger.opt(depth=6, exception=record.exc_info).log(level, record.getMessage())


def setup_logging():
    logger.remove()
    logger.add(sys.stderr, level=settings.log.level)
    if settings.log.to_file:
        logger.add(
            f"{settings.log.dir}/app.log",
            level=settings.log.level,
            rotation=settings.log.rotation,
            retention=settings.log.retention,
        )
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        lg = logging.getLogger(name)
        lg.handlers = [InterceptHandler()]
        lg.propagate = False
