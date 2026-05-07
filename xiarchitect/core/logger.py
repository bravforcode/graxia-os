"""
xiarchitect.core.logger — Structured logger
"""

import logging
import sys
from typing import Optional


def get_logger(name: str, level: Optional[int] = None) -> logging.Logger:
    """
    Get a structured logger for xiarchitect.
    
    Args:
        name: Logger name (usually __name__)
        level: Optional logging level (defaults to INFO)
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(f"xiarchitect.{name}")
    
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    logger.setLevel(level or logging.INFO)
    logger.propagate = False
    
    return logger
