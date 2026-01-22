"""Rule-based Training Plan Generator for automated weekly emails.

This module generates training plans without requiring an AI API key,
using established marathon training principles and the athlete's health data.
"""

import json
from datetime import date, timedelta
from typing import Optional
from user_config import UserConfig


class TrainingPlanGenerator:
    """Generates training plans based on training phase and health metrics."""

    # Base weekly mileage multipliers by phase
    PHASE_MULTIPLIERS = {
        "base": 0.85,
        "build": 1.0,
        "peak": 1.1,
        "taper": 0.6,
        "race_week": 0.3
    }

    # Long run as percentage of weekly mileage
    LONG_RUN_PCT = 0.30

    def __init__(self, user_config: Optional[UserConfig] = None):
        self.user_config = user_config or UserConfig()

    def generate_plan(self, analysis_results: dict) -> dict:
        """
        Generate a weekly training plan based on health metrics and training phase.

        Args:
            analysis_results: Health analysis from GarminDataAnalyzer

        Returns:
            Training plan dictionary
        """
        user = self.user_config.to_dict()
        phase = user['training_phase']
        weeks_to_race = user['weeks_until_race']
        base_mileage = user['current_weekly_mileage']
        long_run_day = user['preferred_long_run_day']
        target_pace = user['target_pace']

        # Adjust mileage based on phase
        phase_multiplier = self.PHASE_MULTIPLIERS.get(phase, 1.0)
        weekly_miles = round(base_mileage * phase_multiplier)

        # Check recovery status and adjust if needed
        recovery_adjustment = self._calculate_recovery_adjustment(analysis_results)
        if recovery_adjustment < 1.0:
            weekly_miles = round(weekly_miles * recovery_adjustment)

        # Calculate long run distance
        long_run_miles = round(weekly_miles * self.LONG_RUN_PCT)

        # Set min/max long run based on phase
        if phase == "taper":
            long_run_miles = max(min(long_run_miles, 12), 8)
        elif phase == "race_week":
            long_run_miles = min(long_run_miles, 6)
        elif phase == "peak":
            long_run_miles = max(min(long_run_miles, 20), 14)  # Peak: 14-20 miles
        elif phase == "build":
            long_run_miles = max(min(long_run_miles, 18), 12)  # Build: 12-18 miles
        else:  # base
            long_run_miles = max(min(long_run_miles, 14), 10)  # Base: 10-14 miles

        # Generate daily plan
        daily_plan = self._generate_daily_plan(
            weekly_miles=weekly_miles,
            long_run_miles=long_run_miles,
            long_run_day=long_run_day,
            phase=phase,
            target_pace=target_pace,
            recovery_adjustment=recovery_adjustment
        )

        # Generate coaching notes
        coaching_notes = self._generate_coaching_notes(
            phase=phase,
            weeks_to_race=weeks_to_race,
            analysis_results=analysis_results,
            recovery_adjustment=recovery_adjustment
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
                "focus": self._get_phase_focus(phase, weeks_to_race, recovery_adjustment)
            },
            "daily_plan": daily_plan,
            "coaching_notes": coaching_notes,
            "recovery_recommendations": recovery_recommendations
        }

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
        recovery_adjustment: float
    ) -> list:
        """Generate the 7-day training plan."""

        # Parse target pace
        pace_parts = target_pace.split(':')
        pace_mins = int(pace_parts[0])
        pace_secs = int(pace_parts[1]) if len(pace_parts) > 1 else 0

        # Calculate pace zones
        easy_pace = f"{pace_mins + 1}:{pace_secs:02d}-{pace_mins + 2}:{pace_secs:02d}"
        recovery_pace = f"{pace_mins + 2}:{pace_secs:02d}-{pace_mins + 3}:{pace_secs:02d}"
        tempo_pace = f"{pace_mins}:{pace_secs:02d}-{pace_mins}:{(pace_secs + 15) % 60:02d}"

        remaining_miles = weekly_miles - long_run_miles

        # Determine workout structure based on phase
        if phase == "race_week":
            return self._race_week_plan(remaining_miles, long_run_miles, long_run_day, easy_pace)
        elif phase == "taper":
            return self._taper_plan(remaining_miles, long_run_miles, long_run_day, easy_pace, tempo_pace, target_pace)
        else:
            return self._standard_plan(remaining_miles, long_run_miles, long_run_day, easy_pace, recovery_pace, tempo_pace, target_pace, phase, recovery_adjustment)

    def _standard_plan(self, remaining_miles, long_run_miles, long_run_day, easy_pace, recovery_pace, tempo_pace, target_pace, phase, recovery_adjustment) -> list:
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

    def _taper_plan(self, remaining_miles, long_run_miles, long_run_day, easy_pace, tempo_pace, target_pace) -> list:
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

    def _race_week_plan(self, remaining_miles, long_run_miles, long_run_day, easy_pace) -> list:
        """Generate race week plan with minimal running."""
        # Race week: only 3 short runs to stay loose
        return [
            {"day": "Monday", "workout_type": "rest", "title": "Rest Day", "distance_miles": None, "description": "Complete rest. Focus on hydration and sleep.", "notes": "Race week begins - stay calm."},
            {"day": "Tuesday", "workout_type": "easy", "title": "Easy Shakeout", "distance_miles": 3, "description": f"Very easy 3 miles at {easy_pace}/mile with 4 strides.", "notes": "Keep legs loose."},
            {"day": "Wednesday", "workout_type": "rest", "title": "Rest Day", "distance_miles": None, "description": "Complete rest. Visualize your race.", "notes": None},
            {"day": "Thursday", "workout_type": "easy", "title": "Easy Shakeout", "distance_miles": 2, "description": f"Very easy 2 miles. Just blood flow.", "notes": "Short and sweet."},
            {"day": "Friday", "workout_type": "rest", "title": "Rest Day", "distance_miles": None, "description": "Rest. Prepare race gear, pin your bib, lay out clothes.", "notes": "Early bedtime tonight."},
            {"day": "Saturday", "workout_type": "easy", "title": "Pre-Race Shakeout", "distance_miles": 2, "description": "Easy 15-20 min with 4 strides. Shake out the nerves.", "notes": "Stay off your feet the rest of the day."},
            {"day": "Sunday", "workout_type": "long_run", "title": "RACE DAY!", "distance_miles": 26.2, "description": "Execute your race plan. Start conservative, negative split, finish strong!", "notes": "Trust your training - you've got this!"}
        ]

    def _get_phase_focus(self, phase: str, weeks_to_race: int, recovery_adjustment: float) -> str:
        """Get the focus description for the week."""
        if recovery_adjustment < 0.85:
            return "Recovery focus - reduced volume due to fatigue indicators"

        focuses = {
            "base": "Building aerobic foundation with easy miles",
            "build": "Increasing volume and introducing quality workouts",
            "peak": f"Peak training - highest volume week, {weeks_to_race} weeks to race",
            "taper": "Tapering - maintaining fitness while recovering for race day",
            "race_week": "Race week - stay fresh and execute your race plan!"
        }
        return focuses.get(phase, "General training")

    def _generate_coaching_notes(self, phase: str, weeks_to_race: int, analysis_results: dict, recovery_adjustment: float) -> list:
        """Generate coaching notes based on data."""
        notes = []

        # Phase-specific note
        if phase == "peak":
            notes.append(f"Peak week with {weeks_to_race} weeks to race. Quality over quantity - nail your long run and tempo, rest the other days.")
        elif phase == "build":
            notes.append(f"Building phase - {weeks_to_race} weeks until race day. Consistency with 4-5 runs per week builds a strong foundation.")
        elif phase == "taper":
            notes.append("Taper time. Reduced volume feels weird but it's working. Trust the process and enjoy the extra rest.")
        elif phase == "race_week":
            notes.append("Race week! Minimal running, maximum rest. Stay calm, trust your training, and execute your plan.")
        elif phase == "base":
            notes.append(f"Base building phase - {weeks_to_race} weeks out. Focus on easy miles and building your aerobic engine.")

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
