import os
import sys
import logging
from typing import Optional

# ANSI Color Codes for clean Docker console output
class LogColors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    MAGENTA = "\033[35m"

class M5Formatter(logging.Formatter):
    """Clean, human-readable structured formatter with ANSI colors for M5 logs."""
    
    LEVEL_COLORS = {
        logging.DEBUG: LogColors.DIM + LogColors.BLUE,
        logging.INFO: LogColors.GREEN,
        logging.WARNING: LogColors.YELLOW,
        logging.ERROR: LogColors.RED,
        logging.CRITICAL: LogColors.BOLD + LogColors.RED,
    }

    def format(self, record: logging.LogRecord) -> str:
        # Time string in ISO format
        time_str = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        
        # Colorized level name
        level_color = self.LEVEL_COLORS.get(record.levelno, "")
        level_str = f"{level_color}{record.levelname:<7}{LogColors.RESET}"
        
        # Component tag
        component_name = record.name if record.name.startswith("m5") else f"m5.{record.name}"
        component_str = f"{LogColors.CYAN}[{component_name}]{LogColors.RESET}"

        # Combine formatted output
        log_line = f"{LogColors.DIM}{time_str}{LogColors.RESET} {level_str} {component_str} {record.getMessage()}"
        
        if record.exc_info:
            log_line += "\n" + self.formatException(record.exc_info)
        return log_line

def setup_m5_logger(name: str = "m5", level: Optional[str] = None) -> logging.Logger:
    """Configures and returns a clean M5 logger singleton."""
    log_level_str = (level or os.getenv("LOG_LEVEL") or os.getenv("M5_LOG_LEVEL") or "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    # Avoid duplicate handlers
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(log_level)
        handler.setFormatter(M5Formatter())
        logger.addHandler(handler)
        logger.propagate = False

    return logger

# Global default logger instance
logger = setup_m5_logger("m5")
