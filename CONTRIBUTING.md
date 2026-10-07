# Need for CONTRIBUTING

- Issue Inheritance 
- Reviewing an Merging PRs 
- Labeling of Issues 
- Automation & Multi Branch Dev facilitation  
- Reference to Code Style 
- Explanation of how to use toolchain 
- Onboarding 
- Creating Issues: Problem Descr. and DoD
- Base for evaluating if PR is accatable quality and style. 




Target Audiance: 
- FML Dev (ELGA)
- OpenSource Contributers (FHIRTypes?)
- Consumers?

After reading this guide, you will know:

- How to use GitHub to report issues.
- How to clone main and run the tool chain.
- How to help resolve existing issues.
- How to contribute to the Repository documentation.
- How to contribute to the mapping.


# 1. Reporting an Issue 

CDA2FHIR uses [Github Issue Tracking](https://github.com/HL7Austria/CDA2FHIR/issues). Primarily new content and features. 

See our [maintenance policy](maintenance and release management) for information on which versions are supported.

## 1.1 Creating an Issue 

If you want to contribute to new content, features or found a problem search the [Issues](https://github.com/HL7Austria/CDA2FHIR/issues) on GitHub, in case it has already been reported. If you cannot find any open GitHub issues addressing the problem you found, your next step will be to open a [new issue](issue template).


We've provided an issue template for you so that when creating an issue you include all the information needed to determine in what way and dimension it will contribute to this project.

Each issue needs to include a title and clear description of the problem. Make sure to include as much relevant information as possible including lincs to specifications, requirements, code sample or failing test that demonstrates the behaviour.  Your goal should be to make it easy for yourself - and others - to contribute to the issue.

# 2. Running the toolchain 

See [README](README.md) for now


# 3. Helping to Resolve Existing Issues

## Testing FML code 

We currently have two git actoins. convert_and_validate.yml must pass. Snapshot_diff should be reviewed if output is as expected. For Issues which deal with qa&tooling, governance there is currently now established Resolving process. 








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



# Additions

- Add constraint to add no special chars in issue title/ branch name. "The head ref may contain hidden characters: "530-add-mapping-for-\u00FCberweisungsgrund-codiert"" this degrades searchability of branches/issues


