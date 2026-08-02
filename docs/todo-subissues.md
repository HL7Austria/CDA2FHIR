# TODO → sub-issues

Two workflows turn `TODO` code comments into tracked GitHub sub-issues and block merging while any remain open. Both call `scripts/todo_subissues.py`.

## Writing a TODO

- Syntax: `TODO #<issue>: <description>`
  - `<issue>` — parent issue number (a plain number).
  - `<description>` — one line, required.
- Any comment leader works: `//`, `#`, `<!-- … -->`, `/* … */`.
- Case-insensitive on `TODO`; trailing `*/` and `-->` are stripped.
- **Not** recognized: no `#<number>:` (e.g. `TODO: fix later`, or prose).

Example (in a `.map` file): `// TODO #<issue>: map specimen nullFlavor`

## Which files are scanned

- **Every tracked text file in the repo — not just maps.** Binary files are skipped.
- `sync` sees only files changed in the push; `gate` greps the whole tree.
- Excluded from `gate`: `scripts/todo_subissues.py`, `.github/workflows/todo-*.yml`.

## `todo-subissues.yml` — sync (on push)

- Runs on push to feature branches (ignores `elga`, `myhealtheu`, `*-dev`).
- Diffs the pushed commits and reconciles sub-issues:
  - **added** `TODO #<n>` → creates a sub-issue under `#<n>` (native link), body links file + line, labeled `todo`.
  - **removed** → comments on and closes its sub-issue.
  - **moved** (removed + re-added in the same push) → no-op.
  - **re-added** after removal → reopens the closed sub-issue.
- Dedup: a fingerprint of `(parent, file, description)` is stored in the sub-issue body, so re-pushes / rebases never duplicate. Line number is **not** part of it; editing the description text = close old + open new.

## `todo-merge-gate.yml` — gate (on PR)

- Runs on every pull request.
- Parses `<No>` from the head branch `<No>-<slug>`.
- **Fails** if any `TODO #<No>:` remains in tracked code (branch with no number → guards against any TODO).
- Must be set as a **required status check** in branch protection to actually block the merge button.

## Script (`scripts/todo_subissues.py`)

- `sync` — parse push diff → reconcile → `gh api` create/link/close. `--dry-run` prints actions without writing.
- `gate` — `git grep` for the branch's TODOs → exit non-zero if any remain.
