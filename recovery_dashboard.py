#!/usr/bin/env python3
"""Daily Ramp-Up Coach — Post-event recovery → ramp-up → steady state.

Evolves from the recovery dashboard. Fetches Garmin data, calculates readiness,
determines training phase, checks gate conditions, and sends a daily email
with tomorrow's workout plan.
"""

import json
import logging
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

from config import config, setup_logging
from email_sender import send_email
from garmin_client import GarminClient

logger = setup_logging("recovery_dashboard")

# ── Ramp-up config ─────────────────────────────────────────────────
RAMPUP_CONFIG = {
    'event_name': 'Marathon',
    'event_date': date(2026, 3, 1),
    'rhr_baseline': 43.2,
    'phases': {
        1: {'name': 'Recovery', 'days': (1, 7), 'desc': 'Walks and easy bike only. No strength.'},
        2: {'name': 'Half-Volume', 'days': (8, 14), 'desc': '2 sets per exercise, skip split squats/calf raises + light aerobic.'},
        3: {'name': 'Three-Quarter', 'days': (15, 21), 'desc': 'All exercises back, 3 sets most + normal aerobic.'},
        4: {'name': 'Steady State', 'days': (22, None), 'desc': 'Full plan. Consider disabling email and using runplan.fun.'},
    },
}

# ── Gate thresholds (checked daily starting day 8) ─────────────────
GATE_THRESHOLDS = {
    'rhr_trending_down': True,   # last 3 days avg < previous 3 days avg
    'sleep_hr_max': 53,
    'bb_wake_min': 80,
    'sleep_score_min': 70,
}

# ── Strength exercises ────────────────────────────────────────────
# sets_by_phase: {phase_num: sets} — None means skip in that phase
STRENGTH_EXERCISES = [
    {'name': 'Pull-ups', 'sets_by_phase': {2: 2, 3: 3, 4: 3}, 'notes': ''},
    {'name': 'Goblet squats', 'sets_by_phase': {2: 2, 3: 3, 4: 3}, 'notes': 'Slow eccentric (3s down)'},
    {'name': 'Ring push-ups', 'sets_by_phase': {2: 2, 3: 3, 4: 3}, 'notes': ''},
    {'name': 'RDL', 'sets_by_phase': {2: 2, 3: 3, 4: 3}, 'notes': 'Slow eccentric (3s down)'},
    {'name': 'Bulgarian split squats', 'sets_by_phase': {2: None, 3: 2, 4: 3}, 'notes': 'Each leg'},
    {'name': 'Ring rows', 'sets_by_phase': {2: 2, 3: 2, 4: 2}, 'notes': ''},
    {'name': 'Ring support hold', 'sets_by_phase': {2: 2, 3: 3, 4: 3}, 'notes': ''},
    {'name': 'Bent-knee calf raises', 'sets_by_phase': {2: None, 3: 2, 4: 2}, 'notes': 'Eccentric focus'},
    {'name': 'Core', 'sets_by_phase': {2: 2, 3: 2, 4: 2}, 'notes': ''},
]

# ── Weekly schedule (phases 2-4; phase 1 overrides everything) ────
# Values: 'strength_bike', 'run', 'rest', 'long_run_ride', 'rest_walk', 'rest_easy'
WEEKLY_SCHEDULE = {
    0: {'type': 'strength_bike', 'label': 'Strength + 30-40 min easy bike'},
    1: {'type': 'run', 'label': 'Easy run (30-45 min, Zone 2) — see runplan.fun'},
    2: {'type': 'rest', 'label': 'Rest day'},
    3: {'type': 'strength_bike', 'label': 'Strength + optional easy bike'},
    4: {'type': 'rest_walk', 'label': 'Rest or easy walk'},
    5: {'type': 'long_run_ride', 'label': 'Longer easy run or ride (45-60 min) — see runplan.fun'},
    6: {'type': 'rest_easy', 'label': 'Rest or easy movement'},
}

# ── Send timing ────────────────────────────────────────────────────
SEND_TIMING = "evening"

# ── Readiness config ──────────────────────────────────────────────
READINESS_CONFIG = {
    'red': {
        'color': '#dc3545',
        'label': 'Rest Day',
        'message': 'Multiple recovery indicators are poor. Your body needs more time.',
    },
    'yellow': {
        'color': '#ffc107',
        'label': 'Light Movement Only',
        'message': 'Recovery is progressing but not there yet.',
    },
    'green': {
        'color': '#28a745',
        'label': 'Easy Activity OK',
        'message': 'Recovery metrics are trending back to normal.',
    },
    'insufficient': {
        'color': '#ffc107',
        'label': 'Insufficient Data',
        'message': 'Not enough metrics available to assess readiness.',
    },
}

# ── Readiness thresholds ──────────────────────────────────────────
THRESHOLDS = {
    'rhr_green': 3,
    'rhr_yellow': 5,
    'bb_green': 80,
    'bb_yellow': 60,
    'sleep_score_green': 75,
    'sleep_score_yellow': 60,
    'sleep_hr_green': 52,
    'sleep_hr_yellow': 56,
    'rem_green': 60,
    'rem_yellow': 40,
}


# ── Timezone-aware "today" ─────────────────────────────────────────
# GitHub Actions runs in UTC. Use the user's timezone so day/phase are correct.
USER_TZ = ZoneInfo("America/Los_Angeles")

def _today() -> date:
    """Return today's date in the user's timezone."""
    return datetime.now(USER_TZ).date()


# ═══════════════════════════════════════════════════════════════════
# Data fetching & loading
# ═══════════════════════════════════════════════════════════════════

def fetch_data() -> bool:
    """Fetch recent Garmin data (14 days for RHR trending)."""
    try:
        client = GarminClient()
        if not client.login():
            logger.error("Failed to login to Garmin Connect")
            return False
        days = 14
        client.fetch_daily_summaries(days=days, force=True)
        client.fetch_sleep(days=days, force=True)
        client.fetch_heart_rate(days=days, force=True)
        logger.info("Data fetch complete")
        return True
    except Exception as e:
        logger.error(f"Fetch failed: {e}")
        return False


def load_daily_summaries() -> list[dict]:
    """Load daily summary JSON files sorted by date."""
    summaries = []
    summary_dir = config.data_dir / "daily_summaries"
    if not summary_dir.exists():
        return summaries
    for f in sorted(summary_dir.glob("*.json")):
        try:
            with open(f) as fh:
                data = json.load(fh)
                data['_date'] = f.stem
                summaries.append(data)
        except (json.JSONDecodeError, IOError):
            continue
    return summaries


def load_sleep_data() -> list[dict]:
    """Load sleep JSON files sorted by date."""
    sleeps = []
    sleep_dir = config.data_dir / "sleep"
    if not sleep_dir.exists():
        return sleeps
    for f in sorted(sleep_dir.glob("*.json")):
        try:
            with open(f) as fh:
                data = json.load(fh)
                data['_date'] = f.stem
                sleeps.append(data)
        except (json.JSONDecodeError, IOError):
            continue
    return sleeps


def get_stat(day: dict, key: str, default=None):
    """Get a stat from daily summary, handling nested 'stats' structure."""
    if key in day:
        return day[key]
    if 'stats' in day and isinstance(day['stats'], dict):
        return day['stats'].get(key, default)
    return default


# ═══════════════════════════════════════════════════════════════════
# Metric extraction & readiness scoring
# ═══════════════════════════════════════════════════════════════════

def extract_metrics(summaries: list[dict], sleeps: list[dict]) -> list[dict]:
    """Extract daily recovery metrics from raw data."""
    rhr_baseline = RAMPUP_CONFIG['rhr_baseline']

    sleep_by_date = {}
    for s in sleeps:
        d = s.get('_date', '')
        if d:
            sleep_by_date[d] = s

    days = []
    for summary in summaries:
        dt = summary.get('_date', '')
        if not dt:
            continue

        rhr = get_stat(summary, 'restingHeartRate')
        bb_wake = get_stat(summary, 'bodyBatteryAtWakeTime')
        bb_highest = get_stat(summary, 'bodyBatteryHighestValue')
        bb_lowest = get_stat(summary, 'bodyBatteryLowestValue')
        stress_avg = get_stat(summary, 'averageStressLevel')

        # Sleep metrics
        sleep = sleep_by_date.get(dt, {})
        sleep_dto = sleep.get('dailySleepDTO', {})
        sleep_score = None
        sleep_scores = sleep_dto.get('sleepScores', {})
        if sleep_scores and 'overall' in sleep_scores:
            sleep_score = sleep_scores['overall'].get('value')

        sleep_seconds = sleep_dto.get('sleepTimeSeconds', 0)
        sleep_hours = round(sleep_seconds / 3600, 1) if sleep_seconds else None
        deep_seconds = sleep_dto.get('deepSleepSeconds', 0)
        deep_min = round(deep_seconds / 60) if deep_seconds else None
        rem_seconds = sleep_dto.get('remSleepSeconds', 0)
        rem_min = round(rem_seconds / 60) if rem_seconds else None
        light_seconds = sleep_dto.get('lightSleepSeconds', 0)
        light_min = round(light_seconds / 60) if light_seconds else None
        sleep_hr = sleep_dto.get('avgHeartRate')

        days.append({
            'date': dt,
            'rhr': rhr,
            'rhr_delta': round(rhr - rhr_baseline, 1) if rhr else None,
            'bb_wake': bb_wake,
            'bb_highest': bb_highest,
            'bb_lowest': bb_lowest,
            'stress_avg': stress_avg,
            'sleep_score': sleep_score,
            'sleep_hours': sleep_hours,
            'deep_min': deep_min,
            'rem_min': rem_min,
            'light_min': light_min,
            'sleep_hr': sleep_hr,
        })

    return days


def calculate_readiness(today: dict) -> dict:
    """Calculate red/yellow/green readiness from today's metrics."""
    rhr = today.get('rhr')
    rhr_delta = today.get('rhr_delta')
    bb_wake = today.get('bb_wake')
    sleep_score = today.get('sleep_score')
    sleep_hr = today.get('sleep_hr')
    rem_min = today.get('rem_min')
    t = THRESHOLDS

    scores = []

    if rhr_delta is not None:
        if rhr_delta <= t['rhr_green']:
            scores.append((2, f"RHR {rhr} bpm (+{rhr_delta} from baseline) — near normal"))
        elif rhr_delta <= t['rhr_yellow']:
            scores.append((1, f"RHR {rhr} bpm (+{rhr_delta} from baseline) — still elevated"))
        else:
            scores.append((0, f"RHR {rhr} bpm (+{rhr_delta} from baseline) — significantly elevated"))

    if bb_wake is not None:
        if bb_wake >= t['bb_green']:
            scores.append((2, f"Body Battery at wake: {bb_wake} — strong recharge"))
        elif bb_wake >= t['bb_yellow']:
            scores.append((1, f"Body Battery at wake: {bb_wake} — partial recharge"))
        else:
            scores.append((0, f"Body Battery at wake: {bb_wake} — poor recharge"))

    if sleep_score is not None:
        if sleep_score >= t['sleep_score_green']:
            scores.append((2, f"Sleep score: {sleep_score} — good quality"))
        elif sleep_score >= t['sleep_score_yellow']:
            scores.append((1, f"Sleep score: {sleep_score} — fair quality"))
        else:
            scores.append((0, f"Sleep score: {sleep_score} — poor quality"))

    if sleep_hr is not None:
        if sleep_hr <= t['sleep_hr_green']:
            scores.append((2, f"Sleep HR: {sleep_hr} bpm — recovered"))
        elif sleep_hr <= t['sleep_hr_yellow']:
            scores.append((1, f"Sleep HR: {sleep_hr} bpm — still elevated"))
        else:
            scores.append((0, f"Sleep HR: {sleep_hr} bpm — high, body still stressed"))

    if rem_min is not None:
        if rem_min >= t['rem_green']:
            scores.append((2, f"REM sleep: {rem_min} min — good"))
        elif rem_min >= t['rem_yellow']:
            scores.append((1, f"REM sleep: {rem_min} min — below optimal"))
        else:
            scores.append((0, f"REM sleep: {rem_min} min — significantly low"))

    if not scores:
        cfg = READINESS_CONFIG['insufficient']
        return {
            'level': 'yellow',
            'color': cfg['color'],
            'label': cfg['label'],
            'message': cfg['message'],
            'details': [],
        }

    avg_score = sum(s for s, _ in scores) / len(scores)
    red_count = sum(1 for s, _ in scores if s == 0)
    details = [reason for _, reason in scores]

    if red_count >= 2 or avg_score < 0.8:
        level = 'red'
    elif avg_score < 1.5:
        level = 'yellow'
    else:
        level = 'green'

    cfg = READINESS_CONFIG[level]
    return {
        'level': level,
        'color': cfg['color'],
        'label': cfg['label'],
        'message': cfg['message'],
        'details': details,
    }


# ═══════════════════════════════════════════════════════════════════
# Phase, gate, and workout logic
# ═══════════════════════════════════════════════════════════════════

def determine_phase(today: date) -> dict:
    """Determine the calendar-based phase from event date."""
    event_date = RAMPUP_CONFIG['event_date']
    day_num = (today - event_date).days

    for phase_num, phase in RAMPUP_CONFIG['phases'].items():
        start, end = phase['days']
        if end is None:
            if day_num >= start:
                return {'phase_num': phase_num, 'name': phase['name'], 'desc': phase['desc'], 'day_num': day_num}
        elif start <= day_num <= end:
            return {'phase_num': phase_num, 'name': phase['name'], 'desc': phase['desc'], 'day_num': day_num}

    # Before event or something unexpected — treat as phase 1
    return {'phase_num': 1, 'name': 'Recovery', 'desc': RAMPUP_CONFIG['phases'][1]['desc'], 'day_num': day_num}


def check_gates(metrics: list[dict]) -> dict:
    """Check 4 gate conditions for phase advancement.

    Returns dict with 'passed' bool, 'results' list, and 'hold_reason' str.
    """
    results = []
    g = GATE_THRESHOLDS

    # Need at least 6 days of data for RHR trending (3+3)
    rhr_values = [m['rhr'] for m in metrics if m.get('rhr') is not None]

    # Gate 1: RHR trending down (last 3 avg < previous 3 avg)
    if len(rhr_values) >= 6:
        recent_3 = sum(rhr_values[-3:]) / 3
        prev_3 = sum(rhr_values[-6:-3]) / 3
        passed = recent_3 < prev_3
        results.append({
            'name': 'RHR trending down',
            'passed': passed,
            'detail': f"Recent 3-day avg: {recent_3:.1f} vs prior 3-day avg: {prev_3:.1f}",
        })
    else:
        results.append({
            'name': 'RHR trending down',
            'passed': None,  # insufficient data
            'detail': f"Need 6+ days of data (have {len(rhr_values)})",
        })

    # Use most recent day with data for remaining gates
    latest = {}
    for m in reversed(metrics):
        if m.get('rhr') is not None or m.get('bb_wake') is not None:
            latest = m
            break

    # Gate 2: Sleep HR < threshold
    sleep_hr = latest.get('sleep_hr')
    if sleep_hr is not None:
        passed = sleep_hr < g['sleep_hr_max']
        results.append({
            'name': f"Sleep HR < {g['sleep_hr_max']}",
            'passed': passed,
            'detail': f"Sleep HR: {sleep_hr} bpm",
        })
    else:
        results.append({
            'name': f"Sleep HR < {g['sleep_hr_max']}",
            'passed': None,
            'detail': "No sleep HR data",
        })

    # Gate 3: Body battery at wake > threshold
    bb_wake = latest.get('bb_wake')
    if bb_wake is not None:
        passed = bb_wake > g['bb_wake_min']
        results.append({
            'name': f"Body battery wake > {g['bb_wake_min']}",
            'passed': passed,
            'detail': f"Body battery at wake: {bb_wake}",
        })
    else:
        results.append({
            'name': f"Body battery wake > {g['bb_wake_min']}",
            'passed': None,
            'detail': "No body battery data",
        })

    # Gate 4: Sleep score > threshold
    sleep_score = latest.get('sleep_score')
    if sleep_score is not None:
        passed = sleep_score > g['sleep_score_min']
        results.append({
            'name': f"Sleep score > {g['sleep_score_min']}",
            'passed': passed,
            'detail': f"Sleep score: {sleep_score}",
        })
    else:
        results.append({
            'name': f"Sleep score > {g['sleep_score_min']}",
            'passed': None,
            'detail': "No sleep score data",
        })

    # Overall: all non-None gates must pass
    evaluated = [r for r in results if r['passed'] is not None]
    all_passed = len(evaluated) > 0 and all(r['passed'] for r in evaluated)

    hold_reasons = [r['name'] for r in results if r['passed'] is False]
    hold_reason = f"Holding due to: {', '.join(hold_reasons)}" if hold_reasons else ""

    return {
        'passed': all_passed,
        'results': results,
        'hold_reason': hold_reason,
    }


def get_effective_phase(calendar_phase: int, gate_result: dict) -> int:
    """Apply gate hold logic. If gates fail and calendar_phase >= 2, hold at previous phase."""
    if calendar_phase <= 1:
        return calendar_phase
    if gate_result['passed']:
        return calendar_phase
    # Hold at previous phase
    return max(1, calendar_phase - 1)


def get_tomorrows_workout(phase_num: int, tomorrow: date = None) -> dict:
    """Get tomorrow's workout based on phase and day of week."""
    if tomorrow is None:
        tomorrow = _today() + timedelta(days=1)

    day_of_week = tomorrow.weekday()  # 0=Monday
    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    day_name = day_names[day_of_week]

    # Phase 1: everything is walk/bike
    if phase_num == 1:
        return {
            'day_name': day_name,
            'type': 'recovery',
            'label': 'Walk or easy bike only (20-40 min, Zone 1)',
            'exercises': [],
        }

    schedule = WEEKLY_SCHEDULE.get(day_of_week, {'type': 'rest', 'label': 'Rest day'})

    exercises = []
    if schedule['type'] == 'strength_bike':
        for ex in STRENGTH_EXERCISES:
            sets = ex['sets_by_phase'].get(phase_num)
            if sets is not None:
                exercises.append({
                    'name': ex['name'],
                    'sets': sets,
                    'notes': ex['notes'],
                })

    return {
        'day_name': day_name,
        'type': schedule['type'],
        'label': schedule['label'],
        'exercises': exercises,
    }


# ═══════════════════════════════════════════════════════════════════
# Trend helpers
# ═══════════════════════════════════════════════════════════════════

def trend_arrow(values: list) -> str:
    """Return trend arrow based on recent values (lower is better)."""
    clean = [v for v in values if v is not None]
    if len(clean) < 2:
        return "—"
    if clean[-1] < clean[-2]:
        return "&#8600;"
    elif clean[-1] > clean[-2]:
        return "&#8599;"
    return "&#8594;"


def trend_arrow_higher_better(values: list) -> str:
    """Return trend arrow where higher is better (body battery, sleep score)."""
    clean = [v for v in values if v is not None]
    if len(clean) < 2:
        return "—"
    if clean[-1] > clean[-2]:
        return "&#8599;"
    elif clean[-1] < clean[-2]:
        return "&#8600;"
    return "&#8594;"


# ═══════════════════════════════════════════════════════════════════
# HTML generation
# ═══════════════════════════════════════════════════════════════════

def _build_trend_rows(metrics: list[dict], today_iso: str) -> str:
    """Build HTML table rows for the trend table."""
    event_date = RAMPUP_CONFIG['event_date']
    rows = ""
    for m in metrics:
        dt = m['date']
        day_num = (date.fromisoformat(dt) - event_date).days
        rhr_str = f"{m['rhr']} <span style='color:#999;font-size:11px;'>(+{m['rhr_delta']})</span>" if m['rhr'] else "—"
        bb_str = str(m['bb_wake']) if m['bb_wake'] else "—"
        sleep_str = str(m['sleep_score']) if m['sleep_score'] else "—"
        rem_str = f"{m['rem_min']}m" if m['rem_min'] else "—"
        deep_str = f"{m['deep_min']}m" if m['deep_min'] else "—"
        sleep_hr_str = str(m['sleep_hr']) if m['sleep_hr'] else "—"

        is_today = dt == today_iso
        row_style = "background-color: #f0f4ff;" if is_today else ""

        rows += f"""
        <tr style="{row_style}">
            <td style="padding:8px 10px;border-bottom:1px solid #eee;font-weight:{'bold' if is_today else 'normal'};">
                Day {day_num}<br><span style="color:#999;font-size:11px;">{dt}</span>
            </td>
            <td style="padding:8px 10px;border-bottom:1px solid #eee;text-align:center;">{rhr_str}</td>
            <td style="padding:8px 10px;border-bottom:1px solid #eee;text-align:center;">{sleep_hr_str}</td>
            <td style="padding:8px 10px;border-bottom:1px solid #eee;text-align:center;">{bb_str}</td>
            <td style="padding:8px 10px;border-bottom:1px solid #eee;text-align:center;">{sleep_str}</td>
            <td style="padding:8px 10px;border-bottom:1px solid #eee;text-align:center;">{rem_str}</td>
            <td style="padding:8px 10px;border-bottom:1px solid #eee;text-align:center;">{deep_str}</td>
        </tr>"""
    return rows


def _build_details_html(details: list[str]) -> str:
    """Build HTML rows for readiness detail indicators."""
    html = ""
    for detail in details:
        if "near normal" in detail or "strong" in detail or "good" in detail or "recovered" in detail:
            dot = "&#9989;"
        elif "still" in detail or "partial" in detail or "fair" in detail or "below" in detail:
            dot = "&#128310;"
        else:
            dot = "&#9888;"
        html += f"<tr><td style='padding:6px 0;'>{dot} {detail}</td></tr>"
    return html


def _build_workout_html(workout: dict) -> str:
    """Build HTML for tomorrow's workout card."""
    exercises = workout.get('exercises', [])
    if not exercises:
        return ""

    rows = ""
    for ex in exercises:
        notes = f" <span style='color:#999;font-size:11px;'>({ex['notes']})</span>" if ex['notes'] else ""
        rows += f"""
        <tr>
            <td style="padding:6px 10px;border-bottom:1px solid #eee;">{ex['name']}{notes}</td>
            <td style="padding:6px 10px;border-bottom:1px solid #eee;text-align:center;">{ex['sets']}</td>
        </tr>"""

    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" style="font-size:13px;margin-top:8px;">
        <tr style="background-color:#f8f9fa;">
            <th style="padding:6px 10px;text-align:left;border-bottom:2px solid #ddd;">Exercise</th>
            <th style="padding:6px 10px;text-align:center;border-bottom:2px solid #ddd;">Sets</th>
        </tr>
        {rows}
    </table>"""


def _build_gate_html(gate_result: dict, phase_info: dict) -> str:
    """Build HTML for gate check status section."""
    rows = ""
    for r in gate_result['results']:
        if r['passed'] is True:
            icon = "&#9989;"
            status = "Pass"
        elif r['passed'] is False:
            icon = "&#10060;"
            status = "Fail"
        else:
            icon = "&#9898;"
            status = "N/A"

        rows += f"""
        <tr>
            <td style="padding:6px 10px;border-bottom:1px solid #eee;">{icon} {r['name']}</td>
            <td style="padding:6px 10px;border-bottom:1px solid #eee;text-align:center;">{status}</td>
            <td style="padding:6px 10px;border-bottom:1px solid #eee;color:#666;font-size:12px;">{r['detail']}</td>
        </tr>"""

    hold_banner = ""
    if gate_result['hold_reason']:
        hold_banner = f"""
        <div style="background-color:#fff3cd;border:1px solid #ffc107;border-radius:6px;padding:10px 14px;margin-top:10px;font-size:13px;">
            &#9888; {gate_result['hold_reason']} — staying in Phase {max(1, phase_info['phase_num'] - 1)}.
        </div>"""

    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" style="font-size:13px;">
        <tr style="background-color:#f8f9fa;">
            <th style="padding:6px 10px;text-align:left;border-bottom:2px solid #ddd;">Gate Check</th>
            <th style="padding:6px 10px;text-align:center;border-bottom:2px solid #ddd;">Status</th>
            <th style="padding:6px 10px;text-align:left;border-bottom:2px solid #ddd;">Detail</th>
        </tr>
        {rows}
    </table>
    {hold_banner}"""


def _build_tomorrows_plan_html(workout: dict) -> str:
    """Build HTML for tomorrow's plan card."""
    exercise_table = _build_workout_html(workout)

    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#e8f5e9;border-radius:8px;border:1px solid #c8e6c9;">
        <tr>
            <td style="padding:16px;">
                <div style="font-size:16px;font-weight:bold;color:#2e7d32;margin-bottom:4px;">
                    Tomorrow ({workout['day_name']})
                </div>
                <div style="font-size:14px;color:#444;margin-bottom:8px;">
                    {workout['label']}
                </div>
                {exercise_table}
            </td>
        </tr>
    </table>"""


def generate_html(metrics: list[dict], readiness: dict, phase_info: dict, gate_result: dict, workout: dict) -> str:
    """Generate the ramp-up coach HTML email."""
    today = _today()
    rhr_baseline = RAMPUP_CONFIG['rhr_baseline']
    day_num = phase_info['day_num']
    effective_phase = phase_info['effective_phase']

    trend_rows = _build_trend_rows(metrics, today.isoformat())
    details_html = _build_details_html(readiness['details'])

    rhr_trend = trend_arrow([m['rhr'] for m in metrics])
    bb_trend = trend_arrow_higher_better([m['bb_wake'] for m in metrics])
    sleep_trend = trend_arrow_higher_better([m['sleep_score'] for m in metrics])

    # Tomorrow's plan section
    tomorrows_plan_html = _build_tomorrows_plan_html(workout)

    # Gate check section (show from phase 2+ calendar time, or always as informational)
    gate_section = ""
    if phase_info['calendar_phase'] >= 2:
        gate_html = _build_gate_html(gate_result, phase_info)
        gate_section = f"""
    <tr>
        <td style="padding:0 24px 20px 24px;">
            <h2 style="color:#333;font-size:16px;margin:0 0 12px 0;border-bottom:2px solid #eee;padding-bottom:8px;">
                Gate Check (Phase Advancement)
            </h2>
            {gate_html}
        </td>
    </tr>"""

    # Phase description
    phase_desc = RAMPUP_CONFIG['phases'][effective_phase]['desc']
    phase_name = RAMPUP_CONFIG['phases'][effective_phase]['name']

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;background-color:#f5f5f5;">
<table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f5f5f5;padding:20px 0;">
<tr><td align="center">
<table width="640" cellpadding="0" cellspacing="0" style="background-color:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1);">

    <!-- Header -->
    <tr>
        <td style="background:linear-gradient(135deg,#1a1a2e 0%,#16213e 100%);padding:24px;text-align:center;">
            <h1 style="color:#fff;margin:0 0 4px 0;font-size:22px;">Ramp-Up Coach</h1>
            <p style="color:rgba(255,255,255,0.7);margin:0;font-size:14px;">
                Day {day_num} | Phase {effective_phase}: {phase_name} | {today.strftime('%B %d, %Y')}
            </p>
            <p style="color:rgba(255,255,255,0.5);margin:4px 0 0 0;font-size:12px;">
                {phase_desc}
            </p>
        </td>
    </tr>

    <!-- Readiness Banner -->
    <tr>
        <td style="padding:0;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background-color:{readiness['color']}18;">
                <tr>
                    <td style="padding:20px 24px;border-left:5px solid {readiness['color']};">
                        <div style="font-size:20px;font-weight:bold;color:{readiness['color']};margin-bottom:4px;">
                            {readiness['label']}
                        </div>
                        <div style="color:#444;font-size:14px;">{readiness['message']}</div>
                    </td>
                </tr>
            </table>
        </td>
    </tr>

    <!-- Metric Details -->
    <tr>
        <td style="padding:20px 24px 8px 24px;">
            <h2 style="color:#333;font-size:16px;margin:0 0 12px 0;border-bottom:2px solid #eee;padding-bottom:8px;">
                Today's Metrics
            </h2>
            <table width="100%" cellpadding="0" cellspacing="0">
                {details_html}
            </table>
        </td>
    </tr>

    <!-- Tomorrow's Plan -->
    <tr>
        <td style="padding:8px 24px 20px 24px;">
            <h2 style="color:#333;font-size:16px;margin:0 0 12px 0;border-bottom:2px solid #eee;padding-bottom:8px;">
                Tomorrow's Plan
            </h2>
            {tomorrows_plan_html}
        </td>
    </tr>

    <!-- Gate Check (phases 2+) -->
    {gate_section}

    <!-- Trend Summary Cards -->
    <tr>
        <td style="padding:0 24px 16px 24px;">
            <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                    <td width="33%" style="padding:4px;">
                        <table width="100%" cellpadding="0" cellspacing="0" style="background:#f8f9fa;border-radius:8px;text-align:center;">
                            <tr><td style="padding:12px 8px 4px 8px;font-size:11px;color:#999;">RHR TREND</td></tr>
                            <tr><td style="padding:0 8px 12px 8px;font-size:18px;font-weight:bold;">{rhr_trend}</td></tr>
                        </table>
                    </td>
                    <td width="33%" style="padding:4px;">
                        <table width="100%" cellpadding="0" cellspacing="0" style="background:#f8f9fa;border-radius:8px;text-align:center;">
                            <tr><td style="padding:12px 8px 4px 8px;font-size:11px;color:#999;">BODY BATTERY</td></tr>
                            <tr><td style="padding:0 8px 12px 8px;font-size:18px;font-weight:bold;">{bb_trend}</td></tr>
                        </table>
                    </td>
                    <td width="33%" style="padding:4px;">
                        <table width="100%" cellpadding="0" cellspacing="0" style="background:#f8f9fa;border-radius:8px;text-align:center;">
                            <tr><td style="padding:12px 8px 4px 8px;font-size:11px;color:#999;">SLEEP SCORE</td></tr>
                            <tr><td style="padding:0 8px 12px 8px;font-size:18px;font-weight:bold;">{sleep_trend}</td></tr>
                        </table>
                    </td>
                </tr>
            </table>
        </td>
    </tr>

    <!-- Daily Trend Table -->
    <tr>
        <td style="padding:0 24px 24px 24px;">
            <h2 style="color:#333;font-size:16px;margin:0 0 12px 0;border-bottom:2px solid #eee;padding-bottom:8px;">
                Trend (since {RAMPUP_CONFIG['event_name'].lower()})
            </h2>
            <table width="100%" cellpadding="0" cellspacing="0" style="font-size:13px;">
                <tr style="background-color:#f8f9fa;">
                    <th style="padding:8px 10px;text-align:left;border-bottom:2px solid #ddd;">Day</th>
                    <th style="padding:8px 10px;text-align:center;border-bottom:2px solid #ddd;">RHR</th>
                    <th style="padding:8px 10px;text-align:center;border-bottom:2px solid #ddd;">Sleep HR</th>
                    <th style="padding:8px 10px;text-align:center;border-bottom:2px solid #ddd;">BB Wake</th>
                    <th style="padding:8px 10px;text-align:center;border-bottom:2px solid #ddd;">Sleep</th>
                    <th style="padding:8px 10px;text-align:center;border-bottom:2px solid #ddd;">REM</th>
                    <th style="padding:8px 10px;text-align:center;border-bottom:2px solid #ddd;">Deep</th>
                </tr>
                {trend_rows}
            </table>
            <p style="color:#999;font-size:11px;margin:8px 0 0 0;">
                RHR baseline: {rhr_baseline} bpm | Gates: RHR trending &#8600;, sleep HR &lt; {GATE_THRESHOLDS['sleep_hr_max']}, BB wake &gt; {GATE_THRESHOLDS['bb_wake_min']}, sleep score &gt; {GATE_THRESHOLDS['sleep_score_min']}
            </p>
        </td>
    </tr>

    <!-- Footer -->
    <tr>
        <td style="background-color:#f8f9fa;padding:16px;text-align:center;border-top:1px solid #eee;">
            <p style="color:#666;font-size:12px;margin:0 0 6px 0;">
                Running plan: <a href="https://runplan.fun" style="color:#2196F3;">runplan.fun</a>
            </p>
            <p style="color:#999;font-size:11px;margin:0 0 6px 0;">
                Disable: <code style="background:#eee;padding:2px 6px;border-radius:3px;font-size:10px;">gh workflow disable recovery-dashboard.yml --repo sharadmangalick/garmin-weekly-email</code>
            </p>
            <p style="color:#bbb;font-size:11px;margin:0;">
                Generated {datetime.now(USER_TZ).strftime('%B %d, %Y at %I:%M %p')} | Ramp-Up Coach
            </p>
        </td>
    </tr>

</table>
</td></tr>
</table>
</body>
</html>"""

    return html


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

def main():
    from user_config import UserConfig
    user_cfg = UserConfig()
    email_to = user_cfg.email

    today = _today()

    logger.info("=" * 50)
    logger.info("Ramp-Up Coach")
    logger.info(f"Date: {today.isoformat()}")
    logger.info("=" * 50)

    # Determine phase
    phase_info = determine_phase(today)
    logger.info(f"Day {phase_info['day_num']} | Calendar phase: {phase_info['phase_num']} ({phase_info['name']})")

    fetch_data()

    summaries = load_daily_summaries()
    sleeps = load_sleep_data()

    if not summaries:
        logger.error("No daily summary data available")
        sys.exit(1)

    metrics = extract_metrics(summaries, sleeps)
    if not metrics:
        logger.error("Could not extract metrics")
        sys.exit(1)

    # Filter to post-event only
    event_iso = RAMPUP_CONFIG['event_date'].isoformat()
    metrics = [m for m in metrics if m['date'] >= event_iso]

    # Use most recent day that actually has data
    today_metrics = {}
    for m in reversed(metrics):
        if m.get('rhr') is not None or m.get('bb_wake') is not None:
            today_metrics = m
            break

    # Remove days with zero data from the display
    metrics = [m for m in metrics if m.get('rhr') is not None or m.get('bb_wake') is not None or m.get('sleep_score') is not None]

    logger.info(f"Metrics for {len(metrics)} days post-event")
    logger.info(f"Using day {today_metrics.get('date', 'unknown')} for readiness")

    # Readiness
    readiness = calculate_readiness(today_metrics)
    logger.info(f"Readiness: {readiness['level']} - {readiness['label']}")

    # Gate checks
    gate_result = check_gates(metrics)
    logger.info(f"Gates passed: {gate_result['passed']}")
    if gate_result['hold_reason']:
        logger.info(f"Hold: {gate_result['hold_reason']}")

    # Effective phase (apply gate hold)
    calendar_phase = phase_info['phase_num']
    effective_phase = get_effective_phase(calendar_phase, gate_result)
    phase_info['calendar_phase'] = calendar_phase
    phase_info['effective_phase'] = effective_phase
    if effective_phase != calendar_phase:
        logger.info(f"Gate hold: calendar phase {calendar_phase} → effective phase {effective_phase}")

    # Tomorrow's workout
    workout = get_tomorrows_workout(effective_phase)
    logger.info(f"Tomorrow: {workout['day_name']} — {workout['label']}")

    # Email
    emoji = {'green': '\U0001f7e2', 'yellow': '\U0001f7e1', 'red': '\U0001f534'}[readiness['level']]
    phase_name = RAMPUP_CONFIG['phases'][effective_phase]['name']
    subject = f"Day {phase_info['day_num']} | Phase {effective_phase}: {phase_name} | {readiness['label']} {emoji}"

    html = generate_html(metrics, readiness, phase_info, gate_result, workout)

    success = send_email(email_to, subject, html)
    if success:
        logger.info("Ramp-up coach email sent!")
    else:
        logger.error("Failed to send email")
        output_path = PROJECT_DIR / "recovery_dashboard.html"
        with open(output_path, 'w') as f:
            f.write(html)
        logger.info(f"HTML saved to {output_path}")
        sys.exit(1)


if __name__ == "__main__":
    main()
