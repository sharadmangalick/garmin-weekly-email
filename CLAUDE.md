# Garmin Weekly Email — Developer Guide

## Repo Overview
Automated Garmin health emails via GitHub Actions. Two workflows:
- **Daily Ramp-Up Coach** (`recovery_dashboard.py`) — daily email with readiness, phase progression, workout plan
- **Weekly training email** (`automated_weekly_email.py`) — weekly training plan (currently inactive)

GitHub Pages is disabled on this repo.

## Key Files
| File | Purpose |
|------|---------|
| `recovery_dashboard.py` | Daily ramp-up coach — phases, gates, workouts, readiness, HTML |
| `automated_weekly_email.py` | Weekly training plan email |
| `email_sender.py` | **Shared** email sending (Gmail API + SMTP fallback) |
| `config.py` | Shared config, `setup_logging(name)`, `data_dir` (default `./data`) |
| `user_config.py` | User preferences — loads from `config.data_dir / "user_config.json"` |
| `garmin_client.py` | OOP Garmin Connect client (login, fetch data) |
| `data_analyzer.py` | Health metric analysis |
| `.github/workflows/recovery-dashboard.yml` | Cron: daily 9 PM PDT (04:00 UTC) |
| `.github/workflows/weekly-email.yml` | Cron: weekly email |
| `RECOVERY_DASHBOARD.md` | Stale — superseded by this file, safe to delete |

## Ramp-Up Coach — Phase System

### Current Event
- **Marathon** on March 1, 2026
- RHR baseline: 43.2 bpm
- Configured in `RAMPUP_CONFIG` at top of `recovery_dashboard.py`

### Phases
| Phase | Days | Description |
|-------|------|-------------|
| 1: Recovery | 1-7 | Walks and easy bike only. No strength. |
| 2: Half-Volume | 8-14 | 2 sets per exercise, skip split squats/calf raises + light aerobic |
| 3: Three-Quarter | 15-21 | All exercises back, 3 sets most + normal aerobic |
| 4: Steady State | 22+ | Full plan. Can disable email and use runplan.fun |

### Gate Checks (evaluated daily from day 8)
Gates control phase advancement. If any gate fails, the athlete is held at the previous phase with an explanation in the email.
- **RHR trending down**: last 3-day avg < previous 3-day avg (needs 6+ days of data)
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

### Strength Exercises (configured in `STRENGTH_EXERCISES`)
Pull-ups, goblet squats (slow eccentric), ring push-ups, RDL (slow eccentric), Bulgarian split squats (each leg), ring rows, ring support hold, bent-knee calf raises (eccentric focus), core. Sets vary by phase. Bulgarian split squats and calf raises are skipped in phase 2.

### Email Structure
1. **Header** — "Ramp-Up Coach | Day N | Phase X: Name"
2. **Readiness banner** — red/yellow/green with message
3. **Today's metrics** — RHR, body battery, sleep score, sleep HR, REM
4. **Tomorrow's plan** — workout card with exercise table (on strength days)
5. **Gate check status** (phases 2+) — 4-row table with pass/fail, hold banner if needed
6. **Trend cards** — RHR, body battery, sleep score arrows
7. **Trend table** — daily metrics since event
8. **Footer** — runplan.fun link, disable instructions, timestamp

### Configuration (top of `recovery_dashboard.py`)
- `RAMPUP_CONFIG` — event name/date, RHR baseline, phase definitions
- `GATE_THRESHOLDS` — 4 gate conditions for phase advancement
- `STRENGTH_EXERCISES` — exercises with sets per phase
- `WEEKLY_SCHEDULE` — day-of-week → workout type mapping
- `READINESS_CONFIG` — red/yellow/green readiness labels and messages
- `THRESHOLDS` — readiness scoring thresholds (RHR delta, BB, sleep score, sleep HR, REM)

### How to Reuse for a New Event
1. Update `RAMPUP_CONFIG` with new event name, date, and RHR baseline
2. Adjust phase day ranges if needed
3. Modify `STRENGTH_EXERCISES` if the workout plan changes
4. Re-enable workflow if disabled

### Running Plans
Running is handled by [runplan.fun](https://runplan.fun), not this email. The email defers to runplan.fun on run days (Tue/Sat).

## Shared Modules

### `email_sender.py`
Both scripts import `send_email(to, subject, html)`. Tries Gmail OAuth first (always fails — missing client_id/secret), then falls back to SMTP via `GMAIL_APP_PASSWORD`. SMTP is the actual send method.

### `config.py`
- `config.data_dir` defaults to `./data`
- `setup_logging(name)` → logs to `logs/{name}.log` + stderr

### `user_config.py`
- Loads from `config.data_dir / "user_config.json"` (i.e., `data/user_config.json`)
- Default email is `your@gmail.com` — if you see that in logs, the config file isn't being found
- The workflow decodes `USER_CONFIG_B64` secret → `data/user_config.json`
- Both scripts get recipient from `UserConfig().email`

## Timezone Handling
- GitHub Actions runs in UTC. The code uses `_today()` which returns `datetime.now(ZoneInfo("America/Los_Angeles")).date()`
- This ensures day number, phase, and tomorrow's workout are correct for Pacific time
- The timezone is currently hardcoded in `USER_TZ` (not read from user config)

## GitHub Actions Secrets
| Secret | Purpose |
|--------|---------|
| `GARMIN_EMAIL` | Garmin Connect login (smangalick@gmail.com) |
| `GARMIN_PASSWORD` | Garmin Connect password |
| `GMAIL_APP_PASSWORD` | Gmail SMTP app password — **this is what actually sends emails** |
| `GMAIL_CREDENTIALS_B64` | OAuth creds (broken — missing client_id/secret, can't refresh) |
| `USER_CONFIG_B64` | User config JSON decoded to `data/user_config.json` at runtime |

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

## Known Issues / Tech Debt
- **`SEND_TIMING` is dead code** — defined but never referenced after the ramp-up refactor
- **`RECOVERY_DASHBOARD.md` is stale** — can be deleted, superseded by this file
- **OAuth always fails** — `email_sender.py` tries Gmail API first, logs a warning, falls back to SMTP. Wastes ~1s per send
- **`USER_TZ` is hardcoded** — could read from `UserConfig().timezone` but adds module-level dependency

## Important Gotchas
- **Today's Garmin data may be incomplete** if fetched before the day ends in Pacific time. Code uses most recent day WITH actual data (not necessarily today).
- **Fetches 14 days** of data to support RHR trending gate check (needs 6+ days).
- **User config path matters** — must be at `data/user_config.json`, not project root. The workflow's "Create data directories" step must run BEFORE the "Create user config" step.
