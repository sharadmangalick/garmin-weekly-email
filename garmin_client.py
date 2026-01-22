"""Garmin Connect API client wrapper."""

import json
import webbrowser
from datetime import date, timedelta
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import threading

import garth
from garminconnect import Garmin
from rich.console import Console
from rich.prompt import Prompt

from config import config

console = Console()


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Handle OAuth callback from Garmin."""

    oauth_code = None

    def do_GET(self):
        """Handle the OAuth callback."""
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if 'code' in params:
            OAuthCallbackHandler.oauth_code = params['code'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"""
                <html><body style="font-family: sans-serif; text-align: center; padding-top: 50px;">
                <h1>Success!</h1>
                <p>You can close this window and return to the terminal.</p>
                </body></html>
            """)
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, format, *args):
        """Suppress logging."""
        pass


class GarminClient:
    """Wrapper for Garmin Connect API with caching support."""

    def __init__(self):
        self.client = None
        self._session_file = config.data_dir / ".garmin_session"

    def login(self) -> bool:
        """Authenticate with Garmin Connect using saved session, env vars, or browser OAuth."""
        import os
        try:
            self.client = Garmin()

            # Try to load existing session first
            if self._session_file.exists():
                try:
                    self.client.login(self._session_file)
                    console.print("[green]Logged in using saved session[/green]")
                    return True
                except Exception:
                    console.print("[yellow]Saved session expired, need to re-authenticate...[/yellow]")

            # Check for environment variables (for CI/automation)
            env_email = os.environ.get('GARMIN_EMAIL')
            env_password = os.environ.get('GARMIN_PASSWORD')
            if env_email and env_password:
                return self._env_login(env_email, env_password)

            # No valid session or env vars - need browser login
            return self._browser_login()

        except Exception as e:
            console.print(f"[red]Login failed: {e}[/red]")
            return False

    def _env_login(self, email: str, password: str) -> bool:
        """Authenticate using environment variables (for CI/automation)."""
        try:
            console.print("[dim]Logging in with environment credentials...[/dim]")
            self.client = Garmin(email, password)
            self.client.login()

            # Save session tokens for future use
            self._session_file.parent.mkdir(parents=True, exist_ok=True)
            self.client.garth.dump(str(self._session_file))

            console.print("[green]Successfully logged in to Garmin Connect[/green]")
            return True

        except Exception as e:
            console.print(f"[red]Login failed: {e}[/red]")
            return False

    def _browser_login(self) -> bool:
        """Authenticate via browser OAuth flow."""
        console.print("\n[bold]Browser Authentication Required[/bold]")
        console.print("A browser window will open for you to log in to Garmin Connect.")
        console.print("After logging in, you'll be redirected back.\n")

        # For garminconnect, we need to use email/password but can prompt for it
        # The library doesn't support pure OAuth redirect flow
        # So we'll prompt for credentials but not store them in a file

        email = Prompt.ask("[blue]Enter your Garmin email[/blue]")
        password = Prompt.ask("[blue]Enter your Garmin password[/blue]", password=True)

        try:
            self.client = Garmin(email, password)
            self.client.login()

            # Save session tokens (not credentials) for future use
            self._session_file.parent.mkdir(parents=True, exist_ok=True)
            self.client.garth.dump(str(self._session_file))

            console.print("[green]Successfully logged in to Garmin Connect[/green]")
            console.print("[dim]Session saved - you won't need to log in again until it expires.[/dim]")
            return True

        except Exception as e:
            console.print(f"[red]Login failed: {e}[/red]")
            return False

    def _save_json(self, data: dict | list, filepath: Path):
        """Save data to JSON file."""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def _load_json(self, filepath: Path) -> dict | list | None:
        """Load data from JSON file if it exists."""
        if filepath.exists():
            with open(filepath) as f:
                return json.load(f)
        return None

    def fetch_activities(self, days: int = 7, force: bool = False) -> list[dict]:
        """Fetch activities for the specified number of days."""
        all_activities = []
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        console.print(f"[blue]Fetching activities from {start_date} to {end_date}...[/blue]")

        try:
            # Fetch activities list
            activities = self.client.get_activities_by_date(
                start_date.isoformat(),
                end_date.isoformat()
            )

            for activity in activities:
                activity_id = activity.get("activityId")
                filepath = config.activities_dir / f"{activity_id}.json"

                # Check cache
                if not force and filepath.exists():
                    cached = self._load_json(filepath)
                    if cached:
                        all_activities.append(cached)
                        continue

                # Fetch detailed activity data
                try:
                    details = self.client.get_activity(activity_id)
                    activity_data = {**activity, "details": details}
                    self._save_json(activity_data, filepath)
                    all_activities.append(activity_data)
                except Exception as e:
                    console.print(f"[yellow]Warning: Could not fetch details for activity {activity_id}: {e}[/yellow]")
                    all_activities.append(activity)

            console.print(f"[green]Fetched {len(all_activities)} activities[/green]")
            return all_activities

        except Exception as e:
            console.print(f"[red]Error fetching activities: {e}[/red]")
            return []

    def fetch_sleep(self, days: int = 7, force: bool = False) -> list[dict]:
        """Fetch sleep data for the specified number of days."""
        all_sleep = []
        end_date = date.today()

        console.print(f"[blue]Fetching sleep data for last {days} days...[/blue]")

        for i in range(days):
            current_date = end_date - timedelta(days=i)
            filepath = config.sleep_dir / f"{current_date.isoformat()}.json"

            # Check cache
            if not force and filepath.exists():
                cached = self._load_json(filepath)
                if cached:
                    all_sleep.append(cached)
                    continue

            try:
                sleep_data = self.client.get_sleep_data(current_date.isoformat())
                if sleep_data:
                    self._save_json(sleep_data, filepath)
                    all_sleep.append(sleep_data)
            except Exception as e:
                console.print(f"[yellow]Warning: Could not fetch sleep for {current_date}: {e}[/yellow]")

        console.print(f"[green]Fetched {len(all_sleep)} days of sleep data[/green]")
        return all_sleep

    def fetch_heart_rate(self, days: int = 7, force: bool = False) -> list[dict]:
        """Fetch heart rate data for the specified number of days."""
        all_hr = []
        end_date = date.today()

        console.print(f"[blue]Fetching heart rate data for last {days} days...[/blue]")

        for i in range(days):
            current_date = end_date - timedelta(days=i)
            filepath = config.heart_rate_dir / f"{current_date.isoformat()}.json"

            # Check cache
            if not force and filepath.exists():
                cached = self._load_json(filepath)
                if cached:
                    all_hr.append(cached)
                    continue

            try:
                hr_data = self.client.get_heart_rates(current_date.isoformat())
                if hr_data:
                    self._save_json(hr_data, filepath)
                    all_hr.append(hr_data)
            except Exception as e:
                console.print(f"[yellow]Warning: Could not fetch heart rate for {current_date}: {e}[/yellow]")

        console.print(f"[green]Fetched {len(all_hr)} days of heart rate data[/green]")
        return all_hr

    def fetch_daily_summaries(self, days: int = 7, force: bool = False) -> list[dict]:
        """Fetch daily summary data (steps, calories, etc.) for the specified number of days."""
        all_summaries = []
        end_date = date.today()

        console.print(f"[blue]Fetching daily summaries for last {days} days...[/blue]")

        for i in range(days):
            current_date = end_date - timedelta(days=i)
            filepath = config.daily_summaries_dir / f"{current_date.isoformat()}.json"

            # Check cache
            if not force and filepath.exists():
                cached = self._load_json(filepath)
                if cached:
                    all_summaries.append(cached)
                    continue

            try:
                # Fetch multiple daily stats
                summary = {
                    "date": current_date.isoformat(),
                    "stats": self.client.get_stats(current_date.isoformat()),
                }

                # Try to get additional metrics
                try:
                    summary["stress"] = self.client.get_stress_data(current_date.isoformat())
                except Exception:
                    pass

                try:
                    summary["body_battery"] = self.client.get_body_battery(current_date.isoformat())
                except Exception:
                    pass

                self._save_json(summary, filepath)
                all_summaries.append(summary)

            except Exception as e:
                console.print(f"[yellow]Warning: Could not fetch summary for {current_date}: {e}[/yellow]")

        console.print(f"[green]Fetched {len(all_summaries)} daily summaries[/green]")
        return all_summaries

    def fetch_vo2max(self, days: int = 7, force: bool = False) -> list[dict]:
        """Fetch VO2 max data for the specified number of days."""
        all_vo2max = []
        end_date = date.today()

        console.print(f"[blue]Fetching VO2 max data for last {days} days...[/blue]")

        for i in range(days):
            current_date = end_date - timedelta(days=i)
            filepath = config.vo2max_dir / f"{current_date.isoformat()}.json"

            # Check cache
            if not force and filepath.exists():
                cached = self._load_json(filepath)
                if cached:
                    all_vo2max.append(cached)
                    continue

            try:
                # Get max metrics which includes VO2 max
                vo2max_data = self.client.get_max_metrics(current_date.isoformat())
                if vo2max_data:
                    vo2max_data['_date'] = current_date.isoformat()
                    self._save_json(vo2max_data, filepath)
                    all_vo2max.append(vo2max_data)
            except Exception as e:
                # VO2 max not available for all days, skip silently
                pass

        console.print(f"[green]Fetched {len(all_vo2max)} VO2 max records[/green]")
        return all_vo2max

    def fetch_all(self, days: int = 7, force: bool = False) -> dict:
        """Fetch all data types for the specified number of days."""
        return {
            "activities": self.fetch_activities(days, force),
            "sleep": self.fetch_sleep(days, force),
            "heart_rate": self.fetch_heart_rate(days, force),
            "daily_summaries": self.fetch_daily_summaries(days, force),
            "vo2max": self.fetch_vo2max(days, force),
        }
