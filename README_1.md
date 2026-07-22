# SHIELD - Security Operations Agent

Detects exposed devices via Microsoft Defender for Endpoint, notifies the
right person by email (Claude drafts the message), verifies the fix
directly via Datto RMM the next day, reminds if needed, and escalates to
IT if it's still unresolved after a configured limit.

## Current status (updated)

- Defender for Endpoint integration: working, confirmed against real devices
- Datto RMM + Microsoft Graph user resolution: working, with fallback if Defender alone can't resolve the user
- Gating logic: findings split into on-hold (no vendor fix yet), not actionable (policy/config, no restart needed), and actionable (restart required, goes to the user)
- Claude API integration: working, drafting real notification emails (falls back to a fixed template automatically if no API key is configured, so the pipeline never breaks)
- Not yet wired: actually sending the drafted email (`send_mail()` is not called yet, still dry-run by design)
- Not yet wired: scheduling (currently run manually)
- Planned next: auto-remediation for the "not actionable" findings, instead of just skipping them, apply safe fixes automatically in the background via Datto RMM Quick Job, and only surface restart-required findings to the user by email

## Quick start (works today, zero credentials needed)

```bash
pip install -r requirements.txt --break-system-packages
cp .env.example .env
python main.py
```

That's it, with `SHIELD_DRY_RUN=true` (the default), every connector
returns realistic fake data instead of calling a real API. You'll see the
full cycle run: new findings detected, one held back because it has no
available vendor fix yet (a fake OpenSSL entry, just like we discussed),
two notification emails printed to your terminal instead of actually sent,
and a summary at the end.

Run it again and you'll see the second-run behavior, nothing duplicated,
because the state store already knows about everything from the first run.

To test against a real device once credentials are filled in:

```bash
python -m tests.test_full_pipeline_dry_run
```

Run the smoke test suite any time to confirm nothing's broken:

```bash
python -m tests.test_orchestrator
```

## How this maps to your Monday board

This code covers items **8 through 12** of the 15-item rollout list.
Items 1-7 are prerequisites that have to happen *before* any of this can
run against real systems, they're admin/setup work, not code:

| Monday item | Status |
|---|---|
| 1. Confirm licensing & prerequisites | Done |
| 2. Get Entra ID admin sign-off | Done |
| 3. Register app + configure credentials | Done, fills in `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CERT_PATH`, `AZURE_CERT_THUMBPRINT` |
| 4. Request & consent permissions | Done |
| 5. Test Defender for Endpoint connection | Done, confirmed working against real devices |
| 6. Validate device-to-user mapping | Done, Datto RMM + Graph fallback resolves users reliably |
| 7. Enable & test Datto RMM API | Done, fills in `DATTO_API_URL`, `DATTO_API_KEY`, `DATTO_API_SECRET` |
| **8. Build the two connectors** | Done: `connectors/defender_connector.py`, `connectors/datto_connector.py` |
| **9. Set up state store & daily scheduler** | Done: `core/state_store.py` (the scheduler itself is just running `main.py` daily, see below) |
| **10. Integrate Claude for message drafting** | Done: `core/claude_client.py`, confirmed working with a real API key |
| **11. Build & test email notification flow** | Drafting works via `connectors/graph_connector.py` + `core/orchestrator.py`; actually sending the email is not wired yet |
| **12. Build recheck, reminder & escalation logic** | In `core/orchestrator.py`, timing configurable in `.env`, not yet tested against a live cycle |
| 13. Run a small pilot | Point this at your own IT team's devices first (see below) |
| 14. Harden for production | See "Before going company-wide" below |
| 15. Company-wide rollout | Flip the switch once 13-14 are done |

## Turning off dry-run mode (once items 1-7 are done)

1. Fill in every value in `.env`, nothing should be blank except the
   ones marked optional.
2. Set `SHIELD_DRY_RUN=false`.
3. Run `python main.py` again. If something's misconfigured, you'll get a
   clear error naming exactly which credential or permission is the
   problem, read the error, don't guess.
4. Start by only running this against a couple of test devices if
   possible, before letting it see your whole device inventory.

## Scheduling it for the pilot (item 13)

While piloting, you don't need Azure Functions yet, just run this
once a day with whatever's easiest:

- **Windows Task Scheduler**, pointed at `python main.py`, once daily.
- Or a scheduled Datto RMM Quick Job that runs the script on a server you
  control (slightly circular, but works fine for a pilot).

Only move this into an actual Azure Function (timer-triggered) once
you're past the pilot and heading toward item 15, nothing in the code
needs to change for that move, just how it gets invoked.

## Before going company-wide (item 14)

This codebase intentionally keeps things simple for building and
piloting. Before a real rollout, revisit these:

- **State store**: SQLite is fine for a pilot; move to Azure Cosmos DB or
  Azure SQL for production (only `core/state_store.py` needs to change,
  everything else calls it through the same methods).
- **Secrets**: `.env` is fine for local development. In production, the
  certificate and API keys should come from Azure Key Vault, not a file.
- **Retries**: none of the connectors currently retry on transient
  failures (rate limits, network blips). Add exponential backoff before
  running this unattended against your whole device inventory.
- **Monitoring**: wire up logging/alerting (Application Insights or
  similar) so a silent failure doesn't just stop notifying people with
  nobody noticing.
- **Ticketing**: `connectors/escalation_connector.py` currently just
  emails your IT team. Replace it with a real call to whichever ticketing
  system you land on once that decision is made.
- **Sending email for real**: `send_mail()` needs to actually be called
  in the orchestrator once you're ready to move past dry-run drafting.
- **Auto-remediation**: planned but not built yet, start with a small,
  known-safe list of fixes before mapping all "not actionable" categories.

## Project layout

```
shield-agent/
|-- main.py                              # entry point, run this once per cycle
|-- config.py                            # all settings, read from .env
|-- connectors/
|   |-- defender_connector.py            # Microsoft Defender for Endpoint
|   |-- datto_connector.py               # Datto RMM, verification + remediation
|   |-- graph_connector.py               # Microsoft Graph, user lookup + email
|   `-- escalation_connector.py          # IT escalation (email for now)
|-- core/
|   |-- models.py                        # shared data shapes
|   |-- state_store.py                   # SQLite-backed lifecycle tracking
|   |-- claude_client.py                 # message drafting
|   |-- fixtures.py                      # fake data powering dry-run mode
|   `-- orchestrator.py                  # the actual daily cycle logic
`-- tests/
    |-- test_orchestrator.py             # smoke test, runs fully offline
    |-- test_defender_connection.py      # isolated Defender connection test
    |-- test_datto_connection.py         # isolated Datto RMM connection test
    |-- test_full_pipeline_dry_run.py    # end-to-end run against a real device
    |-- test_user_resolution_fallback.py # Datto + Graph fallback logic
    |-- debug_datto_device_shape.py      # inspects raw Datto API response shape
    `-- debug_graph_user_shape.py        # inspects raw Graph API response shape
```

## Notes for whoever picks this up

- The naming convention for TLB devices is `TLB-[LASTNAME]-LT` (laptops).
- SHIELD is designed to fail safe: if the Claude API key isn't configured,
  it falls back to a fixed template rather than erroring out.
- Pilot scope is currently limited to a small set of test devices before
  wider rollout.
