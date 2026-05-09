"""
Hotfix-1 T3 — one-time legacy PDF migration.

Sprint 4 BUG-008 routed all NEW /generate output to <OUTPUT_DIR>/<user_id>/
so that /download can no longer be coaxed into serving sovereign.db, source
files, or another tenant's PDFs. Anything that lived at project_root/
before the fix is now unreachable through the app.

This script sweeps the project root for legacy `quote_*.pdf` and
`invoice_*.pdf` files and moves them to an out-of-the-way quarantine under
the new output tree. We deliberately do NOT attribute them to specific
users — the Quote table never recorded the rendered filename, so there is
no reliable mapping from filename hash back to user_id. Putting them under
a per-user bucket would silently cross-pollinate tenants. The quarantine
keeps them off the project root (where the BUG-008 download regression
surfaced) without claiming an ownership we don't actually know.

Behavior
--------
- Scans `project_root/` for files matching `quote_*.pdf`, `invoice_*.pdf`
  (and the bare `quote.pdf` / `invoice.pdf` test artifacts).
- Skips anything already inside the OUTPUT_DIR tree.
- Moves matches to `<OUTPUT_DIR>/_legacy_unattributed/` preserving the
  original basename. On filename collision (re-run, or two roots holding
  the same name) the existing file is kept and the source is left in place
  with a warning — the operator decides what to do.
- Idempotent: a second run finds nothing to move and exits cleanly.
- `--dry-run` prints what would happen without touching the filesystem.

Usage
-----
    python scripts/migrate-pdfs.py [--dry-run]

Exit codes
----------
    0  success (including "nothing to do")
    1  unrecoverable error (cannot create destination, etc.)

Run once at deploy time as part of the Sprint 4 -> ship cutover. Safe to
re-run; subsequent runs are no-ops.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from typing import Iterable

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import config  # noqa: E402  (after sys.path tweak)


QUARANTINE_DIRNAME = "_legacy_unattributed"


def _is_legacy_pdf(name: str) -> bool:
    """Match `quote*.pdf` / `invoice*.pdf` at the root level only.
    The bare `quote.pdf` and `invoice.pdf` test artifacts are included —
    `test_plumbing.py` historically wrote them there and they're equally
    unreachable through the post-BUG-008 download route."""
    if not name.lower().endswith(".pdf"):
        return False
    lower = name.lower()
    return lower.startswith("quote") or lower.startswith("invoice")


def _iter_legacy_pdfs(root: str) -> Iterable[str]:
    """Yield absolute paths of legacy PDFs at the project root.
    Does NOT recurse — we only sweep the root. Anything already inside
    `output/` (or any subdirectory) is left alone."""
    for entry in os.listdir(root):
        full = os.path.join(root, entry)
        if not os.path.isfile(full):
            continue
        if _is_legacy_pdf(entry):
            yield full


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report what would happen without moving any files.",
    )
    args = parser.parse_args()

    quarantine = os.path.join(config.OUTPUT_DIR, QUARANTINE_DIRNAME)
    if not args.dry_run:
        try:
            os.makedirs(quarantine, exist_ok=True)
        except OSError as e:
            print(f"ERROR: cannot create {quarantine}: {e}", file=sys.stderr)
            return 1

    moved = 0
    skipped_collision = 0
    candidates = list(_iter_legacy_pdfs(PROJECT_ROOT))

    if not candidates:
        print(f"No legacy PDFs found at {PROJECT_ROOT}. Nothing to do.")
        return 0

    print(f"Found {len(candidates)} legacy PDF(s) at project root.")
    print(f"Destination: {quarantine}")
    if args.dry_run:
        print("(dry run — no files will be moved)")

    for src in candidates:
        basename = os.path.basename(src)
        dest = os.path.join(quarantine, basename)
        if os.path.exists(dest):
            print(f"  SKIP  {basename} (already at destination)")
            skipped_collision += 1
            continue
        if args.dry_run:
            print(f"  MOVE  {basename}  ->  {dest}")
            moved += 1
            continue
        try:
            shutil.move(src, dest)
            print(f"  MOVED {basename}")
            moved += 1
        except OSError as e:
            print(f"  ERROR moving {basename}: {e}", file=sys.stderr)
            # Continue with the rest — partial migration is recoverable.

    print()
    print(f"Summary: {moved} moved, {skipped_collision} skipped (collision).")
    if args.dry_run:
        print("Re-run without --dry-run to apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
