#!/usr/bin/env python3
"""
Garmin Data Analyzer - Calculates health and training insights from Garmin Connect data.

This module reads JSON data exported from Garmin Connect and calculates:
- Resting heart rate trends
- Body Battery patterns
- Sleep quality correlations
- Sedentary time impact
- Stress and recovery relationships
- Day-of-week patterns
- Monthly trends
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
from typing import Optional
import statistics


class GarminDataAnalyzer:
    """Analyzes Garmin Connect data to generate health and training insights."""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.daily_summaries = []
        self.sleep_data = []
        self.heart_rate_data = []
        self.vo2max_data = []
        self.analysis_results = {}

    def load_data(self) -> dict:
        """Load all available data from the data directory."""
        results = {
            'daily_summaries': 0,
            'sleep': 0,
            'heart_rate': 0,
            'vo2max': 0,
            'date_range': None
        }

        # Load daily summaries
        summary_dir = self.data_dir / "daily_summaries"
        if summary_dir.exists():
            for file in sorted(summary_dir.glob("*.json")):
                try:
                    with open(file, 'r') as f:
                        data = json.load(f)
                        data['_date'] = file.stem  # Add date from filename
                        self.daily_summaries.append(data)
                except (json.JSONDecodeError, IOError):
                    continue
            results['daily_summaries'] = len(self.daily_summaries)

        # Load sleep data
        sleep_dir = self.data_dir / "sleep"
        if sleep_dir.exists():
            for file in sorted(sleep_dir.glob("*.json")):
                try:
                    with open(file, 'r') as f:
                        data = json.load(f)
                        data['_date'] = file.stem
                        self.sleep_data.append(data)
                except (json.JSONDecodeError, IOError):
                    continue
            results['sleep'] = len(self.sleep_data)

        # Load heart rate data
        hr_dir = self.data_dir / "heart_rate"
        if hr_dir.exists():
            for file in sorted(hr_dir.glob("*.json")):
                try:
                    with open(file, 'r') as f:
                        data = json.load(f)
                        data['_date'] = file.stem
                        self.heart_rate_data.append(data)
                except (json.JSONDecodeError, IOError):
                    continue
            results['heart_rate'] = len(self.heart_rate_data)

        # Load VO2 max data
        vo2max_dir = self.data_dir / "vo2max"
        if vo2max_dir.exists():
            for file in sorted(vo2max_dir.glob("*.json")):
                try:
                    with open(file, 'r') as f:
                        data = json.load(f)
                        if '_date' not in data:
                            data['_date'] = file.stem
                        self.vo2max_data.append(data)
                except (json.JSONDecodeError, IOError):
                    continue
            results['vo2max'] = len(self.vo2max_data)

        # Calculate date range
        if self.daily_summaries:
            dates = [d['_date'] for d in self.daily_summaries]
            results['date_range'] = (min(dates), max(dates))

        return results

    def analyze_all(self) -> dict:
        """Run all analyses and return comprehensive results."""
        if not self.daily_summaries:
            raise ValueError("No data loaded. Call load_data() first.")

        self.analysis_results = {
            'overview': self._analyze_overview(),
            'resting_hr': self._analyze_resting_hr(),
            'body_battery': self._analyze_body_battery(),
            'vo2max': self._analyze_vo2max(),
            'sleep': self._analyze_sleep(),
            'sedentary': self._analyze_sedentary(),
            'stress': self._analyze_stress(),
            'steps': self._analyze_steps(),
            'day_of_week': self._analyze_day_of_week(),
            'monthly_trends': self._analyze_monthly_trends(),
            'correlations': self._analyze_correlations(),
            'recommendations': self._generate_recommendations(),
        }

        return self.analysis_results

    def _analyze_overview(self) -> dict:
        """Calculate overview statistics."""
        dates = [d['_date'] for d in self.daily_summaries]

        return {
            'total_days': len(self.daily_summaries),
            'start_date': min(dates),
            'end_date': max(dates),
            'data_types': {
                'daily_summaries': len(self.daily_summaries),
                'sleep': len(self.sleep_data),
                'heart_rate': len(self.heart_rate_data),
            }
        }

    def _get_stat(self, day: dict, key: str, default=None):
        """Get a stat value, handling nested 'stats' structure."""
        # Try direct access first
        value = day.get(key)
        if value is not None:
            return value
        # Try nested under 'stats'
        stats = day.get('stats', {})
        if stats:
            return stats.get(key, default)
        return default

    def _analyze_resting_hr(self) -> dict:
        """Analyze resting heart rate trends."""
        rhr_values = []

        for day in self.daily_summaries:
            rhr = self._get_stat(day, 'restingHeartRate')
            if rhr and rhr > 0:
                rhr_values.append({
                    'date': day['_date'],
                    'rhr': rhr
                })

        if not rhr_values:
            return {'available': False}

        all_rhr = [v['rhr'] for v in rhr_values]

        # Calculate baseline (first 14 days with data)
        first_14 = all_rhr[:14] if len(all_rhr) >= 14 else all_rhr
        baseline = statistics.mean(first_14)

        # Calculate recent (last 14 days with data)
        last_14 = all_rhr[-14:] if len(all_rhr) >= 14 else all_rhr
        recent = statistics.mean(last_14)

        # Calculate trend
        change = recent - baseline
        change_pct = (change / baseline) * 100 if baseline else 0

        return {
            'available': True,
            'baseline': round(baseline, 1),
            'current': round(recent, 1),
            'change': round(change, 1),
            'change_pct': round(change_pct, 1),
            'min': min(all_rhr),
            'max': max(all_rhr),
            'avg': round(statistics.mean(all_rhr), 1),
            'trend': 'rising' if change > 2 else ('falling' if change < -2 else 'stable'),
            'status': 'concern' if change > 3 else ('good' if change < -1 else 'normal'),
        }

    def _analyze_body_battery(self) -> dict:
        """Analyze Body Battery patterns."""
        bb_values = []

        for day in self.daily_summaries:
            bb_high = self._get_stat(day, 'bodyBatteryHighestValue')
            bb_low = self._get_stat(day, 'bodyBatteryLowestValue')
            bb_charged = self._get_stat(day, 'bodyBatteryChargedValue', 0) or 0
            bb_drained = self._get_stat(day, 'bodyBatteryDrainedValue', 0) or 0

            if bb_high and bb_high > 0:
                bb_values.append({
                    'date': day['_date'],
                    'high': bb_high,
                    'low': bb_low or 0,
                    'charged': bb_charged,
                    'drained': bb_drained,
                    'net': bb_charged - bb_drained,
                })

        if not bb_values:
            return {'available': False}

        all_highs = [v['high'] for v in bb_values]
        all_charged = [v['charged'] for v in bb_values if v['charged'] > 0]

        # Baseline vs recent
        first_14 = all_highs[:14] if len(all_highs) >= 14 else all_highs
        last_14 = all_highs[-14:] if len(all_highs) >= 14 else all_highs

        baseline = statistics.mean(first_14)
        recent = statistics.mean(last_14)
        change = recent - baseline

        return {
            'available': True,
            'baseline_wake': round(baseline, 0),
            'current_wake': round(recent, 0),
            'change': round(change, 0),
            'avg_recharge': round(statistics.mean(all_charged), 0) if all_charged else 0,
            'min_wake': min(all_highs),
            'max_wake': max(all_highs),
            'trend': 'declining' if change < -5 else ('improving' if change > 5 else 'stable'),
            'status': 'concern' if recent < 60 else ('good' if recent >= 75 else 'normal'),
        }

    def _analyze_vo2max(self) -> dict:
        """Analyze VO2 max trends."""
        vo2_values = []

        for record in self.vo2max_data:
            # Handle different VO2 max data structures from Garmin
            vo2 = None

            # Try generic field
            if 'generic' in record:
                vo2 = record['generic'].get('vo2MaxValue')

            # Try running specific
            if vo2 is None and 'running' in record:
                vo2 = record['running'].get('vo2MaxValue')

            # Try cycling specific
            if vo2 is None and 'cycling' in record:
                vo2 = record['cycling'].get('vo2MaxValue')

            # Try direct field
            if vo2 is None:
                vo2 = record.get('vo2MaxValue') or record.get('vo2Max')

            if vo2 and vo2 > 0:
                vo2_values.append({
                    'date': record.get('_date', ''),
                    'vo2max': vo2,
                })

        if not vo2_values:
            return {'available': False}

        all_vo2 = [v['vo2max'] for v in vo2_values]

        # Calculate baseline (first readings) vs recent
        first_readings = all_vo2[:7] if len(all_vo2) >= 7 else all_vo2
        last_readings = all_vo2[-7:] if len(all_vo2) >= 7 else all_vo2

        baseline = statistics.mean(first_readings)
        recent = statistics.mean(last_readings)
        change = recent - baseline

        # Determine fitness level (general categories)
        # These are approximate and vary by age/gender
        if recent >= 55:
            fitness_level = 'Excellent'
        elif recent >= 50:
            fitness_level = 'Very Good'
        elif recent >= 45:
            fitness_level = 'Good'
        elif recent >= 40:
            fitness_level = 'Fair'
        else:
            fitness_level = 'Needs Improvement'

        return {
            'available': True,
            'baseline': round(baseline, 1),
            'current': round(recent, 1),
            'change': round(change, 1),
            'min': round(min(all_vo2), 1),
            'max': round(max(all_vo2), 1),
            'avg': round(statistics.mean(all_vo2), 1),
            'fitness_level': fitness_level,
            'trend': 'improving' if change > 1 else ('declining' if change < -1 else 'stable'),
            'status': 'good' if change >= 0 else ('concern' if change < -2 else 'normal'),
            'readings': len(all_vo2),
        }

    def _analyze_sleep(self) -> dict:
        """Analyze sleep duration and quality."""
        sleep_values = []

        for day in self.sleep_data:
            duration = day.get('dailySleepDTO', {}).get('sleepTimeSeconds')
            if duration and duration > 0:
                hours = duration / 3600
                sleep_values.append({
                    'date': day['_date'],
                    'hours': hours,
                    'deep': day.get('dailySleepDTO', {}).get('deepSleepSeconds', 0) / 3600,
                    'light': day.get('dailySleepDTO', {}).get('lightSleepSeconds', 0) / 3600,
                    'rem': day.get('dailySleepDTO', {}).get('remSleepSeconds', 0) / 3600,
                })

        if not sleep_values:
            return {'available': False}

        all_hours = [v['hours'] for v in sleep_values]

        # Count nights by category
        under_6 = sum(1 for h in all_hours if h < 6)
        between_6_7 = sum(1 for h in all_hours if 6 <= h < 7)
        between_7_8 = sum(1 for h in all_hours if 7 <= h < 8)
        over_8 = sum(1 for h in all_hours if h >= 8)

        return {
            'available': True,
            'avg_hours': round(statistics.mean(all_hours), 1),
            'min_hours': round(min(all_hours), 1),
            'max_hours': round(max(all_hours), 1),
            'under_6h_nights': under_6,
            'under_6h_pct': round(under_6 / len(all_hours) * 100, 0),
            'nights_7plus': between_7_8 + over_8,
            'nights_7plus_pct': round((between_7_8 + over_8) / len(all_hours) * 100, 0),
            'total_nights': len(all_hours),
            'status': 'concern' if statistics.mean(all_hours) < 6.5 else ('good' if statistics.mean(all_hours) >= 7 else 'normal'),
        }

    def _analyze_sedentary(self) -> dict:
        """Analyze sedentary time patterns."""
        sed_values = []

        for day in self.daily_summaries:
            sed_seconds = self._get_stat(day, 'sedentarySeconds')
            if sed_seconds and sed_seconds > 0:
                sed_hours = sed_seconds / 3600

                # Get corresponding sleep
                sleep_hours = None
                for sleep in self.sleep_data:
                    if sleep['_date'] == day['_date']:
                        duration = sleep.get('dailySleepDTO', {}).get('sleepTimeSeconds')
                        if duration:
                            sleep_hours = duration / 3600
                        break

                sed_values.append({
                    'date': day['_date'],
                    'sedentary_hours': sed_hours,
                    'sleep_hours': sleep_hours,
                    'steps': self._get_stat(day, 'totalSteps', 0) or 0,
                })

        if not sed_values:
            return {'available': False}

        all_sed = [v['sedentary_hours'] for v in sed_values]

        # Analyze sedentary vs sleep correlation
        high_sed_sleep = []  # >17 hours sedentary
        med_sed_sleep = []   # 14-17 hours
        low_sed_sleep = []   # <14 hours

        for v in sed_values:
            if v['sleep_hours']:
                if v['sedentary_hours'] > 17:
                    high_sed_sleep.append(v['sleep_hours'])
                elif v['sedentary_hours'] >= 14:
                    med_sed_sleep.append(v['sleep_hours'])
                else:
                    low_sed_sleep.append(v['sleep_hours'])

        return {
            'available': True,
            'avg_hours': round(statistics.mean(all_sed), 1),
            'min_hours': round(min(all_sed), 1),
            'max_hours': round(max(all_sed), 1),
            'high_sed_days': sum(1 for h in all_sed if h > 17),
            'high_sed_pct': round(sum(1 for h in all_sed if h > 17) / len(all_sed) * 100, 0),
            'high_sed_avg_sleep': round(statistics.mean(high_sed_sleep), 1) if high_sed_sleep else None,
            'med_sed_avg_sleep': round(statistics.mean(med_sed_sleep), 1) if med_sed_sleep else None,
            'low_sed_avg_sleep': round(statistics.mean(low_sed_sleep), 1) if low_sed_sleep else None,
            'correlation_found': bool(high_sed_sleep and low_sed_sleep and
                                     statistics.mean(low_sed_sleep) - statistics.mean(high_sed_sleep) > 1),
        }

    def _analyze_stress(self) -> dict:
        """Analyze stress levels and recovery impact."""
        stress_values = []

        for day in self.daily_summaries:
            stress = self._get_stat(day, 'averageStressLevel')
            bb_charged = self._get_stat(day, 'bodyBatteryChargedValue', 0) or 0

            if stress and stress > 0:
                stress_values.append({
                    'date': day['_date'],
                    'stress': stress,
                    'bb_charged': bb_charged,
                })

        if not stress_values:
            return {'available': False}

        all_stress = [v['stress'] for v in stress_values]

        # Analyze stress vs recharge
        low_stress_recharge = []   # <30
        med_stress_recharge = []   # 30-45
        high_stress_recharge = []  # >45

        for v in stress_values:
            if v['bb_charged'] > 0:
                if v['stress'] < 30:
                    low_stress_recharge.append(v['bb_charged'])
                elif v['stress'] <= 45:
                    med_stress_recharge.append(v['bb_charged'])
                else:
                    high_stress_recharge.append(v['bb_charged'])

        return {
            'available': True,
            'avg': round(statistics.mean(all_stress), 0),
            'min': min(all_stress),
            'max': max(all_stress),
            'high_stress_days': sum(1 for s in all_stress if s > 45),
            'high_stress_pct': round(sum(1 for s in all_stress if s > 45) / len(all_stress) * 100, 0),
            'low_stress_recharge': round(statistics.mean(low_stress_recharge), 0) if low_stress_recharge else None,
            'med_stress_recharge': round(statistics.mean(med_stress_recharge), 0) if med_stress_recharge else None,
            'high_stress_recharge': round(statistics.mean(high_stress_recharge), 0) if high_stress_recharge else None,
            'status': 'concern' if statistics.mean(all_stress) > 45 else ('good' if statistics.mean(all_stress) < 35 else 'normal'),
        }

    def _analyze_steps(self) -> dict:
        """Analyze step count patterns."""
        step_values = []

        for day in self.daily_summaries:
            steps = self._get_stat(day, 'totalSteps')
            if steps and steps > 0:
                step_values.append({
                    'date': day['_date'],
                    'steps': steps,
                })

        if not step_values:
            return {'available': False}

        all_steps = [v['steps'] for v in step_values]

        # Categorize days
        low_days = sum(1 for s in all_steps if s < 5000)
        moderate_days = sum(1 for s in all_steps if 5000 <= s < 10000)
        active_days = sum(1 for s in all_steps if 10000 <= s < 20000)
        very_active = sum(1 for s in all_steps if s >= 20000)

        return {
            'available': True,
            'avg': round(statistics.mean(all_steps), 0),
            'min': min(all_steps),
            'max': max(all_steps),
            'std_dev': round(statistics.stdev(all_steps), 0) if len(all_steps) > 1 else 0,
            'low_days': low_days,
            'low_days_pct': round(low_days / len(all_steps) * 100, 0),
            'moderate_days': moderate_days,
            'active_days': active_days,
            'very_active_days': very_active,
            'variability': 'high' if statistics.stdev(all_steps) > 8000 else 'moderate' if statistics.stdev(all_steps) > 4000 else 'low',
        }

    def _analyze_day_of_week(self) -> dict:
        """Analyze patterns by day of week."""
        dow_data = defaultdict(lambda: {
            'sleep': [], 'bb_high': [], 'stress': [],
            'steps': [], 'sedentary': []
        })

        for day in self.daily_summaries:
            try:
                date = datetime.strptime(day['_date'], '%Y-%m-%d')
                dow = date.strftime('%A')

                steps = self._get_stat(day, 'totalSteps')
                sed = self._get_stat(day, 'sedentarySeconds')
                bb = self._get_stat(day, 'bodyBatteryHighestValue')
                stress = self._get_stat(day, 'averageStressLevel')

                if steps:
                    dow_data[dow]['steps'].append(steps)
                if sed:
                    dow_data[dow]['sedentary'].append(sed / 3600)
                if bb:
                    dow_data[dow]['bb_high'].append(bb)
                if stress:
                    dow_data[dow]['stress'].append(stress)
            except ValueError:
                continue

        # Add sleep data
        for sleep in self.sleep_data:
            try:
                date = datetime.strptime(sleep['_date'], '%Y-%m-%d')
                dow = date.strftime('%A')
                duration = sleep.get('dailySleepDTO', {}).get('sleepTimeSeconds')
                if duration:
                    dow_data[dow]['sleep'].append(duration / 3600)
            except ValueError:
                continue

        # Calculate averages
        results = {}
        day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

        for day in day_order:
            data = dow_data[day]
            results[day] = {
                'avg_sleep': round(statistics.mean(data['sleep']), 1) if data['sleep'] else None,
                'avg_bb': round(statistics.mean(data['bb_high']), 0) if data['bb_high'] else None,
                'avg_stress': round(statistics.mean(data['stress']), 0) if data['stress'] else None,
                'avg_steps': round(statistics.mean(data['steps']), 0) if data['steps'] else None,
                'avg_sedentary': round(statistics.mean(data['sedentary']), 1) if data['sedentary'] else None,
            }

        # Find best and worst days
        sleep_by_day = [(d, results[d]['avg_sleep']) for d in day_order if results[d]['avg_sleep']]
        bb_by_day = [(d, results[d]['avg_bb']) for d in day_order if results[d]['avg_bb']]

        return {
            'available': True,
            'by_day': results,
            'best_sleep_day': max(sleep_by_day, key=lambda x: x[1])[0] if sleep_by_day else None,
            'worst_sleep_day': min(sleep_by_day, key=lambda x: x[1])[0] if sleep_by_day else None,
            'best_bb_day': max(bb_by_day, key=lambda x: x[1])[0] if bb_by_day else None,
            'worst_bb_day': min(bb_by_day, key=lambda x: x[1])[0] if bb_by_day else None,
        }

    def _analyze_monthly_trends(self) -> dict:
        """Analyze trends by month."""
        monthly_data = defaultdict(lambda: {
            'rhr': [], 'bb_high': [], 'sleep': [],
            'stress': [], 'steps': [], 'vigorous': []
        })

        for day in self.daily_summaries:
            try:
                date = datetime.strptime(day['_date'], '%Y-%m-%d')
                month_key = date.strftime('%Y-%m')

                rhr = self._get_stat(day, 'restingHeartRate')
                bb = self._get_stat(day, 'bodyBatteryHighestValue')
                stress = self._get_stat(day, 'averageStressLevel')
                steps = self._get_stat(day, 'totalSteps')
                vigorous = self._get_stat(day, 'vigorousIntensityMinutes')

                if rhr:
                    monthly_data[month_key]['rhr'].append(rhr)
                if bb:
                    monthly_data[month_key]['bb_high'].append(bb)
                if stress:
                    monthly_data[month_key]['stress'].append(stress)
                if steps:
                    monthly_data[month_key]['steps'].append(steps)
                if vigorous:
                    monthly_data[month_key]['vigorous'].append(vigorous)
            except ValueError:
                continue

        # Add sleep
        for sleep in self.sleep_data:
            try:
                date = datetime.strptime(sleep['_date'], '%Y-%m-%d')
                month_key = date.strftime('%Y-%m')
                duration = sleep.get('dailySleepDTO', {}).get('sleepTimeSeconds')
                if duration:
                    monthly_data[month_key]['sleep'].append(duration / 3600)
            except ValueError:
                continue

        # Calculate monthly averages
        results = {}
        for month in sorted(monthly_data.keys()):
            data = monthly_data[month]
            results[month] = {
                'avg_rhr': round(statistics.mean(data['rhr']), 1) if data['rhr'] else None,
                'avg_bb': round(statistics.mean(data['bb_high']), 0) if data['bb_high'] else None,
                'avg_sleep': round(statistics.mean(data['sleep']), 1) if data['sleep'] else None,
                'avg_stress': round(statistics.mean(data['stress']), 0) if data['stress'] else None,
                'avg_steps': round(statistics.mean(data['steps']), 0) if data['steps'] else None,
                'total_vigorous': sum(data['vigorous']) if data['vigorous'] else None,
                'days': len(data['rhr']) or len(data['bb_high']) or len(data['sleep']),
            }

        return {
            'available': True,
            'by_month': results,
            'months_analyzed': len(results),
        }

    def _analyze_correlations(self) -> dict:
        """Analyze correlations between different metrics."""
        correlations = {}

        # Sleep vs next-day Body Battery
        sleep_bb_pairs = []
        for i, sleep in enumerate(self.sleep_data[:-1]):
            try:
                sleep_date = datetime.strptime(sleep['_date'], '%Y-%m-%d')
                next_date = (sleep_date + timedelta(days=1)).strftime('%Y-%m-%d')

                duration = sleep.get('dailySleepDTO', {}).get('sleepTimeSeconds')
                if not duration:
                    continue

                # Find next day's BB
                for day in self.daily_summaries:
                    if day['_date'] == next_date:
                        bb = day.get('bodyBatteryHighestValue')
                        if bb:
                            sleep_bb_pairs.append({
                                'sleep': duration / 3600,
                                'bb': bb
                            })
                        break
            except ValueError:
                continue

        if sleep_bb_pairs:
            # Group by sleep duration
            short_sleep_bb = [p['bb'] for p in sleep_bb_pairs if p['sleep'] < 6]
            normal_sleep_bb = [p['bb'] for p in sleep_bb_pairs if 6 <= p['sleep'] < 7.5]
            long_sleep_bb = [p['bb'] for p in sleep_bb_pairs if p['sleep'] >= 7.5]

            correlations['sleep_to_bb'] = {
                'short_sleep_avg_bb': round(statistics.mean(short_sleep_bb), 0) if short_sleep_bb else None,
                'normal_sleep_avg_bb': round(statistics.mean(normal_sleep_bb), 0) if normal_sleep_bb else None,
                'long_sleep_avg_bb': round(statistics.mean(long_sleep_bb), 0) if long_sleep_bb else None,
            }

        return correlations

    def _generate_recommendations(self) -> list:
        """Generate personalized recommendations based on the analysis."""
        recommendations = []

        # Check RHR trend
        rhr = self.analysis_results.get('resting_hr', {})
        if rhr.get('available') and rhr.get('status') == 'concern':
            recommendations.append({
                'category': 'Recovery',
                'priority': 'high',
                'finding': f"Resting HR increased from {rhr['baseline']} to {rhr['current']} bpm ({rhr['change']:+.1f})",
                'recommendation': 'Consider a recovery week with reduced training intensity and volume.',
                'science': 'A rise in resting HR often indicates accumulated fatigue or incomplete recovery.'
            })

        # Check Body Battery
        bb = self.analysis_results.get('body_battery', {})
        if bb.get('available') and bb.get('status') == 'concern':
            recommendations.append({
                'category': 'Recovery',
                'priority': 'high',
                'finding': f"Body Battery wake average is {bb['current_wake']} (baseline: {bb['baseline_wake']})",
                'recommendation': 'Focus on sleep quality and stress management. Consider earlier bedtime.',
                'science': 'Body Battery below 60 suggests chronic recovery deficit.'
            })

        # Check sleep
        sleep = self.analysis_results.get('sleep', {})
        if sleep.get('available') and sleep.get('status') == 'concern':
            recommendations.append({
                'category': 'Sleep',
                'priority': 'high',
                'finding': f"Average sleep is {sleep['avg_hours']} hours ({sleep['under_6h_pct']}% of nights under 6h)",
                'recommendation': 'Prioritize sleep: aim for 7-8 hours. Set a consistent bedtime alarm.',
                'science': 'Research shows <7h sleep increases injury risk by 1.7x in athletes.'
            })

        # Check sedentary
        sed = self.analysis_results.get('sedentary', {})
        if sed.get('available') and sed.get('high_sed_pct', 0) > 30:
            recommendations.append({
                'category': 'Movement',
                'priority': 'medium',
                'finding': f"{sed['high_sed_pct']}% of days have 17+ hours sedentary",
                'recommendation': 'Add movement breaks every 90 minutes. Consider walking meetings.',
                'science': 'Prolonged sitting has independent health effects beyond exercise.'
            })

        # Check stress
        stress = self.analysis_results.get('stress', {})
        if stress.get('available') and stress.get('status') == 'concern':
            recommendations.append({
                'category': 'Stress',
                'priority': 'medium',
                'finding': f"Average stress level is {stress['avg']} ({stress['high_stress_pct']}% days above 45)",
                'recommendation': 'Practice stress management: breathing exercises, meditation, or time in nature.',
                'science': 'High stress throttles overnight recovery regardless of sleep duration.'
            })

        # Check step variability
        steps = self.analysis_results.get('steps', {})
        if steps.get('available') and steps.get('variability') == 'high':
            recommendations.append({
                'category': 'Consistency',
                'priority': 'low',
                'finding': f"Step counts vary widely (std dev: {steps['std_dev']})",
                'recommendation': 'Aim for more consistent daily movement rather than extreme swings.',
                'science': 'Consistent moderate activity supports better recovery than feast/famine patterns.'
            })

        # Day of week patterns
        dow = self.analysis_results.get('day_of_week', {})
        if dow.get('available') and dow.get('worst_sleep_day'):
            worst = dow['worst_sleep_day']
            best = dow['best_sleep_day']
            if dow['by_day'][worst]['avg_sleep'] and dow['by_day'][best]['avg_sleep']:
                diff = dow['by_day'][best]['avg_sleep'] - dow['by_day'][worst]['avg_sleep']
                if diff > 1.5:
                    recommendations.append({
                        'category': 'Patterns',
                        'priority': 'medium',
                        'finding': f"{worst} has lowest sleep ({dow['by_day'][worst]['avg_sleep']}h) vs {best} ({dow['by_day'][best]['avg_sleep']}h)",
                        'recommendation': f'Investigate what happens on {worst} nights. Consider protecting sleep on key training days.',
                        'science': 'Consistent sleep timing is more important than occasional catch-up sleep.'
                    })

        return recommendations

    def get_summary_text(self) -> str:
        """Generate a text summary of the analysis."""
        if not self.analysis_results:
            return "No analysis results available. Run analyze_all() first."

        lines = []
        overview = self.analysis_results.get('overview', {})

        lines.append(f"=== GARMIN DATA ANALYSIS SUMMARY ===")
        lines.append(f"Data range: {overview.get('start_date')} to {overview.get('end_date')}")
        lines.append(f"Days analyzed: {overview.get('total_days')}")
        lines.append("")

        # Key metrics
        rhr = self.analysis_results.get('resting_hr', {})
        if rhr.get('available'):
            lines.append(f"Resting HR: {rhr['current']} bpm (baseline: {rhr['baseline']}, {rhr['change']:+.1f} change)")

        bb = self.analysis_results.get('body_battery', {})
        if bb.get('available'):
            lines.append(f"Body Battery: {bb['current_wake']} wake avg (baseline: {bb['baseline_wake']})")

        vo2 = self.analysis_results.get('vo2max', {})
        if vo2.get('available'):
            lines.append(f"VO2 Max: {vo2['current']} ml/kg/min ({vo2['fitness_level']}, {vo2['change']:+.1f} change)")

        sleep = self.analysis_results.get('sleep', {})
        if sleep.get('available'):
            lines.append(f"Sleep: {sleep['avg_hours']} hrs avg ({sleep['under_6h_pct']}% nights under 6h)")

        stress = self.analysis_results.get('stress', {})
        if stress.get('available'):
            lines.append(f"Stress: {stress['avg']} avg ({stress['high_stress_pct']}% days above 45)")

        lines.append("")
        lines.append("=== TOP RECOMMENDATIONS ===")
        for rec in self.analysis_results.get('recommendations', [])[:3]:
            lines.append(f"[{rec['priority'].upper()}] {rec['category']}: {rec['recommendation']}")

        return "\n".join(lines)


def main():
    """Run analysis on data in the default directory."""
    analyzer = GarminDataAnalyzer()

    print("Loading Garmin data...")
    load_result = analyzer.load_data()
    print(f"  Daily summaries: {load_result['daily_summaries']}")
    print(f"  Sleep records: {load_result['sleep']}")
    print(f"  Heart rate records: {load_result['heart_rate']}")
    print(f"  VO2 max records: {load_result['vo2max']}")

    if load_result['date_range']:
        print(f"  Date range: {load_result['date_range'][0]} to {load_result['date_range'][1]}")

    if load_result['daily_summaries'] == 0:
        print("\nNo data found. Run 'python main.py fetch' first to download your Garmin data.")
        return

    print("\nRunning analysis...")
    analyzer.analyze_all()

    print("\n" + analyzer.get_summary_text())


if __name__ == "__main__":
    main()
