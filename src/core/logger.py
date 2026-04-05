import logging
from pathlib import Path

def setup_logger(level: str = "INFO", log_file: str = "logs/bot.log"):
    Path("logs").mkdir(exist_ok=True)
    logger = logging.getLogger("rebalance_bot")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    fmt = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")

    if not logger.handlers:
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        logger.addHandler(sh)

        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    logger.propagate = False
    return logger
