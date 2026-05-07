from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Enterprise-grade configuration management using Pydantic Settings.
    Loads variables from environment or .env file.
    """
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # API Configuration
    API_V1_STR: str = "/v1"
    PROJECT_NAME: str = "Brav OS Intelligence"
    
    # Security
    API_KEY_NAME: str = "X-API-Key"
    API_KEY: str = "brav-os-secret-key" # Default for dev, override in .env
    
    # Redis Configuration
    REDIS_URL: Optional[str] = "redis://localhost:6379/0"
    
    # LLM Providers
    DEFAULT_LLM_MODEL: str = "gpt-4-turbo"
    DEFAULT_EMBEDDING_MODEL: str = "text-embedding-3-small"
    
    # Observability
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "production" # development, staging, production
    
    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60

settings = Settings()
