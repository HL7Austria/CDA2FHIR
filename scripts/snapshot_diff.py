"""Snapshot diff test to catch mapping regressions (issue #423).

Given two compiled MaLaC-HD engines -- one built from the PR branch's maps and one
from the PR's target ``*-dev`` branch -- this converts every sample CDA document in
``input/`` with *both* engines, normalises away the non-deterministic bits (freshly
generated resource UUIDs and ``Bundle.timestamp``) and renders a ``git diff`` of the
two FHIR bundles, grouped by document type.

Because the input fixtures are held constant, any diff is attributable to the change
in the maps -- i.e. a mapping regression (or an intended mapping change to review).

Typical use (from CI, see .github/workflows/snapshot-diff.yml)::

    python scripts/snapshot_diff.py \
        --base-engine engines/base.py --pr-engine engines/pr.py \
        --input-dir input --config input/config.json \
        --work snapshots --report report.md --summary

The report is written to ``--report`` and, when ``--summary`` is given and
``GITHUB_STEP_SUMMARY`` is set, also appended to the GitHub Actions run summary.
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


def git_diff(base_path, pr_path, work_root, max_lines):
    """Return the unified ``git diff`` between two normalized files, or "" if equal.

    ``--no-index`` diffs two files outside a repo; it exits 1 when they differ, which
    is expected and not an error. Paths are made relative to ``work_root`` so the
    diff header reads ``a/base/... b/pr/...``.
    """
    rel_base = os.path.relpath(base_path, work_root)
    rel_pr = os.path.relpath(pr_path, work_root)
    proc = subprocess.run(
        ["git", "diff", "--no-index", "--no-color", "--", rel_base, rel_pr],
        cwd=work_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    diff = proc.stdout
    if not diff.strip():
        return ""
    lines = diff.splitlines()
    if max_lines and len(lines) > max_lines:
        omitted = len(lines) - max_lines
        lines = lines[:max_lines] + [
            f"... diff truncated, {omitted} more line(s); see the uploaded artifact."
        ]
    return "\n".join(lines)


def build(args):
    with open(args.config, "r", encoding="utf-8") as fh:
        config = json.load(fh)

    groups = []  # (heading, [ {file, status, detail} ])
    total_changed = 0
    total_files = 0

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
            total_files += 1

            base_raw = os.path.join(args.work, "_raw", "base", directory, stem + ".json")
            pr_raw = os.path.join(args.work, "_raw", "pr", directory, stem + ".json")
            base_norm = os.path.join(args.work, "base", directory, stem + ".json")
            pr_norm = os.path.join(args.work, "pr", directory, stem + ".json")
            for p in (base_raw, pr_raw):
                os.makedirs(os.path.dirname(p), exist_ok=True)

            base_ok, base_msg = run_engine(args.base_engine, source, base_raw)
            pr_ok, pr_msg = run_engine(args.pr_engine, source, pr_raw)

            if not base_ok or not pr_ok:
                detail = []
                if not base_ok:
                    detail.append(f"base engine failed:\n{base_msg}")
                if not pr_ok:
                    detail.append(f"PR engine failed:\n{pr_msg}")
                results.append({"file": name, "status": "error",
                                "detail": "\n\n".join(detail)})
                total_changed += 1
                continue

            write_normalized(base_raw, base_norm)
            write_normalized(pr_raw, pr_norm)
            diff = git_diff(base_norm, pr_norm, args.work, args.max_lines_per_file)
            if diff:
                results.append({"file": name, "status": "changed", "detail": diff})
                total_changed += 1
            else:
                results.append({"file": name, "status": "same", "detail": ""})

        groups.append((heading_for(directory), results))

    return render(groups, total_changed, total_files, args)


def render(groups, total_changed, total_files, args):
    out = []
    out.append("# Diffreport")
    out.append("")
    subject = f"`{args.base_label}` → `{args.pr_label}`" if args.base_label else ""
    if subject:
        out.append(f"Snapshot of the FHIR output before/after this PR ({subject}), "
                   "with resource ids and `Bundle.timestamp` normalized away.")
    if total_changed == 0:
        out.append(f"\n✅ **No mapping changes** across {total_files} sample(s).")
    else:
        out.append(f"\n⚠️ **{total_changed} of {total_files} sample(s) "
                   "changed** — review the diffs below.")
    out.append("")

    for heading, results in groups:
        changed = sum(1 for r in results if r["status"] != "same")
        out.append(f"## {heading}")
        out.append("")
        for r in results:
            if r["status"] == "same":
                out.append(f"### {r['file']}")
                out.append("")
                out.append("✅ No changes.")
                out.append("")
            elif r["status"] == "error":
                out.append(f"### ❌ {r['file']}")
                out.append("")
                out.append("```")
                out.append(r["detail"])
                out.append("```")
                out.append("")
            else:
                out.append(f"### ⚠️ {r['file']}")
                out.append("")
                out.append("```diff")
                out.append(r["detail"])
                out.append("```")
                out.append("")
    return "\n".join(out).rstrip() + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-engine", required=True,
                        help="compiled engine (.py) built from the base branch maps")
    parser.add_argument("--pr-engine", required=True,
                        help="compiled engine (.py) built from the PR branch maps")
    parser.add_argument("--input-dir", default="input",
                        help="directory holding the per-type CDA fixture folders")
    parser.add_argument("--config", default="input/config.json")
    parser.add_argument("--work", default="snapshots",
                        help="working dir for raw + normalized outputs")
    parser.add_argument("--report", default="report.md")
    parser.add_argument("--base-label", default=os.environ.get("BASE_LABEL", ""))
    parser.add_argument("--pr-label", default=os.environ.get("PR_LABEL", ""))
    parser.add_argument("--max-lines-per-file", type=int, default=400,
                        help="cap per-file diff length (0 = unlimited)")
    parser.add_argument("--summary", action="store_true",
                        help="also append the report to $GITHUB_STEP_SUMMARY")
    args = parser.parse_args()

    report = build(args)

    with open(args.report, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(f"Wrote {args.report} ({len(report)} bytes)")

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if args.summary and summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
