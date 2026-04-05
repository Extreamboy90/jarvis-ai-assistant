#!/usr/bin/env python3
"""
Health Plugin Automation Examples

Script di esempio per automatizzare operazioni comuni del plugin health.
Utile per cron jobs, routine mattutine/serali, integrazioni custom.

Usage:
    python health_automation_example.py --user USER_ID --action ACTION

Examples:
    # Morning routine
    python health_automation_example.py --user john --action morning_routine

    # Evening summary
    python health_automation_example.py --user john --action evening_summary

    # Weekly report (run on Monday)
    python health_automation_example.py --user john --action weekly_report

    # Sync from Google Fit
    python health_automation_example.py --user john --action sync_google_fit
"""

import argparse
import requests
import json
from datetime import datetime, date
from typing import Dict, List, Optional


class HealthAutomation:
    def __init__(self, base_url: str = "http://localhost:8000", user_id: str = "default"):
        self.base_url = base_url
        self.user_id = user_id

    def _get(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """GET request helper"""
        url = f"{self.base_url}{endpoint}"
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()

    def _post(self, endpoint: str, data: Optional[Dict] = None, params: Optional[Dict] = None) -> Dict:
        """POST request helper"""
        url = f"{self.base_url}{endpoint}"
        response = requests.post(url, json=data, params=params)
        response.raise_for_status()
        return response.json()

    def sync_google_fit(self, days: int = 1) -> Dict:
        """Sync data from Google Fit"""
        print(f"📥 Syncing Google Fit data (last {days} days)...")
        result = self._post(
            f"/health/{self.user_id}/sync",
            params={"source": "google_fit", "days": days}
        )
        if result.get("success"):
            print(f"✅ Synced {result.get('data_points', 0)} data points")
        else:
            print(f"❌ Sync failed: {result.get('message')}")
        return result

    def get_sleep_analysis(self, days: int = 7) -> Dict:
        """Get sleep analysis"""
        print(f"😴 Analyzing sleep quality (last {days} days)...")
        result = self._get(f"/health/{self.user_id}/sleep", params={"days": days})
        if result.get("success"):
            avg_hours = result.get("average_hours", 0)
            quality = result.get("quality_score", "unknown")
            print(f"   Average: {avg_hours:.1f}h/night | Quality: {quality}")
            print(f"\n{result.get('ai_analysis', '')}")
        return result

    def get_activity_summary(self, date_str: Optional[str] = None) -> Dict:
        """Get activity summary for a date"""
        if not date_str:
            date_str = date.today().isoformat()
        print(f"🏃 Activity summary for {date_str}...")
        result = self._get(f"/health/{self.user_id}/activity", params={"date": date_str})
        if result.get("success"):
            steps = result.get("steps", 0)
            calories = result.get("calories", 0)
            workouts = result.get("total_workouts", 0)
            print(f"   Steps: {steps:,} | Calories: {calories:,} | Workouts: {workouts}")
        return result

    def detect_anomalies(self) -> Dict:
        """Detect health anomalies"""
        print("🔍 Detecting anomalies...")
        result = self._get(f"/health/{self.user_id}/anomalies")
        if result.get("anomalies_detected"):
            print(f"⚠️  Found {result.get('count', 0)} anomalies:")
            for anomaly in result.get("anomalies", []):
                severity = anomaly.get("severity", "unknown")
                message = anomaly.get("message", "")
                print(f"   [{severity.upper()}] {message}")
        else:
            print("✅ No anomalies detected - all metrics look good!")
        return result

    def get_workout_suggestion(self) -> Dict:
        """Get personalized workout suggestion"""
        print("💪 Getting workout suggestion...")
        result = self._get(f"/health/{self.user_id}/workout-suggestion")
        if result.get("success"):
            print(f"\n{result.get('suggestion', '')}")
        return result

    def get_wellness_report(self, period: str = "week") -> Dict:
        """Generate wellness report"""
        print(f"📊 Generating {period} wellness report...")
        result = self._get(
            f"/health/{self.user_id}/wellness-report",
            params={"period": period}
        )
        if result.get("success"):
            score = result.get("overall_score", 0)
            print(f"   Overall Wellness Score: {score}/100")
            print(f"\n{result.get('ai_summary', '')}")
        return result

    def get_correlations(self, metric: str = "all", days: int = 14) -> Dict:
        """Get health-memory correlations"""
        print(f"🧠 Analyzing {metric} correlations with memory (last {days} days)...")
        result = self._get(
            f"/health/{self.user_id}/correlations",
            params={"metric": metric, "days": days}
        )
        if result.get("success"):
            print(f"\n{result.get('correlation_analysis', '')}")
        return result

    def chat(self, message: str) -> str:
        """Send message to chat API"""
        result = self._post("/chat", data={
            "message": message,
            "user_id": self.user_id
        })
        return result.get("response", "")

    # ========================================================================
    # AUTOMATED ROUTINES
    # ========================================================================

    def morning_routine(self):
        """Complete morning health routine"""
        print("="*60)
        print("🌅 MORNING HEALTH ROUTINE")
        print("="*60)

        # 1. Sync overnight data
        self.sync_google_fit(days=1)
        print()

        # 2. Sleep analysis
        self.get_sleep_analysis(days=1)
        print()

        # 3. Check for anomalies
        self.detect_anomalies()
        print()

        # 4. Workout suggestion
        self.get_workout_suggestion()
        print()

        print("="*60)
        print("✅ Morning routine complete!")
        print("="*60)

    def evening_summary(self):
        """Evening health summary"""
        print("="*60)
        print("🌙 EVENING HEALTH SUMMARY")
        print("="*60)

        # 1. Today's activity
        self.get_activity_summary()
        print()

        # 2. Check anomalies
        self.detect_anomalies()
        print()

        # 3. Brief wellness check
        response = self.chat("Dammi un breve riassunto della mia giornata dal punto di vista salute")
        print(f"\n💬 AI Summary:\n{response}")
        print()

        print("="*60)
        print("✅ Evening summary complete!")
        print("="*60)

    def weekly_report(self):
        """Weekly comprehensive report"""
        print("="*60)
        print("📅 WEEKLY HEALTH REPORT")
        print("="*60)

        # 1. Sync full week
        self.sync_google_fit(days=7)
        print()

        # 2. Sleep analysis
        self.get_sleep_analysis(days=7)
        print()

        # 3. Wellness report
        self.get_wellness_report(period="week")
        print()

        # 4. Correlations
        self.get_correlations(metric="all", days=7)
        print()

        print("="*60)
        print("✅ Weekly report complete!")
        print("="*60)

    def monthly_checkup(self):
        """Monthly comprehensive health checkup"""
        print("="*60)
        print("📆 MONTHLY HEALTH CHECKUP")
        print("="*60)

        # 1. Sync full month
        self.sync_google_fit(days=30)
        print()

        # 2. Wellness report
        self.get_wellness_report(period="month")
        print()

        # 3. Correlations
        self.get_correlations(metric="all", days=30)
        print()

        # 4. Ask AI for long-term insights
        response = self.chat(
            "Analizza la mia salute dell'ultimo mese e dammi insights su trend a lungo termine "
            "e suggerimenti per il mese prossimo"
        )
        print(f"\n💬 Long-term Insights:\n{response}")
        print()

        print("="*60)
        print("✅ Monthly checkup complete!")
        print("="*60)


def main():
    parser = argparse.ArgumentParser(description="Health Plugin Automation")
    parser.add_argument("--user", "-u", required=True, help="User ID")
    parser.add_argument("--action", "-a", required=True, choices=[
        "morning_routine",
        "evening_summary",
        "weekly_report",
        "monthly_checkup",
        "sync_google_fit",
        "sleep_analysis",
        "activity_summary",
        "detect_anomalies",
        "workout_suggestion",
        "wellness_report",
        "correlations"
    ], help="Action to perform")
    parser.add_argument("--base-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--days", type=int, default=7, help="Number of days for analysis")

    args = parser.parse_args()

    automation = HealthAutomation(base_url=args.base_url, user_id=args.user)

    # Execute action
    if args.action == "morning_routine":
        automation.morning_routine()
    elif args.action == "evening_summary":
        automation.evening_summary()
    elif args.action == "weekly_report":
        automation.weekly_report()
    elif args.action == "monthly_checkup":
        automation.monthly_checkup()
    elif args.action == "sync_google_fit":
        automation.sync_google_fit(days=args.days)
    elif args.action == "sleep_analysis":
        automation.get_sleep_analysis(days=args.days)
    elif args.action == "activity_summary":
        automation.get_activity_summary()
    elif args.action == "detect_anomalies":
        automation.detect_anomalies()
    elif args.action == "workout_suggestion":
        automation.get_workout_suggestion()
    elif args.action == "wellness_report":
        automation.get_wellness_report()
    elif args.action == "correlations":
        automation.get_correlations(days=args.days)


if __name__ == "__main__":
    main()


# ============================================================================
# CRON JOB EXAMPLES
# ============================================================================

"""
# Add to crontab (crontab -e):

# Morning routine at 7:00 AM every day
0 7 * * * /usr/bin/python3 /path/to/health_automation_example.py --user john --action morning_routine >> /var/log/health_morning.log 2>&1

# Evening summary at 9:00 PM every day
0 21 * * * /usr/bin/python3 /path/to/health_automation_example.py --user john --action evening_summary >> /var/log/health_evening.log 2>&1

# Weekly report every Monday at 8:00 AM
0 8 * * 1 /usr/bin/python3 /path/to/health_automation_example.py --user john --action weekly_report >> /var/log/health_weekly.log 2>&1

# Monthly checkup on the 1st of each month at 9:00 AM
0 9 1 * * /usr/bin/python3 /path/to/health_automation_example.py --user john --action monthly_checkup >> /var/log/health_monthly.log 2>&1

# Sync Google Fit every hour (keep data fresh)
0 * * * * /usr/bin/python3 /path/to/health_automation_example.py --user john --action sync_google_fit --days 1 >> /var/log/health_sync.log 2>&1
"""

# ============================================================================
# INTEGRATION WITH TELEGRAM BOT
# ============================================================================

"""
# Add to telegram_bot.py:

async def handle_health_command(update, context):
    user_id = str(update.effective_user.id)

    automation = HealthAutomation(user_id=user_id)

    # Get command
    command = context.args[0] if context.args else "summary"

    if command == "morning":
        automation.morning_routine()
        await update.message.reply_text("✅ Morning routine completed!")

    elif command == "evening":
        automation.evening_summary()
        await update.message.reply_text("✅ Evening summary ready!")

    elif command == "sleep":
        result = automation.get_sleep_analysis()
        await update.message.reply_text(result.get("ai_analysis", ""))

    elif command == "workout":
        result = automation.get_workout_suggestion()
        await update.message.reply_text(result.get("suggestion", ""))

    # Usage: /health morning, /health sleep, /health workout
"""
