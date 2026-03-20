# CDA2FHIR

A stand-alone python module for converting CDA documents to FHIR.

Currently the following CDA documents are supported:
- [e-Impfpass](https://wiki.hl7.at/index.php/ILF:E-Impfpass_Guide) (status: immunizations and immunization recommendations)
- [Labor- und Mikrobiologiebefund](https://wiki.hl7.at/index.php/ILF:Labor-_und_Mikrobiologiebefund_Guide) (status: work in progress)

## Getting Started

### Prerequisites

- Python > 3.15
  - install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

### Transformation

```
python CdaToFhirBundle.4.py [-h] -s SOURCE -t TARGET

This has been compiled by the MApping LAnguage compiler for Health Data, short MaLaC-HD. See arguments for more details.

options:
  -h, --help           show this help message and exit
  -s, --source SOURCE  the source file path
  -t, --target TARGET  the target file path the result will be written to
```
#### FHIR XML or FHIR JSON

Depending on the `TARGET`'s fileending either FHIR XML (`.xml`) or FHIR JSON (`.json`) will be returned.