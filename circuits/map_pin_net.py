#!/usr/bin/env python3
import argparse
import re
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


SUBCKT_RE = re.compile(r"^\s*\.subckt\s+(\S+)(.*)$", re.IGNORECASE)
ENDS_RE   = re.compile(r"^\s*\.ends\b", re.IGNORECASE)


@dataclass
class Inst:
    name: str
    cell: str
    nets: List[str]
    line_no: int
    raw: str


@dataclass
class Subckt:
    name: str
    pins: List[str]
    lines: List[Tuple[int, str]] = field(default_factory=list)
    insts: List[Inst] = field(default_factory=list)


@dataclass
class Occurrence:
    hier_inst: str
    inst_name: str
    cell: str
    pin_to_hnet: Dict[str, str]
    line_no: int


def strip_inline_comment(line: str) -> str:
    """
    Conservative comment handling:
      * full-line comments starting with '*' are removed elsewhere
      * inline '$' comments are stripped
    """
    if "$" in line:
        line = line.split("$", 1)[0]
    return line.rstrip()


def logical_lines(path: str) -> List[Tuple[int, str]]:
    """
    Return HSPICE-style logical lines with '+' continuations joined.

    Full-line comments beginning with '*' are ignored.
    Blank lines are ignored.
    """
    out: List[Tuple[int, str]] = []
    cur = ""
    cur_line_no = 0

    with open(path, "r", errors="replace") as f:
        for line_no, raw in enumerate(f, 1):
            s = raw.rstrip("\n")

            if not s.strip():
                continue

            if s.lstrip().startswith("*"):
                continue

            s = strip_inline_comment(s)

            if not s.strip():
                continue

            stripped = s.lstrip()

            if stripped.startswith("+"):
                cont = stripped[1:].strip()
                if cur:
                    cur += " " + cont
                else:
                    # Continuation without a previous line; keep it as its own line.
                    cur = cont
                    cur_line_no = line_no
                continue

            if cur:
                out.append((cur_line_no, cur.strip()))

            cur = s.strip()
            cur_line_no = line_no

    if cur:
        out.append((cur_line_no, cur.strip()))

    return out


def split_tokens(line: str) -> List[str]:
    return line.split()


def collect_subckts_and_top_lines(
    lines: List[Tuple[int, str]]
) -> Tuple[Dict[str, Subckt], List[Tuple[int, str]]]:
    """
    First pass:
      * collect .subckt definitions and their body lines
      * collect top-level lines outside any .subckt
    """
    subckts: Dict[str, Subckt] = {}
    top_lines: List[Tuple[int, str]] = []

    current: Optional[Subckt] = None

    for line_no, line in lines:
        m = SUBCKT_RE.match(line)

        if m:
            if current is not None:
                raise SystemExit(
                    f"Error: nested .subckt at line {line_no}; currently inside {current.name}"
                )

            name = m.group(1)
            rest = m.group(2).strip()
            pins = split_tokens(rest)

            if name in subckts:
                raise SystemExit(f"Error: duplicate .subckt definition for {name} at line {line_no}")

            current = Subckt(name=name, pins=pins)
            subckts[name] = current
            continue

        if ENDS_RE.match(line):
            if current is None:
                raise SystemExit(f"Error: .ends without .subckt at line {line_no}")
            current = None
            continue

        if current is not None:
            current.lines.append((line_no, line))
        else:
            top_lines.append((line_no, line))

    if current is not None:
        raise SystemExit(f"Error: missing .ends for .subckt {current.name}")

    return subckts, top_lines


def parse_x_instance(
    line_no: int,
    line: str,
    subckts: Dict[str, Subckt],
) -> Optional[Inst]:
    """
    Parse only subckt instances.

    Expected form:

        Xname net1 net2 ... cellname [params...]

    The cell name is recognized by matching token[1 + pin_count] against
    a known .subckt name.

    Primitives and undefined subckts are ignored.
    """
    toks = split_tokens(line)
    if not toks:
        return None

    name = toks[0]

    if not name.lower().startswith("x"):
        return None

    matches: List[Tuple[str, List[str]]] = []

    for cell, sub in subckts.items():
        idx = 1 + len(sub.pins)
        if len(toks) > idx and toks[idx] == cell:
            nets = toks[1:idx]
            matches.append((cell, nets))

    if not matches:
        return None

    if len(matches) > 1:
        cells = ", ".join(c for c, _ in matches)
        raise SystemExit(
            f"Error: ambiguous subckt instance at line {line_no}; could match: {cells}\n"
            f"  {line}"
        )

    cell, nets = matches[0]
    return Inst(name=name, cell=cell, nets=nets, line_no=line_no, raw=line)


def parse_instances_in_subckts(subckts: Dict[str, Subckt]) -> None:
    for sub in subckts.values():
        for line_no, line in sub.lines:
            inst = parse_x_instance(line_no, line, subckts)
            if inst is not None:
                sub.insts.append(inst)


def parse_top_instances(
    top_lines: List[Tuple[int, str]],
    subckts: Dict[str, Subckt],
) -> List[Inst]:
    out: List[Inst] = []
    for line_no, line in top_lines:
        inst = parse_x_instance(line_no, line, subckts)
        if inst is not None:
            out.append(inst)
    return out


def hier_join(parts: List[str]) -> str:
    return ".".join(p for p in parts if p)


def resolve_net(
    local_net: str,
    scope_path: List[str],
    formal_to_parent_hnet: Dict[str, str],
) -> str:
    """
    Resolve a net appearing inside the current subckt scope.

    If it is a formal pin of the current subckt, return the already-resolved
    parent hierarchical net.

    Otherwise:
      * inside XTOP scope: XTOP.local
      * inside XTOP.X1 scope: XTOP.X1.local
      * top-level nets connected to XTOP pins remain bare, e.g. IN, OUT
    """
    if local_net in formal_to_parent_hnet:
        return formal_to_parent_hnet[local_net]

    if scope_path:
        return hier_join(scope_path + [local_net])

    return local_net


def walk_scope(
    subckts: Dict[str, Subckt],
    cell: str,
    scope_path: List[str],
    formal_to_parent_hnet: Dict[str, str],
    occurrences: List[Occurrence],
) -> None:
    sub = subckts[cell]

    for inst in sub.insts:
        child_sub = subckts[inst.cell]

        pin_to_hnet: Dict[str, str] = {}
        for pin, net in zip(child_sub.pins, inst.nets):
            pin_to_hnet[pin] = resolve_net(net, scope_path, formal_to_parent_hnet)

        hier_inst = hier_join(scope_path + [inst.name])

        occurrences.append(
            Occurrence(
                hier_inst=hier_inst,
                inst_name=inst.name,
                cell=inst.cell,
                pin_to_hnet=pin_to_hnet,
                line_no=inst.line_no,
            )
        )

        # Descend into this instance.
        walk_scope(
            subckts=subckts,
            cell=inst.cell,
            scope_path=scope_path + [inst.name],
            formal_to_parent_hnet=pin_to_hnet,
            occurrences=occurrences,
        )


def build_design_occurrences(
    subckts: Dict[str, Subckt],
    top_insts: List[Inst],
    topinst_name: str,
) -> List[Occurrence]:
    top = None
    for inst in top_insts:
        if inst.name == topinst_name:
            top = inst
            break

    if top is None:
        candidates = ", ".join(i.name for i in top_insts) or "(none)"
        raise SystemExit(
            f"Error: --topinst {topinst_name!r} was not found as a top-level subckt instance.\n"
            f"Top-level subckt instances found: {candidates}"
        )

    top_sub = subckts[top.cell]

    if len(top.nets) != len(top_sub.pins):
        raise SystemExit(
            f"Internal error: top instance {top.name} pin count mismatch at line {top.line_no}"
        )

    # Top-level nets stay bare.
    top_pin_to_hnet = dict(zip(top_sub.pins, top.nets))

    occurrences: List[Occurrence] = []

    # Include the top instance itself as an occurrence too.
    occurrences.append(
        Occurrence(
            hier_inst=top.name,
            inst_name=top.name,
            cell=top.cell,
            pin_to_hnet=top_pin_to_hnet,
            line_no=top.line_no,
        )
    )

    walk_scope(
        subckts=subckts,
        cell=top.cell,
        scope_path=[top.name],
        formal_to_parent_hnet=top_pin_to_hnet,
        occurrences=occurrences,
    )

    return occurrences


def query_cell_pin(occurrences: List[Occurrence], query: str) -> int:
    cell, pin = query.split(":", 1)

    hits = [
        occ for occ in occurrences
        if occ.cell == cell and pin in occ.pin_to_hnet
    ]

    if not hits:
        print(f"No matches for {cell}:{pin}")
        return 1

    print(f"{cell}:{pin}")
    print("-" * len(f"{cell}:{pin}"))

    for occ in hits:
        print(f"{occ.hier_inst:<50} {cell}:{pin} -> {occ.pin_to_hnet[pin]}")

    return 0


def query_node(occurrences: List[Occurrence], node: str) -> int:
    hits: List[Tuple[Occurrence, str]] = []

    for occ in occurrences:
        for pin, hnet in occ.pin_to_hnet.items():
            if hnet == node:
                hits.append((occ, pin))

    if not hits:
        print(f"No instance pins connect to node {node}")
        return 1

    print(node)
    print("-" * len(node))

    for occ, pin in hits:
        print(f"{occ.hier_inst:<50} {occ.cell}:{pin} -> {node}")

    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Query hierarchical connectivity in an HSPICE-style .subckt/.ends netlist. "
            "Only X... subckt instances with definitions present in the file are reported."
        )
    )

    ap.add_argument(
        "--topinst",
        required=True,
        help="Name of the top-level instance to use as the hierarchy root, e.g. XTOP",
    )

    ap.add_argument(
        "netlist",
        help="Path to HSPICE-style netlist",
    )

    ap.add_argument(
        "query",
        help=(
            "Either cellname:pin_name, or a hierarchical node name such as "
            "XTOP.X1.net. A node with no period is treated as a top-level node."
        ),
    )

    args = ap.parse_args()

    lines = logical_lines(args.netlist)
    subckts, top_lines = collect_subckts_and_top_lines(lines)
    parse_instances_in_subckts(subckts)
    top_insts = parse_top_instances(top_lines, subckts)

    occurrences = build_design_occurrences(
        subckts=subckts,
        top_insts=top_insts,
        topinst_name=args.topinst,
    )

    if ":" in args.query:
        cell, pin = args.query.split(":", 1)
        if not cell or not pin:
            raise SystemExit("Error: cell pin query must be of form cellname:pin_name")
        return query_cell_pin(occurrences, args.query)

    return query_node(occurrences, args.query)


if __name__ == "__main__":
    sys.exit(main())
