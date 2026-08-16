---
name: update-docs
description: Update repository documentation after code, folder, workflow, policy, or automation changes. Use when files under src/, scripts/, .github/, AGENTS.md, or docs/ changed and README, source overview, folder structure, graph docs, or changelog must be kept in sync.
---

# Update Docs

Update only the docs touched by the change. Keep the rest stable.

## Workflow

1. Read `README.md`, `AGENTS.md`, `docs/context.md`, `docs/project_guide.md`, `docs/source_overview.md`, `docs/folder_structure.md`, `docs/src_call_graph.md`, and `docs/changelog.md`.
2. Map the code or workflow change to the minimal affected docs.
3. Update path references and commands so they match the repository layout exactly.
4. If versioned docs changed, run `python scripts/sync_current_files.py --write`.
5. If Mermaid sources changed, run `python scripts/render_docs_graphs.py` or at least `--check`.
6. Append an addendum to `docs/changelog.md` for durable process or structure changes.

## Repo-Specific Rules

- Keep the framing as a monitoring and judgment-support tool, not automated trading or hard investment advice.
- Prefer `scripts/` for canonical automation and describe `cli/` only as compatibility wrappers when both exist.
- When folder layout changes, update both `docs/folder_structure.md` and `docs/source_overview.md`.
- When commands change, update `README.md`, `scripts/README.md`, and any affected workflow files together.

## Do Not

- Do not rewrite human-authored summaries unless they are stale because of the current change.
- Do not promote a template example into project-specific truth without also updating the changelog.
- Do not leave `current.md` pointers stale after adding a new versioned doc.
