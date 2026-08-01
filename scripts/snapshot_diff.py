"""Snapshot diff test to catch mapping regressions (issue #423).

Given two compiled MaLaC-HD engines -- one built from the PR branch's maps and one
from the PR's target ``*-dev`` branch -- this converts every sample CDA document in
``input/`` with *both* engines, normalises away the non-deterministic bits (freshly
generated resource UUIDs and ``Bundle.timestamp``) and renders a ``git diff`` of the
two FHIR bundles, grouped by document type.

Because the input fixtures are held constant, any diff is attributable to the change
in the maps -- i.e. a mapping regression (or an intended mapping change to review).

Readability vs. completeness
----------------------------
The whole point is to catch *unintended* changes, so nothing may be silently dropped.
The report is therefore built in two layers:

* a **complete inventory** (every file + its ``+adds/-dels`` magnitude) that is always
  visible -- the safety net, so no change can hide;
* the actual per-file diffs inside collapsible ``<details>`` sections (groups collapse
  as a whole, small diffs auto-expand) so the reader scans the inventory and drills
  into only what they want instead of scrolling a wall of text.

Two artefacts are emitted:

* ``--report``  -- the *full* report (every diff, nothing stubbed), for the Actions run
  Summary and the uploaded artifact where size is not a hard constraint.
* ``--comment`` -- the same report, but size-guarded to GitHub's 65 536-char PR-comment
  limit: the inventory is always complete; if the diffs don't fit, the largest ones are
  replaced by a stub pointing at the run Summary / artifact so the comment still posts.

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

# GitHub rejects issue/PR comment bodies over 65 536 chars; stay comfortably under.
COMMENT_LIMIT = 60000

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
    """Convert + normalize + diff every fixture; return the list of per-group results."""
    with open(args.config, "r", encoding="utf-8") as fh:
        config = json.load(fh)

    groups = []  # (heading, [result dict])
    for entry in config:
        directory = entry["directory"]
        in_dir = os.path.join(args.input_dir, directory)
        if not os.path.isdir(in_dir):
            continue
        sources = sorted(glob.glob(os.path.join(in_dir, "*.xml")))
        if not sources:
            continue

        results = []
        for source in sources:
            name = os.path.basename(source)
            stem = os.path.splitext(name)[0]

            base_raw = os.path.join(args.work, "_raw", "base", directory, stem + ".json")
            pr_raw = os.path.join(args.work, "_raw", "pr", directory, stem + ".json")
            base_norm = os.path.join(args.work, "base", directory, stem + ".json")
            pr_norm = os.path.join(args.work, "pr", directory, stem + ".json")
            for p in (base_raw, pr_raw):
                os.makedirs(os.path.dirname(p), exist_ok=True)

            base_ok, base_msg = run_engine(args.base_engine, source, base_raw)
            pr_ok, pr_msg = run_engine(args.pr_engine, source, pr_raw)

            r = {"file": name, "adds": 0, "dels": 0, "diff": "", "error": ""}
            if not base_ok or not pr_ok:
                detail = []
                if not base_ok:
                    detail.append(f"base engine failed:\n{base_msg}")
                if not pr_ok:
                    detail.append(f"PR engine failed:\n{pr_msg}")
                r["status"] = "error"
                r["error"] = "\n\n".join(detail)
                results.append(r)
                continue

            write_normalized(base_raw, base_norm)
            write_normalized(pr_raw, pr_norm)
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


def inventory_table(groups):
    """A compact, complete listing of every file -- the 'nothing can hide' safety net."""
    rows = ["| Group | Sample | Change |", "|---|---|---|"]
    for heading, results in groups:
        for r in results:
            if r["status"] == "changed":
                change = f"⚠️ {_badge(r)}"
            elif r["status"] == "error":
                change = "❌ error"
            else:
                change = "✅ —"
            rows.append(f"| {heading} | {r['file']} | {change} |")
    return "\n".join(rows)


def file_block(r, expand_under, full=True):
    """Render one file as a collapsible <details> section."""
    name = r["file"]
    if r["status"] == "same":
        return (f"<details>\n<summary>✅ <code>{name}</code> — no changes</summary>\n"
                f"</details>")
    if r["status"] == "error":
        return (f"<details open>\n<summary>❌ <code>{name}</code> — conversion error"
                f"</summary>\n\n```\n{r['error']}\n```\n\n</details>")
    # changed
    if not full:
        return (f"<details>\n<summary>⚠️ <code>{name}</code> — {_badge(r)} "
                f"(diff too large; see run Summary / artifact)</summary>\n</details>")
    open_attr = " open" if (r["adds"] + r["dels"]) <= expand_under else ""
    return (f"<details{open_attr}>\n<summary>⚠️ <code>{name}</code> — {_badge(r)}"
            f"</summary>\n\n```diff\n{r['diff']}\n```\n\n</details>")


def group_section(heading, results, expand_under, stub_ids):
    changed = sum(1 for r in results if r["status"] != "same")
    label = f"<b>{heading}</b> — {changed} of {len(results)} changed"
    blocks = [file_block(r, expand_under, full=id(r) not in stub_ids) for r in results]
    inner = "\n\n".join(blocks)
    return f"<details open>\n<summary>{label}</summary>\n\n{inner}\n\n</details>"


def header(groups, args, spill=0):
    total = sum(len(r) for _, r in groups)
    changed = sum(1 for _, rs in groups for r in rs if r["status"] != "same")
    lines = ["# Diffreport", ""]
    if args.base_label:
        lines.append(
            f"Snapshot of the FHIR output before/after this PR "
            f"(`{args.base_label}` → `{args.pr_label}`), with resource ids and "
            f"`Bundle.timestamp` normalized away.")
        lines.append("")
    if changed == 0:
        lines.append(f"✅ **No mapping changes** across {total} sample(s).")
    else:
        lines.append(f"⚠️ **{changed} of {total} sample(s) changed** — every sample is "
                     "listed below; expand a section to see its diff.")
    if spill:
        lines.append("")
        lines.append(f"> ℹ️ {spill} large diff(s) exceeded GitHub's comment size limit "
                     "and are collapsed here — see the full diff in the run **Summary** "
                     "or the **snapshot-diff** artifact.")
    return "\n".join(lines)


def assemble(groups, args, stub_ids):
    parts = [header(groups, args, spill=len(stub_ids)), "", inventory_table(groups), ""]
    for heading, results in groups:
        parts.append(group_section(heading, results, args.expand_under, stub_ids))
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def render_full(groups, args):
    """The complete report -- nothing stubbed (for Summary + artifact)."""
    return assemble(groups, args, stub_ids=set())


def render_comment(groups, args, limit):
    """Size-guarded report for the PR comment.

    The inventory stays complete; if the body is over ``limit``, the largest diffs are
    progressively stubbed (replaced by a pointer to Summary/artifact) until it fits.
    """
    body = assemble(groups, args, stub_ids=set())
    if len(body) <= limit:
        return body
    changed = [r for _, rs in groups for r in rs if r["status"] == "changed"]
    changed.sort(key=lambda r: len(r["diff"]), reverse=True)
    stub_ids = set()
    for r in changed:
        stub_ids.add(id(r))
        body = assemble(groups, args, stub_ids)
        if len(body) <= limit:
            break
    return body


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-engine", required=True,
                        help="compiled engine (.py) built from the base branch maps")
    parser.add_argument("--pr-engine", required=True,
                        help="compiled engine (.py) built from the PR branch maps")
    parser.add_argument("--input-dir", default="input",
                        help="directory holding the per-type CDA fixture folders")
    parser.add_argument("--config", default="input/config.json")
    parser.add_argument("--work", default="snapshots",
                        help="working dir for raw + normalized outputs")
    parser.add_argument("--report", default="report.md",
                        help="full report (every diff) for the run Summary / artifact")
    parser.add_argument("--comment", default="",
                        help="optional size-guarded copy for the PR comment")
    parser.add_argument("--base-label", default=os.environ.get("BASE_LABEL", ""))
    parser.add_argument("--pr-label", default=os.environ.get("PR_LABEL", ""))
    parser.add_argument("--context", type=int, default=3,
                        help="lines of context per diff hunk (git --unified)")
    parser.add_argument("--expand-under", type=int, default=40,
                        help="auto-expand a file's <details> when its changed-line "
                             "count is at most this (0 = always collapsed)")
    parser.add_argument("--comment-limit", type=int, default=COMMENT_LIMIT)
    parser.add_argument("--summary", action="store_true",
                        help="also append the full report to $GITHUB_STEP_SUMMARY")
    args = parser.parse_args()

    groups = build(args)

    full = render_full(groups, args)
    with open(args.report, "w", encoding="utf-8") as fh:
        fh.write(full)
    print(f"Wrote {args.report} ({len(full)} bytes)")

    if args.comment:
        comment = render_comment(groups, args, args.comment_limit)
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
