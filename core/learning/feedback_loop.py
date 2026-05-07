import json
import os
from typing import Dict, List, Any, Optional
from pydantic import BaseModel
import time

WEIGHTS_FILE = "C:\\Users\\menum\\brav os\\core\\routing\\routing_weights.json"

class FeedbackEntry(BaseModel):
    query: str
    selected_agent: str
    success: bool
    latency: float
    timestamp: float = time.time()

class FeedbackLoop:
    """
    Autonomous Feedback Loop system for Brav OS.
    Stores query performance and adjusts routing logic weights.
    """
    
    def __init__(self, weights_path: str = WEIGHTS_FILE):
        self.weights_path = weights_path
        self._ensure_weights_exist()

    def _ensure_weights_exist(self):
        """Ensures the weights file exists with default values."""
        if not os.path.exists(self.weights_path):
            # Default weights for 15 sub-agents
            default_weights = {
                "researcher": 1.0,
                "coder": 1.0,
                "security_auditor": 1.0,
                "data_scientist": 1.0,
                "devops_expert": 1.0,
                "architect": 1.0,
                "qa_tester": 1.0,
                "writer": 1.0,
                "legal_advisor": 1.0,
                "math_expert": 1.0,
                "translator": 1.0,
                "ux_designer": 1.0,
                "database_admin": 1.0,
                "network_engineer": 1.0,
                "product_manager": 1.0
            }
            with open(self.weights_path, 'w') as f:
                json.dump(default_weights, f, indent=4)

    def record_feedback(self, feedback: FeedbackEntry):
        """
        Stores feedback into a local JSONL file for offline analysis or auto-tuning.
        """
        log_path = "C:\\Users\\menum\\brav os\\core\\learning\\feedback_log.jsonl"
        with open(log_path, 'a') as f:
            f.write(feedback.model_dump_json() + "\n")
        
        # Trigger an 'Autonomous Fine-tune' if conditions met
        self.fine_tune_routing(feedback.selected_agent, feedback.success)

    def fine_tune_routing(self, agent: str, success: bool):
        """
        Adjusts agent weights based on success/failure.
        Slightly increases weight on success, decreases on failure.
        """
        with open(self.weights_path, 'r') as f:
            weights = json.load(f)
        
        if agent in weights:
            # Learning rate (alpha) = 0.05
            alpha = 0.05
            if success:
                weights[agent] = min(2.0, weights[agent] + alpha)
            else:
                weights[agent] = max(0.1, weights[agent] - alpha)
            
            with open(self.weights_path, 'w') as f:
                json.dump(weights, f, indent=4)
            print(f"Autonomous Adjustment: Updated {agent} weight to {weights[agent]:.2f}")

    def get_weights(self) -> Dict[str, float]:
        """Returns the current routing weights."""
        with open(self.weights_path, 'r') as f:
            return json.load(f)
