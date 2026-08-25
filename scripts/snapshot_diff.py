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

Differences are *not* treated as errors -- a report full of diffs still exits 0. A
*conversion failure* is: if any sample could not be converted, the diff for it does not
exist, so the report is incomplete. The headline says so, names the side whose engine
failed, and the script exits ``EXIT_CONVERSION_FAILED`` (20) -- but only after the
report and comment have been written, so the workflow can still publish them and fail
the job afterwards. The code is distinct from a crash's 1 so the workflow can label the
two differently: a report that is merely large must never read as a conversion error.
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

# A job summary over 1 MiB is dropped by GitHub (and errors the step), so the summary
# is size-guarded exactly like the comment, with headroom under the cap.
SUMMARY_LIMIT = 900000

# Distinct exit code for "some samples could not be converted", so the workflow can
# tell that apart from this script crashing -- the two need different messages.
EXIT_CONVERSION_FAILED = 20

_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_ALIAS_TEMPLATE = "00000000-0000-0000-0000-%012d"
_TIMESTAMP_RE = re.compile(r'("timestamp"\s*:\s*")[^"]*(")')


def normalize(text):
    """Strip the run-to-run noise so identical mappings produce identical text.

    1. Every resource UUID -- ``Bundle.id``/resource ``id`` (bare) and the
       ``urn:uuid:`` values in ``fullUrl``/``reference`` -- is a fresh v4 UUID on
       each run, so each *distinct* one is replaced by a stable alias numbered in
       order of first appearance within the bundle. In this pipeline the UUID pattern
       only ever occurs on those engine-generated fields (input-derived ids are OIDs /
       plain strings), so this does not clobber meaningful data.

       Aliasing, rather than collapsing every UUID onto one shared placeholder, is
       what preserves the *reference graph* in the diff. With one placeholder a
       regression that re-points e.g. ``Composition.subject`` at the wrong resource
       reads identically on both sides and disappears from the report -- valid FHIR,
       wrong content, silently passed. The cost is that inserting or removing a
       resource renumbers the aliases after it and widens that file's diff, which is
       itself a change worth reading.
    2. ``Bundle.timestamp`` is set to the wall-clock time of the run; blank it.

    Returns ``(text, timestamps)``. The regex is deliberately unanchored -- it blanks
    *every* key named ``timestamp``, not just ``Bundle.timestamp`` -- so the count of
    substitutions is reported back and surfaced in the report. Today every bundle has
    exactly one; if a future mapping introduces a nested ``timestamp``, this makes the
    over-match visible instead of silently swallowing a real difference. The count
    comes from the same call that does the blanking, so it cannot drift from it.
    """
    seen = {}

    def alias(match):
        uuid_value = match.group(0)
        if uuid_value not in seen:
            seen[uuid_value] = _ALIAS_TEMPLATE % (len(seen) + 1)
        return seen[uuid_value]

    text = _UUID_RE.sub(alias, text)
    text, timestamps = _TIMESTAMP_RE.subn(r"\1\2", text)
    return text, timestamps


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
    """Normalize ``src_json`` into ``dst_json``; return its ``timestamp`` key count."""
    with open(src_json, "r", encoding="utf-8") as fh:
        text = fh.read()
    normalized, timestamps = normalize(text)
    os.makedirs(os.path.dirname(dst_json), exist_ok=True)
    with open(dst_json, "w", encoding="utf-8") as fh:
        fh.write(normalized)
    return timestamps


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
            failed = []  # which side(s) could not be converted: "base" and/or "pr"
            timestamps = 0  # most `timestamp` keys seen on either side of this file
            if base_src:
                os.makedirs(os.path.dirname(base_raw), exist_ok=True)
                ok, msg = run_engine(args.base_engine, base_src, base_raw)
                if ok:
                    timestamps = max(timestamps,
                                     write_normalized(base_raw, base_norm))
                else:
                    failed.append("base")
                    errors.append(f"base engine failed:\n{msg}")
            else:
                write_empty(base_norm)
            if pr_src:
                os.makedirs(os.path.dirname(pr_raw), exist_ok=True)
                ok, msg = run_engine(args.pr_engine, pr_src, pr_raw)
                if ok:
                    timestamps = max(timestamps,
                                     write_normalized(pr_raw, pr_norm))
                else:
                    failed.append("pr")
                    errors.append(f"PR engine failed:\n{msg}")
            else:
                write_empty(pr_norm)

            r = {"file": name, "kind": kind, "adds": 0, "dels": 0,
                 "diff": "", "error": "", "failed_sides": [],
                 "timestamps": timestamps}
            if errors:
                r["status"] = "error"
                r["error"] = "\n\n".join(errors)
                r["failed_sides"] = failed
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


def _sides_short(sides):
    """``base`` / ``PR`` / ``both`` -- compact, for the inventory cell."""
    if len(sides) > 1:
        return "both"
    return "PR" if sides == ["pr"] else "base"


def _sides_long(sides):
    """``the base engine`` / ``the PR engine`` / ``both engines`` -- for prose."""
    if len(sides) > 1:
        return "both engines"
    return "the PR engine" if sides == ["pr"] else "the base engine"


def tally(groups):
    """``(total, changed, errored)``, counting errors *separately* from changes.

    A sample whose conversion failed produced no diff at all, so folding it into the
    "changed" count would report a broken engine as if it were a mapping change --
    exactly the false alarm this report exists to avoid. It gets its own headline
    line, and its own exit code, instead.
    """
    results = [r for _, rs in groups for r in rs]
    changed = sum(1 for r in results if r["status"] == "changed")
    errored = sum(1 for r in results if r["status"] == "error")
    return len(results), changed, errored


def failed_sides(groups):
    """Sorted ``base``/``pr`` list of every side that failed anywhere in the run."""
    return sorted({s for _, rs in groups for r in rs for s in r["failed_sides"]})


def _change_cell(r):
    """Compact inventory-cell descriptor of a file's change."""
    if r["status"] == "error":
        return f"❌ {_sides_short(r['failed_sides'])} failed"
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
        side = _sides_long(r["failed_sides"])
        return (f"<details open>\n<summary>❌ <code>{name}</code> — not converted, "
                f"{side} failed</summary>\n\n```\n{r['error']}\n```\n\n</details>")
    open_attr = " open" if open_default else ""
    return (f"<details{open_attr}>\n<summary>{_changed_summary(r, name)}"
            f"</summary>\n\n```diff\n{r['diff']}\n```\n\n</details>")


def group_section(heading, results, big_change, expand_under):
    changed = sum(1 for r in results if r["status"] == "changed")
    errored = sum(1 for r in results if r["status"] == "error")
    label = f"<b>{heading}</b> — {changed} of {len(results) - errored} changed"
    if errored:
        label += f", {errored} failed"

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


def timestamp_caveat(groups):
    """Green/yellow line on the scope of the ``timestamp`` blanking.

    ``normalize()`` blanks every key named ``timestamp``, not only
    ``Bundle.timestamp``. That is fine while a bundle has exactly one -- and it does
    today -- but a future mapping adding a nested ``timestamp`` would have its changes
    silently normalised away. Rather than tighten the regex (a pattern that stops
    matching would leave ``Bundle.timestamp`` live and make *every* sample diff on
    every run), the count is simply reported, so the over-match can never go unnoticed.

    Returns "" when nothing was converted, so an all-failed run makes no claim.
    """
    counted = [r for _, rs in groups for r in rs if r["timestamps"]]
    if not counted:
        return ""
    multi = sorted(r["file"] for r in counted if r["timestamps"] > 1)
    if not multi:
        return ("🟢 `timestamp` normalisation: exactly one per bundle "
                "(`Bundle.timestamp`).")
    shown = ", ".join(f"`{display_name(n)}`" for n in multi[:5])
    more = f" (+{len(multi) - 5} more)" if len(multi) > 5 else ""
    return (f"🟡 `timestamp` normalisation: **{len(multi)} sample(s) contain more than "
            f"one `timestamp` field** ({shown}{more}). Every one is blanked, so a "
            f"change to a non-`Bundle.timestamp` value cannot appear in this diff.")


def header(groups, args):
    """Headline counts. Failed samples are excluded from the changed/total ratio and
    called out on their own line, so a broken engine can never read as a clean run
    *or* as a wall of mapping changes."""
    total, changed, errored = tally(groups)
    comparable = total - errored
    lines = ["# Diffreport", ""]
    if args.base_label:
        lines.append(
            f"Snapshot of the FHIR output for PR "
            f"(`{args.base_label}` → `{args.pr_label}`)")
        lines.append("")
    if comparable == 0:
        lines.append(
            f"❌ **No samples could be compared** — all {total} failed to convert.")
    elif changed == 0:
        lines.append(f"✅ **No differences** across {comparable} sample(s).")
    else:
        lines.append(f"⚠️ **{changed} of {comparable}** samples changed.")
    if errored:
        lines.append("")
        lines.append(
            f"❌ **{errored} of {total}** sample(s) failed to convert "
            f"({_sides_long(failed_sides(groups))}) — they are not part of the counts "
            f"above and this run is a failure, not a clean report.")
    caveat = timestamp_caveat(groups)
    if caveat:
        lines.append("")
        lines.append(caveat)
    return "\n".join(lines)


def assemble(groups, args):
    big = is_big_change(groups, args.expand_max_files, args.expand_max_lines)
    parts = [header(groups, args), "", inventory_table(groups), ""]
    for heading, results in groups:
        parts.append(group_section(heading, results, big, args.expand_under))
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def _oversize_note(args, target):
    """Pointer used when the full report does not fit ``target``'s size cap.

    Names the artifact first: it is the one copy that is never truncated. The run
    Summary has its own 1 MiB cap, so pointing a reader there as the primary
    destination can send them to a page that GitHub dropped.
    """
    if target == "summary":
        return ("> ℹ️ The full diffs exceed GitHub's 1 MiB job-summary limit, so only "
                "the inventory is shown here. Download the **snapshot-diff** artifact "
                "from this run and open `report.md` for every diff. Nothing failed — "
                "the report is simply too large to render.")
    run_ref = (f"[this workflow run]({args.summary_url})" if args.summary_url
               else "this workflow run")
    return ("> ℹ️ The full diffs exceed GitHub's comment size limit, so only the "
            f"inventory is shown here. Download the **snapshot-diff** artifact from "
            f"{run_ref} and open `report.md` for every diff. Nothing failed — the "
            "report is simply too large to post.")


def render_capped(body, groups, args, limit, target):
    """Size-guarded rendering of ``body`` for a destination with a hard cap.

    If the full report fits, use it as-is (every file expandable). Otherwise fall back
    to the complete inventory plus a pointer -- never a per-file non-expandable stub.
    Used for both the PR comment and the step summary, which differ only in cap and
    in where they send the reader.
    """
    if len(body) <= limit:
        return body
    parts = [header(groups, args), "", inventory_table(groups), "",
             _oversize_note(args, target)]
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
    parser.add_argument("--summary-limit", type=int, default=SUMMARY_LIMIT,
                        help="cap for the $GITHUB_STEP_SUMMARY copy; over GitHub's "
                             "1 MiB limit the summary is dropped and the step errors")
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
        comment = render_capped(full, groups, args, args.comment_limit, "comment")
        with open(args.comment, "w", encoding="utf-8") as fh:
            fh.write(comment)
        print(f"Wrote {args.comment} ({len(comment)} bytes)")

    # The summary goes through the same guard: over 1 MiB GitHub drops it *and* errors
    # the step, which would surface a merely-large diff as a job failure.
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if args.summary and summary_path:
        summary = render_capped(full, groups, args, args.summary_limit, "summary")
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(summary)
        print(f"Wrote step summary ({len(summary)} bytes)")

    # Diffs are not failures; an engine that could not convert a sample is. Reported
    # only here, so report/comment/summary are all on disk before the non-zero exit --
    # the workflow publishes them and fails the job afterwards.
    total, _, errored = tally(groups)
    if errored:
        print(f"ERROR: {errored} of {total} sample(s) failed to convert "
              f"({_sides_long(failed_sides(groups))}); the report is incomplete.",
              file=sys.stderr)
        return EXIT_CONVERSION_FAILED
    return 0


if __name__ == "__main__":
    sys.exit(main())
