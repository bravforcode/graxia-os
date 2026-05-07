import logging
import json
import time
import sys
from contextvars import ContextVar
from typing import Any, Dict, Optional, List
from datetime import datetime

from collections import deque

# Context variable for tracking request IDs
request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)

class DequeHandler(logging.Handler):
    """
    Log handler that keeps the last N records in memory.
    Useful for self-healing and debugging.
    """
    def __init__(self, maxlen: int = 100):
        super().__init__()
        self.logs = deque(maxlen=maxlen)

    def emit(self, record):
        self.logs.append(self.format(record))

    def get_logs(self, n: int = 50) -> List[str]:
        return list(self.logs)[-n:]

# Global deque handler for retrieving recent logs
memory_handler = DequeHandler(maxlen=200)

class JSONFormatter(logging.Formatter):
    """
    Structured JSON log formatter for enterprise observability.
    """
    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "request_id": request_id_ctx.get(),
            "thread": record.threadName,
        }
        
        # Include extra attributes from the record
        if hasattr(record, "extra"):
            log_data.update(record.extra)
            
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_data)

def setup_logger(name: str = "brav_os", level: str = "INFO") -> logging.Logger:
    """
    Configures and returns a logger instance with JSON formatting.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Avoid duplicate handlers if setup_logger is called multiple times
    if not logger.handlers:
        # Stream handler for stdout
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setFormatter(JSONFormatter())
        logger.addHandler(stdout_handler)
        
        # Memory handler for self-healing
        memory_handler.setFormatter(JSONFormatter())
        logger.addHandler(memory_handler)
        
    return logger

# Pre-configured default logger
logger = setup_logger()
