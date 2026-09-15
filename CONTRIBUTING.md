# Contributing to CDA2FHIR

See [README](README.md) for what the repo is.

## Two things to know first

- **No `main`.** Three branch families, one per target: `elga-*` (ELGA/APS), `myhealtheu-*` (MyHealth@EU/LRR), `hl7eu-dev`. Work lands on `*-dev`. One branch = one target.
- **The Python is generated.** Edit FML in `maps/`; CI compiles it with MaLaC-HD. **Never commit `python-maps/CdaToFhirBundle.4.py`.**

## Issues

- Every change starts as an issue. The issue number becomes the branch name.
- Label the target: `elga`, `myhealth@eu` or `multiple-target-format`. More labels for better categorization of Issues will follow. (See #538)
- **Dual-target change** = 3 issues: a parent with `multiple-target-format` label (never branched from) + one sub-issue per target, titled `[ELGA]-…` / `[MyHealthEu]-…`.
- Put the target prefix **in the issue title** with a separator (`]-`) — the "Create a branch" button derives the branch name from it.
- **New TODOs in code must be anchored to an Issue**: `// TODO #236: …`.

## Branches & PRs

- Branch name: `<issue#>-<target>-<slug>`, cut from your family's `*-dev`, PR back into it.
- Ruleset for development: PR required, **1 approval**, last push must be approved, **merge commits only**, no force push, required check `convert-and-validate`, no todos without linked issue number.
- Every commit on your branch survives into the target history.
- Open PRs as **drafts early**. (So you can use our QA-Git-Actions -> `convert-and-validate` and `snapshot-diff`) Imperative title (it becomes the merge commit). Body: why + link the issue.
- Push *before* requesting review; a new push dismisses approvals.

## CI

- `convert-and-validate` — **required check.** Converts + validates every sample in `input/` (XML and JSON). Failures listed in `validation/failed_bundles.txt`; download the `my-artifact` artifact for the HTML reports.
- `snapshot-diff` — review aid, not a gate. Posts a PR comment with the FHIR diff your change causes. Read it on every mapping PR; explain unexpected diffs.
- `fml2python` (push to `*-main`) and `release.yml` handle generated code and releases.

## Local run

```bash
pip install -r python-maps/requirements.txt
malac-hd -m maps/CdaToFhirBundle.4.map -co /tmp/CdaToFhirBundle.4.py     # scratch path, not the tracked file
python /tmp/CdaToFhirBundle.4.py -s input/eimpf/<sample>.xml -t out.fhir.json
python scripts/convert_and_validate.py && ./check_validation_result.sh   # needs Java + validator_cli.jar
```

## Working in the FML

- `CdaToFhirBundle.4.map` — entry map, CDA header, shared groups. `CdaToFhirTypes.4.map` — shared datatypes (changes here are dual-target). `CdaEimpfToFhirBundle.4.map` / `CdaLabToFhirBundle.4.map` — document-type specifics.
- Naming: groups `Cda<Source>To<Target>`; variables `cda_` / `fhir_` following the element path.
- On a high level Document what CDA ArtDecor templates get mapped into which FHIR Resources. (e.g. CDA ObservationMedia to FHIR Observatoin). 
- ConceptMaps: label `transcoding` and check #482 / #360 / #484 first. Inline ConceptMaps are being moved out. CM is a major WiP at the moment. 
- Samples go in `input/<doc-type>/`, named for what they exercise; they must all be valid CDA against their respective schema.
- `advisor.json` suppressions are a last resort. Narrowest scope, comment why, open a follow-up issue to remove once not necessary anymore.

## Definition of done

- [ ] Branch `<issue#>-<target>-<slug>` off the right `*-dev`
- [ ] `convert-and-validate` green
- [ ] `snapshot-diff` reviewed, every diff intended
- [ ] TODOs anchored to issues
- [ ] Dual-target: sibling sub-issue and PR exist. Or is documented as not done yet. 
- [ ] PR body links the issue

## After PR is merged

- [ ] Close all Issues which are resolved by PR, delete Branches -> Keep the repo clean.  

## License

None declared yet — see [#271](https://github.com/HL7Austria/CDA2FHIR/issues/271).
