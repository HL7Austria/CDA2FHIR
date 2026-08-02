"""Keep GitHub sub-issues in sync with ``TODO #<n>`` code comments (issue #418).

Motivation
----------
TODOs in the code are narrative only -- nothing tracks them or stops a branch merging
with work still open. This turns every ``TODO #<n>`` comment into a real, linked
sub-issue so nothing gets lost and open work is visible per parent issue at a glance.

Comment format (any comment leader works -- ``//``, ``#``, ``<!-- -->``, ``/* */``)::

    // TODO #236: short description of what is left to do

Two sub-commands
----------------
``sync``  (run on *push*)
    Diff the push (``--base..--head``), then for every ``TODO #<n>`` on an **added**
    line create a sub-issue under #``<n>`` -- linked via GitHub's native sub-issue API
    and pointing at the file+line; for every one on a **removed** line, comment on and
    close its sub-issue. A TODO that merely moves (removed *and* re-added in the same
    push) is a no-op; a TODO that reappears after removal reopens its closed sub-issue.

``gate``  (run on *pull_request*)
    The merge guard. Fails while any ``TODO #<n>`` for the PR branch's issue still
    remains in the tracked code, so a PR cannot merge with its TODOs unfinished. Make
    it a required status check in branch protection to actually block the merge button.

De-duplication
--------------
Sub-issues are keyed by a *fingerprint* of ``(parent, file, normalized description)``
stored as an HTML marker (``<!-- todo-fp: … -->``) in the sub-issue body. Re-pushes,
rebases and force-pushes therefore reconcile against the parent's existing sub-issues
instead of creating duplicates. Line numbers are deliberately **excluded** from the
fingerprint because they shift on every edit above the TODO; editing the description
text, however, is treated as closing the old TODO and opening a new one.

GitHub access is via the ``gh`` CLI (``gh api``), matching the other workflows in this
repo; ``--dry-run`` prints intended actions without touching the API.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import namedtuple

# git's canonical empty-tree object -- diffing against it renders a whole branch as
# additions, the fallback when a push has no usable "before" (e.g. a new branch).
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

MARKER_PREFIX = "todo-fp:"
LABEL = "todo"

Todo = namedtuple("Todo", "parent description file line")

# ``TODO #236: text``. Case-insensitive on the keyword; the ``#<n>:`` shape keeps prose
# ("todo: fix later") out. ``.search`` lets any comment leader / indentation precede it.
TODO_RE = re.compile(r"TODO\s*#(\d+)\s*:\s*(.+)$", re.IGNORECASE)
# Trailing block-comment closers to strip off the captured description.
_CLOSERS_RE = re.compile(r"\s*(?:\*/|-->)\s*$")
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
_MARKER_RE = re.compile(r"<!--\s*todo-fp:\s*([0-9a-f]+)\s*-->")


# --------------------------------------------------------------------------- parsing

def _strip_prefix(path):
    return path[2:] if path.startswith(("a/", "b/")) else path


def _match_todo(cur_file, lineno, text):
    """Return a ``Todo`` if ``text`` carries a TODO comment, else ``None``."""
    if cur_file is None:
        return None
    m = TODO_RE.search(text)
    if not m:
        return None
    desc = _CLOSERS_RE.sub("", m.group(2)).strip()
    if not desc:
        return None
    return Todo(parent=int(m.group(1)), description=desc, file=cur_file, line=lineno)


def parse_diff(diff_text):
    """Return ``(added, removed)`` lists of ``Todo`` from unified ``git diff`` text.

    Added TODOs carry their new-file line number (tracked from each ``@@`` hunk header
    and the running count of ``+``/context lines); removed TODOs carry ``line=None``.
    """
    added, removed = [], []
    cur_file = None
    new_lineno = 0
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            path = line[4:].split("\t", 1)[0]
            cur_file = None if path == "/dev/null" else _strip_prefix(path)
            continue
        if line.startswith(("--- ", "diff ", "index ", "old mode", "new mode",
                            "similarity ", "rename ", "copy ", "deleted ", "new file")):
            continue
        m = _HUNK_RE.match(line)
        if m:
            new_lineno = int(m.group(1))
            continue
        if not line:
            new_lineno += 1
            continue
        tag, text = line[0], line[1:]
        if tag == "+":
            todo = _match_todo(cur_file, new_lineno, text)
            if todo:
                added.append(todo)
            new_lineno += 1
        elif tag == "-":
            todo = _match_todo(cur_file, None, text)
            if todo:
                removed.append(todo)
        elif tag == "\\":  # "\ No newline at end of file"
            continue
        else:  # context line (leading space)
            new_lineno += 1
    return added, removed


def fingerprint(parent, file, description):
    """Stable id for a TODO, independent of its line number (which shifts)."""
    norm = re.sub(r"\s+", " ", description.strip().lower())
    key = f"{parent}\x00{file}\x00{norm}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def reconcile(added, removed):
    """Collapse each side to ``{fingerprint: Todo}`` and cancel out pure moves.

    A fingerprint seen on both sides means the TODO only moved lines, so it is dropped
    from both -- no issue churn for a rebase or a shifted line.
    """
    add_map = {fingerprint(t.parent, t.file, t.description): t for t in added}
    del_map = {fingerprint(t.parent, t.file, t.description): t for t in removed}
    for fp in add_map.keys() & del_map.keys():
        add_map.pop(fp)
        del_map.pop(fp)
    return add_map, del_map


def marker_of(body):
    m = _MARKER_RE.search(body or "")
    return m.group(1) if m else None


# ------------------------------------------------------------------------ gh client

class GhError(RuntimeError):
    pass


def gh_api(path, method="GET", body=None, paginate=False, check=True):
    """Call ``gh api``; return parsed JSON (or ``None``). ``check=False`` swallows
    failures and returns ``None`` so best-effort calls don't abort the run."""
    cmd = ["gh", "api", "-H", "Accept: application/vnd.github+json"]
    if method != "GET":
        cmd += ["-X", method]
    cmd.append(path)
    if paginate:
        cmd.append("--paginate")
    stdin = None
    if body is not None:
        cmd += ["--input", "-"]
        stdin = json.dumps(body)
    proc = subprocess.run(cmd, input=stdin, capture_output=True, text=True)
    if proc.returncode != 0:
        if check:
            raise GhError(proc.stderr.strip() or f"gh api {method} {path} failed")
        return None
    out = proc.stdout.strip()
    return json.loads(out) if out else None


def list_subissues(repo, parent):
    """Existing sub-issues of ``parent``; ``[]`` if none or if the API is unavailable
    (a warning is printed in the latter case so missing dedup is visible)."""
    data = gh_api(f"repos/{repo}/issues/{parent}/sub_issues", paginate=True, check=False)
    if data is None:
        print(f"::warning::could not list sub-issues of #{parent} "
              f"(dedup may be incomplete)")
        return []
    return data


def ensure_label(repo, name):
    if gh_api(f"repos/{repo}/labels/{name}", check=False):
        return True
    created = gh_api(f"repos/{repo}/labels", method="POST", check=False,
                     body={"name": name, "color": "d4c5f9",
                           "description": "Auto-tracked TODO from a code comment"})
    return created is not None


# --------------------------------------------------------------------------- render

def make_title(todo):
    return f"TODO: {todo.description}"[:240]


def subissue_body(repo, todo, fp, head_sha):
    loc = f"`{todo.file}`" + (f":{todo.line}" if todo.line else "")
    link = ""
    if head_sha and todo.line:
        link = f"\n{_web(repo)}/blob/{head_sha}/{todo.file}#L{todo.line}"
    asof = f" (as of `{head_sha[:7]}`)" if head_sha else ""
    return (
        f"Auto-generated from a `TODO #{todo.parent}` comment.\n\n"
        f"**Parent:** #{todo.parent}\n"
        f"**Location:** {loc}{asof}{link}\n\n"
        f"> {todo.description}\n\n"
        f"<sub>Tracked automatically by the TODO → sub-issue action. "
        f"Delete the `TODO #{todo.parent}` line to close this issue.</sub>\n\n"
        f"<!-- {MARKER_PREFIX} {fp} -->\n"
    )


def _web(repo):
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    return f"{server}/{repo}"


# ------------------------------------------------------------------------- sync cmd

def read_diff(args):
    if args.diff_file:
        with open(args.diff_file, encoding="utf-8") as fh:
            return fh.read()
    head = args.head or "HEAD"
    base = args.base
    if not base or set(base) <= {"0"}:  # empty or all-zero "before" (new branch)
        base = args.fallback_base or EMPTY_TREE
    diff = _git_diff(base, head)
    if diff is None and base != EMPTY_TREE:  # base not present locally -> whole branch
        diff = _git_diff(EMPTY_TREE, head)
    if diff is None:
        raise GhError(f"git diff failed for base={base!r} head={head!r}")
    return diff


def _git_diff(base, head):
    proc = subprocess.run(
        ["git", "diff", "--no-color", "--unified=0", base, head],
        capture_output=True, text=True)
    return proc.stdout if proc.returncode == 0 else None


def cmd_sync(args):
    if not args.repo:
        raise GhError("--repo (or $GITHUB_REPOSITORY) is required")
    added, removed = parse_diff(read_diff(args))
    add_map, del_map = reconcile(added, removed)
    if not add_map and not del_map:
        print("No TODO changes in this push.")
        return 0

    parents = {t.parent for t in list(add_map.values()) + list(del_map.values())}
    existing = {}  # (parent, fp) -> sub-issue dict
    for p in parents:
        for si in list_subissues(args.repo, p):
            fp = marker_of(si.get("body"))
            if fp:
                existing[(p, fp)] = si

    label_ok = args.dry_run or ensure_label(args.repo, LABEL)
    created = reopened = closed = skipped = 0

    for fp, t in sorted(add_map.items(), key=lambda kv: (kv[1].parent, kv[1].file)):
        si = existing.get((t.parent, fp))
        if si and si.get("state") == "open":
            print(f"· already tracked by #{si['number']} — {t.file}")
            skipped += 1
        elif si and si.get("state") == "closed":
            num = si["number"]
            if args.dry_run:
                print(f"↻ would reopen #{num} (TODO re-added) — {t.file}")
            else:
                gh_api(f"repos/{args.repo}/issues/{num}", method="PATCH",
                       body={"state": "open"})
                gh_api(f"repos/{args.repo}/issues/{num}/comments", method="POST",
                       body={"body": f"↻ `TODO #{t.parent}` re-added in "
                                     f"`{_short(args.head)}` ({_loc(t)}). Reopening."})
                print(f"↻ reopened #{num} — {t.file}")
            reopened += 1
        else:
            title = make_title(t)
            if args.dry_run:
                print(f"+ would create sub-issue under #{t.parent}: {title}")
                created += 1
                continue
            issue = gh_api(f"repos/{args.repo}/issues", method="POST",
                           body={"title": title,
                                 "body": subissue_body(args.repo, t, fp, args.head),
                                 **({"labels": [LABEL]} if label_ok else {})})
            num, iid = issue["number"], issue["id"]
            linked = gh_api(f"repos/{args.repo}/issues/{t.parent}/sub_issues",
                            method="POST", body={"sub_issue_id": iid}, check=False)
            note = "" if linked is not None else "  (native link failed; body references parent)"
            print(f"+ created #{num} under #{t.parent}{note} — {_loc(t)}")
            created += 1

    for fp, t in sorted(del_map.items(), key=lambda kv: (kv[1].parent, kv[1].file)):
        si = existing.get((t.parent, fp))
        if not si:
            print(f"· removed TODO not tracked, nothing to close — {t.file}")
            continue
        if si.get("state") != "open":
            continue
        num = si["number"]
        if args.dry_run:
            print(f"- would close #{num} (TODO removed) — {t.file}")
        else:
            gh_api(f"repos/{args.repo}/issues/{num}/comments", method="POST",
                   body={"body": f"✅ `TODO #{t.parent}` removed in "
                                 f"`{_short(args.head)}` (was in `{t.file}`). "
                                 f"Closing automatically."})
            gh_api(f"repos/{args.repo}/issues/{num}", method="PATCH",
                   body={"state": "closed", "state_reason": "completed"})
            print(f"- closed #{num} — {t.file}")
        closed += 1

    print(f"\nSummary: created {created}, reopened {reopened}, closed {closed}, "
          f"skipped {skipped}.")
    return 0


def _short(sha):
    return (sha or "")[:7]


def _loc(todo):
    return f"`{todo.file}`" + (f":{todo.line}" if todo.line else "")


# ------------------------------------------------------------------------- gate cmd

def cmd_gate(args):
    num = args.issue
    if not num and args.branch:
        m = re.match(r"(\d+)", args.branch)
        num = int(m.group(1)) if m else None
    if num:
        pattern = rf"TODO[[:space:]]*#{num}[[:space:]]*:"
        scope = f"#{num}"
    else:
        # No issue number in the branch name -> guard against *any* open TODO.
        pattern = r"TODO[[:space:]]*#[0-9]+[[:space:]]*:"
        scope = "any issue"

    # Scan tracked files, excluding the action's own files (which contain the pattern
    # in examples / the regex itself).
    proc = subprocess.run(
        ["git", "grep", "-nIE", pattern, "--",
         ":(exclude)scripts/todo_subissues.py",
         ":(exclude).github/workflows/todo-*.yml"],
        capture_output=True, text=True)
    if proc.returncode == 1:  # git grep: no matches
        print(f"✅ No unfinished TODOs for {scope}.")
        return 0
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        return 2
    print(f"❌ Unfinished TODOs for {scope} — resolve or remove the comment(s) "
          f"before merging:\n")
    print(proc.stdout)
    return 1


# ------------------------------------------------------------------------------ cli

def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("sync", help="create/close sub-issues from a push diff")
    s.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""),
                   help="owner/name (default $GITHUB_REPOSITORY)")
    s.add_argument("--base", default="", help="diff base SHA (push 'before')")
    s.add_argument("--head", default="", help="diff head SHA (push 'after')")
    s.add_argument("--fallback-base", default="",
                   help="base to use when --base is empty/all-zero (else the empty tree)")
    s.add_argument("--diff-file", default="",
                   help="read the unified diff from a file instead of running git (tests)")
    s.add_argument("--dry-run", action="store_true",
                   help="print intended actions without calling the API")
    s.set_defaults(func=cmd_sync)

    g = sub.add_parser("gate", help="fail if TODOs for the PR branch's issue remain")
    g.add_argument("--issue", type=int, help="parent issue number to guard")
    g.add_argument("--branch", default=os.environ.get("GITHUB_HEAD_REF", ""),
                   help="PR head branch (issue number parsed from its <No>- prefix)")
    g.set_defaults(func=cmd_gate)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except GhError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2


if __name__ == "__main__":
    sys.exit(main())
