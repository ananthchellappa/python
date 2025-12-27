#!/usr/bin/env python3
"""
ic_culprits.py

Analyze a Spectre `spectre.ic` node-count file and report which hierarchical
instances contribute the most nodes, level by level.

This version implements **Option B** hierarchy detection:

    - A node name is split on dots (".").
    - All segments **except the last** are treated as instance segments.
    - Any trailing `:something` in a segment (e.g. "M3:d") is stripped.
    - No requirement that instance names start with "x" / "X".

Python compatibility: 3.6+
"""
import argparse
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence, Tuple, Set


# Nets that are often global supply / ground nodes and not useful for culprits.
DEFAULT_GLOBALS = set([
    "0", "gnd!", "vss!", "vdd!", "avss!", "agnd!", "dgnd!", "dvss!", "dvdd!"
])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    # type: (Optional[Sequence[str]]) -> argparse.Namespace
    p = argparse.ArgumentParser(
        description=(
            "Summarize node counts in a spectre.ic file by hierarchical instance.\n"
            "By default, all dot-separated segments except the last are treated\n"
            "as instances (Option B)."
        )
    )
    p.add_argument(
        "ic",
        help="Path to spectre.ic file, or '-' for stdin.",
    )
    p.add_argument(
        "-d", "--depth",
        type=int,
        default=2,
        help="How many instance levels to analyze (default: 2).",
    )
    p.add_argument(
        "-L", "--levels",
        type=int,
        default=None,
        help="How many instance levels to print. Defaults to the value of --depth.",
    )
    p.add_argument(
        "-t", "--top",
        type=int,
        default=0,
        help="Only show the top N instances per level (0 = show all, default: 0).",
    )
    p.add_argument(
        "--skip-globals",
        action="store_true",
        help="Skip a built-in list of global nets (0, gnd!, vss!, vdd!, ...).",
    )
    p.add_argument(
        "--extra-globals",
        type=str,
        default="",
        help="Comma-separated list of extra node names to treat as globals.",
    )
    p.add_argument(
        "-e", "--regex-exclude",
        type=str,
        default=None,
        help="Regular expression of node names to exclude.",
    )
    p.add_argument(
        "-i", "--case-insensitive",
        action="store_true",
        help="Case-insensitive matching for globals and regex-exclude.",
    )
    return p.parse_args(argv)


# ---------------------------------------------------------------------------
# Input + filtering
# ---------------------------------------------------------------------------

def load_lines(path):
    # type: (str) -> Iterable[str]
    """Yield all lines from a file or stdin."""
    if path == "-":
        return sys.stdin
    return Path(path).read_text(encoding="utf-8", errors="ignore").splitlines()


def make_node_filter(skip_globals, extra_globals_csv, regex_exclude, case_insensitive):
    # type: (bool, str, Optional[str], bool) -> Callable[[str], bool]
    """
    Build and return a predicate `keep(node_name) -> bool`.

    - If skip_globals is True, drop any node in DEFAULT_GLOBALS.
    - EXTRA globals can be provided via comma-separated `extra_globals_csv`.
    - If regex_exclude is provided, drop any node matching that regex.
    - If case_insensitive is True, matching is done in lower-case / with re.I.
    """
    globals_set = set()  # type: Set[str]
    if skip_globals:
        globals_set.update(DEFAULT_GLOBALS)

    if extra_globals_csv:
        for raw in extra_globals_csv.split(","):
            name = raw.strip()
            if name:
                globals_set.add(name)

    if case_insensitive:
        globals_set = set([g.lower() for g in globals_set])

    regex = None
    if regex_exclude:
        flags = re.IGNORECASE if case_insensitive else 0
        regex = re.compile(regex_exclude, flags)

    def keep(node):
        # type: (str) -> bool
        chk = node.lower() if case_insensitive else node

        if globals_set and chk in globals_set:
            return False

        if regex and regex.search(node):
            return False

        return True

    return keep


# Precompiled regex for v(<node>) syntax.
_VTOKEN = re.compile(r"^v\((.+)\)$", re.IGNORECASE)


def parse_node_from_ic_line(line):
    # type: (str) -> Optional[str]
    """
    Extract node name from a spectre.ic line.

    Returns None for comments/empty/internal-state lines.

    Accepted first tokens:
      - <node> <value>
      - v(<node>) <value>

    Skips lines where the token begins with:
      - '@'  → device internal (e.g. @M1:gm)
      - 'i(' → currents (e.g. i(R1))
    """
    s = line.strip()
    if not s:
        return None

    # Comments: spectre often uses '*' at column 1; we also ignore // and #.
    if s.startswith("*") or s.startswith("//") or s.startswith("#"):
        return None

    first = s.split()[0]

    # Skip internal quantities / branch currents
    if first.startswith("@") or first.lower().startswith("i("):
        return None

    m = _VTOKEN.match(first)
    if m:
        return m.group(1)

    return first


# ---------------------------------------------------------------------------
# Hierarchy helpers  (Option B implementation)
# ---------------------------------------------------------------------------

def split_instance_segments(node):
    # type: (str) -> List[str]
    """
    Extract instance segments from a node name (Option B).

    Rules:
      - Split node on '.' into segments.
      - If there is only one segment, return [] (no hierarchy).
      - All segments except the last are treated as instance names.
      - For each segment, strip any suffix after ':' (e.g. 'M3:d' -> 'M3').
      - Empty segments after stripping are ignored.

    Examples:
      'top.u1.u2.net123'      -> ['top', 'u1', 'u2']
      'soc.chip.xpll.vctrl'   -> ['soc', 'chip', 'xpll']
      'net123'                -> []
      'xtop.xa2.M3:d'         -> ['xtop', 'xa2', 'M3']
    """
    parts = node.split(".")
    if len(parts) <= 1:
        return []

    insts = []  # type: List[str]
    # All but the last segment are considered instances
    for seg in parts[:-1]:
        core = seg.split(":", 1)[0]
        if core:
            insts.append(core)
    return insts


def instance_prefixes(insts, max_levels):
    # type: (Sequence[str], int) -> List[str]
    """
    Given a list of instance segments, return cumulative prefixes up to
    `max_levels` (and at most len(insts)).

    Example:
        insts      = ['top', 'u1', 'u2']
        max_levels = 3
        -> ['top', 'top.u1', 'top.u1.u2']
    """
    out = []  # type: List[str]
    limit = min(max_levels, len(insts))
    for i in range(1, limit + 1):
        out.append(".".join(insts[:i]))
    return out


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def collect_nodes(lines, keep):
    # type: (Iterable[str], Callable[[str], bool]) -> List[str]
    """Parse all node names from spectre.ic lines and apply filter."""
    nodes = []  # type: List[str]
    for ln in lines:
        node = parse_node_from_ic_line(ln)
        if node and keep(node):
            nodes.append(node)
    return nodes


def aggregate_by_level(nodes, max_levels):
    # type: (Sequence[str], int) -> Tuple[int, List[Counter]]
    """
    For each node, derive instance prefixes and count contributions
    at each level up to max_levels.

    Returns (total_nodes, [Counter_for_level0, Counter_for_level1, ...]).
    """
    total = len(nodes)
    level_counters = [Counter() for _ in range(max_levels)]  # type: List[Counter]

    for node in nodes:
        insts = split_instance_segments(node)
        if not insts:
            continue
        prefixes = instance_prefixes(insts, max_levels)
        for lvl, pref in enumerate(prefixes):
            level_counters[lvl][pref] += 1

    return total, level_counters


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def bar(count, total):
    # type: (int, int) -> str
    """ASCII bar: each '#' is ~10% of total nodes (rounded)."""
    if total <= 0:
        return ""
    width = int(round((float(count) / float(total)) * 10.0))
    if count > 0:
        return "#" * max(width, 1)
    return ""


def render_level(level_idx, bucket, total, top_n):
    # type: (int, Counter, int, int) -> str
    """Render one hierarchy level to a human-readable text block."""
    if not bucket:
        return ""

    items = list(bucket.items())
    items.sort(key=lambda kv: (-kv[1], kv[0]))  # by count desc, then name
    if top_n > 0:
        items = items[:top_n]

    max_name = 0
    for name, _cnt in items:
        if len(name) > max_name:
            max_name = len(name)

    lines = []  # type: List[str]
    lines.append("Level {}:".format(level_idx))
    for name, cnt in items:
        lines.append(
            "  {} : {:6d}  {}".format(name.ljust(max_name), cnt, bar(cnt, total))
        )
    lines.append("")  # trailing blank line per level
    return "\n".join(lines)


def render_report(total, level_counters, top_n, max_print_levels):
    # type: (int, Sequence[Counter], int, int) -> str
    """Assemble the full multi-level text report."""
    out = ["Total nodes: {}".format(total), ""]  # type: List[str]
    for lvl, counter in enumerate(level_counters[:max_print_levels]):
        section = render_level(lvl, counter, total, top_n)
        if section:
            out.append(section)
    return "\n".join(out).rstrip()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv=None):
    # type: (Optional[Sequence[str]]) -> None
    args = parse_args(argv)

    max_levels = args.levels if args.levels is not None else args.depth
    if max_levels <= 0:
        print("ERROR: --depth/--levels must be positive.", file=sys.stderr)
        sys.exit(1)

    keep = make_node_filter(
        skip_globals=args.skip_globals,
        extra_globals_csv=args.extra_globals,
        regex_exclude=args.regex_exclude,
        case_insensitive=args.case_insensitive,
    )

    lines = load_lines(args.ic)
    nodes = collect_nodes(lines, keep)
    total, level_counters = aggregate_by_level(nodes, max_levels)

    if total == 0:
        print("No nodes found after filtering.")
        return

    report = render_report(total, level_counters, args.top, max_levels)
    print(report)


if __name__ == "__main__":
    main()
