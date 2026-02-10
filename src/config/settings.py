"""
Configuration settings for Project Position System
"""
import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Application
    APP_NAME: str = "Project Position System"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = Field(default=False, validation_alias="DEBUG")
    
    # Paths
    BASE_DIR: Path = Path(__file__).parent.parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    LOGS_DIR: Path = BASE_DIR / "logs"
    
    # Database
    DATABASE_PATH: Path = Field(
        default=BASE_DIR / "data" / "project_position.db",
        validation_alias="DATABASE_PATH"
    )
    
    # LLM Configuration
    OPENAI_API_KEY: Optional[str] = Field(default=None, validation_alias="OPENAI_API_KEY")
    OPENAI_MODEL: str = Field(default="gpt-4-turbo", validation_alias="OPENAI_MODEL")
    LLM_TEMPERATURE: float = Field(default=0.3, validation_alias="LLM_TEMPERATURE")
    LLM_MAX_TOKENS: int = Field(default=2000, validation_alias="LLM_MAX_TOKENS")
    
    # GitHub Configuration
    GITHUB_TOKEN: Optional[str] = Field(default=None, validation_alias="GITHUB_TOKEN")
    GITHUB_ORG: Optional[str] = Field(default=None, validation_alias="GITHUB_ORG")
    GITHUB_REPO: Optional[str] = Field(default=None, validation_alias="GITHUB_REPO")
    GITHUB_WEBHOOK_SECRET: Optional[str] = Field(default=None, validation_alias="GITHUB_WEBHOOK_SECRET")
    GITHUB_API_BASE_URL: str = "https://api.github.com"
    
    # Lark Configuration
    LARK_APP_ID: Optional[str] = Field(default=None, validation_alias="LARK_APP_ID")
    LARK_APP_SECRET: Optional[str] = Field(default=None, validation_alias="LARK_APP_SECRET")
    LARK_BOT_NAME: str = Field(default="ProjectPositionBot", validation_alias="LARK_BOT_NAME")
    LARK_WEBHOOK_VERIFICATION_TOKEN: Optional[str] = Field(default=None, validation_alias="LARK_WEBHOOK_VERIFICATION_TOKEN")
    LARK_API_BASE_URL: str = "https://open.feishu.cn/open-apis"
    
    # Sync Settings
    SYNC_INTERVAL_SECONDS: int = Field(default=300, validation_alias="SYNC_INTERVAL_SECONDS")
    RETRY_MAX_ATTEMPTS: int = Field(default=3, validation_alias="RETRY_MAX_ATTEMPTS")
    RETRY_BACKOFF_FACTOR: int = Field(default=2, validation_alias="RETRY_BACKOFF_FACTOR")
    GITHUB_SYNC_ENABLED: bool = Field(default=True, validation_alias="GITHUB_SYNC_ENABLED")
    LARK_SYNC_ENABLED: bool = Field(default=True, validation_alias="LARK_SYNC_ENABLED")
    
    # Task Processing
    MAX_TASKS_PER_BATCH: int = Field(default=10, validation_alias="MAX_TASKS_PER_BATCH")
    AUTO_ASSIGN_TASKS: bool = Field(default=True, validation_alias="AUTO_ASSIGN_TASKS")
    
    # Notifications
    NOTIFICATION_ENABLED: bool = Field(default=True, validation_alias="NOTIFICATION_ENABLED")
    
    # API Server (if running as web service)
    API_HOST: str = Field(default="0.0.0.0", validation_alias="API_HOST")
    API_PORT: int = Field(default=8000, validation_alias="API_PORT")
    API_WORKERS: int = Field(default=4, validation_alias="API_WORKERS")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Ensure directories exist
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.LOGS_DIR.mkdir(parents=True, exist_ok=True)


# Global settings instance
settings = Settings()
