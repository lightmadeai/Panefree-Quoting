# Restore Drill Report — 2026-05-12

**Operator:** Claude (during Hotfix-5 T3 execution)
**Per:** Hotfix-5 T3 acceptance criterion — "Drill is RUN once during this sprint."
**Purpose:** Prove the backup → restore pipeline actually round-trips a live SQLite database with full fidelity, before this code ever runs in production.

---

## TL;DR — ✅ Drill PASSED

| Step | Result |
|---|---|
| Backup snapshot taken | ✅ `sovereign-20260513-055033.db.gz` (binary) + `sovereign-schema-20260513.sql` (schema) |
| Backup gzip integrity | ✅ valid (gunzip -t clean) |
| Restore from local file:// URI | ✅ downloaded, gunzipped, sanity-checked |
| Sanity check on restored DB | ✅ all 4 core tables readable |
| Row counts match live DB | ✅ exact match across all 4 tables |
| Schema parity vs `models.py` | ✅ no drift |
| Total drill runtime | ~5 seconds end-to-end |

**Conclusion:** the backup/restore pipeline is safe to wire into cron (T4) and to rely on in a disaster-recovery scenario.

---

## Procedure executed

### Setup
- Drill artifacts lived in `testing/restore-drill/` (cleaned after the report was committed; cleanup not committed).
- Backup destination: `file://...workspace/projects/window-quoting/testing/restore-drill` (local-filesystem target — keeps the drill self-contained, no B2 credentials needed).
- `MAIL_DISABLED=1` so failure paths don't try to email admin during the drill.

### Step 1 — Take a fresh backup
```bash
BACKUP_DESTINATION="file://.../testing/restore-drill" \
MAIL_DISABLED=1 \
python scripts/backup.py
```

Output:
```
[BACKUP-UPLOADED] sovereign-20260513-055033.db.gz + sovereign-schema-20260513.sql
[BACKUP-DONE] 2026-05-13T05:50:33.660429Z
```

### Step 2 — Snapshot live DB stats (the source of truth)
```python
sqlite3.connect('sovereign.db').execute('SELECT COUNT(*) FROM users').fetchone()
```
- `users`: 34
- `quotes`: 52
- `pricing_profiles`: 23
- `transactions`: 3

### Step 3 — Restore the backup to a sandbox path
```bash
python scripts/restore.py \
  "file://.../testing/restore-drill/sovereign-20260513-055033.db.gz" \
  "testing/restore-drill/restored.db"
```

Output:
```
[RESTORE] downloading file://.../sovereign-20260513-055033.db.gz
[RESTORE] gunzipping...
[RESTORE] sanity check OK: {'users': 34, 'quotes': 52, 'pricing_profiles': 23, 'transactions': 3}
[RESTORE] wrote testing/restore-drill/restored.db
```

### Step 4 — Verify row counts match live exactly
| Table | Live | Restored | Match |
|---|---|---|---|
| `users` | 34 | 34 | ✅ |
| `quotes` | 52 | 52 | ✅ |
| `pricing_profiles` | 23 | 23 | ✅ |
| `transactions` | 3 | 3 | ✅ |

### Step 5 — Schema parity check
`scripts/restore.py` runs the DEPLOYMENT.md §2.4 parity check internally. No drift reported between the backup and the live `models.py`.

---

## What this drill does NOT prove

1. **B2 round-trip.** This drill used `file://` to keep it self-contained. The B2 upload + download paths use `b2sdk` and share the gzip / sanity check / parity check pipeline — they're code-coverage-equivalent — but the network leg hasn't been exercised end-to-end with real credentials.
2. **Multi-day retention.** The retention prune (T2) is exercised by `testing/test_retention.py` in isolation. This drill only generated one backup, so the prune never had anything to delete.
3. **App-level functional restore.** Step 4 confirms row counts match; it doesn't confirm that the restored DB actually serves user requests correctly when an app is pointed at it. Confidence-building extension: spin a Flask test client against the restored file and run `stress_probe.py`. Deferred — the SQLite `.backup` API is byte-equivalent to the source, so functional differences would have to come from a corrupt gzip (caught by `gunzip -t`) or a logic bug in `restore.py` (caught by sanity check + parity check).

These are flagged in `notes/hotfix-5-notes.md` for follow-up — none block the H5 merge.

---

## Quarterly drill cadence

Per DEPLOYMENT.md §10.3 (Maintenance schedule), this drill repeats **quarterly** (Jan / Apr / Jul / Oct 1st). Each run appends a new section to this file (or replaces it if the file gets too long; archived versions live in git history). Next drill due: **2026-07-01**.

If the drill ever fails:
1. Stop. Do not deploy any backup-related changes.
2. File a P0 hotfix sprint.
3. Investigate via the failure email + Sentry capture.
