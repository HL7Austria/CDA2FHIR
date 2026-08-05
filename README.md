# CDA2FHIR

Transformation of ELGA CDA documents (Laboratory Report, e-Vac) to FHIR R4, written in the FHIR Mapping Language (FML).

The FML maps in `maps/` are the source of truth. [MaLaC-HD](https://gitlab.com/cdehealth/malac-hd) compiles them into a standalone Python module, `python-maps/CdaToFhirBundle.4.py`, which converts a CDA XML document into a FHIR `Bundle`. That Python file is generated and committed by CI — do not edit it by hand.

## Repository layout

| Path | Content |
| --- | --- |
| `maps/` | The mapping. `CdaToFhirBundle.4.map` is the entry map and dispatches on `ClinicalDocument.code` to `CdaLabToFhirBundle.4.map` or `CdaEimpfToFhirBundle.4.map`; `CdaToFhirTypes.4.map` holds the shared CDA→FHIR datatype transforms. |
| `input/` | CDA samples per document type, the IG each type is validated against (`config.json`) and the validator suppressions (`advisor.json`). |
| `python-maps/` | The compiled mapping (generated) and the pinned MaLaC-HD version (`requirements.txt`). |
| `scripts/` | CI helpers: convert & validate, coverage, ELGA release. |

## Branches

| Branch | Target |
| --- | --- |
| `elga`, `elga-dev` | national ELGA / HL7 Austria |
| `myhealtheu`, `myhealtheu-dev` | cross-border MyHealth@EU / eHDSI |

Branch off the matching `-dev` branch, edit the FML, and open the pull request against it.

## Running the mapping locally

```bash
pip install -r python-maps/requirements.txt

# 1. compile the FML to Python
malac-hd -m maps/CdaToFhirBundle.4.map -co python-maps/CdaToFhirBundle.4.py

# 2. transform a CDA sample — the target extension selects the serialization
python python-maps/CdaToFhirBundle.4.py -s input/lab/ELGA-043-Laborbefund_EIS-FullSupport.xml -t out.fhir.json
```

## CI

| Workflow | Trigger | Purpose |
| --- | --- | --- |
| `convert-and-validate.yml` | pull request | compiles the maps, converts every sample in `input/`, validates each output with the HL7 FHIR validator, uploads output/validation/coverage, and fails the check on validation errors |
| `fml2python.yml` | push to the stable branch | recompiles the maps and commits `python-maps/CdaToFhirBundle.4.py` |
| `release.yml` | GitHub release published | opens a merge request in the ELGA GitLab with the compiled Python, `requirements.txt`, the documentation and the CDA samples |

## Authors

See the list of [contributors](https://github.com/HL7Austria/CDA2FHIR/contributors) who participated in this project.

## Acknowledgments

- [HL7CH - Implementation Guide CDA FHIR Maps](https://github.com/hl7ch/cda-fhir-maps)
- BlackTusk - Mapping Austrian CDA Laboratory Report to FHIR
