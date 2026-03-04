# Garmin Weekly Email — Developer Guide

## Repo Overview
Automated Garmin health emails via GitHub Actions. Two main workflows:
- **Weekly training email** (`automated_weekly_email.py`) — weekly training plan
- **Recovery dashboard** (`recovery_dashboard.py`) — daily post-event recovery email

## Key Files
| File | Purpose |
|------|---------|
| `recovery_dashboard.py` | Daily recovery email — config, scoring, HTML, sending |
| `automated_weekly_email.py` | Weekly training plan email |
| `garmin_client.py` | OOP Garmin Connect client (login, fetch data) |
| `data_analyzer.py` | Health metric analysis |
| `config.py` | Shared project configuration |
| `user_config.py` | User preferences |
| `.github/workflows/recovery-dashboard.yml` | Cron schedule for recovery email |
| `.github/workflows/weekly-email.yml` | Cron schedule for weekly email |

## Recovery Dashboard — How to Make Common Changes

### Change event (e.g., new race)
Edit `EVENT_CONFIG` at top of `recovery_dashboard.py`:
```python
EVENT_CONFIG = {
    'name': 'Half Marathon',
    'date': date(2026, 6, 15),
    'recovery_days': 5,
    'rhr_baseline': 42.0,
    'email_to': 'smangalick@gmail.com',
}
```

### Switch between morning/evening send
1. Update cron in `.github/workflows/recovery-dashboard.yml`
2. Set `SEND_TIMING` in `recovery_dashboard.py`:
   - `"evening"` → guidance says "Tomorrow:", subject says "Evening Recovery"
   - `"morning"` → guidance says "Today:", subject says "Recovery"

### Change guidance text
Edit `READINESS_CONFIG` dict at top of `recovery_dashboard.py`. Use `{prefix}` placeholder for "Tomorrow:"/"Today:" (auto-set by `SEND_TIMING`).

### Tune readiness thresholds
Edit `THRESHOLDS` dict at top of `recovery_dashboard.py`. Keys: `rhr_green`, `rhr_yellow`, `bb_green`, `bb_yellow`, `sleep_score_green`, `sleep_score_yellow`, `sleep_hr_green`, `sleep_hr_yellow`, `rem_green`, `rem_yellow`.

## Garmin Data Format
`garmin_client.py` saves nested format: `{"date": ..., "stats": {...}, "stress": {...}}`. Use `get_stat(day, key)` to access fields — it checks both top-level and nested `stats`.

## GitHub Actions Secrets
- `GARMIN_EMAIL` / `GARMIN_PASSWORD` — Garmin Connect login
- `GMAIL_APP_PASSWORD` — Gmail SMTP app password (primary send method)
- `GMAIL_CREDENTIALS_B64` — OAuth creds (missing client_id/secret, can't auto-refresh)
- `USER_CONFIG_B64` — user config for weekly email

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
- **VO2 max data contamination** — `data/vo2max/` had sample data mixed with real data in the past. Always verify against Garmin Connect app.
