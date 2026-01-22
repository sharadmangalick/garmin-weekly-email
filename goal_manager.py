"""Goal Manager - Validation and management for training goals."""

import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import date, datetime


class GoalManager:
    """Manages goal templates, validation, and configuration creation."""

    def __init__(self, templates_path: Optional[Path] = None):
        """Initialize with path to goal templates JSON."""
        self.templates_path = templates_path or Path(__file__).parent / "goal_templates.json"
        self._templates = None

    @property
    def templates(self) -> dict:
        """Load and cache goal templates."""
        if self._templates is None:
            self._templates = self._load_templates()
        return self._templates

    def _load_templates(self) -> dict:
        """Load goal templates from JSON file."""
        if self.templates_path.exists():
            with open(self.templates_path, 'r') as f:
                return json.load(f)
        return {"race_goals": {}, "non_race_goals": {}, "pace_calculations": {}}

    def get_race_goals(self) -> Dict[str, dict]:
        """Get all race goal templates."""
        return self.templates.get("race_goals", {})

    def get_non_race_goals(self) -> Dict[str, dict]:
        """Get all non-race goal templates."""
        return self.templates.get("non_race_goals", {})

    def get_all_goal_types(self) -> List[str]:
        """Get list of all available goal types."""
        race = list(self.get_race_goals().keys())
        non_race = list(self.get_non_race_goals().keys())
        return race + non_race

    def get_goal_template(self, goal_type: str) -> Optional[dict]:
        """Get template for a specific goal type."""
        if goal_type in self.get_race_goals():
            return self.get_race_goals()[goal_type]
        elif goal_type in self.get_non_race_goals():
            return self.get_non_race_goals()[goal_type]
        return None

    def is_race_goal(self, goal_type: str) -> bool:
        """Check if goal type is a race goal."""
        return goal_type in self.get_race_goals()

    def get_pace_offsets(self, goal_type: str) -> dict:
        """Get pace calculation offsets for a goal type."""
        pace_calcs = self.templates.get("pace_calculations", {})
        return pace_calcs.get(goal_type, pace_calcs.get("default", {
            "easy_offset_min": 1.0,
            "easy_offset_max": 2.0,
            "tempo_offset_min": 0.0,
            "tempo_offset_max": 0.25,
            "recovery_offset_min": 2.0,
            "recovery_offset_max": 3.0
        }))

    def get_phase_config(self, goal_type: str, phase: str) -> dict:
        """Get phase configuration for a goal type."""
        template = self.get_goal_template(goal_type)
        if template and "phases" in template:
            return template["phases"].get(phase, {})
        return {}

    def get_training_phase_for_race(self, goal_type: str, weeks_until_race: int) -> str:
        """Determine training phase based on weeks until race."""
        template = self.get_goal_template(goal_type)
        if not template or "phases" not in template:
            # Fallback to default marathon phases
            if weeks_until_race > 12:
                return "base"
            elif weeks_until_race > 6:
                return "build"
            elif weeks_until_race > 3:
                return "peak"
            elif weeks_until_race > 0:
                return "taper"
            else:
                return "race_week"

        phases = template["phases"]

        # Calculate phase thresholds from min_weeks (phases are in reverse order)
        # e.g., taper min_weeks=3 means taper starts at 3 weeks out
        threshold_weeks = []
        for phase_name in ["base", "build", "peak", "taper", "race_week"]:
            if phase_name in phases:
                min_weeks = phases[phase_name].get("min_weeks", 0)
                threshold_weeks.append((phase_name, min_weeks))

        # Sort by min_weeks descending to check in order
        threshold_weeks.sort(key=lambda x: x[1], reverse=True)

        for phase_name, min_weeks in threshold_weeks:
            if weeks_until_race > min_weeks:
                return phase_name

        return "race_week"

    def validate_goal_config(self, config: dict) -> Dict[str, Any]:
        """
        Validate a goal configuration.

        Returns:
            Dictionary with 'valid' boolean and 'errors' list
        """
        errors = []

        # Required fields
        if not config.get("goal_type"):
            errors.append("goal_type is required")

        goal_type = config.get("goal_type", "")
        goal_category = config.get("goal_category", "race")

        # Validate goal type exists
        if goal_type and goal_type not in self.get_all_goal_types():
            errors.append(f"Unknown goal_type: {goal_type}")

        # Race goal validations
        if goal_category == "race":
            # Must have a race date
            if not config.get("goal_date"):
                errors.append("goal_date is required for race goals")
            else:
                # Validate date format and future date
                try:
                    goal_date = datetime.strptime(config["goal_date"], "%Y-%m-%d").date()
                    if goal_date <= date.today():
                        errors.append("goal_date must be in the future")
                except ValueError:
                    errors.append("goal_date must be in YYYY-MM-DD format")

            # Must have goal time
            if not config.get("goal_time_minutes"):
                errors.append("goal_time_minutes is required for race goals")

            # Custom distance requires custom_distance_miles
            if goal_type == "custom" and not config.get("custom_distance_miles"):
                errors.append("custom_distance_miles is required for custom race distance")

        # Non-race goal validations
        if goal_category == "non_race":
            # Build mileage requires target
            if goal_type == "build_mileage" and not config.get("target_weekly_mileage"):
                errors.append("target_weekly_mileage is required for build_mileage goal")

        # Weekly mileage must be positive
        if config.get("current_weekly_mileage", 0) <= 0:
            errors.append("current_weekly_mileage must be positive")

        # Experience level validation
        valid_levels = ["beginner", "intermediate", "advanced"]
        if config.get("experience_level") and config["experience_level"] not in valid_levels:
            errors.append(f"experience_level must be one of: {', '.join(valid_levels)}")

        return {
            "valid": len(errors) == 0,
            "errors": errors
        }

    def create_race_goal_config(
        self,
        goal_type: str,
        goal_date: str,
        goal_time_minutes: int,
        current_weekly_mileage: int,
        experience_level: str = "intermediate",
        custom_distance_miles: Optional[float] = None,
        goal_target: Optional[str] = None,
        **kwargs
    ) -> dict:
        """Create a validated race goal configuration."""
        template = self.get_goal_template(goal_type)
        if not template:
            raise ValueError(f"Unknown goal type: {goal_type}")

        config = {
            "goal_category": "race",
            "goal_type": goal_type,
            "goal_date": goal_date,
            "goal_time_minutes": goal_time_minutes,
            "goal_target": goal_target or self._generate_goal_target(goal_time_minutes, goal_type),
            "custom_distance_miles": custom_distance_miles if goal_type == "custom" else None,
            "current_weekly_mileage": current_weekly_mileage,
            "experience_level": experience_level,
            **kwargs
        }

        validation = self.validate_goal_config(config)
        if not validation["valid"]:
            raise ValueError(f"Invalid config: {', '.join(validation['errors'])}")

        return config

    def create_non_race_goal_config(
        self,
        goal_type: str,
        current_weekly_mileage: int,
        target_weekly_mileage: Optional[int] = None,
        experience_level: str = "intermediate",
        **kwargs
    ) -> dict:
        """Create a validated non-race goal configuration."""
        template = self.get_goal_template(goal_type)
        if not template:
            raise ValueError(f"Unknown goal type: {goal_type}")

        config = {
            "goal_category": "non_race",
            "goal_type": goal_type,
            "goal_date": None,
            "goal_time_minutes": None,
            "goal_target": template.get("name", goal_type),
            "target_weekly_mileage": target_weekly_mileage,
            "current_weekly_mileage": current_weekly_mileage,
            "experience_level": experience_level,
            **kwargs
        }

        validation = self.validate_goal_config(config)
        if not validation["valid"]:
            raise ValueError(f"Invalid config: {', '.join(validation['errors'])}")

        return config

    def _generate_goal_target(self, time_minutes: int, goal_type: str) -> str:
        """Generate a human-readable goal target string."""
        hours = time_minutes // 60
        mins = time_minutes % 60

        if hours > 0:
            time_str = f"{hours}:{mins:02d}"
        else:
            time_str = f"{mins} minutes"

        goal_names = {
            "5k": "5K",
            "10k": "10K",
            "half_marathon": "Half Marathon",
            "marathon": "Marathon",
            "ultra": "Ultra",
            "custom": "Race"
        }

        goal_name = goal_names.get(goal_type, "Race")
        return f"{time_str} {goal_name}"

    def get_suggested_mileage(self, goal_type: str, experience_level: str) -> int:
        """Get suggested weekly mileage for a goal type and experience level."""
        template = self.get_goal_template(goal_type)
        if template and "suggested_weekly_mileage" in template:
            return template["suggested_weekly_mileage"].get(experience_level, 30)
        return 30  # Default

    def estimate_race_time(self, goal_type: str, recent_race_time: int, recent_race_type: str) -> int:
        """
        Estimate race time based on a recent race performance.

        Uses basic race equivalency formulas.

        Args:
            goal_type: Target race type (e.g., "marathon")
            recent_race_time: Recent race time in minutes
            recent_race_type: Recent race type (e.g., "half_marathon")

        Returns:
            Estimated time in minutes
        """
        distances = {
            "5k": 3.1,
            "10k": 6.2,
            "half_marathon": 13.1,
            "marathon": 26.2,
            "ultra": 50.0
        }

        recent_dist = distances.get(recent_race_type, 13.1)
        target_dist = distances.get(goal_type, 26.2)

        # Riegel formula: T2 = T1 * (D2/D1)^1.06
        ratio = (target_dist / recent_dist) ** 1.06
        estimated_time = int(recent_race_time * ratio)

        return estimated_time


# Global instance
goal_manager = GoalManager()
