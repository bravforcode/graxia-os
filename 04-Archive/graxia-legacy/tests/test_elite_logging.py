import sys
import os
import json
import io

# Add root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))
from packages.logging.python.logger import get_logger, set_context

def test_enterprise_logging():
    print("🚀 Testing Elite Contextual Logger...")
    
    # Redirect stdout to capture the log output
    log_output = io.StringIO()
    logger = get_logger("test")
    
    # Manually add handler to capture output for assertion
    import logging
    from packages.logging.python.logger import BravosJsonFormatter
    handler = logging.StreamHandler(log_output)
    handler.setFormatter(BravosJsonFormatter())
    logger.addHandler(handler)

    # 1. Set Context
    trace_id = "trace_gold_123"
    mission_id = "mis_scout_001"
    set_context(trace_id, mission_id)
    
    # 2. Log something
    logger.info("Agent starting work on task X")
    
    # 3. Verify output
    output = log_output.getvalue()
    log_json = json.loads(output.splitlines()[-1])
    
    print(f"--- Captured Log Entry: {log_json}")
    
    assert log_json["trace_id"] == trace_id
    assert log_json["mission_id"] == mission_id
    assert "Agent starting work" in log_json["message"]
    
    print("✅ Test Passed: Logger correctly injects trace and mission context.")

if __name__ == "__main__":
    test_enterprise_logging()
