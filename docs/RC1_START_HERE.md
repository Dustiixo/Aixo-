# AIXO Collision Wall M0.1.1 / RC1 — Windows repair candidate

**Start with `START_WINDOWS.cmd`** in the extracted folder. RC1 deliberately does **not** call Tkinter and therefore does **not** require the missing Tcl `init.tcl` from Python 3.14. It uses native Windows Forms through built-in Windows PowerShell and the original dependency-free Python SQLite event engine. Windows 10/11 + Windows PowerShell 5.1 + Python 3.10+ are required. No pip packages, external accounts, internet, admin rights, browser server or Python GUI components are needed.

This is a **test candidate**, not a host-accepted or signed production installer. The core Python tests passed in Linux Python 3.13; **Windows GUI and Python 3.14 acceptance remain pending** on your actual PC.

## What went wrong in RC0 and what RC1 changes

Your October 26 host logs exposed **two distinct failures**:

1. `app.py` crashed when `tk.Tk()` could not find a usable `init.tcl` in `Python314`. RC1 replaces the default Tk GUI with `WINDOWS_NATIVE.ps1`, a native Windows Forms application using PowerShell 5.1. RC1 never imports Tkinter.
2. Nine unit-test error reports, mostly Windows `WinError 32` while deleting `*.sqlite3` or replacing backup `*.partial` files. Python's `sqlite3.Connection` context manager does **not** close the connection at `with` exit. RC0 left connections open in existing-store verification/restore helpers, and some test fixtures also retained handles. RC1 adds explicit closing in all affected code paths, updates the tests, and exercises backup/restore/rename in new regression checks.

The optional `Could not find platform independent libraries <prefix>` message is from the installed Python interpreter; RC1 does **not** repair your system Python installation. The core interpreter must pass a simple SQLite preflight. If it doesn't, the launcher blocks and prints a diagnostic.

## Real Windows test, in order

1. Keep the old RC0 archive. Extract this **RC1 ZIP to a NEW FOLDER**; do not replace your old installation and do not move/copy the SQLite database by hand.
2. Double-click `RUN_TESTS_WINDOWS.cmd`. Expect **28 tests** and `OK`. If any fails, stop; the launcher won't auto-promote the candidate.
3. Double-click `START_WINDOWS.cmd`. Expect a Windows Forms window titled **OX / AIXO Collision Wall RC1** with MARBLES, COLLISION CANDIDATES, SELECTED MARBLE and EVENT RECORDS panes.
4. Click `DEMO DATA` (inserts exactly six demo marbles without deleting existing data), then `SCAN QUEUE`. A bounded timer also processes due jobs in the background while the UI is open.
5. Click a marble, then `MULTIPLY`. Enter two lines of the form `Title | Branch explanation`. Confirm both new marbles appear.
6. Click a child marble; click `REVERSE TRACE` and confirm its original ancestor is recorded. Try `SLICE` with an exact excerpt and `MUTATE` to make a new version. The original must remain intact.
7. Use `ACCEPT LINK` on a proposed collision and `REVIEW` to record a human decision. These are **not independently verified facts**.
8. Click `INTEGRITY`, confirm `PASS`, then `BACKUP`. Close all windows, double-click `START_WINDOWS.cmd` again and confirm all records survived.
9. Use `RESTORE NEW` to restore a backup to a different, unused `.sqlite3` path. The active store stays unchanged. `EXPORT JSON` explicitly exports a review packet only; it **does not import into Thought Spine**.

If a Windows error remains, copy the launcher console text and/or the test output. No need to disclose your personal thoughts or database.

## Storage and safety

- Existing default database path stays exactly `%LOCALAPPDATA%\OXsukra\AIXO_Collision_Wall_M0_1\wall.sqlite3`. This is intentional so RC1 can reopen your RC0 candidate's data rather than creating a disconnected workspace.
- For a disposable test store, set `AIXO_WALL_HOME` to a new empty directory **before launching**. Never point it at your IXO/VELA/Thought Spine project stores.
- The SQLite store uses WAL, foreign keys, full synchronous durability, serialised writes, hash-chained event records and graph/replay checks. Startup refuses a damaged store instead of rewriting it.
- Automatic local candidate scoring is **word-overlap matching** (not model inference, truth verification or autonomous research).
- Branches are bounded: maximum five children per node, depth four and 10,000 total marbles. Scanners have finite retries with dead-letter state.
- Windows Forms calls `bridge.py` via a private JSON payload, with a whitelist of allowed operations. There is no arbitrary shell or code execution by the bridge.
- Data remains local. No web requests, installs, Python package downloads, Hermes integration, VELA changes or automatic spending.
- A full LLM/polymathic engine and native Thought Spine link are **not** in this release.

## Release status

- **Core tests (Linux Python 3.13):** 28/28 pass, including new subprocess, Unicode/multiline, hostile-action and Windows-file-handle regression tests.
- **Windows-specific GUI:** Source packaged and statically inspected; not executable in Linux testing environment. **PENDING HOST ACCEPTANCE**.
- **Windows Python 3.14 tests:** PENDING ACTUAL HOST RUN.
- **Release gate:** G0 host acceptance remains **OPEN**, not certified.

The old Tkinter interface is deliberately not included in RC1's default release. RC0 is preserved separately, without changing its source archive.
