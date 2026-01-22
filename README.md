# Garmin Weekly Training Email

Automated weekly training emails powered by your Garmin health data. Get personalized training plans delivered to your inbox every Sunday.

## Features

- **Automatic Garmin Data Sync** - Fetches your latest health metrics (RHR, sleep, Body Battery, stress)
- **Smart Training Plans** - Generates 4-5 day running weeks based on your training phase
- **Recovery-Aware** - Adjusts volume when fatigue indicators are elevated
- **Beautiful HTML Emails** - Professional training plan emails with health snapshots
- **Fully Automated** - Runs on GitHub Actions, no server required

## Quick Start

### 1. Clone and Configure

```bash
git clone https://github.com/YOUR_USERNAME/garmin-weekly-email.git
cd garmin-weekly-email

# Create data directory and user config
mkdir -p data
cat > data/user_config.json << 'EOF'
{
  "email": "your@email.com",
  "name": "Your Name",
  "goal_type": "marathon",
  "goal_target": "sub-4-hour",
  "goal_time_minutes": 240,
  "goal_date": "2026-03-05",
  "current_weekly_mileage": 35,
  "experience_level": "intermediate",
  "preferred_long_run_day": "saturday",
  "email_day": "sunday",
  "email_time": "07:00",
  "timezone": "America/Los_Angeles"
}
EOF
```

### 2. Set Up Gmail Authentication

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project and enable Gmail API
3. Create OAuth 2.0 credentials (Desktop app)
4. Download credentials and authenticate:

```bash
mkdir -p ~/.gmail-mcp
# Place your OAuth credentials as gcp-oauth.keys.json
npx @gongrzhe/server-gmail-autoauth-mcp auth
```

### 3. Run Locally

```bash
pip install -r requirements.txt

# Set Garmin credentials
export GARMIN_EMAIL="your@garmin.email"
export GARMIN_PASSWORD="your-password"

# Run
python automated_weekly_email.py
```

## GitHub Actions (Fully Automated)

### Required Secrets

Add these secrets to your GitHub repo (`Settings > Secrets > Actions`):

| Secret | Description |
|--------|-------------|
| `GARMIN_EMAIL` | Your Garmin Connect email |
| `GARMIN_PASSWORD` | Your Garmin Connect password |
| `GMAIL_CREDENTIALS_B64` | Base64-encoded Gmail OAuth credentials |

### Get Gmail Credentials (Base64)

```bash
cat ~/.gmail-mcp/credentials.json | base64 | tr -d '\n'
```

### Schedule

The workflow runs automatically every **Sunday at 7:00 AM Pacific**. You can also trigger it manually from the Actions tab.

## Configuration

Edit `data/user_config.json` to customize:

| Field | Description |
|-------|-------------|
| `email` | Where to send training emails |
| `name` | Your name (used in emails) |
| `goal_type` | Race type (marathon, half_marathon, etc.) |
| `goal_target` | Goal description (sub-4-hour, BQ, etc.) |
| `goal_time_minutes` | Target finish time in minutes |
| `goal_date` | Race date (YYYY-MM-DD) |
| `current_weekly_mileage` | Your current weekly mileage |
| `preferred_long_run_day` | saturday or sunday |

## How It Works

1. **Fetches** 14 days of Garmin data (sleep, HR, stress, Body Battery)
2. **Analyzes** recovery status and training readiness
3. **Generates** a personalized training plan based on:
   - Weeks until race (training phase)
   - Recovery indicators
   - Your weekly mileage target
4. **Sends** a beautiful HTML email with your weekly plan

## License

MIT
