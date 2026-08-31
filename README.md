# CDA2FHIR

> [!IMPORTANT]
> **You are on the `myhealtheu` branch**
>
> This repository is mirrored across three branch families; the FML maps, the CDA samples and this README differ per branch.
> Other branches: [`elga`](https://github.com/HL7Austria/CDA2FHIR/tree/elga-main) · [`hl7eu`](https://github.com/HL7Austria/CDA2FHIR/tree/hl7eu-dev)

Transformation of ELGA CDA documents (CDA Laboratory Report, e-Vacination (e-Vac)) to FHIR R4, written in the FHIR Mapping Language (FML).

The FML maps in `maps/` describe the rules for transforming CDA to FHIR. [MaLaC-HD](https://gitlab.com/cdehealth/malac-hd) compiles them into a standalone Python module, `python-maps/CdaToFhirBundle.4.py`, which converts a CDA XML document into a FHIR document `Bundle`. That Python file is generated and committed by CI.

## Repository layout

| Path | Content |
| --- | --- |
| `maps/` | The mapping. `CdaToFhirBundle.4.map` is the entry map and dispatches on `ClinicalDocument/code` to `CdaLabToFhirBundle.4.map` or `CdaEimpfToFhirBundle.4.map`; `CdaToFhirTypes.4.map` holds the shared CDA2FHIR datatype transformations. |
| `input/` | CDA samples per document type, the FHIR IG each resulting FHIR document `Bundle` is validated against (`config.json`) and the validator suppressions (`advisor.json`). |
| `python-maps/` | The compiled mapping (generated based on the respective `*-main`-branch), the pinned MaLaC-HD version (`requirements.txt`) and the release version (`pyproject.toml`). |
| `scripts/` | CI helpers: convert & validate, coverage, ELGA release. |

## Branches

| Branch | Ecosystem | Focus | |
| --- | --- | --- | --- |
| `elga-main`, `elga-dev` | [national ELGA / HL7 Austria](https://github.com/HL7Austria/CDA2FHIR/tree/elga-main) | `e-Vac to Austrian Patient Summary (APS)` | |
| `myhealtheu-main`, `myhealtheu-dev` | [cross-border MyHealth@EU / eHDSI](https://github.com/HL7Austria/CDA2FHIR/tree/myhealtheu-main) | `CDA Laboratory Report to Laboratory Result Report (LRR)` | **you are here** |
| `hl7eu-dev` | [HL7EU](https://github.com/HL7Austria/CDA2FHIR/tree/hl7eu-dev) | mapping to the HL7 EU IGs | |

Branch off the matching `-dev` branch, edit the FML, and open the pull request against it.

## Running the mapping locally

```bash
pip install -r python-maps/requirements.txt

# 1. compile the FML to Python
malac-hd -m maps/CdaToFhirBundle.4.map -co python-maps/CdaToFhirBundle.4.py

# 2. transform a CDA sample — the target extension selects the serialization
python python-maps/CdaToFhirBundle.4.py -s input/lab/ELGA-043-Laborbefund_EIS-FullSupport.xml -t out.fhir.json
```

## Specifications

The mappings are defined against the following Austrian ELGA and HL7 specifications.

**Source (CDA)**
- **CDA Laboratory Report** - [ELGA Labor- & Mikrobiologiebefund v2 & v3](https://wiki.hl7.at/index.php/ILF:Labor-_und_Mikrobiologiebefund_Guide), the IG for the laboratory and microbiology report
    - [v2 templates in ART-DECOR](https://art-decor.org/ad/#/elga-/rules/templates/1.2.40.0.34.11.4)
    - [v3 templates in ART-DECOR](https://art-decor.org/ad/#/at-lab-/rules/templates/1.2.40.0.34.6.0.11.0.11)
- **e-Vac** — [ELGA e-Impfpass](https://wiki.hl7.at/index.php/ILF:E-Impfpass_Guide), the IG for the electronic immunization record
    - [templates in ART-DECOR](https://art-decor.org/ad/#/elgaimpf-/rules/templates/1.2.40.0.34.6.0.11.0.4)

**Target (FHIR)**
- **LRR** — [MyHealth@EU Laboratory Result Report](https://fhir.ehdsi.eu/laboratory/index.html), the FHIR IG the generated document `Bundle` conforms to

> [!NOTE]
> **Scope of this branch**
>
> The focus here is `CDA Laboratory Report to LRR`; the `e-Vac to APS` mapping is a **draft** on this branch and maintained on the `elga` branches.
> The e-Vac and laboratory maps are kept in sync where possible, but producing e-Vac data as an LRR — or laboratory results as an APS — is out of scope.

## CI

| Workflow | Trigger | Purpose |
| --- | --- | --- |
| `convert-and-validate.yml` | pull request | compiles the maps, converts every sample in `input/`, validates each output with the HL7 FHIR validator, provides output/validation/coverage as artifacts, and fails if there are validation errors |
| `fml2python.yml` | push to the stable branch | recompiles the maps and commits `python-maps/CdaToFhirBundle.4.py` |
| `release.yml` | manual (`workflow_dispatch`) | takes the version from `python-maps/pyproject.toml` as the tag, creates the GitHub release with generated notes, and opens a merge request in the ELGA GitLab (MalacService) with the compiled Python, `pyproject.toml` and `requirements.txt` |

Releasing: bump the version in `python-maps/pyproject.toml`, then run `release.yml` on the `myhealtheu-main` branch with the ELGA Jira ticket number (and optionally the previous release tag, which sets where the generated notes start).

You can invoke the following request in order to start the pipeline:

```curl
curl -X POST \
  -H "Authorization: Bearer <YOUR_GITHUB_TOKEN>" \
  -H "Accept: application/vnd.github+json" \
  -H "Content-Type: application/json" \
  https://api.github.com/repos/HL7Austria/CDA2FHIR/actions/workflows/release.yml/dispatches \
  -d '{
    "ref": "262-propagate-release-to-elga-gitlab",
    "inputs": {
      "elga_jira_ticket_nr": "<ELGA_TICKET_NR>",
      "previous_release_tag": "<PREVIOUS_RELEASE_TAG>"
    }
  }'
```

## Authors

See the list of [contributors](https://github.com/HL7Austria/CDA2FHIR/contributors) who participated in this project.

## Acknowledgments

- [HL7CH - Implementation Guide CDA FHIR Maps](https://github.com/hl7ch/cda-fhir-maps)
- BlackTusk - initial draft mapping of the Austrian CDA Laboratory Report to FHIR
