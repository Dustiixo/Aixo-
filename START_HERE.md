# AIXO Local Bridge M0.2 — RC0 Windows offline test candidate

**Real executable source, not an installer. No paid model, no cloud, no service daemon, no Tkinter.**

## In your extracted folder, run in this order

1. `RUN_TESTS_WINDOWS.cmd` — should show **48 tests passing** (28 inherited RC1 + 20 bridge tests). If anything fails: **stop, do not import**.
2. `RUN_SAFE_DEMO_WINDOWS.cmd` — creates its own synthetic GREMLIN JSON in a fresh **temporary** folder; it runs preview → approved import → local collision scan → duplicate delivery → verify → Thought Spine review export → cross-store backup → reopen. It prints where the proof files were saved. **This does not touch RC1 or your real GREMLIN data.**
3. `START_BRIDGE_WINDOWS.cmd` — opens the PowerShell **native Windows Forms** operator panel. Use **CHOOSE FILE** on `samples/SYNTHETIC_GREMLIN_STATE.json`, then **PREVIEW**. If you want to save an isolated copy, click **APPROVE IMPORT**, then **SCAN COLLISIONS**, **VERIFY**, and **EXPORT REVIEW** to a folder you choose.
4. `START_WALL_DIAGNOSTIC_WINDOWS.cmd` — optional RC1 diagnostic window, now pointed at the **M0.2 isolated wall**. It does not open your older RC1 database by default.
5. For **Thought Spine**: use its existing **Capture** workflow to import the generated `REVIEW.md` as a *new source*. DO NOT use its Restore/Load Backup for this file. This is an explicit manual handoff; no current auto-sync or owner-store write.

If you receive an error: copy the text from the console or window. Keep the failed source and data untouched; the release remains blocked until accepted.

## What this actually implements

- Reuses the **RC1 Wall engine source**: SQLite marbles, candidate lexical collisions, slice/multiply/mutate/reconcile, event replay, integrity verification, bounded jobs and backups.
- Adds a **one-request-per-process** JSON protocol (`bridge_protocol.py`) suitable for other **local** apps and a corresponding command-line tool (`bridge_cli.py`). No TCP/HTTP server, browser port, agent action or shell execution endpoint.
- Recognizes exact GREMLIN **version 1 or 2 JSON exports**, just `entries`, with explicit preview. Copies full original entry fields into a separate immutable-intended bridge record and preserves the SHA-256 of the entire export at import time. Does not write to GREMLIN, EUREKA, Research Kernel, or Thought Spine.
- Imports only after an **SHA-bound approval**. Up to 50 entries per approved batch. Never silently accepts changed source revisions. Edits require a second explicit review; then generate traceable **MUTATE** descendants.
- Uses Wall idempotency keys and **prepared** intent receipts to recover safely after interruption between two SQLite owners. Replaying a prepared import uses the same request-bound key and cannot create another logical marble.
- Produces a read-only **Thought Spine review bundle**, containing `REVIEW.md` and `RECEIPT.json`. These are source material to be captured manually, **not a Thought Spine database or backup**.
- Copies both stores into a verified **new backup directory**. Never overwrites a backup or restores into a live location.

## Stores and ownership

| Owner | Default Windows storage | Writes |
| --- | --- | --- |
| AIXO M0.2 bridge | `%LOCALAPPDATA%\OXsukra\AIXO_Local_Bridge_M0_2\bridge.sqlite3` | Import receipts and original GREMLIN entry fields |
| AIXO M0.2 wall | `%LOCALAPPDATA%\OXsukra\AIXO_Local_Bridge_M0_2\wall.sqlite3` | Marbles/events/jobs |
| **Older AIXO RC1** | `%LOCALAPPDATA%\OXsukra\AIXO_Collision_Wall_M0_1\wall.sqlite3` | **No default writes from M0.2** |
| GREMLIN export | Wherever you saved the JSON | **Read only** |
| Thought Spine | Independent browser/Obsidian data | **No direct writes** |

`AIXO_BRIDGE_HOME` and `AIXO_WALL_HOME` are optional **developer** overrides for command-line/programmatic use. Normal Windows launchers explicitly choose the M0.2 isolated directory.

## Known restrictions — not finished integration

- The Windows Forms M0.2 panel **has not been run on your actual Windows host** in this packaging environment. Automated engine tests were executed on Linux/Python 3.13; **Windows/Python 3.14 acceptance remains pending**.
- GREMLIN phone export generation, offline persistence, live LAN/Tailscale, Thought Spine actual import/reopen and VELA/IXO calls are **not** claimed as tested.
- The collision detector is lexical Jaccard overlap, **not LLM interpretation, embeddings or fact verification**. A suggested collision is not established truth.
- The two SQLite stores have individually atomic writes; cross-store operations use prepared receipts and idempotent recovery, **not an atomic distributed transaction**. The pair-backup copies them sequentially and checks references; it cannot guarantee a point-in-time snapshot during active concurrent writes.
- Local process protocol trusts software running under the current Windows account. **It is not an authentication boundary against hostile local software**.
- No automatic restart after crash, hidden system service, automatic update or ongoing monitoring is installed. Each request is explicit and bounded.
- User data is local and unencrypted by this package. Protect OS permissions and backups; don't import secrets unless you accept local-at-rest risk.

## G0 host acceptance checklist

- [ ] 48 automated tests pass on your PC.
- [ ] Safe demo passes and the review Markdown is inspectable.
- [ ] Windows Forms bridge opens; `PREFLIGHT` displays version 0.2.0.
- [ ] Preview `samples/SYNTHETIC_GREMLIN_STATE.json` without importing.
- [ ] Approve import; scan; verify; exit; reopen; verify again.
- [ ] Reimport same unchanged file; no additional marble.
- [ ] Export a review bundle; import its `REVIEW.md` into a **test copy** of Thought Spine with **Capture**; close and reopen Thought Spine; original wording remains.
- [ ] Backup both databases; compare to original; verify isolated copied stores.
- [ ] Confirm older RC1 data under its own directory was not modified.

If any required check fails, this remains an RC0 development candidate. No ecosystem-wide promotion.
