# FML ANTLR grammar

`Fml.g4` is a tolerant ANTLR4 grammar for the FHIR Mapping Language (`.map` /
`.fml`). It is *structural*: it parses group headers, parameters, `extends`,
type modes (`<<types>>` / `<<type+types>>`) and `then Group(...)` dependent
invocations precisely, while consuming all FHIRPath inside rule bodies as opaque
filler. That is enough to reconstruct the group call/extends graph
deterministically, without needing a full FML + FHIRPath grammar.

It is consumed by [`../generate_group_layout.py`](../generate_group_layout.py).

## Generated files (committed)

`FmlLexer.py`, `FmlParser.py`, `FmlListener.py`, `FmlVisitor.py` and the
`*.interp` / `*.tokens` files are generated from `Fml.g4` and committed so the
GitHub Action only needs the ANTLR **runtime** (`antlr4-python3-runtime`), not
the Java tool.

## Regenerating after editing `Fml.g4`

The generated parser and the pinned runtime
(`../requirements-group-layout.txt`) must share the same ANTLR major version —
currently **4.13.2**.

```bash
# Java is required only for regeneration, not at runtime.
curl -O https://www.antlr.org/download/antlr-4.13.2-complete.jar
java -jar antlr-4.13.2-complete.jar -Dlanguage=Python3 -visitor -listener Fml.g4
```

Then run `python ../generate_group_layout.py` to confirm all maps still parse.
