"""Rule-based Training Plan Generator for automated weekly emails.

This module generates training plans without requiring an AI API key,
using established training principles and the athlete's health data.
Supports multiple race distances and non-race goals.
"""

import json
from datetime import date, timedelta
from typing import Optional
from user_config import UserConfig
from goal_manager import GoalManager


class TrainingPlanGenerator:
    """Generates training plans based on training phase and health metrics."""

    # Default phase multipliers (fallback if template not found)
    DEFAULT_PHASE_MULTIPLIERS = {
        "base": 0.85,
        "build": 1.0,
        "peak": 1.1,
        "taper": 0.6,
        "race_week": 0.3
    }

    # Default long run percentage
    DEFAULT_LONG_RUN_PCT = 0.30

    def __init__(self, user_config: Optional[UserConfig] = None, goal_manager: Optional[GoalManager] = None):
        self.user_config = user_config or UserConfig()
        self.goal_manager = goal_manager or GoalManager()

    def generate_plan(self, analysis_results: dict) -> dict:
        """
        Generate a weekly training plan based on health metrics and training phase.

        Args:
            analysis_results: Health analysis from GarminDataAnalyzer

        Returns:
            Training plan dictionary
        """
        user = self.user_config.to_dict()
        goal_type = user.get('goal_type', 'marathon')
        goal_category = user.get('goal_category', 'race')
        base_mileage = user['current_weekly_mileage']
        long_run_day = user['preferred_long_run_day']

        # Handle race vs non-race goals differently
        if goal_category == "race":
            return self._generate_race_plan(user, analysis_results, goal_type, base_mileage, long_run_day)
        else:
            return self._generate_non_race_plan(user, analysis_results, goal_type, base_mileage, long_run_day)

    def _generate_race_plan(self, user: dict, analysis_results: dict, goal_type: str, base_mileage: int, long_run_day: str) -> dict:
        """Generate training plan for race goals."""
        phase = user['training_phase']
        weeks_to_race = user.get('weeks_until_race', 0)
        target_pace = user.get('target_pace', '9:00')
        race_distance = user.get('race_distance_miles', 26.2)

        # Get phase config from template
        phase_config = self.goal_manager.get_phase_config(goal_type, phase)
        phase_multiplier = phase_config.get('multiplier', self.DEFAULT_PHASE_MULTIPLIERS.get(phase, 1.0))
        long_run_pct = phase_config.get('long_run_pct', self.DEFAULT_LONG_RUN_PCT)
        long_run_max = phase_config.get('long_run_max', 20)

        weekly_miles = round(base_mileage * phase_multiplier)

        # Check recovery status and adjust if needed
        recovery_adjustment = self._calculate_recovery_adjustment(analysis_results)
        if recovery_adjustment < 1.0:
            weekly_miles = round(weekly_miles * recovery_adjustment)

        # Calculate long run distance using template config
        long_run_miles = round(weekly_miles * long_run_pct)

        # Apply long run cap from template
        long_run_miles = min(long_run_miles, long_run_max)

        # Ensure minimum long run distance
        min_long_run = max(4, round(long_run_max * 0.5))
        long_run_miles = max(long_run_miles, min_long_run)

        # Generate daily plan with distance-appropriate workouts
        daily_plan = self._generate_daily_plan(
            weekly_miles=weekly_miles,
            long_run_miles=long_run_miles,
            long_run_day=long_run_day,
            phase=phase,
            target_pace=target_pace,
            recovery_adjustment=recovery_adjustment,
            goal_type=goal_type,
            race_distance=race_distance
        )

        # Generate coaching notes
        coaching_notes = self._generate_coaching_notes(
            phase=phase,
            weeks_to_race=weeks_to_race,
            analysis_results=analysis_results,
            recovery_adjustment=recovery_adjustment,
            goal_type=goal_type
        )

        # Generate recovery recommendations if needed
        recovery_recommendations = self._generate_recovery_recommendations(
            analysis_results=analysis_results,
            recovery_adjustment=recovery_adjustment
        )

        # Calculate actual total miles
        total_miles = sum(d.get('distance_miles') or 0 for d in daily_plan)

        return {
            "week_summary": {
                "total_miles": total_miles,
                "training_phase": phase,
                "goal_type": goal_type,
                "focus": self._get_phase_focus(phase, weeks_to_race, recovery_adjustment, goal_type)
            },
            "daily_plan": daily_plan,
            "coaching_notes": coaching_notes,
            "recovery_recommendations": recovery_recommendations
        }

    def _generate_non_race_plan(self, user: dict, analysis_results: dict, goal_type: str, base_mileage: int, long_run_day: str) -> dict:
        """Generate training plan for non-race goals (mileage building, maintenance, etc)."""
        target_mileage = user.get('target_weekly_mileage') or base_mileage

        # Get template for non-race goal
        template = self.goal_manager.get_goal_template(goal_type)

        if goal_type == "build_mileage":
            return self._generate_mileage_building_plan(user, analysis_results, base_mileage, target_mileage, long_run_day, template)
        elif goal_type == "maintain_fitness":
            return self._generate_maintenance_plan(user, analysis_results, base_mileage, long_run_day, template)
        elif goal_type == "base_building":
            return self._generate_base_building_plan(user, analysis_results, base_mileage, long_run_day, template)
        elif goal_type == "return_from_injury":
            return self._generate_return_from_injury_plan(user, analysis_results, base_mileage, long_run_day, template)
        else:
            # Default to maintenance
            return self._generate_maintenance_plan(user, analysis_results, base_mileage, long_run_day, template)

    def _generate_mileage_building_plan(self, user: dict, analysis_results: dict, current_mileage: int, target_mileage: int, long_run_day: str, template: dict) -> dict:
        """Generate plan for gradually building weekly mileage."""
        recovery_adjustment = self._calculate_recovery_adjustment(analysis_results)

        # Calculate this week's target (gradual increase)
        progression_rate = template.get('progression_rate', 0.10) if template else 0.10
        weekly_miles = min(round(current_mileage * (1 + progression_rate)), target_mileage)

        if recovery_adjustment < 1.0:
            weekly_miles = round(weekly_miles * recovery_adjustment)

        long_run_miles = round(weekly_miles * 0.28)
        long_run_miles = min(long_run_miles, 14)

        daily_plan = self._generate_easy_week_plan(weekly_miles, long_run_miles, long_run_day)

        coaching_notes = [
            f"Building mileage week - targeting {weekly_miles} miles (current: {current_mileage}, goal: {target_mileage})",
            "Focus on easy effort for all runs. The goal is time on feet, not speed.",
            "Increase no more than 10% per week to avoid injury."
        ]

        if recovery_adjustment < 1.0:
            coaching_notes.append("Recovery indicators suggest backing off - volume adjusted accordingly.")

        recovery_recommendations = self._generate_recovery_recommendations(analysis_results, recovery_adjustment)

        return {
            "week_summary": {
                "total_miles": sum(d.get('distance_miles') or 0 for d in daily_plan),
                "training_phase": "build",
                "goal_type": "build_mileage",
                "focus": f"Building to {target_mileage} miles/week"
            },
            "daily_plan": daily_plan,
            "coaching_notes": coaching_notes,
            "recovery_recommendations": recovery_recommendations
        }

    def _generate_maintenance_plan(self, user: dict, analysis_results: dict, base_mileage: int, long_run_day: str, template: dict) -> dict:
        """Generate plan for maintaining current fitness."""
        recovery_adjustment = self._calculate_recovery_adjustment(analysis_results)
        weekly_miles = base_mileage

        if recovery_adjustment < 1.0:
            weekly_miles = round(weekly_miles * recovery_adjustment)

        long_run_miles = round(weekly_miles * 0.28)

        # Include some quality work for maintenance
        daily_plan = self._generate_maintenance_week_plan(weekly_miles, long_run_miles, long_run_day)

        coaching_notes = [
            f"Maintenance week - {weekly_miles} miles to keep your fitness steady.",
            "Mix of easy runs with one tempo to maintain speed.",
            "Perfect time to work on form, strength, and flexibility."
        ]

        recovery_recommendations = self._generate_recovery_recommendations(analysis_results, recovery_adjustment)

        return {
            "week_summary": {
                "total_miles": sum(d.get('distance_miles') or 0 for d in daily_plan),
                "training_phase": "maintenance",
                "goal_type": "maintain_fitness",
                "focus": "Maintaining current fitness"
            },
            "daily_plan": daily_plan,
            "coaching_notes": coaching_notes,
            "recovery_recommendations": recovery_recommendations
        }

    def _generate_base_building_plan(self, user: dict, analysis_results: dict, base_mileage: int, long_run_day: str, template: dict) -> dict:
        """Generate plan for building aerobic base."""
        recovery_adjustment = self._calculate_recovery_adjustment(analysis_results)
        weekly_miles = round(base_mileage * 0.90)  # Slightly conservative for base building

        if recovery_adjustment < 1.0:
            weekly_miles = round(weekly_miles * recovery_adjustment)

        long_run_miles = round(weekly_miles * 0.30)

        daily_plan = self._generate_easy_week_plan(weekly_miles, long_run_miles, long_run_day, include_strides=True)

        coaching_notes = [
            "Base building week - all easy effort with strides for neuromuscular maintenance.",
            "Keep heart rate in Zone 2 for all runs. You should be able to hold a conversation.",
            "This aerobic foundation will support faster training later."
        ]

        recovery_recommendations = self._generate_recovery_recommendations(analysis_results, recovery_adjustment)

        return {
            "week_summary": {
                "total_miles": sum(d.get('distance_miles') or 0 for d in daily_plan),
                "training_phase": "base",
                "goal_type": "base_building",
                "focus": "Building aerobic foundation"
            },
            "daily_plan": daily_plan,
            "coaching_notes": coaching_notes,
            "recovery_recommendations": recovery_recommendations
        }

    def _generate_return_from_injury_plan(self, user: dict, analysis_results: dict, base_mileage: int, long_run_day: str, template: dict) -> dict:
        """Generate conservative plan for returning from injury."""
        recovery_adjustment = self._calculate_recovery_adjustment(analysis_results)

        # Very conservative - start at 40% of normal mileage
        weekly_miles = round(base_mileage * 0.40)

        if recovery_adjustment < 1.0:
            weekly_miles = round(weekly_miles * recovery_adjustment)

        # No long run - keep all runs short
        max_run = min(4, round(weekly_miles / 3))

        daily_plan = self._generate_return_from_injury_week_plan(weekly_miles, max_run, long_run_day)

        coaching_notes = [
            "Return from injury week - conservative volume with short, easy runs.",
            "Listen to your body. Stop immediately if you feel pain.",
            "Consider run/walk intervals if needed. There's no rush.",
            "Cross-training (swimming, cycling) can maintain fitness while reducing impact."
        ]

        recovery_recommendations = [
            "Ice and elevate after runs if any inflammation present.",
            "Prioritize sleep - this is when healing happens.",
            "Stay in touch with your healthcare provider about progress."
        ]
        recovery_recommendations.extend(self._generate_recovery_recommendations(analysis_results, recovery_adjustment))

        return {
            "week_summary": {
                "total_miles": sum(d.get('distance_miles') or 0 for d in daily_plan),
                "training_phase": "return",
                "goal_type": "return_from_injury",
                "focus": "Careful return to running"
            },
            "daily_plan": daily_plan,
            "coaching_notes": coaching_notes,
            "recovery_recommendations": recovery_recommendations
        }

    def _generate_easy_week_plan(self, weekly_miles: int, long_run_miles: int, long_run_day: str, include_strides: bool = False) -> list:
        """Generate a simple week of easy running."""
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        long_run_idx = 5 if long_run_day == "saturday" else 6

        remaining = weekly_miles - long_run_miles
        easy_miles = max(4, round(remaining / 3))

        plan = []
        for i, day in enumerate(days):
            if i == long_run_idx:
                plan.append({
                    "day": day,
                    "workout_type": "long_run",
                    "title": "Long Run",
                    "distance_miles": long_run_miles,
                    "description": "Easy effort throughout. Focus on time on feet.",
                    "notes": "Stay relaxed and enjoy the run."
                })
            elif i == 0:
                plan.append({
                    "day": day,
                    "workout_type": "rest",
                    "title": "Rest Day",
                    "distance_miles": None,
                    "description": "Complete rest or light stretching.",
                    "notes": None
                })
            elif i == 1:
                title = "Easy Run + Strides" if include_strides else "Easy Run"
                desc = "Easy pace, conversational effort."
                if include_strides:
                    desc += " Finish with 4x100m strides with full recovery."
                plan.append({
                    "day": day,
                    "workout_type": "easy",
                    "title": title,
                    "distance_miles": easy_miles,
                    "description": desc,
                    "notes": None
                })
            elif i == 3:
                plan.append({
                    "day": day,
                    "workout_type": "rest",
                    "title": "Rest / Cross-Train",
                    "distance_miles": None,
                    "description": "Rest or low-impact cross-training.",
                    "notes": None
                })
            elif i == 4:
                plan.append({
                    "day": day,
                    "workout_type": "easy",
                    "title": "Easy Run",
                    "distance_miles": easy_miles,
                    "description": "Easy pace, stay relaxed.",
                    "notes": None
                })
            elif i == 6 and long_run_day == "saturday":
                plan.append({
                    "day": day,
                    "workout_type": "rest",
                    "title": "Rest Day",
                    "distance_miles": None,
                    "description": "Rest and recovery.",
                    "notes": None
                })
            else:
                plan.append({
                    "day": day,
                    "workout_type": "easy",
                    "title": "Easy Run",
                    "distance_miles": easy_miles,
                    "description": "Easy pace.",
                    "notes": None
                })

        return plan

    def _generate_maintenance_week_plan(self, weekly_miles: int, long_run_miles: int, long_run_day: str) -> list:
        """Generate a maintenance week with some quality."""
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        long_run_idx = 5 if long_run_day == "saturday" else 6

        remaining = weekly_miles - long_run_miles
        tempo_miles = min(6, round(remaining * 0.25))
        easy_miles = max(4, round((remaining - tempo_miles) / 2))

        plan = []
        for i, day in enumerate(days):
            if i == long_run_idx:
                plan.append({
                    "day": day,
                    "workout_type": "long_run",
                    "title": "Long Run",
                    "distance_miles": long_run_miles,
                    "description": "Steady effort throughout.",
                    "notes": None
                })
            elif i == 0:
                plan.append({
                    "day": day,
                    "workout_type": "rest",
                    "title": "Rest Day",
                    "distance_miles": None,
                    "description": "Complete rest.",
                    "notes": None
                })
            elif i == 1:
                plan.append({
                    "day": day,
                    "workout_type": "easy",
                    "title": "Easy Run",
                    "distance_miles": easy_miles,
                    "description": "Easy pace to start the week.",
                    "notes": None
                })
            elif i == 2:
                plan.append({
                    "day": day,
                    "workout_type": "tempo",
                    "title": "Tempo Run",
                    "distance_miles": tempo_miles,
                    "description": "1 mile easy, middle miles at tempo, 1 mile easy.",
                    "notes": "Comfortably hard effort."
                })
            elif i == 3:
                plan.append({
                    "day": day,
                    "workout_type": "rest",
                    "title": "Rest / Cross-Train",
                    "distance_miles": None,
                    "description": "Rest or cross-training.",
                    "notes": None
                })
            elif i == 4:
                plan.append({
                    "day": day,
                    "workout_type": "easy",
                    "title": "Easy Run + Strides",
                    "distance_miles": easy_miles,
                    "description": "Easy run with 4 strides at the end.",
                    "notes": None
                })
            elif i == 6 and long_run_day == "saturday":
                plan.append({
                    "day": day,
                    "workout_type": "rest",
                    "title": "Rest Day",
                    "distance_miles": None,
                    "description": "Rest and recovery.",
                    "notes": None
                })
            else:
                plan.append({
                    "day": day,
                    "workout_type": "rest",
                    "title": "Rest Day",
                    "distance_miles": None,
                    "description": "Rest.",
                    "notes": None
                })

        return plan

    def _generate_return_from_injury_week_plan(self, weekly_miles: int, max_run: int, long_run_day: str) -> list:
        """Generate a conservative return-from-injury week."""
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

        # Only 3 runs, all short
        run_miles = min(max_run, round(weekly_miles / 3))

        plan = []
        for i, day in enumerate(days):
            if i == 0:
                plan.append({
                    "day": day,
                    "workout_type": "rest",
                    "title": "Rest Day",
                    "distance_miles": None,
                    "description": "Complete rest.",
                    "notes": None
                })
            elif i == 1:
                plan.append({
                    "day": day,
                    "workout_type": "easy",
                    "title": "Easy Run",
                    "distance_miles": run_miles,
                    "description": "Very easy pace. Walk breaks OK.",
                    "notes": "Stop if any pain."
                })
            elif i == 2:
                plan.append({
                    "day": day,
                    "workout_type": "rest",
                    "title": "Rest / Cross-Train",
                    "distance_miles": None,
                    "description": "Swimming or cycling if desired.",
                    "notes": None
                })
            elif i == 3:
                plan.append({
                    "day": day,
                    "workout_type": "easy",
                    "title": "Easy Run",
                    "distance_miles": run_miles,
                    "description": "Very easy. Check in with how you feel.",
                    "notes": None
                })
            elif i == 4:
                plan.append({
                    "day": day,
                    "workout_type": "rest",
                    "title": "Rest Day",
                    "distance_miles": None,
                    "description": "Complete rest.",
                    "notes": None
                })
            elif i == 5:
                plan.append({
                    "day": day,
                    "workout_type": "easy",
                    "title": "Easy Run",
                    "distance_miles": run_miles,
                    "description": "Gentle run. Assess how the week felt.",
                    "notes": None
                })
            else:
                plan.append({
                    "day": day,
                    "workout_type": "rest",
                    "title": "Rest Day",
                    "distance_miles": None,
                    "description": "Rest and reflect on the week.",
                    "notes": None
                })

        return plan

    def _calculate_recovery_adjustment(self, analysis: dict) -> float:
        """Calculate mileage adjustment based on recovery indicators."""
        adjustment = 1.0
        concerns = 0

        # Check resting HR
        rhr = analysis.get('resting_hr', {})
        if rhr.get('available') and rhr.get('status') == 'concern':
            concerns += 1

        # Check body battery
        bb = analysis.get('body_battery', {})
        if bb.get('available') and bb.get('status') == 'concern':
            concerns += 1

        # Check sleep
        sleep = analysis.get('sleep', {})
        if sleep.get('available') and sleep.get('status') == 'concern':
            concerns += 1

        # Adjust based on concerns - less aggressive reduction
        if concerns >= 3:
            adjustment = 0.80  # All indicators concerning
        elif concerns >= 2:
            adjustment = 0.85  # Moderate reduction
        elif concerns == 1:
            adjustment = 0.90  # Slight reduction

        return adjustment

    def _generate_daily_plan(
        self,
        weekly_miles: int,
        long_run_miles: int,
        long_run_day: str,
        phase: str,
        target_pace: str,
        recovery_adjustment: float,
        goal_type: str = "marathon",
        race_distance: float = 26.2
    ) -> list:
        """Generate the 7-day training plan."""

        # Parse target pace
        pace_parts = target_pace.split(':')
        pace_mins = int(pace_parts[0])
        pace_secs = int(pace_parts[1]) if len(pace_parts) > 1 else 0

        # Get pace offsets from template (different distances have different training zones)
        pace_offsets = self.goal_manager.get_pace_offsets(goal_type)
        easy_offset_min = pace_offsets.get('easy_offset_min', 1.0)
        easy_offset_max = pace_offsets.get('easy_offset_max', 2.0)
        tempo_offset_min = pace_offsets.get('tempo_offset_min', 0.0)
        tempo_offset_max = pace_offsets.get('tempo_offset_max', 0.25)
        recovery_offset_min = pace_offsets.get('recovery_offset_min', 2.0)
        recovery_offset_max = pace_offsets.get('recovery_offset_max', 3.0)

        # Calculate pace zones using template offsets
        easy_pace_min = pace_mins + int(easy_offset_min)
        easy_pace_max = pace_mins + int(easy_offset_max)
        easy_secs_min = int((easy_offset_min % 1) * 60) + pace_secs
        easy_secs_max = int((easy_offset_max % 1) * 60) + pace_secs

        easy_pace = f"{easy_pace_min}:{easy_secs_min % 60:02d}-{easy_pace_max}:{easy_secs_max % 60:02d}"
        recovery_pace = f"{pace_mins + int(recovery_offset_min)}:{pace_secs:02d}-{pace_mins + int(recovery_offset_max)}:{pace_secs:02d}"
        tempo_pace = f"{pace_mins}:{pace_secs:02d}-{pace_mins}:{(pace_secs + 15) % 60:02d}"

        remaining_miles = weekly_miles - long_run_miles

        # Determine workout structure based on phase
        if phase == "race_week":
            return self._race_week_plan(remaining_miles, long_run_miles, long_run_day, easy_pace, goal_type, race_distance)
        elif phase == "taper":
            return self._taper_plan(remaining_miles, long_run_miles, long_run_day, easy_pace, tempo_pace, target_pace, goal_type)
        else:
            return self._standard_plan(remaining_miles, long_run_miles, long_run_day, easy_pace, recovery_pace, tempo_pace, target_pace, phase, recovery_adjustment, goal_type)

    def _standard_plan(self, remaining_miles, long_run_miles, long_run_day, easy_pace, recovery_pace, tempo_pace, target_pace, phase, recovery_adjustment, goal_type: str = "marathon") -> list:
        """Generate standard training week with 4-5 running days."""

        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        long_run_idx = 5 if long_run_day == "saturday" else 6  # Saturday or Sunday

        # For 4-5 runs per week, distribute miles across fewer days
        # Key sessions: Long run, Tempo/Quality (in build/peak), 2-3 easy runs
        include_tempo = phase in ["build", "peak"]  # Always include tempo in build/peak

        # Calculate run distances for 4-5 day week
        if include_tempo:
            # 5 runs: Long, Tempo, 3 easy
            tempo_miles = min(max(round(remaining_miles * 0.25), 5), 7)  # 5-7 miles
            easy_total = remaining_miles - tempo_miles
            easy_miles_each = max(round(easy_total / 3), 4)  # At least 4 miles per easy run
        else:
            # 4 runs: Long + 3 easy (base phase or taper)
            easy_miles_each = max(round(remaining_miles / 3), 4)
            tempo_miles = 0

        plan = []
        for i, day in enumerate(days):
            if i == long_run_idx:
                # Long run day (Saturday or Sunday)
                plan.append({
                    "day": day,
                    "workout_type": "long_run",
                    "title": "Long Run",
                    "distance_miles": long_run_miles,
                    "description": f"Start easy at {easy_pace}/mile for first few miles, then settle into {target_pace}/mile for the middle portion. Practice race-day nutrition.",
                    "notes": "Key workout #1 - stay relaxed and focus on time on feet."
                })
            elif i == 0:
                # Monday - Rest after long run weekend
                plan.append({
                    "day": day,
                    "workout_type": "rest",
                    "title": "Rest Day",
                    "distance_miles": None,
                    "description": "Complete rest or light stretching/yoga. Let your body recover from the long run.",
                    "notes": "Recovery is when fitness gains happen."
                })
            elif i == 1:
                # Tuesday - Easy run
                plan.append({
                    "day": day,
                    "workout_type": "easy",
                    "title": "Easy Run",
                    "distance_miles": easy_miles_each,
                    "description": f"Easy pace at {easy_pace}/mile. Keep heart rate in Zone 2. Should feel conversational.",
                    "notes": None
                })
            elif i == 2:
                # Wednesday - Tempo (if included) or Rest
                if include_tempo:
                    warmup = 1
                    cooldown = 1
                    tempo_portion = max(tempo_miles - warmup - cooldown, 2)
                    plan.append({
                        "day": day,
                        "workout_type": "tempo",
                        "title": "Tempo Run",
                        "distance_miles": tempo_miles,
                        "description": f"{warmup} mile warm-up, {tempo_portion} miles at {tempo_pace}/mile, {cooldown} mile cool-down.",
                        "notes": "Key workout #2 - comfortably hard effort."
                    })
                else:
                    plan.append({
                        "day": day,
                        "workout_type": "rest",
                        "title": "Rest Day",
                        "distance_miles": None,
                        "description": "Rest or cross-training (swimming, cycling, yoga).",
                        "notes": "Active recovery keeps you fresh."
                    })
            elif i == 3:
                # Thursday - Rest
                plan.append({
                    "day": day,
                    "workout_type": "rest",
                    "title": "Rest / Cross-Train",
                    "distance_miles": None,
                    "description": "Rest day or optional cross-training. Good day for strength work or yoga.",
                    "notes": "Quality over quantity - rest makes you faster."
                })
            elif i == 4:
                # Friday - Easy run
                plan.append({
                    "day": day,
                    "workout_type": "easy",
                    "title": "Easy Run + Strides",
                    "distance_miles": easy_miles_each,
                    "description": f"Easy {easy_miles_each} miles at {easy_pace}/mile, then 4x100m strides with full recovery.",
                    "notes": "Strides keep your legs feeling snappy."
                })
            elif i == (long_run_idx - 1) and long_run_day == "sunday":
                # Saturday before Sunday long run - short easy or rest
                plan.append({
                    "day": day,
                    "workout_type": "easy",
                    "title": "Pre-Long Run Shakeout",
                    "distance_miles": round(easy_miles_each * 0.6),
                    "description": f"Short easy run at {easy_pace}/mile. Just loosening up for tomorrow.",
                    "notes": "Keep it short and easy. Prepare gear for tomorrow."
                })
            elif i == 6 and long_run_day == "saturday":
                # Sunday after Saturday long run - rest
                plan.append({
                    "day": day,
                    "workout_type": "rest",
                    "title": "Rest Day",
                    "distance_miles": None,
                    "description": "Complete rest. Recover from yesterday's long run.",
                    "notes": "Enjoy your rest day!"
                })
            else:
                # Fill any gaps with easy run
                plan.append({
                    "day": day,
                    "workout_type": "easy",
                    "title": "Easy Run",
                    "distance_miles": easy_miles_each,
                    "description": f"Easy pace at {easy_pace}/mile.",
                    "notes": None
                })

        return plan

    def _taper_plan(self, remaining_miles, long_run_miles, long_run_day, easy_pace, tempo_pace, target_pace, goal_type: str = "marathon") -> list:
        """Generate taper week plan with 4 running days."""
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        long_run_idx = 5 if long_run_day == "saturday" else 6

        # Taper: 4 runs only - Long, Tempo, 2 easy
        easy_miles = round(remaining_miles / 3)

        plan = []
        for i, day in enumerate(days):
            if i == long_run_idx:
                plan.append({
                    "day": day,
                    "workout_type": "long_run",
                    "title": "Taper Long Run",
                    "distance_miles": long_run_miles,
                    "description": f"Easy effort at {easy_pace}/mile with a few miles at {target_pace}/mile to stay sharp.",
                    "notes": "Keep it controlled - save energy for race day."
                })
            elif i == 0:
                # Monday - Rest
                plan.append({
                    "day": day,
                    "workout_type": "rest",
                    "title": "Rest Day",
                    "distance_miles": None,
                    "description": "Complete rest. Focus on sleep and nutrition.",
                    "notes": "Taper = trust the process."
                })
            elif i == 1:
                # Tuesday - Easy
                plan.append({
                    "day": day,
                    "workout_type": "easy",
                    "title": "Easy Run",
                    "distance_miles": easy_miles,
                    "description": f"Easy at {easy_pace}/mile. Keep legs moving.",
                    "notes": None
                })
            elif i == 2:
                # Wednesday - Short tempo to stay sharp
                plan.append({
                    "day": day,
                    "workout_type": "tempo",
                    "title": "Short Tempo",
                    "distance_miles": easy_miles,
                    "description": f"1 mile easy, 2 miles at {tempo_pace}/mile, 1 mile easy. Stay sharp without fatiguing.",
                    "notes": "Brief quality to maintain sharpness."
                })
            elif i == 3:
                # Thursday - Rest
                plan.append({
                    "day": day,
                    "workout_type": "rest",
                    "title": "Rest Day",
                    "distance_miles": None,
                    "description": "Complete rest or light yoga/stretching.",
                    "notes": None
                })
            elif i == 4:
                # Friday - Easy
                plan.append({
                    "day": day,
                    "workout_type": "easy",
                    "title": "Easy Run + Strides",
                    "distance_miles": easy_miles,
                    "description": f"Easy {easy_miles} miles with 4x100m strides at the end.",
                    "notes": "Keep the legs feeling fresh and fast."
                })
            elif i == 6 and long_run_day == "saturday":
                # Sunday after Saturday long run
                plan.append({
                    "day": day,
                    "workout_type": "rest",
                    "title": "Rest Day",
                    "distance_miles": None,
                    "description": "Complete rest after long run.",
                    "notes": None
                })
            else:
                plan.append({
                    "day": day,
                    "workout_type": "rest",
                    "title": "Rest Day",
                    "distance_miles": None,
                    "description": "Rest and recovery.",
                    "notes": None
                })

        return plan

    def _race_week_plan(self, remaining_miles, long_run_miles, long_run_day, easy_pace, goal_type: str = "marathon", race_distance: float = 26.2) -> list:
        """Generate race week plan with minimal running."""
        # Get race name for display
        race_names = {
            "5k": "5K",
            "10k": "10K",
            "half_marathon": "Half Marathon",
            "marathon": "Marathon",
            "ultra": "Ultra",
            "custom": "Race"
        }
        race_name = race_names.get(goal_type, "Race")

        # Adjust shakeout distances based on race distance
        if race_distance <= 6.2:  # 5K or 10K
            shakeout_1 = 2
            shakeout_2 = 1.5
            shakeout_3 = 1.5
        elif race_distance <= 13.1:  # Half marathon
            shakeout_1 = 2.5
            shakeout_2 = 2
            shakeout_3 = 2
        else:  # Marathon and beyond
            shakeout_1 = 3
            shakeout_2 = 2
            shakeout_3 = 2

        return [
            {"day": "Monday", "workout_type": "rest", "title": "Rest Day", "distance_miles": None, "description": "Complete rest. Focus on hydration and sleep.", "notes": "Race week begins - stay calm."},
            {"day": "Tuesday", "workout_type": "easy", "title": "Easy Shakeout", "distance_miles": shakeout_1, "description": f"Very easy {shakeout_1} miles at {easy_pace}/mile with 4 strides.", "notes": "Keep legs loose."},
            {"day": "Wednesday", "workout_type": "rest", "title": "Rest Day", "distance_miles": None, "description": "Complete rest. Visualize your race.", "notes": None},
            {"day": "Thursday", "workout_type": "easy", "title": "Easy Shakeout", "distance_miles": shakeout_2, "description": f"Very easy {shakeout_2} miles. Just blood flow.", "notes": "Short and sweet."},
            {"day": "Friday", "workout_type": "rest", "title": "Rest Day", "distance_miles": None, "description": "Rest. Prepare race gear, pin your bib, lay out clothes.", "notes": "Early bedtime tonight."},
            {"day": "Saturday", "workout_type": "easy", "title": "Pre-Race Shakeout", "distance_miles": shakeout_3, "description": f"Easy 15-20 min with 4 strides. Shake out the nerves.", "notes": "Stay off your feet the rest of the day."},
            {"day": "Sunday", "workout_type": "race", "title": f"RACE DAY - {race_name}!", "distance_miles": race_distance, "description": "Execute your race plan. Start conservative, negative split, finish strong!", "notes": "Trust your training - you've got this!"}
        ]

    def _get_phase_focus(self, phase: str, weeks_to_race: int, recovery_adjustment: float, goal_type: str = "marathon") -> str:
        """Get the focus description for the week."""
        if recovery_adjustment < 0.85:
            return "Recovery focus - reduced volume due to fatigue indicators"

        race_names = {
            "5k": "5K",
            "10k": "10K",
            "half_marathon": "Half Marathon",
            "marathon": "Marathon",
            "ultra": "Ultra",
            "custom": "Race"
        }
        race_name = race_names.get(goal_type, "race")

        focuses = {
            "base": "Building aerobic foundation with easy miles",
            "build": "Increasing volume and introducing quality workouts",
            "peak": f"Peak training - highest volume week, {weeks_to_race} weeks to {race_name}",
            "taper": f"Tapering - maintaining fitness while recovering for {race_name}",
            "race_week": f"{race_name} week - stay fresh and execute your race plan!"
        }
        return focuses.get(phase, "General training")

    def _generate_coaching_notes(self, phase: str, weeks_to_race: int, analysis_results: dict, recovery_adjustment: float, goal_type: str = "marathon") -> list:
        """Generate coaching notes based on data."""
        notes = []

        race_names = {
            "5k": "5K",
            "10k": "10K",
            "half_marathon": "Half Marathon",
            "marathon": "Marathon",
            "ultra": "Ultra",
            "custom": "Race"
        }
        race_name = race_names.get(goal_type, "race")

        # Phase-specific note
        if phase == "peak":
            notes.append(f"Peak week with {weeks_to_race} weeks to {race_name}. Quality over quantity - nail your long run and tempo, rest the other days.")
        elif phase == "build":
            notes.append(f"Building phase - {weeks_to_race} weeks until {race_name}. Consistency with 4-5 runs per week builds a strong foundation.")
        elif phase == "taper":
            notes.append(f"Taper time for {race_name}. Reduced volume feels weird but it's working. Trust the process and enjoy the extra rest.")
        elif phase == "race_week":
            notes.append(f"{race_name} week! Minimal running, maximum rest. Stay calm, trust your training, and execute your plan.")
        elif phase == "base":
            notes.append(f"Base building phase - {weeks_to_race} weeks out from {race_name}. Focus on easy miles and building your aerobic engine.")

        # Recovery note if needed
        if recovery_adjustment < 1.0:
            notes.append("Your health metrics show some fatigue - this week's plan has been adjusted to prioritize recovery.")

        # 4-5 day running philosophy
        if phase in ["build", "peak"]:
            notes.append("With 4-5 running days, every run has purpose: long run for endurance, tempo for race fitness, easy runs for recovery.")
        elif phase == "base":
            notes.append("4 easy runs this week builds consistency without overloading. Quality rest days are part of the training.")

        # Rest day note
        notes.append("Rest days aren't lazy - they're when your body adapts and gets stronger. Use them wisely.")

        return notes

    def _generate_recovery_recommendations(self, analysis_results: dict, recovery_adjustment: float) -> list:
        """Generate recovery recommendations if needed."""
        recs = []

        sleep = analysis_results.get('sleep', {})
        if sleep.get('available') and sleep.get('status') == 'concern':
            avg_sleep = sleep.get('avg_hours', 0)
            recs.append(f"Sleep is critical: You're averaging {avg_sleep:.1f} hours. Aim for 7-8 hours to support recovery.")

        rhr = analysis_results.get('resting_hr', {})
        if rhr.get('available') and rhr.get('status') == 'concern':
            recs.append("Elevated resting heart rate detected. Consider extra rest days if fatigue persists.")

        bb = analysis_results.get('body_battery', {})
        if bb.get('available') and bb.get('status') == 'concern':
            recs.append("Body Battery is low. Prioritize sleep and reduce stress where possible.")

        if recovery_adjustment < 0.85:
            recs.append("Multiple fatigue indicators present - consider a recovery week with reduced intensity.")

        return recs
