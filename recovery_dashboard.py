#!/usr/bin/env python3
"""Daily Recovery Dashboard - Post-event recovery tracking email.

Fetches Garmin data, calculates recovery metrics, and sends a daily
email with RHR trend, sleep quality, body battery, and a readiness score.
"""

import json
import logging
import os
import sys
import base64
from datetime import date, datetime, timedelta
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

from config import config
from garmin_client import GarminClient

# Logging
LOG_DIR = PROJECT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / "recovery_dashboard.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ── Event & user config ─────────────────────────────────────────────
# Update these when reusing the dashboard for a new event.
EVENT_CONFIG = {
    'name': 'Marathon',            # shown in email header
    'date': date(2026, 3, 1),      # event date
    'recovery_days': 7,            # how many days to track
    'rhr_baseline': 43.2,          # pre-event resting heart rate
    'email_to': 'smangalick@gmail.com',
}

# ── Send timing ─────────────────────────────────────────────────────
# "evening" → guidance says "Tomorrow", subject says "Evening Recovery"
# "morning" → guidance says "Today", subject says "Recovery"
SEND_TIMING = "evening"   # change to "morning" if cron moves back to AM

# ── Readiness guidance text ─────────────────────────────────────────
# Edit these strings to change what the email recommends.
# {prefix} is replaced with "Tomorrow:" or "Today:" based on SEND_TIMING.
READINESS_CONFIG = {
    'red': {
        'color': '#dc3545',
        'label': 'Rest Day',
        'message': 'Multiple recovery indicators are poor. Your body needs more time.',
        'guidance': '{prefix} Complete rest. Walk only. Prioritize sleep, hydration, and protein.',
    },
    'yellow': {
        'color': '#ffc107',
        'label': 'Light Movement Only',
        'message': 'Recovery is progressing but not there yet.',
        'guidance': '{prefix} Easy walk (20-30 min) or gentle bike (Zone 1, HR under 110). No running.',
    },
    'green': {
        'color': '#28a745',
        'label': 'Easy Activity OK',
        'message': 'Recovery metrics are trending back to normal.',
        'guidance': '{prefix} Easy run/bike (30-45 min, Zone 2). Keep it conversational. No intensity.',
    },
    'insufficient': {
        'color': '#ffc107',
        'label': 'Insufficient Data',
        'message': 'Not enough metrics available to assess readiness.',
        'guidance': 'Take it easy until we have more data.',
    },
}

# ── Readiness thresholds ────────────────────────────────────────────
THRESHOLDS = {
    'rhr_green': 3,      # delta from baseline
    'rhr_yellow': 5,
    'bb_green': 80,
    'bb_yellow': 60,
    'sleep_score_green': 75,
    'sleep_score_yellow': 60,
    'sleep_hr_green': 52,
    'sleep_hr_yellow': 56,
    'rem_green': 60,     # minutes
    'rem_yellow': 40,
}

# ── Derived helpers ─────────────────────────────────────────────────
def _guidance_prefix() -> str:
    return "Tomorrow:" if SEND_TIMING == "evening" else "Today:"

def _guidance_label() -> str:
    return "Tomorrow's guidance:" if SEND_TIMING == "evening" else "Today's guidance:"

def _subject_prefix() -> str:
    return "Evening " if SEND_TIMING == "evening" else ""


# ═══════════════════════════════════════════════════════════════════
# Data fetching & loading
# ═══════════════════════════════════════════════════════════════════

def fetch_data() -> bool:
    """Fetch recent Garmin data."""
    try:
        client = GarminClient()
        if not client.login():
            logger.error("Failed to login to Garmin Connect")
            return False
        days = EVENT_CONFIG['recovery_days']
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
    rhr_baseline = EVENT_CONFIG['rhr_baseline']

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

        logger.debug(f"Day {dt}: rhr={rhr}, bb_wake={bb_wake}, bb_high={bb_highest}, stress={stress_avg}")
        logger.debug(f"  Top-level keys: {list(summary.keys())}")
        if 'stats' in summary:
            stats_keys = list(summary['stats'].keys()) if isinstance(summary['stats'], dict) else type(summary['stats'])
            logger.debug(f"  Stats keys: {stats_keys}")

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

    scores = []  # list of (score, reason) where 0=red, 1=yellow, 2=green

    # RHR
    if rhr_delta is not None:
        if rhr_delta <= t['rhr_green']:
            scores.append((2, f"RHR {rhr} bpm (+{rhr_delta} from baseline) — near normal"))
        elif rhr_delta <= t['rhr_yellow']:
            scores.append((1, f"RHR {rhr} bpm (+{rhr_delta} from baseline) — still elevated"))
        else:
            scores.append((0, f"RHR {rhr} bpm (+{rhr_delta} from baseline) — significantly elevated"))

    # Body Battery
    if bb_wake is not None:
        if bb_wake >= t['bb_green']:
            scores.append((2, f"Body Battery at wake: {bb_wake} — strong recharge"))
        elif bb_wake >= t['bb_yellow']:
            scores.append((1, f"Body Battery at wake: {bb_wake} — partial recharge"))
        else:
            scores.append((0, f"Body Battery at wake: {bb_wake} — poor recharge"))

    # Sleep Score
    if sleep_score is not None:
        if sleep_score >= t['sleep_score_green']:
            scores.append((2, f"Sleep score: {sleep_score} — good quality"))
        elif sleep_score >= t['sleep_score_yellow']:
            scores.append((1, f"Sleep score: {sleep_score} — fair quality"))
        else:
            scores.append((0, f"Sleep score: {sleep_score} — poor quality"))

    # Sleep HR
    if sleep_hr is not None:
        if sleep_hr <= t['sleep_hr_green']:
            scores.append((2, f"Sleep HR: {sleep_hr} bpm — recovered"))
        elif sleep_hr <= t['sleep_hr_yellow']:
            scores.append((1, f"Sleep HR: {sleep_hr} bpm — still elevated"))
        else:
            scores.append((0, f"Sleep HR: {sleep_hr} bpm — high, body still stressed"))

    # REM sleep
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
            'guidance': cfg['guidance'],
        }

    avg_score = sum(s for s, _ in scores) / len(scores)
    red_count = sum(1 for s, _ in scores if s == 0)
    details = [reason for _, reason in scores]
    prefix = _guidance_prefix()

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
        'guidance': cfg['guidance'].format(prefix=prefix),
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
        return "&#8600;"  # ↘ improving (lower is better for RHR/stress)
    elif clean[-1] > clean[-2]:
        return "&#8599;"  # ↗ worsening
    return "&#8594;"  # → stable


def trend_arrow_higher_better(values: list) -> str:
    """Return trend arrow where higher is better (body battery, sleep score)."""
    clean = [v for v in values if v is not None]
    if len(clean) < 2:
        return "—"
    if clean[-1] > clean[-2]:
        return "&#8599;"  # ↗ improving
    elif clean[-1] < clean[-2]:
        return "&#8600;"  # ↘ worsening
    return "&#8594;"  # → stable


# ═══════════════════════════════════════════════════════════════════
# HTML generation
# ═══════════════════════════════════════════════════════════════════

def _build_trend_rows(metrics: list[dict], today_iso: str) -> str:
    """Build HTML table rows for the recovery trend table."""
    event_date = EVENT_CONFIG['date']
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


def generate_html(metrics: list[dict], readiness: dict) -> str:
    """Generate the recovery dashboard HTML email."""
    today = date.today()
    event_date = EVENT_CONFIG['date']
    event_name = EVENT_CONFIG['name']
    recovery_days = EVENT_CONFIG['recovery_days']
    rhr_baseline = EVENT_CONFIG['rhr_baseline']
    recovery_day = (today - event_date).days

    trend_rows = _build_trend_rows(metrics, today.isoformat())
    details_html = _build_details_html(readiness['details'])
    guidance_label = _guidance_label()

    rhr_trend = trend_arrow([m['rhr'] for m in metrics])
    bb_trend = trend_arrow_higher_better([m['bb_wake'] for m in metrics])
    sleep_trend = trend_arrow_higher_better([m['sleep_score'] for m in metrics])

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
            <h1 style="color:#fff;margin:0 0 4px 0;font-size:22px;">{event_name} Recovery Dashboard</h1>
            <p style="color:rgba(255,255,255,0.7);margin:0;font-size:14px;">
                Day {recovery_day} of {recovery_days} | {today.strftime('%B %d, %Y')}
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

    <!-- Guidance -->
    <tr>
        <td style="padding:8px 24px 20px 24px;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f8f9fa;border-radius:8px;">
                <tr>
                    <td style="padding:14px 16px;">
                        <strong style="color:#333;">{guidance_label}</strong>
                        <span style="color:#555;"> {readiness['guidance']}</span>
                    </td>
                </tr>
            </table>
        </td>
    </tr>

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
                Recovery Trend (since {event_name.lower()})
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
                RHR baseline: {rhr_baseline} bpm | Target: RHR within 3 bpm of baseline, BB wake &gt; 80, sleep score &gt; 75
            </p>
        </td>
    </tr>

    <!-- Footer -->
    <tr>
        <td style="background-color:#f8f9fa;padding:16px;text-align:center;border-top:1px solid #eee;">
            <p style="color:#bbb;font-size:11px;margin:0;">
                Generated {datetime.now().strftime('%B %d, %Y at %I:%M %p')} | Garmin Recovery Dashboard
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
# Email sending
# ═══════════════════════════════════════════════════════════════════

def send_email(to_address: str, subject: str, html_body: str) -> bool:
    """Send email using Gmail API or SMTP fallback."""
    if _send_via_gmail_api(to_address, subject, html_body):
        return True
    if _send_via_smtp(to_address, subject, html_body):
        return True
    return False


def _send_via_gmail_api(to_address: str, subject: str, html_body: str) -> bool:
    """Send via Gmail API with OAuth credentials."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        creds_path = Path.home() / ".gmail-mcp" / "credentials.json"
        if not creds_path.exists():
            logger.info("No Gmail API credentials found, will try SMTP")
            return False

        with open(creds_path, 'r') as f:
            creds_data = json.load(f)

        token = creds_data.get('access_token') or creds_data.get('token')
        refresh_token = creds_data.get('refresh_token')
        client_id = creds_data.get('client_id')
        client_secret = creds_data.get('client_secret')

        if not token:
            logger.warning("No access token in credentials")
            return False

        credentials = Credentials(
            token=token,
            refresh_token=refresh_token,
            token_uri=creds_data.get('token_uri', 'https://oauth2.googleapis.com/token'),
            client_id=client_id,
            client_secret=client_secret,
        )

        if not credentials.valid and refresh_token and client_id and client_secret:
            logger.info("Refreshing expired credentials...")
            credentials.refresh(Request())

        message = MIMEMultipart('alternative')
        message['to'] = to_address
        message['subject'] = subject
        html_part = MIMEText(html_body, 'html')
        message.attach(html_part)

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service = build('gmail', 'v1', credentials=credentials)
        result = service.users().messages().send(userId='me', body={'raw': raw}).execute()

        logger.info(f"Email sent via Gmail API! Message ID: {result['id']}")
        return True

    except Exception as e:
        logger.warning(f"Gmail API send failed: {e}")
        return False


def _send_via_smtp(to_address: str, subject: str, html_body: str) -> bool:
    """Send via Gmail SMTP with app password from environment."""
    import smtplib

    smtp_user = os.environ.get('GMAIL_SMTP_USER') or os.environ.get('GARMIN_EMAIL')
    smtp_pass = os.environ.get('GMAIL_APP_PASSWORD')

    if not smtp_user or not smtp_pass:
        logger.error("No SMTP credentials available (set GMAIL_APP_PASSWORD secret)")
        logger.error("Or update GMAIL_CREDENTIALS_B64 with client_id and client_secret for OAuth refresh")
        return False

    try:
        message = MIMEMultipart('alternative')
        message['From'] = smtp_user
        message['To'] = to_address
        message['Subject'] = subject
        message.attach(MIMEText(html_body, 'html'))

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(smtp_user, smtp_pass)
            server.send_message(message)

        logger.info(f"Email sent via SMTP to {to_address}")
        return True

    except Exception as e:
        logger.error(f"SMTP send failed: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

def main():
    event_date = EVENT_CONFIG['date']
    recovery_days = EVENT_CONFIG['recovery_days']
    email_to = EVENT_CONFIG['email_to']

    logger.info("=" * 50)
    logger.info("Recovery Dashboard")
    logger.info(f"Date: {date.today().isoformat()}")
    logger.info(f"Recovery day: {(date.today() - event_date).days}")
    logger.info("=" * 50)

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
    metrics = [m for m in metrics if m['date'] >= event_date.isoformat()]

    # Use most recent day that actually has data (today may be incomplete)
    today_metrics = {}
    for m in reversed(metrics):
        if m.get('rhr') is not None or m.get('bb_wake') is not None:
            today_metrics = m
            break

    # Remove days with zero data from the display
    metrics = [m for m in metrics if m.get('rhr') is not None or m.get('bb_wake') is not None or m.get('sleep_score') is not None]

    logger.info(f"Metrics for {len(metrics)} days post-event")
    logger.info(f"Using day {today_metrics.get('date', 'unknown')} for readiness")

    readiness = calculate_readiness(today_metrics)
    logger.info(f"Readiness: {readiness['level']} - {readiness['label']}")

    recovery_day = (date.today() - event_date).days
    subject_prefix = _subject_prefix()
    emoji = {'green': '\U0001f7e2', 'yellow': '\U0001f7e1', 'red': '\U0001f534'}[readiness['level']]
    subject = f"{subject_prefix}Recovery Day {recovery_day}: {readiness['label']} {emoji}"

    html = generate_html(metrics, readiness)

    success = send_email(email_to, subject, html)
    if success:
        logger.info("Recovery dashboard email sent!")
    else:
        logger.error("Failed to send email")
        output_path = PROJECT_DIR / "recovery_dashboard.html"
        with open(output_path, 'w') as f:
            f.write(html)
        logger.info(f"HTML saved to {output_path}")
        sys.exit(1)


if __name__ == "__main__":
    main()
