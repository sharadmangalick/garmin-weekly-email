"""Email Generator - Creates HTML email content for weekly training reports."""

from datetime import datetime, date, timedelta
from typing import Optional

from jinja2 import Template


class EmailGenerator:
    """Generates HTML email content for weekly training reports."""

    def __init__(self):
        self.template = self._get_email_template()

    def generate_email(
        self,
        user_config: dict,
        analysis_results: dict,
        training_plan: dict
    ) -> dict:
        """
        Generate email content from training plan and health data.

        Args:
            user_config: User configuration dictionary
            analysis_results: Health analysis from GarminDataAnalyzer
            training_plan: Training plan from AICoach

        Returns:
            Dictionary with 'subject' and 'html_body'
        """
        # Calculate week info
        week_start = date.today()
        # Adjust to start from Monday
        week_start = week_start - timedelta(days=week_start.weekday())
        week_end = week_start + timedelta(days=6)

        weeks_to_race = user_config.get('weeks_until_race', 0)
        race_name = f"{user_config.get('goal_target', '')} {user_config.get('goal_type', 'Marathon')}".title()

        # Build subject line
        subject = f"Your Training Plan: Week of {week_start.strftime('%b %d')} | {weeks_to_race} weeks to {race_name}"

        # Extract health metrics
        rhr = analysis_results.get('resting_hr', {})
        bb = analysis_results.get('body_battery', {})
        sleep = analysis_results.get('sleep', {})
        stress = analysis_results.get('stress', {})
        vo2max = analysis_results.get('vo2max', {})

        # Build health snapshot
        health_snapshot = []
        if rhr.get('available'):
            change_str = f"{rhr['change']:+.0f}" if rhr.get('change') else ""
            status_emoji = self._get_status_emoji(rhr.get('status'))
            health_snapshot.append({
                "metric": "Resting HR",
                "value": f"{rhr.get('current', 'N/A')} bpm",
                "detail": f"{change_str} from baseline" if change_str else "",
                "status": rhr.get('status', 'normal'),
                "emoji": status_emoji
            })

        if bb.get('available'):
            status_emoji = self._get_status_emoji(bb.get('status'))
            health_snapshot.append({
                "metric": "Body Battery",
                "value": f"{bb.get('current_wake', 'N/A')} wake avg",
                "detail": bb.get('trend', '').title(),
                "status": bb.get('status', 'normal'),
                "emoji": status_emoji
            })

        if sleep.get('available'):
            status_emoji = self._get_status_emoji(sleep.get('status'))
            health_snapshot.append({
                "metric": "Sleep",
                "value": f"{sleep.get('avg_hours', 'N/A')} hrs avg",
                "detail": f"{sleep.get('under_6h_pct', 0)}% nights under 6h",
                "status": sleep.get('status', 'normal'),
                "emoji": status_emoji
            })

        if stress.get('available'):
            status_emoji = self._get_status_emoji(stress.get('status'))
            health_snapshot.append({
                "metric": "Stress",
                "value": f"{stress.get('avg', 'N/A')} avg",
                "detail": f"{stress.get('high_stress_pct', 0)}% high stress days",
                "status": stress.get('status', 'normal'),
                "emoji": status_emoji
            })

        # Determine overall recovery status
        recovery_status = self._determine_recovery_status(rhr, bb, sleep, stress)

        # Render template
        template = Template(self.template)
        html_body = template.render(
            user_name=user_config.get('name', 'Runner'),
            week_start=week_start.strftime('%B %d'),
            week_end=week_end.strftime('%B %d, %Y'),
            weeks_to_race=weeks_to_race,
            race_name=race_name,
            race_date=user_config.get('goal_date', ''),
            target_pace=user_config.get('target_pace', 'N/A'),
            training_phase=user_config.get('training_phase', 'build').title(),
            health_snapshot=health_snapshot,
            recovery_status=recovery_status,
            week_summary=training_plan.get('week_summary', {}),
            daily_plan=training_plan.get('daily_plan', []),
            coaching_notes=training_plan.get('coaching_notes', []),
            recovery_recommendations=training_plan.get('recovery_recommendations', []),
            generated_date=datetime.now().strftime('%B %d, %Y at %I:%M %p')
        )

        return {
            "subject": subject,
            "html_body": html_body
        }

    def _get_status_emoji(self, status: str) -> str:
        """Return emoji for status."""
        return {
            "good": "&#9989;",      # Green checkmark
            "normal": "&#128310;",  # Yellow circle
            "concern": "&#9888;",   # Warning sign
        }.get(status, "&#128310;")

    def _determine_recovery_status(self, rhr: dict, bb: dict, sleep: dict, stress: dict) -> dict:
        """Determine overall recovery status from health metrics."""
        concern_count = 0
        good_count = 0

        for metric in [rhr, bb, sleep, stress]:
            if metric.get('available'):
                status = metric.get('status', 'normal')
                if status == 'concern':
                    concern_count += 1
                elif status == 'good':
                    good_count += 1

        if concern_count >= 2:
            return {
                "status": "recovery_recommended",
                "message": "Multiple fatigue indicators detected",
                "color": "#dc3545"  # Red
            }
        elif concern_count == 1:
            return {
                "status": "caution",
                "message": "Monitor recovery this week",
                "color": "#ffc107"  # Yellow
            }
        elif good_count >= 2:
            return {
                "status": "ready_to_train",
                "message": "Recovery metrics look strong",
                "color": "#28a745"  # Green
            }
        else:
            return {
                "status": "normal",
                "message": "Recovery within normal range",
                "color": "#6c757d"  # Gray
            }

    def _get_email_template(self) -> str:
        """Return the Jinja2 HTML email template."""
        return '''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Weekly Training Plan</title>
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f5f5f5;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f5f5f5; padding: 20px 0;">
        <tr>
            <td align="center">
                <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                    <!-- Header -->
                    <tr>
                        <td style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; text-align: center;">
                            <h1 style="color: #ffffff; margin: 0 0 8px 0; font-size: 24px; font-weight: 600;">
                                Your Weekly Training Plan
                            </h1>
                            <p style="color: rgba(255,255,255,0.9); margin: 0; font-size: 16px;">
                                Week of {{ week_start }} | {{ weeks_to_race }} weeks to {{ race_name }}
                            </p>
                        </td>
                    </tr>

                    <!-- Recovery Status Banner -->
                    <tr>
                        <td style="padding: 0;">
                            <table width="100%" cellpadding="0" cellspacing="0" style="background-color: {{ recovery_status.color }}15; border-left: 4px solid {{ recovery_status.color }};">
                                <tr>
                                    <td style="padding: 16px 20px;">
                                        <strong style="color: {{ recovery_status.color }};">{{ recovery_status.status | replace('_', ' ') | title }}</strong>
                                        <span style="color: #666;"> - {{ recovery_status.message }}</span>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Health Snapshot -->
                    <tr>
                        <td style="padding: 24px;">
                            <h2 style="color: #333; font-size: 18px; margin: 0 0 16px 0; padding-bottom: 8px; border-bottom: 2px solid #eee;">
                                Health Snapshot
                            </h2>
                            <table width="100%" cellpadding="0" cellspacing="0">
                                {% for metric in health_snapshot %}
                                <tr>
                                    <td style="padding: 8px 0; border-bottom: 1px solid #f0f0f0;">
                                        <table width="100%" cellpadding="0" cellspacing="0">
                                            <tr>
                                                <td width="40" style="font-size: 20px;">{{ metric.emoji | safe }}</td>
                                                <td>
                                                    <strong style="color: #333;">{{ metric.metric }}</strong><br>
                                                    <span style="color: #666; font-size: 14px;">{{ metric.value }}</span>
                                                    {% if metric.detail %}
                                                    <span style="color: #999; font-size: 12px;"> ({{ metric.detail }})</span>
                                                    {% endif %}
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                                {% endfor %}
                            </table>
                        </td>
                    </tr>

                    <!-- Week Summary -->
                    <tr>
                        <td style="padding: 0 24px;">
                            <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f8f9fa; border-radius: 8px; overflow: hidden;">
                                <tr>
                                    <td style="padding: 16px; text-align: center;">
                                        <div style="font-size: 32px; font-weight: bold; color: #667eea;">
                                            {{ week_summary.total_miles | default(0) }}
                                        </div>
                                        <div style="color: #666; font-size: 14px;">miles this week</div>
                                    </td>
                                    <td style="padding: 16px; text-align: center; border-left: 1px solid #dee2e6;">
                                        <div style="font-size: 18px; font-weight: 600; color: #333;">
                                            {{ week_summary.training_phase | default('Build') | title }}
                                        </div>
                                        <div style="color: #666; font-size: 14px;">training phase</div>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Daily Plan -->
                    <tr>
                        <td style="padding: 24px;">
                            <h2 style="color: #333; font-size: 18px; margin: 0 0 16px 0; padding-bottom: 8px; border-bottom: 2px solid #eee;">
                                This Week's Plan
                            </h2>
                            <table width="100%" cellpadding="0" cellspacing="0">
                                {% for day in daily_plan %}
                                <tr>
                                    <td style="padding: 12px 0; border-bottom: 1px solid #f0f0f0;">
                                        <table width="100%" cellpadding="0" cellspacing="0">
                                            <tr>
                                                <td width="80" style="vertical-align: top;">
                                                    <strong style="color: #667eea; font-size: 14px;">{{ day.day[:3] | upper }}</strong>
                                                </td>
                                                <td>
                                                    <div style="font-weight: 600; color: #333;">{{ day.title }}</div>
                                                    {% if day.distance_miles %}
                                                    <div style="color: #666; font-size: 14px; margin-top: 4px;">
                                                        {{ day.distance_miles }} miles
                                                    </div>
                                                    {% endif %}
                                                    <div style="color: #888; font-size: 13px; margin-top: 4px;">
                                                        {{ day.description }}
                                                    </div>
                                                    {% if day.notes %}
                                                    <div style="color: #764ba2; font-size: 12px; margin-top: 4px; font-style: italic;">
                                                        {{ day.notes }}
                                                    </div>
                                                    {% endif %}
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                                {% endfor %}
                            </table>
                        </td>
                    </tr>

                    <!-- Coaching Notes -->
                    {% if coaching_notes %}
                    <tr>
                        <td style="padding: 0 24px 24px 24px;">
                            <h2 style="color: #333; font-size: 18px; margin: 0 0 16px 0; padding-bottom: 8px; border-bottom: 2px solid #eee;">
                                Coach's Notes
                            </h2>
                            <table width="100%" cellpadding="0" cellspacing="0">
                                {% for note in coaching_notes %}
                                <tr>
                                    <td style="padding: 8px 0; padding-left: 16px; border-left: 3px solid #667eea; margin-bottom: 8px;">
                                        <span style="color: #444; font-size: 14px;">{{ note }}</span>
                                    </td>
                                </tr>
                                {% endfor %}
                            </table>
                        </td>
                    </tr>
                    {% endif %}

                    <!-- Recovery Recommendations -->
                    {% if recovery_recommendations %}
                    <tr>
                        <td style="padding: 0 24px 24px 24px;">
                            <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #fff3cd; border-radius: 8px; border-left: 4px solid #ffc107;">
                                <tr>
                                    <td style="padding: 16px;">
                                        <strong style="color: #856404;">Recovery Focus</strong>
                                        <ul style="margin: 8px 0 0 0; padding-left: 20px; color: #856404;">
                                            {% for rec in recovery_recommendations %}
                                            <li style="margin-bottom: 4px;">{{ rec }}</li>
                                            {% endfor %}
                                        </ul>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    {% endif %}

                    <!-- Footer -->
                    <tr>
                        <td style="background-color: #f8f9fa; padding: 20px; text-align: center; border-top: 1px solid #eee;">
                            <p style="color: #999; font-size: 12px; margin: 0 0 8px 0;">
                                Target pace: {{ target_pace }}/mile | Race: {{ race_date }}
                            </p>
                            <p style="color: #bbb; font-size: 11px; margin: 0;">
                                Generated {{ generated_date }} by Garmin Health Analyzer with Claude AI
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>'''

    def generate_preview_text(self, training_plan: dict) -> str:
        """Generate plain text preview of the training plan."""
        lines = []

        week_summary = training_plan.get('week_summary', {})
        lines.append(f"=== WEEKLY TRAINING PLAN ===")
        lines.append(f"Total Miles: {week_summary.get('total_miles', 'N/A')}")
        lines.append(f"Phase: {week_summary.get('training_phase', 'N/A').title()}")
        lines.append(f"Focus: {week_summary.get('focus', 'N/A')}")
        lines.append("")

        lines.append("=== DAILY SCHEDULE ===")
        for day in training_plan.get('daily_plan', []):
            day_str = day.get('day', '')[:3].upper()
            title = day.get('title', 'Rest')
            distance = day.get('distance_miles')
            distance_str = f" - {distance}mi" if distance else ""
            lines.append(f"{day_str}: {title}{distance_str}")
            if day.get('description'):
                lines.append(f"     {day['description']}")

        lines.append("")
        lines.append("=== COACHING NOTES ===")
        for note in training_plan.get('coaching_notes', []):
            lines.append(f"- {note}")

        if training_plan.get('recovery_recommendations'):
            lines.append("")
            lines.append("=== RECOVERY RECOMMENDATIONS ===")
            for rec in training_plan.get('recovery_recommendations', []):
                lines.append(f"- {rec}")

        return "\n".join(lines)
