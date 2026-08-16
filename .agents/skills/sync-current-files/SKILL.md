---
name: sync-current-files
description: Synchronize docs/requirements/current.md, docs/specs/current.md, and docs/screen_specs/current.md with the latest versioned files. Use when adding or promoting requirements_v*.md, api_spec_v*.md, or screen_spec_v*.md files and the current pointers or current-version lines must be refreshed.
---

# Sync Current Files

Use the repo script for the mechanical sync, then review the human-authored summary sections.

## Workflow

1. Inspect the latest versioned files under `docs/requirements/`, `docs/specs/`, and `docs/screen_specs/`.
2. Run `python scripts/sync_current_files.py --write`.
3. Re-open each `current.md` and confirm the pointer line and current-version bullet match the latest file.
4. Preserve the summary, history, and operational guidance unless the version change makes them stale.
5. Run `python scripts/sync_current_files.py --check` before finishing.

## Repo-Specific Rules

- Treat `current.md` as a pointer and short synopsis, not the canonical full spec.
- Keep old versioned files in place; never delete them as part of synchronization.
- If a new version materially changes behavior, also update `docs/changelog.md`.

## When Manual Edits Are Still Required

- The sync script only updates mechanical pointer fields.
- If the latest version introduces new scope or operating rules, update the synopsis and version history lines by hand.
- If filenames stop matching `*_vX.Y.md`, fix the naming instead of hardcoding exceptions into the script.
