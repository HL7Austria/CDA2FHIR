# CDA2FHIR

> [IMPORTANT]
> **You are on the `elga` branch**
>
> This repository is mirrored across three branch families; the FML-maps, the CDA-samples and this README differ per variant.
> Other variants: [`myhealtheu`](https://github.com/HL7Austria/CDA2FHIR/tree/myhealtheu-main) · [`hl7eu`](https://github.com/HL7Austria/CDA2FHIR/tree/hl7eu-dev)

Transformation of ELGA CDA documents (Laboratory Report, e-Vac) to FHIR R4, written in the FHIR Mapping Language (FML).

The FML maps in `maps/` describe the rules for transforming CDA to FHIR. [MaLaC-HD](https://gitlab.com/cdehealth/malac-hd) compiles them into a standalone Python module, `python-maps/CdaToFhirBundle.4.py`, which converts a CDA XML document into a FHIR document `Bundle`. That Python file is generated and committed by CI.

## Repository layout

| Path | Content |
| --- | --- |
| `maps/` | The mapping. `CdaToFhirBundle.4.map` is the entry map and dispatches on `ClinicalDocument/code` to `CdaLabToFhirBundle.4.map` or `CdaEimpfToFhirBundle.4.map`; `CdaToFhirTypes.4.map` holds the shared CDA2FHIR datatype transformations. |
| `input/` | CDA samples per document type, the FHIR IG each resulting FHIR document `Bundle` is validated against (`config.json`) and the validator suppressions (`advisor.json`). |
| `python-maps/` | The compiled mapping (generated based on the respective `*-main`-branch), the pinned MaLaC-HD version (`requirements.txt`) and the release version (`pyproject.toml`). |
| `scripts/` | CI helpers: convert & validate, coverage, ELGA release. |

## Branches

| Branch | Target | |
| --- | --- | --- |
| `elga-main`, `elga-dev` | [national ELGA / HL7 Austria](https://github.com/HL7Austria/CDA2FHIR/tree/elga-main) | **you are here** |
| `myhealtheu-main`, `myhealtheu-dev` | [cross-border MyHealth@EU / eHDSI](https://github.com/HL7Austria/CDA2FHIR/tree/myhealtheu-main) | |
| `hl7eu-dev` | [HL7EU](https://github.com/HL7Austria/CDA2FHIR/tree/hl7eu-dev) | |

Branch off the matching `-dev` branch, edit the FML, and open the pull request against it.

## Running the mapping locally

```bash
pip install -r python-maps/requirements.txt

# 1. compile the FML to Python
malac-hd -m maps/CdaToFhirBundle.4.map -co python-maps/CdaToFhirBundle.4.py

# 2. transform a CDA sample — the target extension selects the serialization
python python-maps/CdaToFhirBundle.4.py -s input/lab/eImpf-Kompletter_Immunisierungsstatus.xml -t out.fhir.json
```

## Specifications

The mappings are defined against the following Austrian ELGA and HL7 specifications.

**Source (CDA)**
- [ELGA Labor- & Mikrobiologiebefund v2 & v3](https://wiki.hl7.at/index.php/ILF:Labor-_und_Mikrobiologiebefund_Guide) - IG for the laboratory and microbiology report
    - [v2 templates in ART-DECOR](https://art-decor.org/ad/#/elga-/rules/templates/1.2.40.0.34.11.4)
    - [v3 templates in ART-DECOR](https://art-decor.org/ad/#/at-lab-/rules/templates/1.2.40.0.34.6.0.11.0.11)
- [e-Impfpass](https://wiki.hl7.at/index.php/ILF:E-Impfpass_Guide) - IG for the electronic immunization record (e-vac)
    - [templates in ART-DECOR](https://art-decor.org/ad/#/elgaimpf-/rules/templates/1.2.40.0.34.6.0.11.0.4)

**Target (FHIR)**
- [Austrian Patient Summary](https://fhir.hl7.at/r4-ELGA-AustrianPatientSummary-main/index.html) - The FHIR IG which the generated Bundles conform to

> Scope per branch
> 
> - On the `elga` branches the Laboratory Result Report (LRR) mapping is a **draft**: their focus is the e-vac to APS mapping. 
> - The `myhealtheu` branches focus on the CDA Laboratory Report to MyHealth@EU LRR mapping.
> - The `hl7eu` branches focus on mapping to the HL7 EU IGs. 
> - The e-vac and laboratory maps are kept in sync where possible, but producing e-vac data in the MyHealth@EU format or laboratory results in the APS is currently out of scope.

## CI

| Workflow | Trigger | Purpose |
| --- | --- | --- |
| `convert-and-validate.yml` | pull request | compiles the maps, converts every sample in `input/`, validates each output with the HL7 FHIR validator, provides output/validation/coverage as artifacts, and fails if there are validation errors |
| `fml2python.yml` | push to the stable branch | recompiles the maps and commits `python-maps/CdaToFhirBundle.4.py` |
| `release.yml` | GitHub release published | opens a merge request in the ELGA GitLab with the compiled Python, `requirements.txt`, the documentation and the CDA samples |

## Authors

See the list of [contributors](https://github.com/HL7Austria/CDA2FHIR/contributors) who participated in this project.

## Acknowledgments

- [HL7CH - Implementation Guide CDA FHIR Maps](https://github.com/hl7ch/cda-fhir-maps)
- BlackTusk - Initial Draft mapping Austrian CDA Laboratory Report to FHIR
