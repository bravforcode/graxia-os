"""
Configuration Management

Provides hot reload, validation, and configuration UI.
"""
import logging
from typing import Optional
from pathlib import Path
from datetime import datetime, timezone

import yaml
from pydantic import BaseModel, validator

logger = logging.getLogger(__name__)


class AgentConfig(BaseModel):
    """Configuration for individual agent."""
    enabled: bool = True
    schedule: Optional[str] = None
    max_items: int = 100
    timeout_seconds: int = 300
    retry_attempts: int = 3


class ScraperConfig(BaseModel):
    """Configuration for scraper."""
    enabled: bool = True
    platform: str
    frequency_hours: int = 6
    max_pages: int = 5
    use_openclaw: bool = False


class NotificationConfig(BaseModel):
    """Configuration for notifications."""
    enabled: bool = True
    max_per_hour: int = 10
    urgent_bypass: bool = True
    channels: list[str] = ["telegram"]


class CostConfig(BaseModel):
    """Configuration for cost limits."""
    daily_budget_usd: float = 1.67
    monthly_budget_usd: float = 50.0
    alert_threshold: float = 0.8
    auto_pause_at_limit: bool = True


class SystemConfig(BaseModel):
    """Complete system configuration."""
    
    # Agents
    job_hunter: AgentConfig = AgentConfig()
    network_builder: AgentConfig = AgentConfig()
    email_manager: AgentConfig = AgentConfig()
    personal_assistant: AgentConfig = AgentConfig()
    
    # Scrapers
    scrapers: dict[str, ScraperConfig] = {
        "linkedin": ScraperConfig(platform="linkedin", use_openclaw=True),
        "upwork": ScraperConfig(platform="upwork", use_openclaw=True),
        "fiverr": ScraperConfig(platform="fiverr", use_openclaw=True),
        "fastwork": ScraperConfig(platform="fastwork", use_openclaw=False),
        "devpost": ScraperConfig(platform="devpost", use_openclaw=False)
    }
    
    # Notifications
    notifications: NotificationConfig = NotificationConfig()
    
    # Costs
    costs: CostConfig = CostConfig()
    
    # General
    timezone: str = "Asia/Bangkok"
    log_level: str = "INFO"
    debug_mode: bool = False
    
    @validator("log_level")
    def validate_log_level(cls, v):
        """Validate log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level. Must be one of: {valid_levels}")
        return v.upper()


class ConfigManager:
    """
    Configuration manager with hot reload and validation.
    
    Features:
    - Load configuration from YAML file
    - Validate configuration schema
    - Hot reload on file changes
    - Configuration versioning
    - Audit trail for changes
    """
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = Path(config_path)
        self.config: Optional[SystemConfig] = None
        self.last_modified: Optional[datetime] = None
        self.version: int = 1
        
        # Load initial configuration
        self.load_config()
    
    def load_config(self) -> SystemConfig:
        """Load configuration from file."""
        try:
            if not self.config_path.exists():
                logger.warning(f"Config file not found: {self.config_path}. Using defaults.")
                self.config = SystemConfig()
                self.save_config()
                return self.config
            
            # Read YAML file
            with open(self.config_path, 'r') as f:
                config_data = yaml.safe_load(f)
            
            # Validate and parse
            self.config = SystemConfig(**config_data)
            self.last_modified = datetime.fromtimestamp(
                self.config_path.stat().st_mtime,
                tz=timezone.utc
            )
            
            logger.info(f"Configuration loaded from {self.config_path}")
            return self.config
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            # Use defaults on error
            self.config = SystemConfig()
            return self.config
    
    def save_config(self) -> None:
        """Save configuration to file."""
        try:
            # Convert to dict
            config_dict = self.config.dict()
            
            # Write YAML file
            with open(self.config_path, 'w') as f:
                yaml.dump(config_dict, f, default_flow_style=False, sort_keys=False)
            
            self.last_modified = datetime.now(timezone.utc)
            self.version += 1
            
            logger.info(f"Configuration saved to {self.config_path} (version {self.version})")
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")
    
    def reload_if_changed(self) -> bool:
        """
        Check if config file changed and reload if needed.
        
        Returns:
            True if reloaded, False otherwise
        """
        try:
            if not self.config_path.exists():
                return False
            
            current_mtime = datetime.fromtimestamp(
                self.config_path.stat().st_mtime,
                tz=timezone.utc
            )
            
            if self.last_modified and current_mtime > self.last_modified:
                logger.info("Configuration file changed. Reloading...")
                self.load_config()
                return True
            
            return False
        except Exception as e:
            logger.error(f"Failed to check config changes: {e}")
            return False
    
    def update_config(self, updates: dict) -> bool:
        """
        Update configuration with new values.
        
        Args:
            updates: Dictionary of configuration updates
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Merge updates with current config
            config_dict = self.config.dict()
            self._deep_update(config_dict, updates)
            
            # Validate new configuration
            new_config = SystemConfig(**config_dict)
            
            # Save if valid
            self.config = new_config
            self.save_config()
            
            logger.info(f"Configuration updated: {list(updates.keys())}")
            return True
        except Exception as e:
            logger.error(f"Failed to update configuration: {e}")
            return False
    
    def _deep_update(self, base: dict, updates: dict) -> None:
        """Deep update dictionary."""
        for key, value in updates.items():
            if isinstance(value, dict) and key in base and isinstance(base[key], dict):
                self._deep_update(base[key], value)
            else:
                base[key] = value
    
    def get_agent_config(self, agent_name: str) -> Optional[AgentConfig]:
        """Get configuration for specific agent."""
        return getattr(self.config, agent_name, None)
    
    def get_scraper_config(self, platform: str) -> Optional[ScraperConfig]:
        """Get configuration for specific scraper."""
        return self.config.scrapers.get(platform)
    
    def is_agent_enabled(self, agent_name: str) -> bool:
        """Check if agent is enabled."""
        agent_config = self.get_agent_config(agent_name)
        return agent_config.enabled if agent_config else False
    
    def is_scraper_enabled(self, platform: str) -> bool:
        """Check if scraper is enabled."""
        scraper_config = self.get_scraper_config(platform)
        return scraper_config.enabled if scraper_config else False
    
    def get_config_dict(self) -> dict:
        """Get configuration as dictionary."""
        return self.config.dict()
    
    def get_config_json(self) -> str:
        """Get configuration as JSON string."""
        return self.config.json(indent=2)
    
    def validate_config(self, config_dict: dict) -> tuple[bool, Optional[str]]:
        """
        Validate configuration dictionary.
        
        Returns:
            (is_valid, error_message)
        """
        try:
            SystemConfig(**config_dict)
            return True, None
        except Exception as e:
            return False, str(e)


# Global instance
config_manager = ConfigManager()


# Auto-reload configuration every 5 minutes
import asyncio

async def auto_reload_config():
    """Background task to auto-reload configuration."""
    while True:
        try:
            await asyncio.sleep(300)  # 5 minutes
            if config_manager.reload_if_changed():
                logger.info("Configuration auto-reloaded")
        except Exception as e:
            logger.error(f"Auto-reload failed: {e}")
