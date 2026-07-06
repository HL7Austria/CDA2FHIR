| Dim | Key | Comes from (FHIR) | Your lab map's value |
|-----|-----|-------------------|----------------------|
| 0 | ConceptMap **url or id** | `ConceptMap.url` ?? `ConceptMap.id` | `"elga-laboratory-observation-code-to-eHDSILabCodeWithExceptions"` |
| 1 | **sourceScope** valueset | `ConceptMap.sourceScope` | `"%"` (absent → wildcard) default key |
| 2 | **targetScope** valueset | `ConceptMap.targetScope` | `"%"` |
| 3 | source **system** | `group.source` | `https://termgit…/elga-laborparameterergaenzung` |
| 4 | target **system** | `group.target` | `http://terminology.hl7.org/CodeSystem/v3-NullFlavor` |
| 5 | source **code** | `element.code` | `"V00432-7"` |
| 6 | (the value) list of targets | `element.target[]` | `[{relationship, concept: {system,code,display}, source}]` |