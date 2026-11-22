# AIXO Collision Wall M0.1.1 RC1 — Engineering Contract

## Isolation and component ownership

This is an independently runnable Windows Forms desktop *candidate* using a Python SQLite backend; native host acceptance remains pending. Its dedicated SQLite file is the only mutable source of truth. `Hermes.xo` is not a dependency or memory owner. The separately named GitHub Hermes Agent is outside this package. Existing IXO, VELA, personal EUREKA, Thought Spine, Packbot, FrameShift, GREMLIN and other owner stores are untouched. JSON export is a review handoff only.

## Operations and semantics

- `PASS`: worker found no sufficiently close local lexical match.
- `COLLISION_SUGGESTED`: deterministic token-set Jaccard score >= 0.15, at least 2 overlapping non-stopwords, top 12 matches per processed marble, compare last 2,500 existing marbles. **Not semantic equivalence or verified truth**.
- `COLLIDE`: recorded, manually accepted relationship between marbles.
- `SLICE`: new descendant whose body must be an exact substring of the parent body.
- `MUTATE`: new descendant with changed body; prior source remains immutable.
- `MULTIPLY`: atomic creation of 1-5 user-authored child marbles.
- `RECONCILE`: directional graph relationship; does not silently merge source text or identities.
- `REVERSE TRACE`: traverse immutable parent identity and adjacent relationships.

## G0 invariants actually implemented

- SQLite with foreign keys, WAL journaling, synchronous FULL and a busy timeout; write transactions use `BEGIN IMMEDIATE`.
- Writes to marbles and event-log receipts are committed in the same transaction. Events are SHA-256 chained, with content hashes and a materialized-graph-to-event replay comparison for tamper detection.
- Explicit idempotency keys for CLI/import callers on add, slice, multiply, mutate. Reused keys with conflicting requests are rejected.
- Durable scan queue with claimed running jobs, leased recovery, bounded retries/backoff and terminal `dead` state (dead-letter equivalent). One scan per added marble.
- Quotas: maximum 10,000 marbles, 5 direct children and depth 4; 12 collision suggestions per job; text payload bounded to 12,000 characters.
- Automatic startup refuses existing database files that fail integrity verification. No automatic destructive repair.
- SQLite online backup via `Connection.backup()` to a temporary file; verify before atomic promotion. Restore only to an absent/new path.
- JSON export includes stable identities, sources, relationships and event records; explicit owner and NOT_IMPORTED status.
- Window can be closed and reopened with the same SQLite location. No unexpected use of system clipboard, network or external app state.

## Boundaries (not represented as complete)

- This is **a real functioning offline finite-scale vertical slice**; it is not a full polymathic reasoning model or LLM agent. Local collision finding uses lexical token Jaccard, not embeddings.
- State is stored transactionally with an append-only evidence log and replay checks; it is not a complete arbitrary-state rebuild tool from a bare event stream. Queue schedule cannot be restored solely from events.
- Event hashes are *integrity checks*, not signed attestations and not protection against a malicious actor who can rewrite both records and hashes.
- No automatic code execution, autonomous system modification, finance operations, cloud installation, native updater, running model server or prior project migration.
- No second independent process-level file lock for export or backup while adversarial writers are running. SQLite serializes database writes; deep-integrity checks are intended for a paused/quiescent workspace.
- Jobs in the `dead` state do not auto-replay. Inspect error and restore a verified backup or create a new job by adding a new marble after diagnosis.
- No guaranteed deterministic ordering of wall-clock timestamps or random UUIDs across runs; deterministic *content/link rules* plus IDs provide causal reconstruction.
- The default GUI is Windows Forms through Windows PowerShell 5.1 and does not import tkinter. The Python 3.14 system Tcl installation remains broken but is not required. No signed executable, installer or updater is being claimed.

## Host acceptance gates before promotion

1. Windows starts with one double-click; screenshot and Python version captured.
2. Add, slice, multiply, mutate, review and link all work on real GUI without unhandled exception.
3. Close, cold restart, reopen — data and event checks pass.
4. Capture a backup, restore to a new store, open new store, compare data and history.
5. Run tests and record 28/28 with actual Python executable and system build.
6. Fault test: CLI `fault-once` on an isolated work db schedules one retry; `scan` handles ready jobs after backoff; no duplicate descendants.
7. Optional: kill process mid-operation in a disposable workspace, reopen, verify or inspect/recover. Do not use personal-data stores for fault experiments.
8. Only after recorded evidence: decide whether any adapter to Thought Spine/IXO/VELA should be designed. No automatic promotion.

## RC1 repair delta

- Python `sqlite3.Connection` context managers commit/rollback, but do **not** close handles. Backup/source-check/restore helpers now explicitly close connections using `contextlib.closing`; Windows test tamper fixtures close as well.
- `bridge.py` implements only a fixed allowlist of AIXO standalone operations. Requests are base64-encoded UTF-8 JSON sent locally through a private subprocess pipe; untrusted input is never interpolated into shell commands.
- `WINDOWS_NATIVE.ps1` is the default Windows Forms GUI, started with Windows PowerShell 5.1 (`-STA`). A local 4.5-second timer checks pending jobs and processes bounded scans. No tkinter/Tcl dependency.
- New bridge/subprocess/backup/file-rename tests raise the test count from 23 to 28, all verified on Linux. Windows PowerShell 5.1 and Python 3.14 host acceptance remain required.
- RC0 existing standalone data path is deliberately preserved; existing stores are verified before any startup recovery writes.
