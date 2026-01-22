"""Configuration handling for Garmin Data Analyzer."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Application configuration."""

    def __init__(self):
        self.data_dir = Path(os.getenv("DATA_DIR", "./data"))

    @property
    def activities_dir(self) -> Path:
        return self.data_dir / "activities"

    @property
    def sleep_dir(self) -> Path:
        return self.data_dir / "sleep"

    @property
    def heart_rate_dir(self) -> Path:
        return self.data_dir / "heart_rate"

    @property
    def daily_summaries_dir(self) -> Path:
        return self.data_dir / "daily_summaries"

    @property
    def vo2max_dir(self) -> Path:
        return self.data_dir / "vo2max"

    @property
    def session_file(self) -> Path:
        return self.data_dir / ".garmin_session"

    @property
    def user_config_file(self) -> Path:
        return self.data_dir / "user_config.json"

    @property
    def email_queue_dir(self) -> Path:
        return self.data_dir / "email_queue"

    @property
    def anthropic_api_key(self) -> str:
        """Get Anthropic API key from environment."""
        return os.getenv("ANTHROPIC_API_KEY", "")

    def has_garmin_session(self) -> bool:
        """Check if a saved Garmin session exists."""
        return self.session_file.exists()

    def has_anthropic_key(self) -> bool:
        """Check if Anthropic API key is configured."""
        return bool(self.anthropic_api_key)

    def ensure_directories(self):
        """Create data directories if they don't exist."""
        self.activities_dir.mkdir(parents=True, exist_ok=True)
        self.sleep_dir.mkdir(parents=True, exist_ok=True)
        self.heart_rate_dir.mkdir(parents=True, exist_ok=True)
        self.daily_summaries_dir.mkdir(parents=True, exist_ok=True)
        self.vo2max_dir.mkdir(parents=True, exist_ok=True)
        self.email_queue_dir.mkdir(parents=True, exist_ok=True)


# Global config instance
config = Config()
