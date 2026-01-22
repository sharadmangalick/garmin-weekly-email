"""User configuration management for training email system."""

import json
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from config import config


# Race distance mapping for pace calculations
RACE_DISTANCES = {
    "5k": 3.1,
    "10k": 6.2,
    "half_marathon": 13.1,
    "marathon": 26.2,
    "ultra": 50.0,
    "custom": None  # User-specified
}


class UserConfig:
    """Manages user profile and training goals."""

    DEFAULT_CONFIG = {
        "email": "your@gmail.com",
        "name": "Runner",
        # Goal category: "race" or "non_race"
        "goal_category": "race",
        # For race goals: "5k", "10k", "half_marathon", "marathon", "ultra", "custom"
        # For non-race goals: "build_mileage", "maintain_fitness", "base_building", "return_from_injury"
        "goal_type": "marathon",
        "goal_target": "sub-4-hour",
        "goal_time_minutes": 240,
        "goal_date": "2026-03-05",
        # Custom distance in miles (only used when goal_type is "custom")
        "custom_distance_miles": None,
        # Target weekly mileage (used for non-race goals)
        "target_weekly_mileage": None,
        "current_weekly_mileage": 35,
        "experience_level": "intermediate",
        "preferred_long_run_day": "sunday",
        "email_day": "sunday",
        "email_time": "07:00",
        "timezone": "America/Los_Angeles",
        # GitHub Pages URL for goal updates (set after deployment)
        "goals_update_url": None
    }

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or config.data_dir / "user_config.json"
        self._config = {}
        self.load()

    def load(self) -> dict:
        """Load user configuration from JSON file."""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    self._config = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._config = self.DEFAULT_CONFIG.copy()
        else:
            self._config = self.DEFAULT_CONFIG.copy()
        return self._config

    def save(self) -> None:
        """Save current configuration to JSON file."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, 'w') as f:
            json.dump(self._config, f, indent=2)

    def update(self, **kwargs) -> None:
        """Update configuration values."""
        self._config.update(kwargs)
        self.save()

    @property
    def email(self) -> str:
        return self._config.get("email", self.DEFAULT_CONFIG["email"])

    @property
    def name(self) -> str:
        return self._config.get("name", self.DEFAULT_CONFIG["name"])

    @property
    def goal_type(self) -> str:
        return self._config.get("goal_type", self.DEFAULT_CONFIG["goal_type"])

    @property
    def goal_target(self) -> str:
        return self._config.get("goal_target", self.DEFAULT_CONFIG["goal_target"])

    @property
    def goal_time_minutes(self) -> int:
        return self._config.get("goal_time_minutes", self.DEFAULT_CONFIG["goal_time_minutes"])

    @property
    def goal_date(self) -> date:
        date_str = self._config.get("goal_date", self.DEFAULT_CONFIG["goal_date"])
        return datetime.strptime(date_str, "%Y-%m-%d").date()

    @property
    def current_weekly_mileage(self) -> int:
        return self._config.get("current_weekly_mileage", self.DEFAULT_CONFIG["current_weekly_mileage"])

    @property
    def experience_level(self) -> str:
        return self._config.get("experience_level", self.DEFAULT_CONFIG["experience_level"])

    @property
    def preferred_long_run_day(self) -> str:
        return self._config.get("preferred_long_run_day", self.DEFAULT_CONFIG["preferred_long_run_day"])

    @property
    def email_day(self) -> str:
        return self._config.get("email_day", self.DEFAULT_CONFIG["email_day"])

    @property
    def email_time(self) -> str:
        return self._config.get("email_time", self.DEFAULT_CONFIG["email_time"])

    @property
    def timezone(self) -> str:
        return self._config.get("timezone", self.DEFAULT_CONFIG["timezone"])

    @property
    def goal_category(self) -> str:
        return self._config.get("goal_category", self.DEFAULT_CONFIG["goal_category"])

    @property
    def custom_distance_miles(self) -> Optional[float]:
        return self._config.get("custom_distance_miles")

    @property
    def target_weekly_mileage(self) -> Optional[int]:
        return self._config.get("target_weekly_mileage")

    @property
    def goals_update_url(self) -> Optional[str]:
        return self._config.get("goals_update_url")

    def get_race_distance(self) -> float:
        """Get the race distance in miles based on goal type."""
        if self.goal_type == "custom" and self.custom_distance_miles:
            return self.custom_distance_miles
        return RACE_DISTANCES.get(self.goal_type, 26.2)  # Default to marathon

    def is_race_goal(self) -> bool:
        """Check if current goal is a race goal."""
        return self.goal_category == "race"

    def weeks_until_race(self) -> int:
        """Calculate weeks remaining until race day."""
        today = date.today()
        delta = self.goal_date - today
        return max(0, delta.days // 7)

    def days_until_race(self) -> int:
        """Calculate days remaining until race day."""
        today = date.today()
        delta = self.goal_date - today
        return max(0, delta.days)

    def get_training_phase(self) -> str:
        """Determine current training phase based on weeks to race."""
        weeks = self.weeks_until_race()

        if weeks > 12:
            return "base"
        elif weeks > 6:
            return "build"
        elif weeks > 3:
            return "peak"
        elif weeks > 0:
            return "taper"
        else:
            return "race_week"

    def get_target_pace(self) -> str:
        """Calculate target pace from goal time and distance."""
        total_minutes = self.goal_time_minutes
        distance = self.get_race_distance()

        if distance <= 0:
            distance = 26.2  # Fallback to marathon

        pace_per_mile = total_minutes / distance
        minutes = int(pace_per_mile)
        seconds = int((pace_per_mile - minutes) * 60)
        return f"{minutes}:{seconds:02d}"

    def to_dict(self) -> dict:
        """Return configuration as dictionary."""
        result = {
            "email": self.email,
            "name": self.name,
            "goal_category": self.goal_category,
            "goal_type": self.goal_type,
            "goal_target": self.goal_target,
            "goal_time_minutes": self.goal_time_minutes,
            "goal_date": self.goal_date.isoformat() if self.is_race_goal() else None,
            "custom_distance_miles": self.custom_distance_miles,
            "target_weekly_mileage": self.target_weekly_mileage,
            "race_distance_miles": self.get_race_distance() if self.is_race_goal() else None,
            "current_weekly_mileage": self.current_weekly_mileage,
            "experience_level": self.experience_level,
            "preferred_long_run_day": self.preferred_long_run_day,
            "email_day": self.email_day,
            "email_time": self.email_time,
            "timezone": self.timezone,
            "goals_update_url": self.goals_update_url,
        }

        # Add race-specific fields
        if self.is_race_goal():
            result.update({
                "weeks_until_race": self.weeks_until_race(),
                "days_until_race": self.days_until_race(),
                "training_phase": self.get_training_phase(),
                "target_pace": self.get_target_pace(),
            })
        else:
            # For non-race goals, use different phase determination
            result.update({
                "weeks_until_race": None,
                "days_until_race": None,
                "training_phase": "maintenance" if self.goal_type == "maintain_fitness" else "build",
                "target_pace": None,
            })

        return result

    def is_configured(self) -> bool:
        """Check if user has configured their profile."""
        return self.email != "your@gmail.com"


# Global instance
user_config = UserConfig()
