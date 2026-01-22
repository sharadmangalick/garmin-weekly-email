#!/usr/bin/env python3
"""Automated Weekly Training Email - Runs without API key or manual intervention.

This script:
1. Fetches recent Garmin data
2. Analyzes health metrics
3. Generates a training plan using rule-based logic
4. Creates and sends a personalized HTML email

Schedule with launchd or cron to run every Sunday morning.
"""

import json
import logging
import sys
import base64
from datetime import datetime
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Add project to path
PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

from config import config
from user_config import UserConfig
from data_analyzer import GarminDataAnalyzer
from training_plan_generator import TrainingPlanGenerator
from email_generator import EmailGenerator

# Set up logging
LOG_DIR = PROJECT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / "weekly_email.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def fetch_garmin_data(days: int = 14) -> bool:
    """Fetch recent Garmin data."""
    try:
        from garmin_client import GarminClient
        client = GarminClient()

        if not client.login():
            logger.error("Failed to login to Garmin Connect")
            return False

        logger.info(f"Fetching {days} days of Garmin data...")
        client.fetch_all(days=days, force=False)
        logger.info("Garmin data fetch complete")
        return True

    except Exception as e:
        logger.warning(f"Could not fetch new data: {e}")
        logger.info("Will use cached data if available")
        return False


def run_analysis() -> dict:
    """Run health data analysis."""
    logger.info("Analyzing Garmin data...")
    analyzer = GarminDataAnalyzer(str(config.data_dir))
    load_result = analyzer.load_data()

    if load_result['daily_summaries'] == 0:
        raise ValueError("No data available for analysis")

    logger.info(f"Loaded {load_result['daily_summaries']} days of data")
    return analyzer.analyze_all()


def generate_training_plan(analysis: dict, user_config: UserConfig) -> dict:
    """Generate training plan using rule-based generator."""
    logger.info("Generating training plan...")
    generator = TrainingPlanGenerator(user_config)
    plan = generator.generate_plan(analysis)
    logger.info(f"Generated {plan['week_summary']['total_miles']} mile training week")
    return plan


def generate_email(user_config: UserConfig, analysis: dict, training_plan: dict) -> dict:
    """Generate HTML email content."""
    logger.info("Generating email content...")
    generator = EmailGenerator()
    return generator.generate_email(
        user_config.to_dict(),
        analysis,
        training_plan
    )


def send_email(to_address: str, subject: str, html_body: str) -> bool:
    """Send email using Gmail API with saved credentials."""
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        # Load credentials
        creds_path = Path.home() / ".gmail-mcp" / "credentials.json"
        if not creds_path.exists():
            logger.error("Gmail credentials not found. Run Gmail MCP auth first.")
            return False

        with open(creds_path, 'r') as f:
            creds_data = json.load(f)

        credentials = Credentials(
            token=creds_data.get('access_token'),
            refresh_token=creds_data.get('refresh_token'),
            token_uri='https://oauth2.googleapis.com/token',
            client_id=creds_data.get('client_id'),
            client_secret=creds_data.get('client_secret')
        )

        # Create message
        message = MIMEMultipart('alternative')
        message['to'] = to_address
        message['subject'] = subject
        html_part = MIMEText(html_body, 'html')
        message.attach(html_part)

        # Encode and send
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service = build('gmail', 'v1', credentials=credentials)
        result = service.users().messages().send(userId='me', body={'raw': raw}).execute()

        logger.info(f"Email sent successfully! Message ID: {result['id']}")
        return True

    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False


def main():
    """Main entry point for automated weekly email."""
    logger.info("=" * 50)
    logger.info("Starting automated weekly training email")
    logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 50)

    try:
        # Load user config
        user_config = UserConfig()
        if not user_config.is_configured():
            logger.error("User not configured. Run 'python main.py email setup' first.")
            sys.exit(1)

        logger.info(f"User: {user_config.name} ({user_config.email})")
        logger.info(f"Goal: {user_config.goal_target} {user_config.goal_type}")
        logger.info(f"Weeks to race: {user_config.weeks_until_race()}")

        # Step 1: Fetch Garmin data
        fetch_garmin_data(days=14)

        # Step 2: Run analysis
        analysis = run_analysis()

        # Step 3: Generate training plan
        training_plan = generate_training_plan(analysis, user_config)

        # Step 4: Generate email
        email = generate_email(user_config, analysis, training_plan)

        # Step 5: Send email
        success = send_email(
            to_address=user_config.email,
            subject=email['subject'],
            html_body=email['html_body']
        )

        if success:
            logger.info("Weekly training email sent successfully!")

            # Save a copy of the plan for reference
            plan_archive = config.data_dir / "plan_archive"
            plan_archive.mkdir(exist_ok=True)
            archive_file = plan_archive / f"plan_{datetime.now().strftime('%Y%m%d')}.json"
            with open(archive_file, 'w') as f:
                json.dump({
                    "date": datetime.now().isoformat(),
                    "training_plan": training_plan,
                    "analysis_summary": {
                        "rhr": analysis.get('resting_hr', {}).get('current'),
                        "body_battery": analysis.get('body_battery', {}).get('current_wake'),
                        "sleep_avg": analysis.get('sleep', {}).get('avg_hours')
                    }
                }, f, indent=2)
            logger.info(f"Plan archived to: {archive_file}")
        else:
            logger.error("Failed to send email")
            sys.exit(1)

    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)

    logger.info("=" * 50)
    logger.info("Weekly email automation complete")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
