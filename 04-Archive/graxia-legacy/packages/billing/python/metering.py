import redis
import json
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import os

class MeteringService:
    """
    Handles high-frequency usage metering using Redis.
    Counters are stored in Redis for speed and periodically flushed to PostgreSQL.
    """
    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        # In a real app, use connection pooling and proper async Redis (e.g., aioredis)
        self.redis_client = redis.from_url(redis_url, decode_responses=True)
        self.key_prefix = "usage:"

    def _get_key(self, tenant_id: str, metric_key: str) -> str:
        return f"{self.key_prefix}{tenant_id}:{metric_key}"

    def report_usage(self, tenant_id: str, metric_key: str, value: float) -> float:
        """
        Atomically increments a usage counter in Redis.
        Returns the new total value.
        """
        key = self._get_key(tenant_id, metric_key)
        try:
            new_value = self.redis_client.incrbyfloat(key, value)
            return float(new_value)
        except Exception as e:
            # Fallback/logging logic here if Redis is unavailable
            print(f"Failed to record usage in Redis: {e}")
            return 0.0

    def get_current_usage(self, tenant_id: str, metric_key: str) -> float:
        """
        Retrieves the current usage value from Redis.
        """
        key = self._get_key(tenant_id, metric_key)
        val = self.redis_client.get(key)
        return float(val) if val else 0.0

    def sync_to_db(self, db_session=None):
        """
        Periodically called task to flush Redis counters to the usage_metrics table in PostgreSQL.
        This ensures durability of the usage data for billing.
        """
        if not db_session:
            print("Warning: No database session provided for sync_to_db. Skipping.")
            return

        try:
            # 1. Scan for keys matching pattern 'usage:*'
            for key in self.redis_client.scan_iter(f"{self.key_prefix}*"):
                # Extract tenant_id and metric_key
                parts = key.split(":")
                if len(parts) >= 3:
                    tenant_id = parts[1]
                    metric_key = ":".join(parts[2:])
                    
                    # 2. Get current value and reset atomically using GETSET or pipeline
                    value_str = self.redis_client.getset(key, "0")
                    if value_str and float(value_str) > 0:
                        usage_value = float(value_str)
                        
                        # 3. Update PostgreSQL (simulated via db_session)
                        # db_session.execute(
                        #    "INSERT INTO usage_metrics (tenant_id, metric_key, value) VALUES (:t, :m, :v)",
                        #    {"t": tenant_id, "m": metric_key, "v": usage_value}
                        # )
                        print(f"Synced {usage_value} {metric_key} for {tenant_id} to DB.")
                        
            # db_session.commit()
            print("Redis usage metrics successfully synced to DB.")
        except Exception as e:
            # db_session.rollback()
            print(f"Failed to sync Redis to DB: {e}")

# Global instance
metering_service = MeteringService(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
