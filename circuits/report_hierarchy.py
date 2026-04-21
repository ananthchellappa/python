#!/usr/bin/env python3
import re
import sys
import argparse
from collections import Counter, defaultdict

import pdb

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
    - token[0] is the instance name
    - scan from the right
    - skip trailing tokens that are clearly metadata / params / options
    - first remaining token is the instantiated subckt name
    """
    if len(tokens) < 2:
        return None

    for i in range(len(tokens) - 1, 0, -1):
        t = tokens[i]

        # SPICE/S-edit style metadata tokens:
        # $, $m, $x=..., $y=..., etc.
        if t.startswith("$"):
            continue

        # ordinary parameter assignments
        if "=" in t and not t.startswith("="):
            continue

        # pure punctuation separators, if any
        if re.fullmatch(r'[^A-Za-z0-9_.<>/\[\]-]+', t):
            continue

        return t

    return None


def parse_netlist(path):
    defined_subckts = set()
    raw_children = defaultdict(list)
    top_level_x_instances = []

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
                if not tokens:
                    continue

                inst_name = tokens[0]
                cell = extract_instantiated_cell(tokens)
                if not cell:
                    continue

                if current_subckt is None:
                    top_level_x_instances.append((inst_name, cell))
                else:
                    raw_children[current_subckt].append(cell)

    subckt_children = {}
    for parent, kids in raw_children.items():
        subckt_children[parent] = [k for k in kids if k in defined_subckts]

    for s in defined_subckts:
        subckt_children.setdefault(s, [])

    return subckt_children, defined_subckts, top_level_x_instances


def find_internal_top_cells(subckt_children, defined_subckts):
    referenced = set()
    for kids in subckt_children.values():
        referenced.update(kids)
    return sorted(defined_subckts - referenced)


def format_label(name, count):
    return f"{name} ({count})" if count > 1 else name


def print_tree(subckt_children, top_cell, max_depth=None, out=sys.stdout):
    visited_stack = set()

    def rec(cell, prefix="", depth=0):
        if max_depth is not None and depth >= max_depth:
            return

        if cell in visited_stack:
            print(prefix + r"\----- " + cell + " [recursive]", file=out)
            return

        visited_stack.add(cell)

        counts = Counter(subckt_children.get(cell, []))
        items = list(counts.items())

        for i, (child, count) in enumerate(items):
            is_last = (i == len(items) - 1)
            branch = r"\----- " if is_last else r"|----- "
            print(prefix + branch + format_label(child, count), file=out)

            child_prefix = prefix + ("       " if is_last else "|      ")
            rec(child, child_prefix, depth + 1)

        visited_stack.remove(cell)

    print(top_cell, file=out)
    rec(top_cell, depth=0)


def choose_top(subckt_children, defined_subckts, top_level_x_instances, explicit_top=None):
    if explicit_top:
        if explicit_top not in defined_subckts:
            raise ValueError(f'top cell "{explicit_top}" is not defined in the netlist')
        return explicit_top

    valid_top_level = [(iname, cell) for (iname, cell) in top_level_x_instances if cell in defined_subckts]

    if len(valid_top_level) == 1:
        return valid_top_level[0][1]

    internal_tops = find_internal_top_cells(subckt_children, defined_subckts)
    if len(internal_tops) == 1:
        return internal_tops[0]

    msg = []
    if len(valid_top_level) > 1:
        msg.append("multiple top-level X instances found outside .subckt definitions:")
        msg.extend([f"  {iname} -> {cell}" for iname, cell in valid_top_level])

    if len(internal_tops) > 1:
        msg.append("multiple possible internal top subckts found:")
        msg.extend([f"  {x}" for x in internal_tops])

    if not msg:
        msg.append("could not determine a unique top cell")

    raise ValueError("\n".join(msg) + "\nPlease specify --top.")


def nonnegative_int(value):
    ivalue = int(value)
    if ivalue < 0:
        raise argparse.ArgumentTypeError(f"depth must be >= 0, got {value}")
    return ivalue


def main():
    ap = argparse.ArgumentParser(description="Build a subckt hierarchy tree from a SPICE netlist.")
    ap.add_argument("netlist", help="Input SPICE netlist")
    ap.add_argument("-t", "--top", help="Top cell name")
    ap.add_argument(
        "-d", "--depth",
        type=nonnegative_int,
        default=None,
        help="Maximum depth below the top to print (0=top only, 1=top plus children)"
    )
    args = ap.parse_args()
#    pdb.set_trace()
    subckt_children, defined_subckts, top_level_x_instances = parse_netlist(args.netlist)

    try:
        top_cell = choose_top(subckt_children, defined_subckts, top_level_x_instances, args.top)
    except ValueError as e:
        sys.stderr.write("Error: " + str(e) + "\n")
        sys.exit(1)

    print_tree(subckt_children, top_cell, max_depth=args.depth)


if __name__ == "__main__":
    main()
