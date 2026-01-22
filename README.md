# Garmin Weekly Training Email

Automated weekly training emails powered by your Garmin health data. Get personalized training plans delivered to your inbox every Sunday.

## Features

- **Multiple Goal Types** - Train for 5K, 10K, Half Marathon, Marathon, Ultra, or custom distances
- **Non-Race Goals** - Build mileage, maintain fitness, base building, or return from injury
- **Automatic Garmin Data Sync** - Fetches your latest health metrics (RHR, sleep, Body Battery, stress)
- **Smart Training Plans** - Generates 4-5 day running weeks based on your training phase
- **Recovery-Aware** - Adjusts volume when fatigue indicators are elevated
- **Beautiful HTML Emails** - Professional training plan emails with health snapshots
- **Easy Goal Updates** - Web-based wizard to change goals anytime
- **Fully Automated** - Runs on GitHub Actions, no server required

## Quick Start

### 1. Clone and Configure

```bash
git clone https://github.com/YOUR_USERNAME/garmin-weekly-email.git
cd garmin-weekly-email
```

**Option A: Use the Web Wizard (Recommended)**

Open `docs/index.html` in your browser and follow the steps to generate your config.

**Option B: Create config manually**

```bash
mkdir -p data
cat > data/user_config.json << 'EOF'
{
  "email": "your@email.com",
  "name": "Your Name",
  "goal_category": "race",
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
| `USER_CONFIG_B64` | Base64-encoded user configuration |

### Generate Base64 Secrets

**Gmail credentials:**
```bash
cat ~/.gmail-mcp/credentials.json | base64 | tr -d '\n'
```

**User config:**
```bash
cat data/user_config.json | base64 | tr -d '\n'
```

### Schedule

The workflow runs automatically every **Sunday at 7:00 AM Pacific**. You can also trigger it manually from the Actions tab.

### Enable GitHub Pages (for Goal Wizard)

1. Go to your repo Settings → Pages
2. Source: Deploy from a branch
3. Branch: `main`, Folder: `/docs`
4. Save

Your goal wizard will be available at `https://YOUR_USERNAME.github.io/garmin-weekly-email/`

## Supported Goals

### Race Goals

| Goal Type | Distance | Description |
|-----------|----------|-------------|
| `5k` | 3.1 mi | Speed-focused training |
| `10k` | 6.2 mi | Speed and endurance |
| `half_marathon` | 13.1 mi | Endurance with speed |
| `marathon` | 26.2 mi | Maximum endurance |
| `ultra` | 50+ mi | Extreme endurance |
| `custom` | User-defined | Any custom distance |

### Non-Race Goals

| Goal Type | Description |
|-----------|-------------|
| `build_mileage` | Gradually increase weekly volume |
| `maintain_fitness` | Maintain current fitness level |
| `base_building` | Build aerobic foundation |
| `return_from_injury` | Conservative return to running |

## Updating Your Goals

### Option 1: Web Wizard (Easiest)

1. Go to your GitHub Pages site: `https://YOUR_USERNAME.github.io/garmin-weekly-email/`
2. Complete the goal wizard
3. Copy the generated Base64 config
4. Update the `USER_CONFIG_B64` secret in GitHub

### Option 2: Manual Trigger with Overrides

Run the workflow manually from GitHub Actions with goal overrides:

1. Go to Actions → Weekly Training Email → Run workflow
2. Fill in the optional inputs:
   - `goal_type`: 5k, 10k, half_marathon, marathon, etc.
   - `goal_date`: YYYY-MM-DD (for race goals)
   - `goal_time_minutes`: Target time in minutes
   - `current_weekly_mileage`: Your current mileage

### Option 3: Update Config Directly

Edit your config and re-encode:

```bash
# Edit data/user_config.json, then:
cat data/user_config.json | base64 | tr -d '\n'
# Update USER_CONFIG_B64 secret with the output
```

## Configuration

| Field | Description |
|-------|-------------|
| `email` | Where to send training emails |
| `name` | Your name (used in emails) |
| `goal_category` | `race` or `non_race` |
| `goal_type` | See supported goals above |
| `goal_target` | Goal description (e.g., "sub-4-hour Marathon") |
| `goal_time_minutes` | Target finish time in minutes (race goals) |
| `goal_date` | Race date YYYY-MM-DD (race goals) |
| `custom_distance_miles` | Distance for custom races |
| `target_weekly_mileage` | Target mileage (for build_mileage goal) |
| `current_weekly_mileage` | Your current weekly mileage |
| `experience_level` | beginner, intermediate, or advanced |
| `preferred_long_run_day` | saturday or sunday |
| `goals_update_url` | URL to your GitHub Pages goal wizard |

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
