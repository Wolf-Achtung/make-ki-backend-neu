from loguru import logger
import sys, os

def configure_logging():
    logger.remove()
    logger.add(sys.stdout, level=os.environ.get("LOG_LEVEL", "INFO"), enqueue=True, backtrace=False, diagnose=False,
               format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")
    return logger
