# utils/logger.py
import logging
import os
from logging.handlers import RotatingFileHandler

if not os.path.exists("logs"):
    os.makedirs("logs")

formatter = logging.Formatter(
    "[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

def setup_logger(name, log_file, level=logging.INFO):
    handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3)
    handler.setFormatter(formatter)
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(handler)
    logger.addHandler(console)
    return logger

app_logger = setup_logger("app", "logs/app.log", logging.INFO)
error_logger = setup_logger("error", "logs/errors.log", logging.ERROR)