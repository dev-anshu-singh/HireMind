"""
Autonomous Campaign Monitoring Cron Worker.

Runs nightly (or on a 24-hour schedule) to inspect all active campaigns,
detect pacing bottlenecks, and generate proactive optimization recommendations.
"""

import sys
import os
import asyncio
from datetime import datetime, timezone

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.core.database import get_async_session
from app.services.monitoring_service import MonitoringService


async def run_nightly_monitoring_cron():
    """
    Iterates through all active campaigns in the database and runs the Campaign Monitor AI Agent.
    """
    print("=" * 70)
    print(f"[{datetime.now(timezone.utc).isoformat()}] STARTING NIGHTLY CAMPAIGN MONITORING CRON")
    print("=" * 70)

    async for db in get_async_session():
        try:
            logs = await MonitoringService.monitor_all_active_campaigns(db)
            print(f" -> Successfully audited {len(logs)} active campaign(s).")
            for idx, log in enumerate(logs, 1):
                category = (log.guardrail_flags or {}).get("diagnostic_category", "UNKNOWN")
                print(f"    [{idx}] Campaign {log.campaign_id} -> {category} | Action: {log.action_proposed} | Status: {log.status}")
        except Exception as e:
            print(f" -> ERROR during nightly monitoring cron: {e}")
        finally:
            break

    print("=" * 70)
    print("NIGHTLY MONITORING CRON COMPLETED SUCCESSFULLY.")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_nightly_monitoring_cron())
