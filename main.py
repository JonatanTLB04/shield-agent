"""
Entry point. Run this once per cycle.
"""
from datetime import datetime, timezone
from config import settings
from core.orchestrator import Orchestrator

def main():
    print(f"=== SHIELD run started at {datetime.now(timezone.utc).isoformat()} ===")
    print(f"Dry run: {settings.dry_run}")

    for tenant in settings.tenants:
        print(f"\n--- Tenant: {tenant.name} ---")
        if not settings.dry_run:
            if tenant.pilot_device_hostnames:
                print(f"Pilot: {list(tenant.pilot_device_hostnames)}")
            else:
                print("Pilot: ALL devices")

        orchestrator = Orchestrator(tenant=tenant)
        summary = orchestrator.run_daily_cycle()
        orchestrator.store.record_run(summary)

        print(f"  Summary for {tenant.name}:")
        for key, value in summary.items():
            if value > 0:
                print(f"    {key}: {value}")
        if all(v == 0 for v in summary.values()):
            print("    No activity.")

    print("\n====================\n")

if __name__ == "__main__":
    main()
