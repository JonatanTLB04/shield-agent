# SHIELD — Security Operations Agent

Detects exposed devices via Microsoft Defender for Endpoint, notifies the
right person by email (Claude drafts the message), verifies the fix
directly via Datto RMM the next day, reminds if needed, and escalates to
IT if it's still unresolved after a configured limit.

## Quick start (works today, zero credentials needed)

```bash
pip install -r requirements.txt --break-system-packages
cp .env.example .env
python main.py
```

That's it — with `SHIELD_DRY_RUN=true` (the default), every connector
returns realistic fake data instead of calling a real API. You'll see the
full cycle run: new findings detected, one held back because it has no
available vendor fix yet (a fake OpenSSL entry, just like we discussed),
two notification emails printed to your terminal instead of actually sent,
and a summary at the end.

Run it again and you'll see the second-run behavior — nothing duplicated,
because the state store already knows about everything from the first run.

Run the test suite any time to confirm nothing's broken:

```bash
python -m tests.test_orchestrator
```

## How this maps to your Monday board

This code covers items **8 through 12** of your 15-item rollout list.
Items 1–7 are prerequisites that have to happen *before* any of this can
run against real systems — they're admin/setup work, not code:

| Monday item | What it unlocks in this repo |
|---|---|
| 1. Confirm licensing & prerequisites | Confirms the Defender/Datto API calls below will actually work |
| 2. Get Entra ID admin sign-off | Needed before item 3 |
| 3. Register app + configure credentials | Fills in `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CERT_PATH`, `AZURE_CERT_THUMBPRINT` |
| 4. Request & consent permissions | Makes the Defender/Graph calls actually authorized |
| 5. Test Defender for Endpoint connection | You'll know this works once `SHIELD_DRY_RUN=false` runs without auth errors |
| 6. Validate device-to-user mapping | Watch the `notified` count in real runs — if it's much lower than `new_findings`, mapping is failing for some devices |
| 7. Enable & test Datto RMM API | Fills in `DATTO_API_URL`, `DATTO_API_KEY`, `DATTO_API_SECRET` |
| **8. Build the two connectors** | ✅ `connectors/defender_connector.py`, `connectors/datto_connector.py` |
| **9. Set up state store & daily scheduler** | ✅ `core/state_store.py` (the scheduler itself is just running `main.py` daily — see below) |
| **10. Integrate Claude for message drafting** | ✅ `core/claude_client.py` |
| **11. Build & test email notification flow** | ✅ `connectors/graph_connector.py` + the flow in `core/orchestrator.py` |
| **12. Build recheck, reminder & escalation logic** | ✅ Already in `core/orchestrator.py`, timing configurable in `.env` |
| 13. Run a small pilot | Point this at your own IT team's devices first (see below) |
| 14. Harden for production | See "Before going company-wide" below |
| 15. Company-wide rollout | Flip the switch once 13-14 are done |

## Turning off dry-run mode (once items 1-7 are done)

1. Fill in every value in `.env` — nothing should be blank except the
   ones marked optional.
2. Set `SHIELD_DRY_RUN=false`.
3. Run `python main.py` again. If something's misconfigured, you'll get a
   clear error naming exactly which credential or permission is the
   problem — read the error, don't guess.
4. Start by only running this against a couple of test devices if
   possible, before letting it see your whole device inventory.

## Scheduling it for the pilot (item 13)

While you're piloting, you don't need Azure Functions yet — just run this
once a day with whatever's easiest:

- **Windows Task Scheduler**, pointed at `python main.py`, once daily.
- Or a scheduled Datto RMM Quick Job that runs the script on a server you
  control (slightly circular, but works fine for a pilot).

Only move this into an actual Azure Function (timer-triggered) once
you're past the pilot and heading toward item 15 — nothing in the code
needs to change for that move, just how it gets invoked.

## Before going company-wide (item 14)

This codebase intentionally keeps things simple for building and
piloting. Before a real rollout, revisit these:

- **State store**: SQLite is fine for a pilot; move to Azure Cosmos DB or
  Azure SQL for production (only `core/state_store.py` needs to change —
  everything else calls it through the same methods).
- **Secrets**: `.env` is fine for local development. In production, the
  certificate and API keys should come from Azure Key Vault, not a file.
- **Retries**: none of the connectors currently retry on transient
  failures (rate limits, network blips). Add exponential backoff before
  running this unattended against your whole device inventory.
- **Monitoring**: wire up logging/alerting (Application Insights or
  similar) so a silent failure doesn't just... stop notifying people with
  nobody noticing.
- **Ticketing**: `connectors/escalation_connector.py` currently just
  emails your IT team. Replace it with a real call to whichever ticketing
  system you land on once that decision is made.

## Project layout

```
shield-agent/
├── main.py                          # entry point — run this once per cycle
├── config.py                        # all settings, read from .env
├── connectors/
│   ├── defender_connector.py        # Microsoft Defender for Endpoint
│   ├── datto_connector.py           # Datto RMM — verification + remediation
│   ├── graph_connector.py           # Microsoft Graph — user lookup + email
│   └── escalation_connector.py      # IT escalation (email for now)
├── core/
│   ├── models.py                    # shared data shapes
│   ├── state_store.py               # SQLite-backed lifecycle tracking
│   ├── claude_client.py             # message drafting
│   ├── fixtures.py                  # fake data powering dry-run mode
│   └── orchestrator.py              # the actual daily cycle logic
└── tests/
    └── test_orchestrator.py         # smoke test, runs fully offline
```
