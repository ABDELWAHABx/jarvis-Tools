import logging
import sys

from app.runtime.log_buffer import log_buffer_handler

logger = logging.getLogger("tools-api")
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter(
    "%(asctime)s %(levelname)s %(name)s %(message)s"
)
handler.setFormatter(formatter)
logger.addHandler(handler)

log_buffer_handler.setFormatter(formatter)
logger.addHandler(log_buffer_handler)
