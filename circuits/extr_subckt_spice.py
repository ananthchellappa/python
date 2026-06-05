#!/usr/bin/env python3
"""
Extract a .subckt definition from a SPICE-style netlist.

Usage:
    python extract_subckt.py /path/to/netlist SUBCKT_NAME
"""

import sys
import re
from pathlib import Path


def is_subckt_start(line: str, subckt_name: str) -> bool:
    """
    Match lines like:
        .subckt mycell in out vdd vss
    Case-insensitive.
    Allows leading whitespace.
    """
    pattern = rf"^\s*\.subckt\s+{re.escape(subckt_name)}(\s|$)"
    return re.search(pattern, line, re.IGNORECASE) is not None


def is_matching_ends(line: str, subckt_name: str) -> bool:
    """
    Match:
        .ends
        .ends mycell

    Case-insensitive.
    Allows leading whitespace and trailing comments/text is not treated specially.
    """
    stripped = line.strip()
    tokens = stripped.split()

    if not tokens:
        return False

    if tokens[0].lower() != ".ends":
        return False

    if len(tokens) == 1:
        return True

    return tokens[1].lower() == subckt_name.lower()


def extract_subckt(netlist_path: Path, subckt_name: str) -> list[str]:
    inside = False
    extracted = []

    with netlist_path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if not inside:
                if is_subckt_start(line, subckt_name):
                    inside = True
                    extracted.append(line)
            else:
                extracted.append(line)

                if is_matching_ends(line, subckt_name):
                    return extracted

    if not extracted:
        raise RuntimeError(f"Subckt not found: {subckt_name}")

    raise RuntimeError(
        f"Found .subckt {subckt_name}, but did not find matching .ends or .ends {subckt_name}"
    )


def main() -> int:
    if len(sys.argv) != 3:
        print(
            f"Usage: python {sys.argv[0]} /path/to/netlist SUBCKT_NAME",
            file=sys.stderr,
        )
        return 2

    netlist_path = Path(sys.argv[1])
    subckt_name = sys.argv[2]

    if not netlist_path.is_file():
        print(f"Error: file not found: {netlist_path}", file=sys.stderr)
        return 1

    try:
        lines = extract_subckt(netlist_path, subckt_name)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print("".join(lines), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
