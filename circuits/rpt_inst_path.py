#!/usr/bin/env python3
import re
import sys
import argparse
from collections import defaultdict


SUBCKT_RE = re.compile(r'^\s*\.subckt\s+(\S+)\b', re.IGNORECASE)
ENDS_RE   = re.compile(r'^\s*\.ends\b', re.IGNORECASE)
XLINE_RE  = re.compile(r'^\s*x', re.IGNORECASE)


def strip_comment(line: str) -> str:
    s = line.rstrip("\n")

    if re.match(r'^\s*\*', s):
        return ""

    s = re.sub(r'//.*$', '', s)
    return s.rstrip()


def logical_lines(lines):
    """
    Join continuation lines starting with '+'.
    """
    buf = ""
    for raw in lines:
        line = strip_comment(raw)
        if not line.strip():
            continue

        if re.match(r'^\s*\+', line):
            cont = re.sub(r'^\s*\+\s*', '', line)
            if buf:
                buf += " " + cont
            else:
                buf = cont
        else:
            if buf:
                yield buf
            buf = line.strip()

    if buf:
        yield buf


def extract_instantiated_cell(tokens):
    """
    Return the instantiated subckt name from an X-instance line.

    Strategy:
    - tokens[0] is the instance name
    - scan from the right
    - skip trailing metadata / params / options
    - first remaining token is the instantiated subckt name
    """
    if len(tokens) < 2:
        return None

    for i in range(len(tokens) - 1, 0, -1):
        t = tokens[i]

        if t.startswith("$"):
            continue

        if "=" in t and not t.startswith("="):
            continue

        if re.fullmatch(r'[^A-Za-z0-9_.<>/\[\]-]+', t):
            continue

        return t

    return None


def maybe_drop_x(name, dropx):
    if dropx and re.match(r'^[Xx]', name):
        return name[1:]
    return name


def dedupe_preserve_order(items):
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def parse_netlist(path):
    """
    Parse the netlist into instance edges.

    Each edge is:
      {
        "parent_cell": <enclosing subckt name or None for top-level>,
        "inst_name":   <instance name>,
        "child_cell":  <instantiated cell name>
      }

    Returns:
      defined_subckts
      all_edges
      children_by_parent   : parent_cell -> [edge, ...]
      parents_by_child     : child_cell  -> [edge, ...]
      top_level_by_cell    : child_cell  -> [edge, ...]   (subset where parent_cell is None)
    """
    defined_subckts = set()
    raw_edges = []

    current_subckt = None

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in logical_lines(f):
            m = SUBCKT_RE.match(line)
            if m:
                current_subckt = m.group(1)
                defined_subckts.add(current_subckt)
                continue

            if ENDS_RE.match(line):
                current_subckt = None
                continue

            if XLINE_RE.match(line):
                tokens = line.split()
                if len(tokens) < 2:
                    continue

                inst_name = tokens[0]
                child_cell = extract_instantiated_cell(tokens)
                if not child_cell:
                    continue

                raw_edges.append({
                    "parent_cell": current_subckt,
                    "inst_name": inst_name,
                    "child_cell": child_cell,
                })

    children_by_parent = defaultdict(list)
    parents_by_child = defaultdict(list)
    top_level_by_cell = defaultdict(list)

    for edge in raw_edges:
        child_cell = edge["child_cell"]
        parent_cell = edge["parent_cell"]

        if child_cell not in defined_subckts:
            continue

        if parent_cell is None:
            top_level_by_cell[child_cell].append(edge)
        else:
            children_by_parent[parent_cell].append(edge)

        parents_by_child[child_cell].append(edge)

    for s in defined_subckts:
        children_by_parent.setdefault(s, [])
        parents_by_child.setdefault(s, [])
        top_level_by_cell.setdefault(s, [])

    return defined_subckts, raw_edges, children_by_parent, parents_by_child, top_level_by_cell


def format_normal_path(root_cell, inst_names, dropx=False):
    parts = [root_cell] + [maybe_drop_x(x, dropx) for x in inst_names]
    return "/".join(parts)


def format_inst_path(inst_names, dropx=False):
    parts = [maybe_drop_x(x, dropx) for x in inst_names]
    return "/".join(parts)


def find_matches_under_top(children_by_parent, top_cell, target_cell):
    """
    Top-down from explicit top cell.

    Returns list of tuples:
      (root_cell_name, [inst1, inst2, ...])
    """
    results = []

    def dfs(current_cell, inst_path, active_cells):
        if current_cell in active_cells:
            return

        active_cells.add(current_cell)

        for edge in children_by_parent.get(current_cell, []):
            child_cell = edge["child_cell"]
            inst_name = edge["inst_name"]
            new_inst_path = inst_path + [inst_name]

            if child_cell == target_cell:
                results.append((top_cell, new_inst_path))

            dfs(child_cell, new_inst_path, active_cells)

        active_cells.remove(current_cell)

    dfs(top_cell, [], set())
    return results


def build_upward_cell_and_inst_prefixes(parents_by_child, start_cell):
    """
    Build all maximal upward prefixes ending at start_cell.

    Returns a list of tuples:
      (root_cell_name, [inst1, inst2, ..., inst_into_start_cell])
    """
    results = []

    def rec(current_cell, suffix_inst_names, active_cells):
        if current_cell in active_cells:
            return

        active_cells.add(current_cell)

        parent_edges = parents_by_child.get(current_cell, [])
        internal_parents = [e for e in parent_edges if e["parent_cell"] is not None]

        if internal_parents:
            for edge in internal_parents:
                rec(
                    edge["parent_cell"],
                    suffix_inst_names + [edge["inst_name"]],
                    active_cells,
                )
        else:
            results.append((current_cell, list(reversed(suffix_inst_names))))

        active_cells.remove(current_cell)

    rec(start_cell, [], set())
    return results


def find_matches_without_top(parents_by_child, target_cell):
    """
    Without explicit --top, report all maximal paths.

    Returns list of tuples:
      (root_cell_name, [inst1, inst2, ..., inst_target])
    """
    results = []

    for match_edge in parents_by_child.get(target_cell, []):
        parent_cell = match_edge["parent_cell"]
        match_inst = match_edge["inst_name"]

        if parent_cell is None:
            results.append((target_cell, [match_inst]))
            continue

        prefixes = build_upward_cell_and_inst_prefixes(parents_by_child, parent_cell)
        for root_cell, inst_names in prefixes:
            results.append((root_cell, inst_names + [match_inst]))

    return results


def expand_to_inst_paths(path_records, top_level_by_cell):
    """
    Convert logical paths:
      (root_cell, [inst1, inst2, ...])
    into pure instance-name paths:
      [root_inst, inst1, inst2, ...]
    """
    out = []

    for root_cell, tail_inst_names in path_records:
        root_edges = top_level_by_cell.get(root_cell, [])
        for edge in root_edges:
            out.append([edge["inst_name"]] + tail_inst_names)

    return out


def main():
    ap = argparse.ArgumentParser(
        description=(
            "Report hierarchical paths of all instances of --cell. "
            "Default output uses root cell name followed by instance names. "
            "With --instpath, output uses instance names only."
        )
    )
    ap.add_argument("netlist", help="Input SPICE netlist")
    ap.add_argument("--top", help="Top cell name")
    ap.add_argument("--cell", required=True, help="Target cell name")
    ap.add_argument(
        "--dropx",
        action="store_true",
        help="Drop a leading X or x from each reported instance name"
    )
    ap.add_argument(
        "--instpath",
        action="store_true",
        help="Report a pure instance-name path; prepend the top-level instance of the root cell"
    )
    args = ap.parse_args()

    (
        defined_subckts,
        _all_edges,
        children_by_parent,
        parents_by_child,
        top_level_by_cell,
    ) = parse_netlist(args.netlist)

    if args.cell not in defined_subckts:
        sys.stderr.write(
            f'Warning: target cell "{args.cell}" is not defined as a .subckt in the netlist\n'
        )

    if args.top:
        if args.top not in defined_subckts:
            sys.stderr.write(f'Error: top cell "{args.top}" is not defined in the netlist\n')
            sys.exit(1)

        logical_paths = find_matches_under_top(children_by_parent, args.top, args.cell)
        logical_paths = [(root, tail) for (root, tail) in logical_paths if root == args.top]
    else:
        logical_paths = find_matches_without_top(parents_by_child, args.cell)

    if args.instpath:
        if args.top:
            top_instances = top_level_by_cell.get(args.top, [])
            if len(top_instances) > 1:
                sys.stderr.write(
                    f'Warning: multiple top-level instances of top cell "{args.top}" found; '
                    f'all corresponding instance-rooted paths will be reported\n'
                )

        inst_paths = expand_to_inst_paths(logical_paths, top_level_by_cell)

        if args.top:
            allowed_root_insts = {edge["inst_name"] for edge in top_level_by_cell.get(args.top, [])}
            inst_paths = [p for p in inst_paths if p and p[0] in allowed_root_insts]

        output_lines = [format_inst_path(p, dropx=args.dropx) for p in inst_paths]
    else:
        print("Note: use --instpath to report pure instance-name paths.")
        output_lines = [
            format_normal_path(root, insts, dropx=args.dropx)
            for (root, insts) in logical_paths
        ]

    output_lines = dedupe_preserve_order(output_lines)

    for line in output_lines:
        print(line)


if __name__ == "__main__":
    main()
