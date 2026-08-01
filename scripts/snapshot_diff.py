"""Snapshot diff test to catch mapping regressions (issue #423).

Given two compiled MaLaC-HD engines -- one built from the PR branch's maps and one
from the PR's target ``*-dev`` branch -- this converts each branch's sample CDA
documents with its *matching* engine, normalises away the non-deterministic bits
(freshly generated resource UUIDs and ``Bundle.timestamp``) and renders a ``git diff``
of the two FHIR bundles, grouped by document type.

The base engine reads the base (``*-dev``) branch's ``input/`` fixtures and the PR
engine reads the PR branch's, so the diff reflects everything the PR changes: map
edits *and* changes to the sample CDA themselves. A fixture edited on both sides shows
the resulting FHIR delta; one present on only a single side renders as a whole-bundle
addition (new sample) or removal -- so a mapping regression and an input change are
both visible, and reviewable, in the same report.

Readability vs. completeness
----------------------------
The whole point is to catch *unintended* changes, so nothing may be silently dropped.
The report is therefore built in two layers:

* a **complete inventory** (every file + its ``+adds/-dels`` magnitude) that is always
  visible -- the safety net, so no change can hide;
* the actual per-file diffs inside collapsible ``<details>`` sections. Every changed
  file is always expandable. When the change is small (few files, few lines) the diffs
  are expanded by default; on a large change they collapse by default so the reader
  scans the inventory and opens only what they want.

Two artefacts are emitted:

* ``--report``  -- the *full* report (every diff), for the Actions run Summary and the
  uploaded artifact, where size is not a hard constraint.
* ``--comment`` -- the same report for the PR comment. GitHub caps a comment at 65 536
  chars; if the full report would exceed that, the comment degrades to the (small,
  complete) inventory plus a pointer to the Summary/artifact -- it never drops an
  individual file's diff in favour of a non-expandable stub.

Differences are *not* treated as errors: the script exits non-zero only on a hard
failure (e.g. an engine that cannot be run at all).
"""

import argparse
import glob
import json
import os
import re
import subprocess
import sys

# Human-readable heading per input directory. Anything not listed falls back to a
# title-cased directory name, so new document types still render sensibly.
GROUP_HEADINGS = {
    "lab": "Lab",
    "eimpf": "eVac",
    "emed": "eMed",
}

# GitHub rejects issue/PR comment bodies over 65 536 chars; stay just under.
COMMENT_LIMIT = 65000

_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_ZERO_UUID = "00000000-0000-0000-0000-000000000000"
_TIMESTAMP_RE = re.compile(r'("timestamp"\s*:\s*")[^"]*(")')


def normalize(text):
    """Strip the run-to-run noise so identical mappings produce identical text.

    1. Every resource UUID -- ``Bundle.id``/resource ``id`` (bare) and the
       ``urn:uuid:`` values in ``fullUrl``/``reference`` -- is a fresh v4 UUID on
       each run, so collapse them all to a single placeholder. In this pipeline the
       UUID pattern only ever occurs on those engine-generated fields (input-derived
       ids are OIDs / plain strings), so this does not clobber meaningful data.
    2. ``Bundle.timestamp`` is set to the wall-clock time of the run; blank it.
    """
    text = _UUID_RE.sub(_ZERO_UUID, text)
    text = _TIMESTAMP_RE.sub(r"\1\2", text)
    return text


def heading_for(directory):
    return GROUP_HEADINGS.get(directory, directory.replace("_", " ").title())


def display_name(name):
    """Drop the ``.xml`` extension shared by every fixture (pure visual noise)."""
    return name[:-4] if name.endswith(".xml") else name


def run_engine(engine, source, target):
    """Run a compiled engine to transform ``source`` -> ``target`` (FHIR JSON).

    Returns ``(ok, message)``. A conversion failure is reported per file rather than
    aborting the whole run, so one broken sample doesn't hide the rest of the diff.
    """
    proc = subprocess.run(
        [sys.executable, engine, "-s", source, "-t", target],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if proc.returncode != 0 or not os.path.exists(target):
        tail = "\n".join(proc.stdout.strip().splitlines()[-15:])
        return False, tail
    return True, ""


def write_normalized(src_json, dst_json):
    with open(src_json, "r", encoding="utf-8") as fh:
        text = fh.read()
    os.makedirs(os.path.dirname(dst_json), exist_ok=True)
    with open(dst_json, "w", encoding="utf-8") as fh:
        fh.write(normalize(text))


def write_empty(dst_json):
    """Materialize an empty normalized file for a fixture that exists on only one
    branch, so the absent side diffs as a clean whole-bundle add (new sample) or
    remove."""
    os.makedirs(os.path.dirname(dst_json), exist_ok=True)
    with open(dst_json, "w", encoding="utf-8") as fh:
        fh.write("")


def xml_fixtures(directory_path):
    """``basename -> full path`` for every ``*.xml`` fixture in a dir (empty if the
    directory is absent, e.g. a document type that exists on only one branch)."""
    if not os.path.isdir(directory_path):
        return {}
    return {os.path.basename(p): p
            for p in glob.glob(os.path.join(directory_path, "*.xml"))}


def git_diff(base_path, pr_path, work_root, context):
    """Diff two normalized files; return ``(adds, dels, body)``.

    ``--no-index`` diffs two files outside a repo; it exits 1 when they differ, which
    is expected and not an error. The noisy git header lines (``diff --git``/``index``/
    ``---``/``+++``) are dropped -- the file name is already the section title -- so
    only the hunks remain. ``adds``/``dels`` count changed lines for the inventory.
    """
    rel_base = os.path.relpath(base_path, work_root)
    rel_pr = os.path.relpath(pr_path, work_root)
    proc = subprocess.run(
        ["git", "diff", "--no-index", "--no-color",
         f"--unified={context}", "--", rel_base, rel_pr],
        cwd=work_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if not proc.stdout.strip():
        return 0, 0, ""
    adds = dels = 0
    body = []
    for line in proc.stdout.splitlines():
        if (line.startswith("diff --git ") or line.startswith("index ")
                or line.startswith("--- ") or line.startswith("+++ ")):
            continue
        if line.startswith("+"):
            adds += 1
        elif line.startswith("-"):
            dels += 1
        body.append(line)
    return adds, dels, "\n".join(body)


def build(args):
    """Convert + normalize + diff every fixture; return the list of per-group results.

    Each engine converts *its own branch's* fixtures: the base engine reads
    ``--base-input-dir`` and the PR engine ``--pr-input-dir``. Per directory we take the
    union of the two file sets, so a fixture present on both sides diffs its two
    outputs, while one present on only a single side renders as a whole-bundle add
    (``kind="added"``) or remove (``kind="removed"``) -- the absent side is an empty
    normalized file.
    """
    with open(args.config, "r", encoding="utf-8") as fh:
        config = json.load(fh)

    groups = []  # (heading, [result dict])
    for entry in config:
        directory = entry["directory"]
        base_files = xml_fixtures(os.path.join(args.base_input_dir, directory))
        pr_files = xml_fixtures(os.path.join(args.pr_input_dir, directory))
        names = sorted(set(base_files) | set(pr_files))
        if not names:
            continue

        results = []
        for name in names:
            stem = os.path.splitext(name)[0]
            base_src = base_files.get(name)
            pr_src = pr_files.get(name)
            kind = "both" if base_src and pr_src else "added" if pr_src else "removed"

            base_raw = os.path.join(args.work, "_raw", "base", directory, stem + ".json")
            pr_raw = os.path.join(args.work, "_raw", "pr", directory, stem + ".json")
            base_norm = os.path.join(args.work, "base", directory, stem + ".json")
            pr_norm = os.path.join(args.work, "pr", directory, stem + ".json")

            # Run each present side's engine into a normalized file; a side with no
            # fixture normalizes to empty so the diff is a clean add/remove.
            errors = []
            if base_src:
                os.makedirs(os.path.dirname(base_raw), exist_ok=True)
                ok, msg = run_engine(args.base_engine, base_src, base_raw)
                write_normalized(base_raw, base_norm) if ok else errors.append(
                    f"base engine failed:\n{msg}")
            else:
                write_empty(base_norm)
            if pr_src:
                os.makedirs(os.path.dirname(pr_raw), exist_ok=True)
                ok, msg = run_engine(args.pr_engine, pr_src, pr_raw)
                write_normalized(pr_raw, pr_norm) if ok else errors.append(
                    f"PR engine failed:\n{msg}")
            else:
                write_empty(pr_norm)

            r = {"file": name, "kind": kind, "adds": 0, "dels": 0,
                 "diff": "", "error": ""}
            if errors:
                r["status"] = "error"
                r["error"] = "\n\n".join(errors)
                results.append(r)
                continue

            adds, dels, diff = git_diff(base_norm, pr_norm, args.work, args.context)
            if diff:
                r.update(status="changed", adds=adds, dels=dels, diff=diff)
            else:
                r["status"] = "same"
            results.append(r)

        groups.append((heading_for(directory), results))
    return groups


# --------------------------------------------------------------------------- render

def _badge(r):
    return f"+{r['adds']} / -{r['dels']}"


def _change_cell(r):
    """Compact inventory-cell descriptor of a file's change."""
    if r["status"] == "error":
        return "❌ error"
    if r["status"] != "changed":
        return "✅ —"
    if r["kind"] == "added":
        return f"🆕 new (+{r['adds']})"
    if r["kind"] == "removed":
        return f"🗑️ removed (-{r['dels']})"
    return f"⚠️ {_badge(r)}"


def _changed_summary(r, name):
    """``<summary>`` text for a changed file, distinguishing add / remove / edit."""
    if r["kind"] == "added":
        return f"🆕 <code>{name}</code> — new sample, +{r['adds']}"
    if r["kind"] == "removed":
        return f"🗑️ <code>{name}</code> — removed sample, -{r['dels']}"
    return f"⚠️ <code>{name}</code> — {_badge(r)}"


def is_big_change(groups, max_files, max_lines):
    """A change is 'big' when many files changed OR the total diff is large.

    Small changes auto-expand (you see them without clicking); big ones collapse by
    default so the reader isn't buried and drills in from the inventory instead.
    """
    changed = [r for _, rs in groups for r in rs if r["status"] == "changed"]
    total = sum(r["adds"] + r["dels"] for r in changed)
    return len(changed) > max_files or total > max_lines


def inventory_table(groups):
    """A compact, complete listing of every file -- the 'nothing can hide' safety net.

    Sample names are rendered small (``<sub>``) and without the shared ``.xml`` so the
    table stays narrow enough to read at a glance.
    """
    rows = ["| Group | Sample | Change |", "|---|---|---|"]
    for heading, results in groups:
        for r in results:
            rows.append(
                f"| {heading} | <sub>{display_name(r['file'])}</sub> "
                f"| {_change_cell(r)} |")
    return "\n".join(rows)


def file_block(r, open_default):
    """Render one file as a collapsible <details> section (diff always included)."""
    name = display_name(r["file"])
    if r["status"] == "same":
        return (f"<details>\n<summary>✅ <code>{name}</code> — no changes</summary>\n"
                f"</details>")
    if r["status"] == "error":
        return (f"<details open>\n<summary>❌ <code>{name}</code> — conversion error"
                f"</summary>\n\n```\n{r['error']}\n```\n\n</details>")
    open_attr = " open" if open_default else ""
    return (f"<details{open_attr}>\n<summary>{_changed_summary(r, name)}"
            f"</summary>\n\n```diff\n{r['diff']}\n```\n\n</details>")


def group_section(heading, results, big_change, expand_under):
    changed = sum(1 for r in results if r["status"] != "same")
    label = f"<b>{heading}</b> — {changed} of {len(results)} changed"
    blocks = []
    for r in results:
        open_default = (
            r["status"] == "changed"
            and not big_change
            and (r["adds"] + r["dels"]) <= expand_under
        )
        blocks.append(file_block(r, open_default))
    inner = "\n\n".join(blocks)
    return f"<details open>\n<summary>{label}</summary>\n\n{inner}\n\n</details>"


def header(groups, args):
    total = sum(len(r) for _, r in groups)
    changed = sum(1 for _, rs in groups for r in rs if r["status"] != "same")
    lines = ["# Diffreport", ""]
    if args.base_label:
        lines.append(
            f"Snapshot of the FHIR output for PR "
            f"(`{args.base_label}` → `{args.pr_label}`)")
        lines.append("")
    if changed == 0:
        lines.append(f"✅ **No differences** across {total} sample(s).")
    else:
        lines.append(f"⚠️ **{changed} of {total}** samples changed.")
    return "\n".join(lines)


def assemble(groups, args):
    big = is_big_change(groups, args.expand_max_files, args.expand_max_lines)
    parts = [header(groups, args), "", inventory_table(groups), ""]
    for heading, results in groups:
        parts.append(group_section(heading, results, big, args.expand_under))
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def render_comment(body, groups, args, limit):
    """Size-guarded PR comment.

    If the full report fits, use it as-is (every file expandable). Otherwise fall back
    to the complete inventory plus a pointer -- never a per-file non-expandable stub.
    """
    if len(body) <= limit:
        return body
    summary_ref = (f"[**run Summary**]({args.summary_url})" if args.summary_url
                   else "run **Summary**")
    parts = [
        header(groups, args), "", inventory_table(groups), "",
        f"> ℹ️ Diffs exceed GitHub's comment size limit. Change sample listed above. Open {summary_ref} or the **snapshot-diff** artifact for all Diffs.",
    ]
    return "\n".join(parts).rstrip() + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-engine", required=True,
                        help="compiled engine (.py) built from the base branch maps")
    parser.add_argument("--pr-engine", required=True,
                        help="compiled engine (.py) built from the PR branch maps")
    parser.add_argument("--input-dir", default="input",
                        help="fallback fixture dir used for whichever side is not given "
                             "explicitly (see --base-input-dir / --pr-input-dir)")
    parser.add_argument("--base-input-dir", default="",
                        help="per-type CDA fixture folders the BASE engine converts "
                             "(defaults to --input-dir)")
    parser.add_argument("--pr-input-dir", default="",
                        help="per-type CDA fixture folders the PR engine converts "
                             "(defaults to --input-dir)")
    parser.add_argument("--config", default="input/config.json")
    parser.add_argument("--work", default="snapshots",
                        help="working dir for raw + normalized outputs")
    parser.add_argument("--report", default="report.md",
                        help="full report (every diff) for the run Summary / artifact")
    parser.add_argument("--comment", default="",
                        help="optional size-guarded copy for the PR comment")
    parser.add_argument("--base-label", default=os.environ.get("BASE_LABEL", ""))
    parser.add_argument("--pr-label", default=os.environ.get("PR_LABEL", ""))
    parser.add_argument("--summary-url",
                        default=os.environ.get("SNAPSHOT_SUMMARY_URL", ""),
                        help="deep link to this run's Summary, used in the comment's "
                             "size-limit fallback note")
    parser.add_argument("--context", type=int, default=3,
                        help="lines of context per diff hunk (git --unified)")
    parser.add_argument("--expand-under", type=int, default=30,
                        help="auto-expand a file when its changed-line count is at "
                             "most this (and the overall change is not big)")
    parser.add_argument("--expand-max-files", type=int, default=4,
                        help="above this many changed files, collapse everything")
    parser.add_argument("--expand-max-lines", type=int, default=80,
                        help="above this many total changed lines, collapse everything")
    parser.add_argument("--comment-limit", type=int, default=COMMENT_LIMIT)
    parser.add_argument("--summary", action="store_true",
                        help="also append the full report to $GITHUB_STEP_SUMMARY")
    args = parser.parse_args()
    # Each side falls back to the shared --input-dir, preserving the old single-input
    # behaviour for local runs that pass only --input-dir.
    args.base_input_dir = args.base_input_dir or args.input_dir
    args.pr_input_dir = args.pr_input_dir or args.input_dir

    groups = build(args)

    full = assemble(groups, args)
    with open(args.report, "w", encoding="utf-8") as fh:
        fh.write(full)
    print(f"Wrote {args.report} ({len(full)} bytes)")

    if args.comment:
        comment = render_comment(full, groups, args, args.comment_limit)
        with open(args.comment, "w", encoding="utf-8") as fh:
            fh.write(comment)
        print(f"Wrote {args.comment} ({len(comment)} bytes)")

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if args.summary and summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(full)

    return 0


if __name__ == "__main__":
    sys.exit(main())
