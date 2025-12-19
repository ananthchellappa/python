#!/usr/bin/env python3
"""
sim_report.py

- Find newest ~/CDS.log* (CDS.log, CDS.log.2, CDS.log.3, ...)
- In that newest file, find the LAST line containing "_axlToolDisplayTestPointOutputLog"
- From that line, extract the log file path in the double-quotes closest to the end of the line
- In that log file:
    - print the line matching: ^\s*nodes\s+\d+
    - print the final line of the file
"""

import sys
import re
from pathlib import Path


NEEDLE = "_axlToolDisplayTestPointOutputLog"
RE_QUOTED_AT_END = re.compile(r'"([^"]+)"[^"]*$')	# AC hack
RE_NODES = re.compile(r"^\s*nodes\s+\d+")


def newest_cds_log(home: Path) -> Path:
    # Match CDS.log and CDS.log.NUMBER (and any other CDS.log* variants)
    candidates = list(home.glob("CDS.log*"))
    # Keep only files (ignore dirs)
    candidates = [p for p in candidates if p.is_file()]
    if not candidates:
        raise FileNotFoundError(f"No CDS.log* files found in {home}")

    # Newest by mtime; tie-breaker by name for determinism
    candidates.sort(key=lambda p: (p.stat().st_mtime, p.name))
    return candidates[-1]


def last_line_containing(path: Path, substring: str) -> str:
    last = None
    with path.open("r", errors="replace") as f:
        for line in f:
            if substring in line:
                last = line.rstrip("\n")
    if last is None:
        raise ValueError(f'No line containing "{substring}" found in {path}')
    return last


def extract_quoted_path_at_end(line: str) -> str:
    m = RE_QUOTED_AT_END.search(line)
    if not m:
        raise ValueError(
            "Could not find a double-quoted string near the end of the line.\n"
            f"Line was: {line}"
        )
    return m.group(1)


def find_nodes_line(path: Path) -> str:
    found = None
    with path.open("r", errors="replace") as f:
        for line in f:
            if RE_NODES.match(line):
                found = line.rstrip("\n")
    if found is None:
        raise ValueError(f'No nodes line matching r"^\\s*nodes\\s+\\d+" found in {path}')
    return found


def last_line_of_file(path: Path) -> str:
    last = ""
    with path.open("r", errors="replace") as f:
        for line in f:
            last = line.rstrip("\n")
    return last


def main() -> int:
    home = Path.home()

    try:
        cds = newest_cds_log(home)
        line = last_line_containing(cds, NEEDLE)
        log_path_str = extract_quoted_path_at_end(line)
        print(log_path_str)	# AC hack

        log_path = Path(log_path_str).expanduser()
        if not log_path.is_absolute():
            # If it’s relative, treat it as relative to home (common behavior for tool logs)
            # If you prefer relative-to-CDSlog directory, change `home` to `cds.parent`.
            log_path = (home / log_path).resolve()

        if not log_path.exists() or not log_path.is_file():
            raise FileNotFoundError(f"Log file does not exist or is not a file: {log_path}")

        nodes_line = find_nodes_line(log_path)
        last_line = last_line_of_file(log_path)

        print(nodes_line)
        print(last_line)

        return 0

    except Exception as e:
        print(f"sim_report.py: error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
