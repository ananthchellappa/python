#!/usr/bin/env python3

from __future__ import annotations
import argparse
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Callable, Iterable, Iterator, List, Optional, Sequence, Tuple

DEFAULT_GLOBALS = {
    "0", "gnd!", "vss!", "vdd!", "avss!", "agnd!", "dgnd!", "dvss!", "dvdd!"
}

# ---------- CLI ----------

def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Find node-count culprits from spectre.ic")
    p.add_argument("ic", help="Path to spectre.ic (or - for stdin)")
    p.add_argument("--depth", type=int, default=2,
                   help="Instance depth to report (default: 2)")
    p.add_argument("--levels", type=int, default=None,
                   help="How many levels to print (default: same as --depth). "
                        "E.g., --levels 3 prints level 0,1,2")
    p.add_argument("--top", type=int, default=0,
                   help="Show only top N per level (0 = all)")
    p.add_argument("--skip-globals", action="store_true",
                   help="Ignore a default set of global nets")
    p.add_argument("--extra-globals", default="",
                   help="Comma-separated extra global nets to ignore")
    p.add_argument("--regex-exclude", default="",
                   help="Regex of node names to exclude")
    p.add_argument("--case-insensitive", action="store_true",
                   help="Case-insensitive matching for excludes")
    return p.parse_args(argv)

# ---------- I/O ----------

def load_lines(path: str) -> Iterable[str]:
    """Yield lines from file or stdin ('-')."""
    if path == "-":
        return sys.stdin
    return Path(path).read_text(encoding="utf-8", errors="ignore").splitlines()

# ---------- Filtering & Parsing ----------

def make_node_filter(skip_globals: bool,
                     extra_globals_csv: str,
                     regex_exclude: str,
                     case_insensitive: bool) -> Callable[[str], bool]:
    """
    Returns predicate(node_name) -> True if node should be kept.
    """
    globs = set(DEFAULT_GLOBALS) if skip_globals else set()
    if extra_globals_csv:
        globs |= {s.strip() for s in extra_globals_csv.split(",") if s.strip()}

    flags = re.I if case_insensitive else 0
    rex = re.compile(regex_exclude, flags) if regex_exclude else None

    def keep(node: str) -> bool:
        if node in globs:
            return False
        if rex and rex.search(node):
            return False
        return True

    return keep

_VTOKEN = re.compile(r"^v\((.+)\)$", re.I)

def parse_node_from_ic_line(line: str) -> Optional[str]:
    """
    Extract node name from a spectre.ic line.
    Returns None for comments/empty/internal-state lines.
    Accepted first tokens:
      - <node> <value>
      - v(<node>) <value>
    Skips lines beginning with @ (device internal) or i( (currents).
    """
    s = line.strip()
    if not s or s.startswith(("*", "//", "#")):
        return None

    first = s.split(None, 1)[0]
    if first.startswith(('@', 'i(')):
        return None

    m = _VTOKEN.match(first)
    return m.group(1) if m else first

# ---------- Instance path handling ----------

def split_instance_segments(node: str) -> List[str]:
    """
    Return consecutive instance segments from the start of a hierarchical node.
    Instance segments are those starting with 'x'/'X'. Stops at first non-instance part.
    E.g.:
      'xtop2.xb4.net123' -> ['xtop2', 'xb4']
      'xtop1.xa2.M3:d'   -> ['xtop1', 'xa2']
    """
    segs = node.split('.')
    insts: List[str] = []
    for seg in segs:
        core = seg.split(':', 1)[0]
        if core and core[0] in ('x', 'X'):
            insts.append(core)
        else:
            break
    return insts

def instance_prefixes(insts: Sequence[str], max_levels: int) -> List[str]:
    """Return cumulative prefixes up to max_levels (at most len(insts))."""
    out: List[str] = []
    for i in range(1, min(max_levels, len(insts)) + 1):
        out.append('.'.join(insts[:i]))
    return out

# ---------- Aggregation ----------

def collect_nodes(lines: Iterable[str],
                  keep: Callable[[str], bool]) -> List[str]:
    """Parse all node names from spectre.ic lines and apply filter."""
    nodes: List[str] = []
    for ln in lines:
        node = parse_node_from_ic_line(ln)
        if node and keep(node):
            nodes.append(node)
    return nodes

def aggregate_by_level(nodes: Sequence[str], max_levels: int) -> Tuple[int, List[Counter[str]]]:
    """
    For each node, compute its instance prefixes once,
    then aggregate counts per level (level 0=top instance, etc.).
    Returns (total_nodes, [Counter per level]).
    """
    total = len(nodes)
    if total == 0:
        return 0, []

    level_counters: List[Counter[str]] = [Counter() for _ in range(max_levels)]
    for node in nodes:
        insts = split_instance_segments(node)
        if not insts:
            continue
        prefs = instance_prefixes(insts, max_levels)
        for lvl, pref in enumerate(prefs):
            level_counters[lvl][pref] += 1
    return total, level_counters

# ---------- Rendering ----------

def bar(count: int, total: int) -> str:
    """1 hash per 10% of total (rounded)."""
    if total <= 0:
        return ""
    return "#" * round((count / total) * 10)

def render_level(level_idx: int,
                 bucket: Counter[str],
                 total: int,
                 top_n: int) -> str:
    if not bucket:
        return ""
    lines: List[str] = []
    lines.append(f"level {level_idx}:")
    width = max(len(k) for k in bucket.keys())
    items = sorted(bucket.items(), key=lambda x: (-x[1], x[0]))
    if top_n > 0:
        items = items[:top_n]
    for name, cnt in items:
        lines.append(f"{name.ljust(width)} : {str(cnt).rjust(4)}  {bar(cnt, total)}")
    lines.append("")  # blank line after each level
    return "\n".join(lines)

def render_report(total: int,
                  level_counters: List[Counter[str]],
                  top_n: int,
                  max_print_levels: int) -> str:
    out: List[str] = [f"Total nodes: {total}", ""]
    for lvl, counter in enumerate(level_counters[:max_print_levels]):
        section = render_level(lvl, counter, total, top_n)
        if section:
            out.append(section)
    return "\n".join(out).rstrip()  # tidy trailing newline

# ---------- Orchestration ----------

def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)

    max_levels = args.levels if args.levels is not None else args.depth
    if max_levels <= 0:
        print("Nothing to do: --levels/--depth must be >= 1", file=sys.stderr)
        sys.exit(2)

    keep = make_node_filter(
        skip_globals=args.skip_globals,
        extra_globals_csv=args.extra_globals,
        regex_exclude=args.regex_exclude,
        case_insensitive=args.case_insensitive,
    )

    nodes = collect_nodes(load_lines(args.ic), keep)
    total, level_counters = aggregate_by_level(nodes, max_levels)
    if total == 0:
        print("No nodes found after filtering.")
        return

    report = render_report(total, level_counters, args.top, max_levels)
    print(report)

if __name__ == "__main__":
    main()
