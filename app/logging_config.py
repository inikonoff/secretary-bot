import logging
import sys


def configure_logging(level: str) -> None:
    root = logging.getLogger()
    root.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root.handlers.clear()
    root.addHandler(handler)

    # aiohttp access logs are noisy at INFO; keep them at WARNING.
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)
