#!/usr/bin/env python3
import re
import sys
import argparse
from collections import defaultdict
from difflib import SequenceMatcher


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


def instname_matches(inst_name, target_instname, dropx=False):
    """
    Match an instance name supplied by --instname.

    Normally this is an exact match against the raw instance name.
    With --dropx, also allow the user to provide the post-drop form.
    Example: --instname U1 --dropx matches both U1 and XU1.
    """
    if inst_name == target_instname:
        return True

    if dropx and maybe_drop_x(inst_name, True) == target_instname:
        return True

    return False




def collect_instance_names(all_edges):
    """
    Return all parsed X-instance names from the netlist.

    This intentionally ignores scope. It is used only for diagnostics when
    --instname produces no exact path matches.
    """
    return dedupe_preserve_order(edge["inst_name"] for edge in all_edges)


def closest_instance_names(target_instname, all_edges, dropx=False, limit=3):
    """
    Return up to `limit` closest raw instance names for diagnostics.

    With --dropx, compare using the post-drop form, but print the raw name so
    the user can grep for the real netlist instance.
    """
    candidates = collect_instance_names(all_edges)
    if not candidates:
        return []

    # Rank all candidates instead of relying only on get_close_matches so we
    # always get the best available suggestions, even for short instance names.
    target_cmp = maybe_drop_x(target_instname, True) if dropx else target_instname
    ranked = []

    for cand in candidates:
        cand_cmp = maybe_drop_x(cand, True) if dropx else cand
        ratio = SequenceMatcher(None, target_cmp, cand_cmp).ratio()
        ranked.append((ratio, cand))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [cand for _ratio, cand in ranked[:limit]]

def collect_top_level_instance_names(top_level_by_cell):
    """
    Return top-level X-instance names that instantiate defined .subckt cells.

    These are the names accepted by --topinst for hierarchy traversal.
    """
    names = []
    for edges in top_level_by_cell.values():
        for edge in edges:
            names.append(edge["inst_name"])
    return dedupe_preserve_order(names)


def closest_names(target_name, candidates, limit=3):
    """
    Return up to `limit` closest names from candidates.

    This diagnostic intentionally does raw string comparison only. It does not
    apply --dropx and does not change exact-match behavior.
    """
    candidates = dedupe_preserve_order(candidates)
    ranked = []
    for cand in candidates:
        ratio = SequenceMatcher(None, target_name, cand).ratio()
        ranked.append((ratio, cand))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [cand for _ratio, cand in ranked[:limit]]


def print_closest_topinst_diagnostic(target_topinst, top_level_by_cell, limit=3):
    """
    Print closest --topinst suggestions after exact --topinst resolution fails.
    """
    close = closest_names(
        target_topinst,
        collect_top_level_instance_names(top_level_by_cell),
        limit=limit,
    )
    if close:
        sys.stderr.write('Closest top-level instance name(s):\n')
        for name in close:
            sys.stderr.write(f'  {name}\n')


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
                             Includes primitive/non-subckt X-lines as leaves.
      parents_by_child     : child_cell  -> [edge, ...]
                             Only includes edges whose child_cell is a defined .subckt.
      top_level_by_cell    : child_cell  -> [edge, ...]   (subset where parent_cell is None)
                             Only includes edges whose child_cell is a defined .subckt.
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
        child_is_subckt = child_cell in defined_subckts

        # Keep all X-lines inside subckts in children_by_parent so --instname
        # can find primitive/PCell/model instances such as MOSFETs.
        # Only defined-subckt children can be traversed further.
        if parent_cell is not None:
            children_by_parent[parent_cell].append(edge)
        elif child_is_subckt:
            top_level_by_cell[child_cell].append(edge)

        # Upward hierarchy and top-level scoping require a defined child subckt.
        if child_is_subckt:
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


def find_cell_matches_under_top(children_by_parent, top_cell, target_cell):
    """
    Top-down from explicit top cell, finding instances whose child cell is target_cell.

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


def find_instname_matches_under_top(children_by_parent, top_cell, target_instname, dropx=False):
    """
    Top-down from explicit top cell, finding instances whose name matches target_instname.

    Returns list of tuples:
      (root_cell_name, [inst1, inst2, ..., matched_inst])
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

            if instname_matches(inst_name, target_instname, dropx=dropx):
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


def find_cell_matches_without_top(parents_by_child, target_cell):
    """
    Without explicit --top, report all maximal paths to instances of target_cell.

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


def find_instname_matches_without_top(all_edges, parents_by_child, target_instname, dropx=False):
    """
    Without explicit --top, report all maximal paths to instances named target_instname.

    Returns list of tuples:
      (root_cell_name, [inst1, inst2, ..., matched_inst])
    """
    results = []

    for match_edge in all_edges:
        # Ignore primitive/non-subckt instances, matching the rest of this script's hierarchy model.
        if match_edge["child_cell"] not in parents_by_child:
            continue

        if not instname_matches(match_edge["inst_name"], target_instname, dropx=dropx):
            continue

        parent_cell = match_edge["parent_cell"]
        match_inst = match_edge["inst_name"]

        if parent_cell is None:
            results.append((match_edge["child_cell"], [match_inst]))
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


def find_top_level_instance_edges(top_level_by_cell, target_topinst, dropx=False):
    """
    Find top-level X-instances whose instance name matches target_topinst.

    With --dropx, also allow the user to provide the post-drop form.
    Example: --topinst top --dropx matches a top-level instance named Xtop.
    """
    matches = []
    for edges in top_level_by_cell.values():
        for edge in edges:
            if instname_matches(edge["inst_name"], target_topinst, dropx=dropx):
                matches.append(edge)
    return matches


def filter_inst_paths_by_allowed_roots(inst_paths, allowed_root_insts):
    """
    Keep only pure instance paths whose first element is one of allowed_root_insts.
    """
    return [p for p in inst_paths if p and p[0] in allowed_root_insts]


def main():
    ap = argparse.ArgumentParser(
        description=(
            "Report hierarchical paths to matching instances. "
            "Search by instantiated cell with --cell or by instance name with --instname. "
            "Scope the search with --topcell <cell_name> or --topinst <top_level_instance_name>. "
            "Default output uses root cell name followed by instance names. "
            "With --instpath, output uses instance names only."
        )
    )
    ap.add_argument("netlist", help="Input SPICE netlist")

    scope = ap.add_mutually_exclusive_group()
    scope.add_argument(
        "--topcell",
        help="Top subckt/cell name to start traversal from"
    )
    scope.add_argument(
        "--topinst",
        help=(
            "Top-level instance name to start traversal from. "
            "The instance must appear outside any .subckt."
        )
    )

    target = ap.add_mutually_exclusive_group(required=True)
    target.add_argument("--cell", help="Target instantiated cell / subckt name")
    target.add_argument("--instname", help="Target instance name")

    ap.add_argument(
        "--dropx",
        action="store_true",
        help=(
            "Drop a leading X or x from each reported instance name. "
            "When used with --instname or --topinst, also lets the search name be the post-drop form."
        )
    )
    ap.add_argument(
        "--instpath",
        action="store_true",
        help=(
            "Report a pure instance-name path. "
            "With --topcell, prepend matching top-level instance(s) of that cell. "
            "With --topinst, prepend that selected top-level instance."
        )
    )
    args = ap.parse_args()

    (
        defined_subckts,
        all_edges,
        children_by_parent,
        parents_by_child,
        top_level_by_cell,
    ) = parse_netlist(args.netlist)

    if args.cell and args.cell not in defined_subckts:
        sys.stderr.write(
            f'Warning: target cell "{args.cell}" is not defined as a .subckt in the netlist\n'
        )

    selected_topinst_edges = []
    selected_topinst_inst_paths = []

    if args.topcell:
        if args.topcell not in defined_subckts:
            sys.stderr.write(f'Error: top cell "{args.topcell}" is not defined in the netlist\n')
            sys.exit(1)

        if args.cell:
            logical_paths = find_cell_matches_under_top(children_by_parent, args.topcell, args.cell)
        else:
            logical_paths = find_instname_matches_under_top(
                children_by_parent,
                args.topcell,
                args.instname,
                dropx=args.dropx,
            )

        logical_paths = [(root, tail) for (root, tail) in logical_paths if root == args.topcell]

    elif args.topinst:
        selected_topinst_edges = find_top_level_instance_edges(
            top_level_by_cell,
            args.topinst,
            dropx=args.dropx,
        )

        if not selected_topinst_edges:
            sys.stderr.write(
                f'Error: top-level instance "{args.topinst}" was not found in the netlist\n'
            )
            print_closest_topinst_diagnostic(args.topinst, top_level_by_cell, limit=3)
            sys.exit(1)

        if len(selected_topinst_edges) > 1:
            sys.stderr.write(
                f'Warning: multiple top-level instances matched "{args.topinst}"; '
                f'all corresponding instance-rooted paths will be reported\n'
            )

        logical_paths = []
        selected_topinst_inst_paths = []

        for top_edge in selected_topinst_edges:
            top_cell = top_edge["child_cell"]

            if args.cell:
                edge_paths = find_cell_matches_under_top(children_by_parent, top_cell, args.cell)
            else:
                edge_paths = find_instname_matches_under_top(
                    children_by_parent,
                    top_cell,
                    args.instname,
                    dropx=args.dropx,
                )

            edge_paths = [(root, tail) for (root, tail) in edge_paths if root == top_cell]
            logical_paths.extend(edge_paths)

            for _root, tail_inst_names in edge_paths:
                selected_topinst_inst_paths.append([top_edge["inst_name"]] + tail_inst_names)

    else:
        if args.cell:
            logical_paths = find_cell_matches_without_top(parents_by_child, args.cell)
        else:
            logical_paths = find_instname_matches_without_top(
                all_edges,
                parents_by_child,
                args.instname,
                dropx=args.dropx,
            )

    if args.instpath:
        if args.topcell:
            top_instances = top_level_by_cell.get(args.topcell, [])
            if len(top_instances) > 1:
                sys.stderr.write(
                    f'Warning: multiple top-level instances of top cell "{args.topcell}" found; '
                    f'all corresponding instance-rooted paths will be reported\n'
                )

        if args.topinst:
            inst_paths = selected_topinst_inst_paths
        else:
            inst_paths = expand_to_inst_paths(logical_paths, top_level_by_cell)

            if args.topcell:
                allowed_root_insts = {edge["inst_name"] for edge in top_level_by_cell.get(args.topcell, [])}
                inst_paths = filter_inst_paths_by_allowed_roots(inst_paths, allowed_root_insts)

        output_lines = [format_inst_path(p, dropx=args.dropx) for p in inst_paths]
    else:
        output_lines = [
            format_normal_path(root, insts, dropx=args.dropx)
            for (root, insts) in logical_paths
        ]
        if output_lines:
            sys.stderr.write("Note: use --instpath to report pure instance-name paths.\n")

    output_lines = dedupe_preserve_order(output_lines)

    if not output_lines:
        scope_desc = (
            f'under top-level instance "{args.topinst}"' if args.topinst else
            f'under top cell "{args.topcell}"' if args.topcell else
            'in the netlist'
        )
        target_desc = (
            f'instance name "{args.instname}"' if args.instname else
            f'cell "{args.cell}"'
        )
        sys.stderr.write(f'No matching paths found for {target_desc} {scope_desc}.\n')

        if args.instname:
            close = closest_instance_names(
                args.instname,
                all_edges,
                dropx=args.dropx,
                limit=3,
            )
            if close:
                sys.stderr.write('Closest instance name(s) anywhere in the parsed netlist:\n')
                for name in close:
                    shown = maybe_drop_x(name, args.dropx)
                    if shown == name:
                        sys.stderr.write(f'  {name}\n')
                    else:
                        sys.stderr.write(f'  {shown}  (raw: {name})\n')

        sys.exit(2)

    for line in output_lines:
        print(line)


if __name__ == "__main__":
    main()
