# Garmin Weekly Email — Developer Guide

## Repo Overview
Automated Garmin health emails via GitHub Actions. Two main workflows:
- **Ramp-Up Coach** (`recovery_dashboard.py`) — daily post-event ramp-up email with phase system
- **Weekly training email** (`automated_weekly_email.py`) — weekly training plan

## Key Files
| File | Purpose |
|------|---------|
| `recovery_dashboard.py` | Daily ramp-up coach — phases, gates, workouts, readiness, HTML |
| `automated_weekly_email.py` | Weekly training plan email |
| `email_sender.py` | **Shared** email sending (Gmail API + SMTP fallback) |
| `config.py` | Shared config + `setup_logging(name)` helper |
| `user_config.py` | User preferences (name, email, goals) — single source of truth for recipient |
| `garmin_client.py` | OOP Garmin Connect client (login, fetch data) |
| `data_analyzer.py` | Health metric analysis |
| `.github/workflows/recovery-dashboard.yml` | Cron schedule for ramp-up coach (9 PM PDT) |
| `.github/workflows/weekly-email.yml` | Cron schedule for weekly email |

## Ramp-Up Coach — Phase System

### Phases
| Phase | Days | Description |
|-------|------|-------------|
| 1: Recovery | 1-7 | Walks and easy bike only. No strength. |
| 2: Half-Volume | 8-14 | 2 sets per exercise, skip split squats/calf raises + light aerobic |
| 3: Three-Quarter | 15-21 | All exercises back, 3 sets most + normal aerobic |
| 4: Steady State | 22+ | Full plan. Can disable email and use runplan.fun |

### Gate Checks (evaluated daily from day 8)
Gates control phase advancement. If any gate fails, the athlete is held at the previous phase.
- **RHR trending down**: last 3-day avg < previous 3-day avg
- **Sleep HR < 53**
- **Body battery wake > 80**
- **Sleep score > 70**

### Weekly Schedule (phases 2-4)
| Day | Workout |
|-----|---------|
| Mon | Strength + 30-40 min easy bike |
| Tue | Easy run (30-45 min, Zone 2) — defer to runplan.fun |
| Wed | Rest |
| Thu | Strength + optional easy bike |
| Fri | Rest or easy walk |
| Sat | Longer easy run or ride (45-60 min) — defer to runplan.fun |
| Sun | Rest or easy movement |

Phase 1 overrides everything to "walk or easy bike only."

### Configuration (top of `recovery_dashboard.py`)
- `RAMPUP_CONFIG` — event name/date, RHR baseline, phase definitions
- `GATE_THRESHOLDS` — 4 gate conditions
- `STRENGTH_EXERCISES` — exercises with sets per phase
- `WEEKLY_SCHEDULE` — day-of-week → workout type
- `READINESS_CONFIG` — red/yellow/green readiness labels
- `THRESHOLDS` — readiness scoring thresholds
- `SEND_TIMING` — "evening" or "morning"

### How to Reuse for a New Event
1. Update `RAMPUP_CONFIG` with new event name, date, and RHR baseline
2. Adjust phase day ranges if needed
3. Modify `STRENGTH_EXERCISES` if the workout plan changes
4. Re-enable workflow if disabled

### Running Plans
Running is handled by [runplan.fun](https://runplan.fun), not this email. The email defers to runplan.fun on run days (Tue/Sat).

## Shared Modules

### `email_sender.py`
Both scripts import `send_email(to, subject, html)`. Tries Gmail API first, falls back to SMTP (`GMAIL_APP_PASSWORD`).

### `config.py` — `setup_logging(name)`
Call `logger = setup_logging("my_script")` for logging to `logs/{name}.log` + stderr.

### `user_config.py` — recipient email
Both scripts get recipient from `UserConfig().email`. No hardcoded emails.

## GitHub Actions Secrets
- `GARMIN_EMAIL` / `GARMIN_PASSWORD` — Garmin Connect login
- `GMAIL_APP_PASSWORD` — Gmail SMTP app password (primary send method)
- `GMAIL_CREDENTIALS_B64` — OAuth creds (missing client_id/secret, can't auto-refresh)
- `USER_CONFIG_B64` — user config JSON (email, name, goals, timezone)

## Workflow Commands
```bash
# View workflow status
gh workflow view recovery-dashboard.yml --repo sharadmangalick/garmin-weekly-email

# Manual trigger
gh workflow run recovery-dashboard.yml --repo sharadmangalick/garmin-weekly-email

# Disable/enable
gh workflow disable recovery-dashboard.yml --repo sharadmangalick/garmin-weekly-email
gh workflow enable recovery-dashboard.yml --repo sharadmangalick/garmin-weekly-email
```

## Important Gotchas
- **Today's data may be incomplete** if fetched before the day ends in Pacific time. Code uses most recent day WITH actual data.
- **Gmail OAuth can't refresh** — falls back to SMTP via `GMAIL_APP_PASSWORD`.
- **Fetches 14 days** of data (need 6+ for RHR trending gate check).
