import logging
import json
import uuid
import sys
from datetime import datetime, timezone
from contextvars import ContextVar
from typing import Any, Dict, Optional

# Context Variables to store trace and mission context across async calls
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")
mission_id_var: ContextVar[str] = ContextVar("mission_id", default="")

class BravosJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "module": record.module,
            "func": record.funcName,
            "trace_id": trace_id_var.get() or getattr(record, "trace_id", "N/A"),
            "mission_id": mission_id_var.get() or getattr(record, "mission_id", "N/A"),
        }
        
        # Add extra fields if they exist
        if hasattr(record, "extra_fields"):
            log_entry.update(record.extra_fields)
            
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_entry)

def setup_logger(name: str = "bravos"):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # Avoid duplicate handlers
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(BravosJsonFormatter())
        logger.addHandler(handler)
        
    return logger

# Convenience functions to manage context
def set_context(trace_id: str, mission_id: Optional[str] = None):
    trace_id_var.set(trace_id)
    if mission_id:
        mission_id_var.set(mission_id)

def get_logger(name: str = "bravos"):
    return setup_logger(name)
