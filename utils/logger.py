import logging
import os
from logging.handlers import RotatingFileHandler

# Create logs folder if not exist
if not os.path.exists("logs"):
    os.makedirs("logs")

# Log formatter
formatter = logging.Formatter(
    "[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

def setup_logger(name, log_file, level=logging.INFO):
    handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3)
    handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(handler)
    logger.addHandler(console_handler)

    return logger

# Main app logger
app_logger = setup_logger("app", "logs/app.log", logging.INFO)

# Error logger
error_logger = setup_logger("error", "logs/errors.log", logging.ERROR)