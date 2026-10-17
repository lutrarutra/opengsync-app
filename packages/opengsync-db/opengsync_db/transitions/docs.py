"""Renders the generated part of docs/state-transitions.md from the registry.

    python -m opengsync_db.transitions.docs            # print the generated markdown
    python -m opengsync_db.transitions.docs --check    # exit 1 if the doc is out of date
    python -m opengsync_db.transitions.docs --write    # update the doc in place
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

from .core import ANY, NEW, Effect, Entity, Operation, spec_str
from .registry import GRAPH_KINDS, Registry, registry

BEGIN = "<!-- BEGIN GENERATED: transitions (python -m opengsync_db.transitions.docs --write) -->"
END = "<!-- END GENERATED: transitions -->"
DEFAULT_PATH = Path("docs/state-transitions.md")

_AREAS = {
    "request": "Requests", "receipt": "Receipt", "prep": "Lab prep", "mux": "Lab prep", "pool": "Pools", "qc": "QC measurements",
    "experiment": "Sequencing", "library": "Libraries", "project": "Projects", "api": "API", "worker": "Worker",
    "manual": "Manual edits", "migration": "Migrations", "system": "System",
}


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _anchor(text: str) -> str:
    return "".join(c for c in text.lower().replace(" ", "-") if c.isalnum() or c in "-_")


def _effect(eff: Effect) -> str:
    s = f"{eff.entity.label}: {spec_str(eff.src)} → {'chosen' if eff.dst is ANY else spec_str(eff.dst)}"
    if eff.via != "self":
        s += f" <sub>via `{eff.via}`</sub>"
    if eff.when:
        s += f" — {eff.when}"
    if eff.gap:
        s += f" ⚠️ {eff.gap}"
    return _cell(s)


def _mermaid(reg: Registry, entity: Entity) -> list[str]:
    labels: dict[tuple[str, str], list[str]] = defaultdict(list)
    for op in reg.operations.values():
        if op.kind not in GRAPH_KINDS:
            continue
        for eff in op.effects_on(entity):
            if eff.dst is ANY:
                continue
            srcs = ["any"] if eff.src is ANY else ["[*]" if s is NEW else s.name for s in sorted(eff.src, key=lambda s: -1 if s is None else s.id)]  # type: ignore[union-attr]
            for src in srcs:
                for dst in sorted(eff.dst, key=lambda s: s.id):  # type: ignore[union-attr]
                    if src != dst.name and op.id not in labels[(src, dst.name)]:
                        labels[(src, dst.name)].append(op.id)
    lines = ["```mermaid", "stateDiagram-v2"]
    if any(src == "any" for src, _ in labels):
        lines.append("    state \"any status\" as any")
    for (src, dst), ops in sorted(labels.items()):
        lines.append(f"    {src} --> {dst} : {', '.join(ops)}")
    lines.append("```")
    return lines


def _entity_section(reg: Registry, entity: Entity) -> list[str]:
    set_by: dict = defaultdict(list)
    for op in reg.operations.values():
        if op.kind not in GRAPH_KINDS:
            continue
        for eff in op.effects_on(entity):
            if eff.dst is not ANY:
                for s in eff.dst:  # type: ignore[union-attr]
                    if op.id not in set_by[s]:
                        set_by[s].append(op.id)
    unused = dict(entity.unused)
    lines = [f"### {entity.label}", "", f"Table `{entity.name}`, enum `{entity.status_enum.__name__}`" + (" (nullable)" if entity.nullable else "") + ".", ""]
    lines += ["| Status | Id | Description | Set by |", "|---|---|---|---|"]
    for status in entity.status_enum:
        if status in unused:
            how = f"⚠️ {unused[status]}"
        elif status in entity.manual_only:
            how = "by hand only (edit form or chosen status)"
        else:
            how = ", ".join(f"`{id}`" for id in set_by[status])
        desc = getattr(status, "description", "")
        lines.append(f"| {status.name} | {status.id} | {_cell(desc)} | {_cell(how)} |")
    lines += [""] + _mermaid(reg, entity) + [""]
    return lines


def _operation_rows(ops: list[Operation]) -> list[str]:
    lines = ["| Operation | Kind | Effects | Guard / reason | Where |", "|---|---|---|---|---|"]
    for op in ops:
        effects = "<br>".join(_effect(e) for e in op.effects) or "—"
        notes = []
        if op.guard is not None:
            notes.append(f"guard: {op.guard.describe()}")
        if op.reason:
            notes.append(f"reason: “{op.reason}”")
        if op.gap:
            notes.append(f"⚠️ {op.gap}")
        if op.doc:
            notes.append(op.doc)
        where = "<br>".join(f"`{w}`" for w in op.where) or "—"
        lines.append(f"| `{op.id}`<br>{_cell(op.label)} | {op.kind.label} | {effects} | {_cell('<br>'.join(notes)) or '—'} | {where} |")
    return lines


def render(reg: Registry | None = None) -> str:
    reg = reg or registry()
    lines: list[str] = [BEGIN, "", "## Entities and states", ""]
    lines.append("Diagrams show process edges only: actions, workflows, API calls and worker rules. "
                 "Manual edits (any → any), chosen statuses and migrations are listed in the operations table.")
    lines.append("")
    for entity in reg.entities:
        lines += _entity_section(reg, entity)

    lines += ["## Operations", ""]
    by_area: dict[str, list[Operation]] = defaultdict(list)
    for op in reg.operations.values():
        by_area[_AREAS.get(op.area, op.area)].append(op)
    for area, ops in by_area.items():
        lines += [f"### {area}", ""] + _operation_rows(ops) + [""]

    lines += ["## Routes", ""]
    for route in reg.routes.values():
        lines += [f"### {route.label} (`{route.id}`)", "", f"Applies when: {route.applies.describe()}."]
        if route.doc:
            lines += ["", route.doc]
        lines += ["", "| # | Step | Done when | Ways |", "|---|---|---|---|"]
        for i, step in enumerate(route.steps, 1):
            label = step.label + (" *(optional)*" if step.optional else "")
            ways = ", ".join(f"`{a}`" for a in step.alternatives)
            lines.append(f"| {i} | {_cell(label)} | {_cell(step.done_when.describe())} | {ways} |")
        lines.append("")

    lines += ["## Known gaps", "", "Behaviour that the registry documents as it is, and that looks wrong. Fixing one is a separate decision.", ""]
    lines += ["| Where | Gap |", "|---|---|"]
    for where, text in reg.gaps():
        lines.append(f"| {_cell(where)} | {_cell(text)} |")
    lines += ["", END]
    return "\n".join(lines) + "\n"


def replace_generated(document: str, generated: str) -> str:
    start, end = document.find(BEGIN), document.find(END)
    if start == -1 or end == -1 or end < start:
        raise ValueError("generated markers not found in document")
    return document[:start] + generated.rstrip("\n") + document[end + len(END):]


def extract_generated(document: str) -> str:
    start, end = document.find(BEGIN), document.find(END)
    if start == -1 or end == -1:
        raise ValueError("generated markers not found in document")
    return document[start:end + len(END)] + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--path", type=Path, default=DEFAULT_PATH)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--write", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    reg = registry()
    reg.validate()
    generated = render(reg)
    if not args.write and not args.check:
        sys.stdout.write(generated)
        return 0
    document = args.path.read_text()
    if args.check:
        if extract_generated(document) != generated:
            print(f"{args.path} is out of date; run python -m opengsync_db.transitions.docs --write", file=sys.stderr)
            return 1
        return 0
    args.path.write_text(replace_generated(document, generated))
    return 0


if __name__ == "__main__":
    sys.exit(main())

