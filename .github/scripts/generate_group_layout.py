#!/usr/bin/env python3
"""
generate_group_layout.py
========================

Parses every FHIR Mapping Language file under ``maps/`` (``*.map`` and
``*.fml``, including any standalone ones) with an ANTLR4 grammar and writes a
human-friendly overview of the group modularization to ``documentation/``:

  * ``group_layout.md``      - call graph + extends hierarchy (Mermaid diagrams,
                               an ASCII entry-point tree and index tables).
  * ``group_parameters.md``  - the source (input) and target (output) parameters
                               of every group.
  * ``group_layout.json``    - the same information as machine-readable JSON.

The FML is parsed with the ANTLR grammar in ``.github/scripts/fml/Fml.g4``
(generated parser committed alongside it), which makes recovering the
group -> group call/extends structure deterministic rather than regex-guesswork.

The parser is resilient: a file with, e.g., a missing closing brace still yields
all of its groups and the problem is reported as a warning (in the action log
and at the top of ``group_layout.md``) instead of aborting.

Run locally:   python .github/scripts/generate_group_layout.py
It is normally run by the ``group-layout`` GitHub Action on push to ``maps/**``.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# --- ANTLR runtime + generated parser -------------------------------------
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "fml"))

from antlr4 import CommonTokenStream, InputStream, ParserRuleContext, Token  # noqa: E402
from antlr4.error.ErrorListener import ErrorListener  # noqa: E402

from FmlLexer import FmlLexer  # noqa: E402
from FmlParser import FmlParser  # noqa: E402


# ==========================================================================
# Data model
# ==========================================================================
@dataclass
class Param:
    direction: str          # "source" | "target"
    name: str
    type: str | None


@dataclass
class Call:
    callee: str
    line: int


@dataclass
class Group:
    name: str
    params: list[Param]
    extends: str | None
    type_mode: str | None       # "types" / "type+types" / "any" / None
    def_line: int
    calls: list[Call]
    map_file: str = ""          # filled in by the caller
    map_name: str = ""

    @property
    def is_default_transform(self) -> bool:
        return self.type_mode is not None

    @property
    def sources(self) -> list[Param]:
        return [p for p in self.params if p.direction == "source"]

    @property
    def targets(self) -> list[Param]:
        return [p for p in self.params if p.direction == "target"]

    @property
    def unique_callees(self) -> list[str]:
        seen: dict[str, None] = {}
        for c in self.calls:
            seen.setdefault(c.callee, None)
        return list(seen)


@dataclass
class MapFile:
    file: str
    url: str | None
    name: str | None
    imports: list[str]
    groups: list[Group]
    warnings: list[str] = field(default_factory=list)


# ==========================================================================
# Parsing
# ==========================================================================
class _ErrorCollector(ErrorListener):
    def __init__(self) -> None:
        self.errors: list[str] = []

    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):  # noqa: N802
        self.errors.append(f"line {line}:{column} {msg}")


def _strip_quotes(text: str) -> str:
    if len(text) >= 2 and text[0] in "'\"`":
        return text[1:-1]
    return text


def _iter_invocations(node):
    """Yield every InvocationContext in the subtree (any nesting depth)."""
    stack = [node]
    while stack:
        cur = stack.pop()
        for i in range(cur.getChildCount()):
            child = cur.getChild(i)
            if isinstance(child, FmlParser.InvocationContext):
                yield child
            if isinstance(child, ParserRuleContext):
                stack.append(child)


def _extract_group(gctx: "FmlParser.GroupContext", line_offset: int = 0) -> Group | None:
    if gctx is None or gctx.name is None:
        return None
    name = gctx.name.text
    def_line = gctx.name.line + line_offset

    params: list[Param] = []
    pctx = gctx.params()
    if pctx is not None:
        for p in pctx.param():
            direction = "source" if p.SOURCE() is not None else "target"
            pname = p.pname.text if p.pname is not None else "?"
            ptype = p.ptype.text if p.ptype is not None else None
            params.append(Param(direction, pname, ptype))

    extends = gctx.extendsClause().parent.text if gctx.extendsClause() is not None else None

    type_mode = None
    if gctx.typeMode() is not None:
        body = gctx.typeMode().typeModeBody()
        type_mode = body.getText() if body is not None else ""

    calls = [Call(inv.callee.text, inv.callee.line + line_offset)
             for inv in _iter_invocations(gctx) if inv.callee is not None]

    return Group(name, params, extends, type_mode, def_line, calls)


def _lex_tokens(text: str) -> list[Token]:
    stream = CommonTokenStream(FmlLexer(InputStream(text)))
    stream.fill()
    return [t for t in stream.tokens if t.type != Token.EOF]


def _scan_meta(tokens: list[Token]) -> tuple[str | None, str | None, list[str]]:
    """Recover ``map "url" = "name"`` and ``imports "url"`` from the token stream."""
    url = name = None
    imports: list[str] = []
    for i, tok in enumerate(tokens):
        if tok.type == FmlLexer.ID and tok.text == "map" and url is None:
            strings = [tokens[j].text for j in range(i + 1, min(i + 6, len(tokens)))
                       if tokens[j].type == FmlLexer.STRING]
            if strings:
                url = _strip_quotes(strings[0])
            if len(strings) >= 2:
                name = _strip_quotes(strings[1])
        elif tok.type == FmlLexer.ID and tok.text == "imports":
            for j in range(i + 1, min(i + 3, len(tokens))):
                if tokens[j].type == FmlLexer.STRING:
                    imports.append(_strip_quotes(tokens[j].text))
                    break
    return url, name, imports


def _split_group_spans(tokens: list[Token]):
    """Split the token stream into one span per top-level ``group``.

    A ``group`` keyword is a hard delimiter: a group ends at its matching closing
    brace, or (if that brace is missing) at the next ``group`` keyword / EOF.
    Yields ``(start_idx, end_idx, closed, missing_braces)``.
    """
    positions = [i for i, t in enumerate(tokens) if t.type == FmlLexer.GROUP]
    for j, start in enumerate(positions):
        limit = positions[j + 1] if j + 1 < len(positions) else len(tokens)
        depth = 0
        seen_open = False
        end = limit - 1
        closed = False
        for k in range(start, limit):
            tt = tokens[k].type
            if tt == FmlLexer.LBRACE:
                depth += 1
                seen_open = True
            elif tt == FmlLexer.RBRACE:
                depth -= 1
                if seen_open and depth == 0:
                    end = k
                    closed = True
                    break
        yield start, end, closed, max(depth, 0)


def _parse_single_group(text_slice: str) -> "FmlParser.GroupContext | None":
    parser = FmlParser(CommonTokenStream(FmlLexer(InputStream(text_slice))))
    parser.removeErrorListeners()
    try:
        return parser.group()
    except Exception:  # pragma: no cover - defensive
        return None


def parse_map_file(path: Path) -> MapFile:
    text = path.read_text(encoding="utf-8")
    tokens = _lex_tokens(text)
    url, name, imports = _scan_meta(tokens)

    # Fast path: parse the whole file. Works for well-formed maps.
    parser = FmlParser(CommonTokenStream(FmlLexer(InputStream(text))))
    collector = _ErrorCollector()
    parser.removeErrorListeners()
    parser.addErrorListener(collector)
    tree = parser.program()

    groups: list[Group] = []
    warnings: list[str] = []

    if not collector.errors:
        for child in tree.getChildren():
            if isinstance(child, FmlParser.GroupContext):
                grp = _extract_group(child)
                if grp is not None:
                    groups.append(grp)
    else:
        # Resilient fallback: parse group-by-group so one malformed group
        # cannot swallow the rest of the file.
        for start, end, closed, missing in _split_group_spans(tokens):
            base_line = tokens[start].line
            slice_text = text[tokens[start].start: tokens[end].stop + 1]
            if not closed:
                slice_text += "\n" + ("}" * max(missing, 1))
            gctx = _parse_single_group(slice_text)
            grp = _extract_group(gctx, line_offset=base_line - 1)
            if grp is None:
                warnings.append(f"could not parse the group starting at line {base_line}")
                continue
            groups.append(grp)
            if not closed:
                warnings.append(
                    f"group `{grp.name}` (line {base_line}) is missing "
                    f"{max(missing, 1)} closing brace(s) - parsed with best-effort recovery"
                )

    for grp in groups:
        grp.map_file = path.name
        grp.map_name = name or path.stem
    return MapFile(path.name, url, name, imports, groups, warnings)


# ==========================================================================
# Cross-map model
# ==========================================================================
class Model:
    def __init__(self, maps: list[MapFile]) -> None:
        self.maps = maps
        self.groups: list[Group] = [g for m in maps for g in m.groups]
        self.by_name: dict[str, Group] = {}
        self.dupes: list[str] = []
        for g in self.groups:
            if g.name in self.by_name:
                self.dupes.append(g.name)
            else:
                self.by_name[g.name] = g

        # reverse call edges: callee -> set(caller names)
        self.called_by: dict[str, set[str]] = {g.name: set() for g in self.groups}
        for g in self.groups:
            for callee in g.unique_callees:
                if callee in self.called_by:
                    self.called_by[callee].add(g.name)

        # unresolved callees (called via `then X(...)` but no group X defined)
        self.unresolved: dict[str, set[str]] = {}
        defined = set(self.by_name)
        for g in self.groups:
            for callee in g.unique_callees:
                if callee not in defined:
                    self.unresolved.setdefault(callee, set()).add(g.name)

    def map_of(self, group_name: str) -> str | None:
        g = self.by_name.get(group_name)
        return g.map_file if g else None

    def roots(self) -> list[Group]:
        """Entry points: groups nobody calls and that are not default transforms."""
        rs = [g for g in self.groups
              if not self.called_by[g.name] and not g.is_default_transform]
        rs.sort(key=lambda g: (g.map_file != "CdaToFhirBundle.4.map", g.map_file, g.def_line))
        return rs


# ==========================================================================
# Rendering helpers
# ==========================================================================
def _anchor(name: str) -> str:
    return name.lower()


def _nid(name: str) -> str:
    """Mermaid-safe node id (prefixed to dodge reserved words like `end`)."""
    return "g_" + "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in name)


def _mermaid_call_graph(model: Model, mp: MapFile) -> str:
    local = {g.name for g in mp.groups}
    lines = ["```mermaid", "graph LR"]
    # declare local nodes
    for g in sorted(mp.groups, key=lambda x: x.name):
        shape = f'{_nid(g.name)}["{g.name}"]'
        lines.append(f"  {shape}")
    edges: list[str] = []
    external: dict[str, str] = {}   # external node id -> label
    defaults: set[str] = {g.name for g in mp.groups if g.is_default_transform}
    for g in sorted(mp.groups, key=lambda x: x.name):
        for callee in sorted(g.unique_callees):
            target = model.by_name.get(callee)
            if target is not None and callee not in local:
                external[_nid(callee)] = f'{callee}<br/><i>{target.map_file}</i>'
                if target.is_default_transform:
                    defaults.add(callee)
            elif target is None:
                external[_nid(callee)] = f'{callee}<br/><i>?unresolved</i>'
            edges.append(f"  {_nid(g.name)} --> {_nid(callee)}")
    for eid, label in sorted(external.items()):
        lines.append(f'  {eid}(["{label}"])')
    lines.extend(sorted(set(edges)))
    # style default transforms
    dnodes = sorted({_nid(n) for n in defaults})
    if dnodes:
        lines.append("  classDef dfltTransform fill:#e8f0ff,stroke:#4472c4,color:#1f3864;")
        lines.append("  class " + ",".join(dnodes) + " dfltTransform;")
    lines.append("```")
    return "\n".join(lines)


def _mermaid_extends(model: Model) -> str:
    lines = ["```mermaid", "graph TD"]
    involved: set[str] = set()
    edges: list[str] = []
    for g in model.groups:
        if g.extends:
            involved.add(g.name)
            involved.add(g.extends)
            edges.append(f"  {_nid(g.name)} -. extends .-> {_nid(g.extends)}")
    for name in sorted(involved):
        g = model.by_name.get(name)
        label = name
        if g and g.type_mode:
            label = f"{name}<br/>«{g.type_mode}»"
        lines.append(f'  {_nid(name)}["{label}"]')
    lines.extend(sorted(set(edges)))
    defaults = sorted({_nid(g.name) for g in model.groups
                       if g.is_default_transform and g.name in involved})
    if defaults:
        lines.append("  classDef dfltTransform fill:#e8f0ff,stroke:#4472c4,color:#1f3864;")
        lines.append("  class " + ",".join(defaults) + " dfltTransform;")
    lines.append("```")
    return "\n".join(lines)


def _mermaid_map_overview(model: Model) -> str:
    lines = ["```mermaid", "graph LR"]
    by_file = {m.file: m for m in model.maps}
    for m in model.maps:
        lines.append(f'  {_nid(m.file)}["{m.name or m.file}<br/><i>{m.file}</i>"]')
    edges: set[str] = set()
    # cross-map call edges (aggregated)
    for g in model.groups:
        for callee in g.unique_callees:
            tgt = model.by_name.get(callee)
            if tgt and tgt.map_file != g.map_file:
                edges.add(f"  {_nid(g.map_file)} --> {_nid(tgt.map_file)}")
    lines.extend(sorted(edges))
    lines.append("```")
    return "\n".join(lines)


def _ascii_tree(model: Model) -> list[str]:
    out: list[str] = []
    expanded: set[str] = set()

    def walk(name: str, prefix: str, is_last: bool, path: set[str]) -> None:
        g = model.by_name.get(name)
        connector = "└─ " if is_last else "├─ "
        tag = ""
        if g:
            tag = f"  [{g.map_file}]"
            if g.is_default_transform:
                tag += f"  <<{g.type_mode}>>"
        else:
            tag = "  [unresolved]"
        suffix = ""
        if name in path:
            suffix = "  (↻ recursion)"
            out.append(f"{prefix}{connector}{name}{tag}{suffix}")
            return
        if name in expanded and g and g.unique_callees:
            suffix = "  (↑ see above)"
            out.append(f"{prefix}{connector}{name}{tag}{suffix}")
            return
        out.append(f"{prefix}{connector}{name}{tag}")
        if not g:
            return
        expanded.add(name)
        callees = sorted(g.unique_callees)
        child_prefix = prefix + ("   " if is_last else "│  ")
        for idx, callee in enumerate(callees):
            walk(callee, child_prefix, idx == len(callees) - 1, path | {name})

    roots = model.roots()
    for r in roots:
        g = r
        head_tag = f"  [{g.map_file}]"
        out.append(f"{g.name}{head_tag}")
        expanded.add(g.name)
        callees = sorted(g.unique_callees)
        for idx, callee in enumerate(callees):
            walk(callee, "", idx == len(callees) - 1, {g.name})
        out.append("")
    return out


# ==========================================================================
# Documents
# ==========================================================================
def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def render_layout_md(model: Model) -> str:
    L: list[str] = []
    A = L.append
    A("# Group Layout")
    A("")
    A("> **Auto-generated** by [`.github/scripts/generate_group_layout.py`]"
      "(../.github/scripts/generate_group_layout.py) — do not edit by hand.  ")
    A(f"> Last generated: {_stamp()}")
    A("")
    A("This document shows how the FHIR Mapping Language groups under `maps/` are "
      "modularized: which group **calls** (`then Group(...)`) which other group, "
      "which group **extends** which, and which groups are **default transforms** "
      "(type-conversion groups declared with a `<<types>>` / `<<type+types>>` type mode, "
      "usually extending `Any`).")
    A("")

    # summary
    n_calls = sum(len(g.unique_callees) for g in model.groups)
    n_default = sum(1 for g in model.groups if g.is_default_transform)
    A("## Summary")
    A("")
    A("| Map file | Canonical name | Groups | Imports |")
    A("| --- | --- | ---: | --- |")
    for m in model.maps:
        imported = ", ".join(sorted({model_import_label(model, u) for u in m.imports})) or "—"
        A(f"| `{m.file}` | {m.name or '—'} | {len(m.groups)} | {imported} |")
    A(f"| **Total** | | **{len(model.groups)}** | |")
    A("")
    A(f"- **{len(model.groups)}** groups across **{len(model.maps)}** map files  ")
    A(f"- **{n_calls}** distinct group-to-group call edges  ")
    A(f"- **{n_default}** default transforms (type-mode groups)")
    A("")

    # warnings
    all_warnings = [(m.file, w) for m in model.maps for w in m.warnings]
    if model.dupes:
        for d in sorted(set(model.dupes)):
            all_warnings.append(("*", f"group name `{d}` is defined more than once"))
    if model.unresolved:
        for callee, callers in sorted(model.unresolved.items()):
            all_warnings.append(("*", f"`then {callee}(...)` called by "
                                      f"{', '.join(sorted(callers))} but no group `{callee}` is defined"))
    if all_warnings:
        A("## ⚠️ Warnings")
        A("")
        for file, w in all_warnings:
            where = "" if file == "*" else f"`{file}`: "
            A(f"- {where}{w}")
        A("")

    # legend
    A("## Legend")
    A("")
    A("- `A --> B` — group **A calls** group B via `then B(...)`.")
    A("- `A -. extends .-> B` — group **A extends** group B.")
    A("- Blue nodes are **default transforms** (declared with a `<<…>>` type mode).")
    A("- Rounded nodes in a per-map graph live in **another** map file.")
    A("")

    # map overview
    A("## Map dependencies")
    A("")
    A("How the map files call into each other (aggregated cross-map call edges):")
    A("")
    A(_mermaid_map_overview(model))
    A("")

    # entry tree
    A("## Entry-point call tree")
    A("")
    A("Expansion of every entry-point group (a group that nobody calls and that "
      "is not a default transform), following `then Group(...)` calls. Repeated "
      "sub-trees are collapsed with `(↑ see above)`; recursive calls are marked `(↻ recursion)`.")
    A("")
    A("```text")
    L.extend(_ascii_tree(model))
    A("```")
    A("")

    # per-map call graphs -> interactive drill-down
    A("## Interactive drill-down")
    A("")
    A("The per-map call graphs render as an unreadable hairball because the shared "
      "type-conversion groups are called by almost everything. Instead, open the "
      "**interactive drill-down** — it separates the semantic call flow from the "
      "datatype layer and lets you click Maps → Groups → Datatypes:")
    A("")
    A("➡️ [`group_layout.html`](group_layout.html) "
      "&nbsp;·&nbsp; open locally, or publish `documentation/` to a GitHub Pages "
      "branch to browse it online (GitHub shows raw `.html` as source in the repo view).")
    A("")

    # extends hierarchy
    A("## Extends / default-transform hierarchy")
    A("")
    A("Inheritance across all maps. The type-conversion layer (rooted at `Any`) "
      "and the CDA header/section defaults are default transforms.")
    A("")
    A(_mermaid_extends(model))
    A("")

    # index table
    A("## Group index")
    A("")
    A("| Group | Map | Extends | Default transform | Calls out | Called by |")
    A("| --- | --- | --- | :---: | ---: | ---: |")
    for g in sorted(model.groups, key=lambda x: (x.map_file, x.name)):
        ext = f"`{g.extends}`" if g.extends else "—"
        dflt = f"`<<{g.type_mode}>>`" if g.is_default_transform else "—"
        A(f"| `{g.name}` | `{g.map_file}` | {ext} | {dflt} | "
          f"{len(g.unique_callees)} | {len(model.called_by[g.name])} |")
    A("")
    return "\n".join(L) + "\n"


def model_import_label(model: Model, url: str) -> str:
    for m in model.maps:
        if m.url == url:
            return m.file
    # fall back to the last path segment of the canonical url
    return url.rsplit("/", 1)[-1]


def render_params_md(model: Model) -> str:
    L: list[str] = []
    A = L.append
    A("# Group Parameters")
    A("")
    A("> **Auto-generated** by [`.github/scripts/generate_group_layout.py`]"
      "(../.github/scripts/generate_group_layout.py) — do not edit by hand.  ")
    A(f"> Last generated: {_stamp()}")
    A("")
    A("Input (`source`) and output (`target`) parameters of every group. "
      "In FHIR Mapping Language the `target` parameters are the resources/elements "
      "a group produces.")
    A("")
    for m in model.maps:
        A(f"## `{m.file}`")
        A("")
        if not m.groups:
            A("_No groups._")
            A("")
            continue
        for g in m.groups:
            header = f"### `{g.name}`"
            A(header)
            meta = []
            if g.extends:
                meta.append(f"extends `{g.extends}`")
            if g.is_default_transform:
                meta.append(f"default transform `<<{g.type_mode}>>`")
            meta.append(f"line {g.def_line}")
            A("")
            A(f"<sub>{' · '.join(meta)}</sub>")
            A("")
            A("| Dir | # | Name | Type |")
            A("| --- | ---: | --- | --- |")
            for i, p in enumerate(g.sources, 1):
                A(f"| source (in) | {i} | `{p.name}` | {('`' + p.type + '`') if p.type else '—'} |")
            for i, p in enumerate(g.targets, 1):
                A(f"| target (out) | {i} | `{p.name}` | {('`' + p.type + '`') if p.type else '—'} |")
            A("")
    return "\n".join(L) + "\n"


def render_json(model: Model) -> str:
    payload = {
        "generated": _stamp(),
        "maps": [
            {
                "file": m.file,
                "name": m.name,
                "url": m.url,
                "imports": m.imports,
                "warnings": m.warnings,
                "groups": [
                    {
                        "name": g.name,
                        "line": g.def_line,
                        "extends": g.extends,
                        "typeMode": g.type_mode,
                        "isDefaultTransform": g.is_default_transform,
                        "params": [
                            {"direction": p.direction, "name": p.name, "type": p.type}
                            for p in g.params
                        ],
                        "calls": sorted(g.unique_callees),
                        "calledBy": sorted(model.called_by[g.name]),
                    }
                    for g in m.groups
                ],
            }
            for m in model.maps
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


# ==========================================================================
# Interactive HTML drill-down
# ==========================================================================
def _is_type_map(mp: MapFile) -> bool:
    hay = f"{mp.name or ''} {mp.url or ''} {mp.file}".lower()
    return "type" in hay


def build_app_data(model: Model) -> dict:
    """Shape the model for the interactive drill-down.

    A group is a **datatype** group (part of the shared type-conversion library)
    if it declares a `<<…>>` type mode *or* is defined in a "types" map;
    otherwise it is a **semantic** ("inhaltliche") group.
    """
    type_map_files = {m.file for m in model.maps if _is_type_map(m)}

    def kind_of(name: str | None) -> str:
        if name is None:
            return "external"
        g = model.by_name.get(name)
        if g is None:
            return "external"
        if g.type_mode is not None or g.map_file in type_map_files:
            return "datatype"
        return "semantic"

    maps_out = []
    for m in model.maps:
        sem = sum(1 for g in m.groups if kind_of(g.name) == "semantic")
        dt = sum(1 for g in m.groups if kind_of(g.name) == "datatype")
        maps_out.append({
            "file": m.file,
            "name": m.name or m.file,
            "url": m.url,
            "imports": sorted({model_import_label(model, u) for u in m.imports}),
            "isTypeMap": m.file in type_map_files,
            "semantic": sem,
            "datatype": dt,
            "warnings": m.warnings,
        })

    groups_out = []
    for g in model.groups:
        groups_out.append({
            "name": g.name,
            "map": g.map_file,
            "mapName": g.map_name,
            "kind": kind_of(g.name),
            "extends": g.extends,
            "extendsKind": kind_of(g.extends),
            "typeMode": g.type_mode,
            "line": g.def_line,
            "params": [{"dir": p.direction, "name": p.name, "type": p.type} for p in g.params],
            "calls": [{"name": c, "map": model.map_of(c), "kind": kind_of(c)}
                      for c in g.unique_callees],
            "calledBy": [{"name": c, "map": model.map_of(c), "kind": kind_of(c)}
                         for c in sorted(model.called_by[g.name])],
        })

    return {
        "generated": _stamp(),
        "maps": maps_out,
        "groups": groups_out,
        "stats": {
            "groups": len(model.groups),
            "maps": len(model.maps),
            "semantic": sum(1 for g in model.groups if kind_of(g.name) == "semantic"),
            "datatype": sum(1 for g in model.groups if kind_of(g.name) == "datatype"),
            "calls": sum(len(g.unique_callees) for g in model.groups),
        },
    }


def render_html(model: Model) -> str:
    data = build_app_data(model)
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    inner = (_APP_INNER
             .replace("/*__DATA__*/", payload)
             .replace("__STAMP__", data["generated"]))
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>CDA→FHIR — Group Layout</title>\n"
        "</head>\n<body>\n"
        + inner +
        "\n</body>\n</html>\n"
    )


# The full drill-down UI (style + markup + script). Kept as one plain string so
# CSS/JS braces stay literal; only /*__DATA__*/ and __STAMP__ are substituted.
_APP_INNER = r"""
<style>
:root{
  --bg:#f6f7f9; --panel:#ffffff; --ink:#1b1f24; --muted:#5b6572; --line:#e4e7ec;
  --soft:#f0f2f5; --accent:#3b5bdb; --dt:280; --shadow:0 1px 2px rgba(16,24,40,.06),0 4px 16px rgba(16,24,40,.06);
}
@media (prefers-color-scheme:dark){
  :root{ --bg:#0f1216; --panel:#171b21; --ink:#e8ecf1; --muted:#9aa4b2; --line:#262c34;
         --soft:#1e242c; --accent:#7aa2ff; --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 28px rgba(0,0,0,.35); }
}
:root[data-theme="light"]{ --bg:#f6f7f9; --panel:#fff; --ink:#1b1f24; --muted:#5b6572; --line:#e4e7ec; --soft:#f0f2f5; --accent:#3b5bdb; --shadow:0 1px 2px rgba(16,24,40,.06),0 4px 16px rgba(16,24,40,.06);}
:root[data-theme="dark"]{ --bg:#0f1216; --panel:#171b21; --ink:#e8ecf1; --muted:#9aa4b2; --line:#262c34; --soft:#1e242c; --accent:#7aa2ff; --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 28px rgba(0,0,0,.35);}
*{box-sizing:border-box}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:6px}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important;scroll-behavior:auto!important}}
body{margin:0;background:var(--bg);color:var(--ink);
  font:14.5px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Inter,Helvetica,Arial,sans-serif;
  font-variant-numeric:tabular-nums;}
a{color:inherit}
.wrap{max-width:1180px;margin:0 auto;padding:0 20px 64px}
.topbar{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:16px;
  padding:14px 20px;margin:0 -20px 0;background:color-mix(in srgb,var(--bg) 82%,transparent);
  backdrop-filter:saturate(1.4) blur(10px);border-bottom:1px solid var(--line)}
.brand{display:flex;align-items:center;gap:10px;font-weight:680;letter-spacing:.2px;white-space:nowrap}
.brand .dot{width:11px;height:11px;border-radius:3px;background:linear-gradient(135deg,#3b5bdb,#9b59ff)}
.brand small{font-weight:500;color:var(--muted)}
.search{position:relative;margin-left:auto;width:min(360px,42vw)}
.search input{width:100%;padding:9px 12px;border-radius:10px;border:1px solid var(--line);
  background:var(--panel);color:var(--ink);outline:none;transition:border-color .15s,box-shadow .15s}
.search input:focus{border-color:var(--accent);box-shadow:0 0 0 3px color-mix(in srgb,var(--accent) 22%,transparent)}
.results{position:absolute;top:44px;left:0;right:0;background:var(--panel);border:1px solid var(--line);
  border-radius:12px;box-shadow:var(--shadow);overflow:hidden;display:none;max-height:60vh;overflow-y:auto}
.results.show{display:block}
.results button{display:flex;gap:8px;align-items:center;width:100%;text-align:left;border:0;background:none;
  color:var(--ink);padding:9px 12px;cursor:pointer;border-bottom:1px solid var(--line)}
.results button:hover,.results button.active{background:var(--soft)}
.results .rm{margin-left:auto;color:var(--muted);font-size:12px}
.theme{border:1px solid var(--line);background:var(--panel);color:var(--muted);border-radius:9px;
  width:34px;height:34px;cursor:pointer;font-size:15px}
.crumbs{display:flex;flex-wrap:wrap;align-items:center;gap:7px;padding:16px 0 4px;color:var(--muted);font-size:13px}
.crumbs button{border:0;background:none;color:var(--accent);cursor:pointer;padding:2px 2px;font-size:13px}
.crumbs button:hover{text-decoration:underline}
.crumbs .sep{opacity:.5}
.crumbs .cur{color:var(--ink);font-weight:600}
h1.title{font-size:22px;margin:8px 0 2px;letter-spacing:-.2px}
.sub{color:var(--muted);margin:0 0 18px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(255px,1fr));gap:16px}
.card{position:relative;background:var(--panel);border:1px solid var(--line);border-radius:14px;
  padding:16px 16px 14px;box-shadow:var(--shadow);cursor:pointer;overflow:hidden;
  transition:transform .12s ease,border-color .12s ease}
.card:hover{transform:translateY(-2px);border-color:color-mix(in srgb,hsl(var(--h) 70% 55%) 55%,var(--line))}
.card .bar{position:absolute;inset:0 0 auto 0;height:4px;background:hsl(var(--h) 70% 55%)}
.card h3{margin:6px 0 2px;font-size:16px}
.card .file{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11.5px;color:var(--muted)}
.card .row{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.pill{display:inline-flex;align-items:center;gap:6px;padding:3px 9px;border-radius:999px;font-size:12px;
  background:var(--soft);border:1px solid var(--line);color:var(--muted)}
.pill.sem{color:hsl(var(--h) 70% 42%);background:hsl(var(--h) 70% 55%/.12);border-color:hsl(var(--h) 70% 55%/.3)}
.pill.dt{color:hsl(var(--dt) 70% 55%);background:hsl(var(--dt) 70% 60%/.14);border-color:hsl(var(--dt) 70% 60%/.32)}
@media (prefers-color-scheme:dark){.pill.sem{color:hsl(var(--h) 80% 74%)}}
.lib{--h:280}
.badge{font-size:11px;padding:1px 7px;border-radius:6px;background:var(--soft);border:1px solid var(--line);color:var(--muted)}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow);padding:18px 18px;margin:14px 0;overflow-x:auto}
.toolbar{display:flex;flex-wrap:wrap;gap:16px;align-items:center;margin:6px 0 2px;color:var(--muted);font-size:13px}
.toggle{display:inline-flex;align-items:center;gap:8px;cursor:pointer;user-select:none}
.toggle input{position:absolute;opacity:0;pointer-events:none}
.track{width:34px;height:19px;border-radius:999px;background:var(--line);position:relative;transition:background .15s}
.track::after{content:"";position:absolute;top:2px;left:2px;width:15px;height:15px;border-radius:50%;
  background:#fff;box-shadow:0 1px 2px rgba(0,0,0,.3);transition:transform .15s}
.toggle input:checked + .track{background:var(--accent)}
.toggle input:checked + .track::after{transform:translateX(15px)}
/* tree */
.tree{margin-top:6px}
.node{margin:0}
.node .self{display:flex;align-items:center;gap:8px;padding:5px 8px;border-radius:9px;position:relative}
.node .self:hover{background:var(--soft)}
.tw{width:18px;height:18px;flex:0 0 auto;border:0;background:none;color:var(--muted);cursor:pointer;
  display:inline-flex;align-items:center;justify-content:center;font-size:11px;transition:transform .12s}
.tw.empty{visibility:hidden}
.node.collapsed>.self .tw{transform:rotate(-90deg)}
.gname{border:0;background:none;color:var(--ink);cursor:pointer;font-weight:600;font-size:14px;padding:0}
.gname:hover{color:var(--accent)}
.gname .sq{display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:7px;vertical-align:middle;
  background:hsl(var(--h) 70% 55%)}
.tag{font-size:11px;color:var(--muted);padding:1px 7px;border-radius:999px;border:1px solid var(--line);background:var(--panel)}
.tag.dt{color:hsl(var(--dt) 70% 55%);border-color:hsl(var(--dt) 70% 60%/.4)}
.tag.x{color:var(--muted)}
.kids{margin-left:9px;padding-left:11px;border-left:1px dashed var(--line)}
.node.collapsed>.kids{display:none}
.paramline{margin:2px 0 6px 34px;color:var(--muted);font-size:12.5px}
.paramline code{background:var(--soft);padding:1px 5px;border-radius:5px}
/* group detail */
.gd-head{display:flex;flex-wrap:wrap;align-items:center;gap:10px}
.gd-head h1{font-size:22px;margin:0}
.kindtag{font-size:12px;font-weight:600;padding:3px 10px;border-radius:999px}
.kindtag.semantic{color:hsl(var(--h) 70% 42%);background:hsl(var(--h) 70% 55%/.14);border:1px solid hsl(var(--h) 70% 55%/.3)}
.kindtag.datatype{color:hsl(var(--dt) 70% 52%);background:hsl(var(--dt) 70% 60%/.16);border:1px solid hsl(var(--dt) 70% 60%/.34)}
@media (prefers-color-scheme:dark){.kindtag.semantic{color:hsl(var(--h) 80% 76%)}.kindtag.datatype{color:hsl(var(--dt) 80% 80%)}}
.meta{display:flex;flex-wrap:wrap;gap:8px 18px;color:var(--muted);font-size:13px;margin:12px 0 2px}
.meta b{color:var(--ink);font-weight:600}
.sect{margin-top:16px}
.sect h4{margin:0 0 9px;font-size:12px;letter-spacing:.6px;text-transform:uppercase;color:var(--muted)}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chip{display:inline-flex;align-items:center;gap:7px;border:1px solid var(--line);background:var(--panel);
  border-radius:10px;padding:6px 11px;cursor:pointer;font-size:13px;transition:border-color .12s,background .12s}
.chip:hover{background:var(--soft)}
.chip .sq{width:8px;height:8px;border-radius:2px;background:hsl(var(--h) 70% 55%)}
.chip.dt .sq{background:hsl(var(--dt) 70% 58%)}
.chip.x{cursor:default;color:var(--muted);opacity:.75}
.chip .mm{color:var(--muted);font-size:11.5px}
.params{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:640px){.params{grid-template-columns:1fr}.search{width:44vw}}
.pcol{background:var(--soft);border:1px solid var(--line);border-radius:12px;padding:12px 12px}
.pcol h5{margin:0 0 9px;font-size:12px;color:var(--muted);letter-spacing:.4px;text-transform:uppercase}
.prow{display:flex;align-items:center;gap:8px;padding:4px 0}
.prow .nm{font-weight:600}
.prow .ty{margin-left:auto;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;
  color:hsl(var(--dt) 70% 52%);background:hsl(var(--dt) 70% 60%/.12);padding:1px 7px;border-radius:6px}
.io-in .prow .ty{color:var(--accent);background:color-mix(in srgb,var(--accent) 14%,transparent)}
.empty-note{color:var(--muted);font-size:13px}
.warn{background:hsl(38 92% 50%/.12);border:1px solid hsl(38 92% 45%/.4);color:hsl(38 60% 40%);
  border-radius:12px;padding:10px 14px;font-size:13px;margin:12px 0}
@media (prefers-color-scheme:dark){.warn{color:hsl(38 90% 72%)}}
.foot{color:var(--muted);font-size:12px;margin-top:26px;text-align:center}
kbd{font:inherit;background:var(--soft);border:1px solid var(--line);border-bottom-width:2px;border-radius:6px;padding:0 6px}
</style>

<div class="wrap">
  <header class="topbar">
    <div class="brand"><span class="dot"></span> CDA&nbsp;→&nbsp;FHIR <small>Group Layout</small></div>
    <div class="search">
      <input id="q" type="text" placeholder="Search groups…  ( / )" autocomplete="off" spellcheck="false">
      <div class="results" id="results"></div>
    </div>
    <button class="theme" id="theme" title="Toggle light / dark">◐</button>
  </header>
  <nav class="crumbs" id="crumbs"></nav>
  <main id="view"></main>
  <div class="foot">Auto-generated from <code>maps/</code> · __STAMP__ · <span id="statline"></span></div>
</div>

<script id="appdata" type="application/json">/*__DATA__*/</script>
<script>
(function(){
"use strict";
var DATA = JSON.parse(document.getElementById('appdata').textContent);
var G = new Map(DATA.groups.map(function(g){return [g.name,g];}));
var MAPS = DATA.maps;
var HUES = {}; var PAL=[222,168,28,332,140,258];
MAPS.forEach(function(m,i){ HUES[m.file]= m.isTypeMap?280:PAL[i%PAL.length]; });
function hue(file){ return HUES[file]!=null?HUES[file]:222; }
function el(html){ var t=document.createElement('template'); t.innerHTML=html.trim(); return t.content.firstChild; }
function esc(s){ return String(s==null?'':s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];}); }

var view=document.getElementById('view');
var crumbs=document.getElementById('crumbs');
document.getElementById('statline').textContent =
  DATA.stats.groups+' groups · '+DATA.stats.semantic+' semantic · '+DATA.stats.datatype+' datatypes · '+DATA.stats.calls+' calls';

/* ---------- routing ---------- */
function go(hash){ if(location.hash===hash){ render(); } else { location.hash=hash; } }
function parse(){
  var h=decodeURIComponent(location.hash.replace(/^#/,''));
  var p=h.split('/').filter(Boolean);
  if(p[0]==='map') return {v:'map',file:p.slice(1).join('/')};
  if(p[0]==='group') return {v:'group',name:p.slice(1).join('/')};
  return {v:'home'};
}
window.addEventListener('hashchange',render);

/* ---------- breadcrumbs ---------- */
function setCrumbs(items){
  crumbs.innerHTML='';
  items.forEach(function(it,i){
    if(i) crumbs.appendChild(el('<span class="sep">›</span>'));
    if(it.hash){ var b=el('<button>'+esc(it.label)+'</button>'); b.onclick=function(){go(it.hash);}; crumbs.appendChild(b); }
    else crumbs.appendChild(el('<span class="cur">'+esc(it.label)+'</span>'));
  });
}

/* ---------- home: maps ---------- */
function renderHome(){
  setCrumbs([{label:'Maps'}]);
  var wrap=el('<div></div>');
  wrap.appendChild(el('<h1 class="title">Mapping group layout</h1>'));
  wrap.appendChild(el('<p class="sub">Pick a mapping to explore its <b>semantic groups</b>, then drill into the shared <b>datatype</b> conversions they use.</p>'));
  var sem=MAPS.filter(function(m){return !m.isTypeMap;});
  var lib=MAPS.filter(function(m){return m.isTypeMap;});
  var grid=el('<div class="grid"></div>');
  sem.forEach(function(m){ grid.appendChild(mapCard(m)); });
  wrap.appendChild(grid);
  if(lib.length){
    wrap.appendChild(el('<h4 style="color:var(--muted);letter-spacing:.6px;text-transform:uppercase;font-size:12px;margin:26px 0 12px">Shared datatype library</h4>'));
    var g2=el('<div class="grid"></div>');
    lib.forEach(function(m){ g2.appendChild(mapCard(m)); });
    wrap.appendChild(g2);
  }
  view.innerHTML=''; view.appendChild(wrap);
}
function mapCard(m){
  var c=el('<div class="card'+(m.isTypeMap?' lib':'')+'" style="--h:'+hue(m.file)+'"></div>');
  c.appendChild(el('<div class="bar"></div>'));
  c.appendChild(el('<h3>'+esc(m.name)+'</h3>'));
  c.appendChild(el('<div class="file">'+esc(m.file)+'</div>'));
  var row=el('<div class="row"></div>');
  if(m.isTypeMap){ row.appendChild(el('<span class="pill dt">'+m.datatype+' datatypes</span>')); }
  else{
    row.appendChild(el('<span class="pill sem">'+m.semantic+' semantic</span>'));
    if(m.datatype) row.appendChild(el('<span class="pill dt">'+m.datatype+' datatype</span>'));
  }
  if(m.warnings&&m.warnings.length) row.appendChild(el('<span class="pill" title="'+esc(m.warnings.join(' | '))+'">⚠ '+m.warnings.length+'</span>'));
  c.appendChild(row);
  c.onclick=function(){ go('#/map/'+m.file); };
  return c;
}

/* ---------- map view: semantic tree ---------- */
var showParams=false, includeTypes=false;
function renderMap(file){
  var m=MAPS.find(function(x){return x.file===file;});
  if(!m){ renderHome(); return; }
  setCrumbs([{label:'Maps',hash:'#/'},{label:m.name}]);
  var wrap=el('<div></div>');
  wrap.appendChild(el('<h1 class="title" style="--h:'+hue(file)+'">'+esc(m.name)+'</h1>'));
  var sub=el('<p class="sub"></p>');
  sub.innerHTML='<span class="file">'+esc(m.file)+'</span>'+(m.url?' · <span class="file">'+esc(m.url)+'</span>':'');
  wrap.appendChild(sub);
  if(m.warnings&&m.warnings.length) m.warnings.forEach(function(w){ wrap.appendChild(el('<div class="warn">⚠ '+esc(w)+'</div>')); });

  var panel=el('<div class="panel"></div>');
  var bar=el('<div class="toolbar"></div>');
  bar.appendChild(makeToggle('Show parameters',showParams,function(v){showParams=v;renderMap(file);}));
  if(!m.isTypeMap) bar.appendChild(makeToggle('Include datatype groups',includeTypes,function(v){includeTypes=v;renderMap(file);}));
  bar.appendChild(el('<span style="margin-left:auto">'+esc(m.isTypeMap?'Datatype conversion groups':'Semantic call flow — datatype calls shown as chips')+'</span>'));
  panel.appendChild(bar);

  var tree=el('<div class="tree"></div>');
  var roots=mapRoots(file,m.isTypeMap);
  if(!roots.length) tree.appendChild(el('<div class="empty-note">No groups.</div>'));
  roots.forEach(function(r){ tree.appendChild(treeNode(r,file,{},0)); });
  panel.appendChild(tree);
  wrap.appendChild(panel);
  view.innerHTML=''; view.appendChild(wrap);
}
function inMapGroups(file){
  return DATA.groups.filter(function(g){ return g.map===file && (includeTypes || g.kind==='semantic'); });
}
function mapRoots(file,isTypeMap){
  var inm=inMapGroups(file);
  if(isTypeMap){ return inm.slice().sort(byName).map(function(g){return g.name;}); }
  var called=new Set();
  inm.forEach(function(g){ g.calls.forEach(function(c){ if(c.map===file && (includeTypes||c.kind==='semantic')) called.add(c.name); }); });
  var roots=inm.filter(function(g){ return !called.has(g.name); }).sort(byName).map(function(g){return g.name;});
  return roots.length?roots:inm.slice().sort(byName).map(function(g){return g.name;});
}
function byName(a,b){ return a.name<b.name?-1:a.name>b.name?1:0; }
function treeNode(name,file,anc,depth){
  var g=G.get(name);
  var node=el('<div class="node'+(depth>=1?' collapsed':'')+'" style="--h:'+hue(g?g.map:file)+'"></div>');
  var self=el('<div class="self"></div>');
  var childNames=[], dtCalls=[], xCalls=[];
  if(g){
    g.calls.forEach(function(c){
      if(c.map===file && (includeTypes||c.kind==='semantic') && !anc[c.name]) childNames.push(c.name);
      else if(c.kind==='datatype') dtCalls.push(c);
      else if(c.map!==file) xCalls.push(c);
    });
  }
  childNames=uniq(childNames).sort();
  var tw=el('<button class="tw'+(childNames.length?'':' empty')+'">▾</button>');
  self.appendChild(tw);
  var nm=el('<button class="gname"><span class="sq"></span>'+esc(name)+'</button>');
  nm.onclick=function(){ go('#/group/'+name); };
  self.appendChild(nm);
  if(anc[name]) self.appendChild(el('<span class="tag x">↻ recursion</span>'));
  if(g&&g.extends) self.appendChild(el('<span class="tag">extends '+esc(g.extends)+'</span>'));
  var dcount=uniq(dtCalls.map(function(c){return c.name;})).length;
  if(dcount) self.appendChild(el('<span class="tag dt">'+dcount+' datatype'+(dcount>1?'s':'')+'</span>'));
  var xcount=uniq(xCalls.map(function(c){return c.name;})).length;
  if(xcount) self.appendChild(el('<span class="tag">'+xcount+' cross-map</span>'));
  node.appendChild(self);
  if(showParams && g){
    var ins=g.params.filter(function(p){return p.dir==='source';}).map(function(p){return '<code>'+esc(p.name)+'</code>';}).join(' ');
    var outs=g.params.filter(function(p){return p.dir==='target';}).map(function(p){return '<code>'+esc(p.name)+'</code>';}).join(' ');
    node.appendChild(el('<div class="paramline"><b>in</b> '+(ins||'—')+' &nbsp; <b>out</b> '+(outs||'—')+'</div>'));
  }
  if(childNames.length){
    var built=false;
    var buildKids=function(){
      if(built) return; built=true;
      var kids=el('<div class="kids"></div>');
      var anc2=Object.assign({},anc); anc2[name]=true;
      childNames.forEach(function(cn){ kids.appendChild(treeNode(cn,file,anc2,depth+1)); });
      node.appendChild(kids);
    };
    tw.onclick=function(){ if(!node.classList.toggle('collapsed')) buildKids(); };
    if(depth<1){ buildKids(); } else { node.classList.add('collapsed'); }
  }
  return node;
}
function uniq(a){ return Array.from(new Set(a)); }

/* ---------- group detail ---------- */
function renderGroup(name){
  var g=G.get(name);
  if(!g){ renderHome(); return; }
  setCrumbs([{label:'Maps',hash:'#/'},{label:g.mapName,hash:'#/map/'+g.map},{label:g.name}]);
  var wrap=el('<div style="--h:'+hue(g.map)+'"></div>');
  var head=el('<div class="gd-head"></div>');
  head.appendChild(el('<h1>'+esc(g.name)+'</h1>'));
  head.appendChild(el('<span class="kindtag '+g.kind+'">'+(g.kind==='datatype'?'Datatype':'Semantic')+'</span>'));
  wrap.appendChild(head);
  var meta=el('<div class="meta"></div>');
  meta.appendChild(el('<span>map <b>'+esc(g.mapName)+'</b></span>'));
  meta.appendChild(el('<span>line <b>'+g.line+'</b></span>'));
  if(g.typeMode) meta.appendChild(el('<span>type mode <b>«'+esc(g.typeMode)+'»</b></span>'));
  if(g.extends){
    var ex=el('<span>extends </span>');
    ex.appendChild(linkChipInline(g.extends));
    meta.appendChild(ex);
  }
  wrap.appendChild(meta);

  var panel=el('<div class="panel"></div>');
  // params
  var ps=el('<div class="sect"></div>');
  ps.appendChild(el('<h4>Parameters</h4>'));
  var pg=el('<div class="params"></div>');
  pg.appendChild(paramCol('Inputs (source)','io-in',g.params.filter(function(p){return p.dir==='source';})));
  pg.appendChild(paramCol('Outputs (target)','io-out',g.params.filter(function(p){return p.dir==='target';})));
  ps.appendChild(pg); panel.appendChild(ps);
  // calls
  var sem=g.calls.filter(function(c){return c.kind==='semantic';});
  var dt=g.calls.filter(function(c){return c.kind==='datatype';});
  var xx=g.calls.filter(function(c){return c.kind==='external';});
  panel.appendChild(callSect('Calls — semantic groups',sem,'Groups this group hands off to.'));
  panel.appendChild(callSect('Calls — datatypes used',dt,'Shared type-conversion groups invoked via then.'));
  if(xx.length) panel.appendChild(callSect('Calls — unresolved',xx,''));
  panel.appendChild(callSect('Called by',g.calledBy,'Groups that invoke this group.'));
  wrap.appendChild(panel);
  view.innerHTML=''; view.appendChild(wrap);
}
function paramCol(title,cls,items){
  var c=el('<div class="pcol '+cls+'"></div>');
  c.appendChild(el('<h5>'+esc(title)+' · '+items.length+'</h5>'));
  if(!items.length){ c.appendChild(el('<div class="empty-note">none</div>')); return c; }
  items.forEach(function(p){
    var r=el('<div class="prow"><span class="nm">'+esc(p.name)+'</span></div>');
    r.appendChild(el('<span class="ty">'+esc(p.type||'—')+'</span>'));
    c.appendChild(r);
  });
  return c;
}
function callSect(title,items,note){
  var s=el('<div class="sect"></div>');
  s.appendChild(el('<h4>'+esc(title)+' · '+items.length+'</h4>'));
  if(!items.length){ s.appendChild(el('<div class="empty-note">'+esc(note?('none — '+note):'none')+'</div>')); return s; }
  var chips=el('<div class="chips"></div>');
  items.slice().sort(byNameC).forEach(function(c){ chips.appendChild(linkChip(c)); });
  s.appendChild(chips);
  return s;
}
function byNameC(a,b){ return a.name<b.name?-1:a.name>b.name?1:0; }
function linkChip(c){
  var known=G.has(c.name);
  var cls='chip'+(c.kind==='datatype'?' dt':'')+(known?'':' x');
  var ch=el('<div class="'+cls+'" style="--h:'+hue(c.map||'')+'"><span class="sq"></span>'+esc(c.name)+'</div>');
  if(c.map) ch.appendChild(el('<span class="mm">'+esc(mapNameOf(c.map))+'</span>'));
  if(known) ch.onclick=function(){ go('#/group/'+c.name); };
  return ch;
}
function linkChipInline(name){
  var g=G.get(name); var known=!!g;
  var ch=el('<button class="chip'+(g&&g.kind==='datatype'?' dt':'')+(known?'':' x')+'" style="--h:'+hue(g?g.map:'')+';padding:2px 9px"><span class="sq"></span>'+esc(name)+'</button>');
  if(known) ch.onclick=function(){ go('#/group/'+name); };
  return ch;
}
function mapNameOf(file){ var m=MAPS.find(function(x){return x.file===file;}); return m?m.name:file; }

/* ---------- toggles ---------- */
function makeToggle(label,val,onchange){
  var l=el('<label class="toggle"><input type="checkbox"'+(val?' checked':'')+'><span class="track"></span><span>'+esc(label)+'</span></label>');
  l.querySelector('input').addEventListener('change',function(e){ onchange(e.target.checked); });
  return l;
}

/* ---------- search ---------- */
var q=document.getElementById('q'), results=document.getElementById('results'), rIdx=-1, rList=[];
function doSearch(){
  var term=q.value.trim().toLowerCase();
  if(!term){ results.classList.remove('show'); results.innerHTML=''; rList=[]; return; }
  rList=DATA.groups.filter(function(g){return g.name.toLowerCase().indexOf(term)>=0;})
    .sort(function(a,b){ return a.name.toLowerCase().indexOf(term)-b.name.toLowerCase().indexOf(term) || (a.name<b.name?-1:1); })
    .slice(0,12);
  results.innerHTML=''; rIdx=-1;
  rList.forEach(function(g,i){
    var b=el('<button><span class="sq" style="--h:'+hue(g.map)+';display:inline-block;width:8px;height:8px;border-radius:2px;background:hsl('+(g.kind==='datatype'?280:hue(g.map))+' 70% 55%)"></span> '+esc(g.name)+'<span class="rm">'+esc(g.kind)+' · '+esc(g.mapName)+'</span></button>');
    b.onmousedown=function(e){ e.preventDefault(); pick(i); };
    results.appendChild(b);
  });
  results.classList.toggle('show',rList.length>0);
}
function pick(i){ var g=rList[i]; if(!g)return; q.value=''; results.classList.remove('show'); go('#/group/'+g.name); }
q.addEventListener('input',doSearch);
q.addEventListener('keydown',function(e){
  if(!rList.length) return;
  if(e.key==='ArrowDown'){e.preventDefault();rIdx=Math.min(rIdx+1,rList.length-1);hi();}
  else if(e.key==='ArrowUp'){e.preventDefault();rIdx=Math.max(rIdx-1,0);hi();}
  else if(e.key==='Enter'){e.preventDefault();pick(rIdx<0?0:rIdx);}
  else if(e.key==='Escape'){results.classList.remove('show');q.blur();}
});
function hi(){ Array.from(results.children).forEach(function(b,i){ b.classList.toggle('active',i===rIdx); }); }
document.addEventListener('keydown',function(e){ if(e.key==='/'&&document.activeElement!==q){ e.preventDefault(); q.focus(); } });
document.addEventListener('click',function(e){ if(!results.contains(e.target)&&e.target!==q) results.classList.remove('show'); });

/* ---------- theme ---------- */
var themeBtn=document.getElementById('theme');
themeBtn.onclick=function(){
  var cur=document.documentElement.getAttribute('data-theme');
  var next = cur==='dark'?'light':(cur==='light'?'dark':(matchMedia('(prefers-color-scheme:dark)').matches?'light':'dark'));
  document.documentElement.setAttribute('data-theme',next);
};

/* ---------- dispatch ---------- */
function render(){
  var r=parse();
  window.scrollTo(0,0);
  if(r.v==='map') renderMap(r.file);
  else if(r.v==='group') renderGroup(r.name);
  else renderHome();
}
render();
})();
</script>
"""


# ==========================================================================
# Main
# ==========================================================================
def find_map_files(maps_dir: Path) -> list[Path]:
    files = sorted(p for p in maps_dir.iterdir()
                   if p.is_file() and p.suffix.lower() in {".map", ".fml"})
    return files


def main(argv: list[str]) -> int:
    repo_root = _HERE.parent.parent
    maps_dir = repo_root / "maps"
    docs_dir = repo_root / "documentation"
    if len(argv) > 1:
        maps_dir = Path(argv[1])
    if len(argv) > 2:
        docs_dir = Path(argv[2])

    if not maps_dir.is_dir():
        print(f"::error::maps directory not found: {maps_dir}", file=sys.stderr)
        return 1

    map_files = find_map_files(maps_dir)
    if not map_files:
        print(f"::warning::no .map/.fml files found in {maps_dir}", file=sys.stderr)

    maps: list[MapFile] = []
    for path in map_files:
        print(f"Parsing {path.name} …")
        mf = parse_map_file(path)
        for w in mf.warnings:
            print(f"::warning file=maps/{path.name}::{w}")
        maps.append(mf)

    model = Model(maps)
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "group_layout.md").write_text(render_layout_md(model), encoding="utf-8")
    (docs_dir / "group_parameters.md").write_text(render_params_md(model), encoding="utf-8")
    (docs_dir / "group_layout.json").write_text(render_json(model), encoding="utf-8")
    (docs_dir / "group_layout.html").write_text(render_html(model), encoding="utf-8")

    print(f"Wrote {len(model.groups)} groups from {len(maps)} maps to {docs_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
