# Recovery Dashboard - Quick Reference

## Stop the daily emails
```bash
gh workflow disable recovery-dashboard.yml --repo sharadmangalick/garmin-weekly-email
```
Or: GitHub repo → Actions → Daily Recovery Dashboard → "..." → Disable workflow

## Re-enable later
```bash
gh workflow enable recovery-dashboard.yml --repo sharadmangalick/garmin-weekly-email
```

## Run manually (one-off)
```bash
gh workflow run recovery-dashboard.yml --repo sharadmangalick/garmin-weekly-email
```

## When to stop
Disable when you see **green for 3 consecutive days**. That means:
- RHR within 3 bpm of baseline (46 or lower)
- Body Battery waking above 80
- Sleep score above 75

## Modify the report

Everything is in `recovery_dashboard.py`:

### Change your baseline
```python
RHR_BASELINE = 43.2          # your normal resting heart rate
MARATHON_DATE = date(2026, 3, 1)  # start date for recovery tracking
RECOVERY_DAYS = 7             # days of history to fetch/show
```

### Change readiness thresholds
In `calculate_readiness()`:
- **RHR**: green ≤ +3 bpm, yellow ≤ +5 bpm, red > +5 bpm
- **Body Battery wake**: green ≥ 80, yellow ≥ 60, red < 60
- **Sleep score**: green ≥ 75, yellow ≥ 60, red < 60
- **Sleep HR**: green ≤ 52, yellow ≤ 56, red > 56
- **REM sleep**: green ≥ 60 min, yellow ≥ 40 min, red < 40 min

### Change the schedule
In `.github/workflows/recovery-dashboard.yml`:
```yaml
cron: '0 14 * * *'   # 7:00 AM Pacific (UTC-7) daily
```

### Repurpose for normal training
Update `MARATHON_DATE` to today's date and adjust thresholds for ongoing readiness tracking instead of recovery.

## Secrets (in GitHub repo settings)
- `GARMIN_EMAIL` - Garmin Connect email
- `GARMIN_PASSWORD` - Garmin Connect password
- `GMAIL_APP_PASSWORD` - Gmail app password for sending
- `GMAIL_CREDENTIALS_B64` - Gmail OAuth credentials (optional, API method)
