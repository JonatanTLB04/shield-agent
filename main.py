"""
Entry point. Run this once per cycle.
"""
from datetime import datetime, timezone
from config import settings
from core.orchestrator import Orchestrator

def main():
    print(f"=== SHIELD run started at {datetime.now(timezone.utc).isoformat()} ===")
    print(f"Dry run: {settings.dry_run}")

    combined_summary = {
        "new_findings": 0,
        "on_hold_no_fix": 0,
        "not_actionable": 0,
        "notified": 0,
        "resolved": 0,
        "reminded": 0,
        "escalated": 0,
        "auto_remediated": 0,
    }

    for tenant in settings.tenants:
        print(f"\n--- Tenant: {tenant.name} ---")
        if not settings.dry_run:
            if tenant.pilot_device_hostnames:
                print(f"Pilot mode: ON — restricted to {list(tenant.pilot_device_hostnames)}")
            else:
                print("WARNING: no pilot devices configured — will act on ALL devices.")

        orchestrator = Orchestrator(tenant=tenant)
        summary = orchestrator.run_daily_cycle()
        orchestrator.store.record_run(summary)

        for key, value in summary.items():
            combined_summary[key] += value

    print("\n=== Run summary (all tenants) ===")
    for key, value in combined_summary.items():
        print(f"  {key}: {value}")
    print("====================\n")

if __name__ == "__main__":
    main()
