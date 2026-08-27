# CDA2FHIR

Transformation of ELGA CDA documents (Laboratory Report, e-Vac) to FHIR R4, written in the FHIR Mapping Language (FML).

The FML maps in `maps/` describe the rules for transforming CDA to FHIR. [MaLaC-HD](https://gitlab.com/cdehealth/malac-hd) compiles them into a standalone Python module, `python-maps/CdaToFhirBundle.4.py`, which converts a CDA XML document into a FHIR `Bundle`. That Python file is generated and committed by CI.

## Repository layout

| Path | Content |
| --- | --- |
| `maps/` | The mapping. `CdaToFhirBundle.4.map` is the entry map and dispatches on `ClinicalDocument/code` to `CdaLabToFhirBundle.4.map` or `CdaEimpfToFhirBundle.4.map`; `CdaToFhirTypes.4.map` holds the shared CDA→FHIR datatype transformations. |
| `input/` | CDA samples per document type, the IG each type is validated against (`config.json`) and the validator suppressions (`advisor.json`). |
| `python-maps/` | The compiled mapping (generated based on the respective `*-main`-branch), the pinned MaLaC-HD version (`requirements.txt`) and the release version (`pyproject.toml`). |
| `scripts/` | CI helpers: convert & validate, coverage, ELGA release. |

## Branches

| Branch | Target |
| --- | --- |
| `elga-main`, `elga-dev` | national ELGA / HL7 Austria |
| `myhealtheu-main`, `myhealtheu-dev` | cross-border MyHealth@EU / eHDSI |

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
- [ELGA Labor- & Mikrobiologiebefund v2 & v3](https://wiki.hl7.at/index.php/ILF:Labor-_und_Mikrobiologiebefund_Guide) - IG for the Laboratory and Microbiology Report
    - [v2 templates in ART-DECOR](https://art-decor.org/ad/#/elga-/rules/templates/1.2.40.0.34.11.4/2023-05-08T13:51:02)
    - [v3 templates in ART-DECOR](https://art-decor.org/ad/#/at-lab-/rules/templates/1.2.40.0.34.6.0.11.0.11/2020-08-25T14:35:13)
- [e-Impfpass](https://wiki.hl7.at/index.php/ILF:E-Impfpass_Guide) - IG for the electronic immunization record (e-Vac)
    - [templates in ART-DECOR](https://art-decor.org/ad/#/elgaimpf-/rules/templates/1.2.40.0.34.6.0.11.0.4/2026-02-04T15:09:45)

**Target (FHIR)**
- [MyHealth@EU Laboratory Report](https://fhir.ehdsi.eu/laboratory/index.html) - The MyHealth@EU Laboratory Result Report which the generated Bundles conform to 

## CI

| Workflow | Trigger | Purpose |
| --- | --- | --- |
| `convert-and-validate.yml` | pull request | compiles the maps, converts every sample in `input/`, validates each output with the HL7 FHIR validator, uploads output/validation/coverage, and fails the check on validation errors |
| `fml2python.yml` | push to the stable branch | recompiles the maps and commits `python-maps/CdaToFhirBundle.4.py` |
| `release.yml` | manual (`workflow_dispatch`) | takes the version from `python-maps/pyproject.toml` as the tag, creates the GitHub release with generated notes, and opens a merge request in the ELGA GitLab (MalacService) with the compiled Python, `pyproject.toml` and `requirements.txt` |

Releasing: bump the version in `python-maps/pyproject.toml`, then run `release.yml` on the stable branch with the ELGA Jira ticket number (and optionally the previous release tag, which sets where the generated notes start).

## Authors

See the list of [contributors](https://github.com/HL7Austria/CDA2FHIR/contributors) who participated in this project.

## Acknowledgments

- [HL7CH - Implementation Guide CDA FHIR Maps](https://github.com/hl7ch/cda-fhir-maps)
- BlackTusk - Initial Draft mapping Austrian CDA Laboratory Report to FHIR
