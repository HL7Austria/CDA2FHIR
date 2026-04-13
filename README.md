# CDA2FHIR

Transformation of the ELGA CDA Laboratory Report to FHIR using the FHIR Mapping Language.

## Getting Started

These instructions will get you a copy of the project up and running on your local machine for development and testing purposes.

### Prerequisites

The following software is required to be installed upfront:
- [Java JDK](https://adoptium.net/de/)
- [Apache Maven](https://maven.apache.org/)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [VS Code - REST Client](https://marketplace.visualstudio.com/items?itemName=humao.rest-client)

### Installing

Set up Matchbox locally:
- `git clone https://github.com/ahdis/matchbox`
- Checkout version `2.3.0` as with the current version the mapping fails.
  - `git checkout tags/v2.3.0`
- `mvn clean install -DskipTests`
- `docker build -t matchbox .`
- `cd with-postgres`
  - in `docker-compose.yml` change `postgres:current` to `postgres:14.5` (there occurs an error when creating the database with the current version)
- `mkdir data`
- `docker-compose up matchbox-db`
  - `Strg + C` as soon as database is set up
- `docker-compose up`
- access Matchbox at http://localhost:8080/matchbox/#/
  - Upload the [CDA Logical Model](https://github.com/HL7Austria/CDA-core-2.0/tree/cda-ext-elga) using http://localhost:8080/matchbox/#/igs

### Transformation

In order to execute a transformation execute the following REST calls from within `CdaToBundle.http`:
- 1.a. POST CdaToFhirTypes.map
- 1.b. POST CdaToBundle.map
- 2.a. POST Lab_Allgemeiner_Laborbefund.xml (CdaToBundle)

![FHIR Structure](fhir_structure.drawio.svg)

### Validation of resources

https://validator.fhir.org/

    java -jar validator_cli.jar hl7at/hl7at_CDA2FHIR/output/hl7eu_patient.json -version 4.0 -ig hl7eu_laboratory_package.tgz > hl7at/hl7at_CDA2FHIR/output/validation.log

    java -jar validator_cli.jar hl7at/hl7at_CDA2FHIR/output/hl7eu_bundle.json -version 4.0 -ig hl7eu_laboratory_package.tgz -ig hl7at_fhir_core_package.tgz > hl7at/hl7at_CDA2FHIR/output/validation.log

## Built With

* [Matchbox 2.3.0](https://github.com/ahdis/matchbox/releases/tag/v2.3.0) - The mapping engine used
* [CDA Logical Model](https://github.com/HL7Austria/CDA-core-2.0/tree/cda-ext-elga) - The CDA Logical Model adapted to the Austrian requirements

## Versioning

We use [SemVer](http://semver.org/) for versioning. For the versions available, see the [tags on this repository](https://github.com/HL7Austria/CDA2FHIR/tags).

## Authors

See the list of [contributors](https://github.com/HL7Austria/CDA2FHIR/contributors) who participated in this project.

## Acknowledgments

- [HL7CH - Implementation Guide CDA FHIR Maps](https://github.com/hl7ch/cda-fhir-maps)
- BlackTusk - Mapping Austrian CDA Laboratory Report to FHIR


