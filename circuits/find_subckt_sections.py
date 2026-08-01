#!/usr/bin/env python3
"""
find_subckt_sections.py

Locate Spectre/SPICE subcircuit definitions in a sectioned model library.

The second positional argument is interpreted as follows:

  * If it is an existing regular file, read a list of subcircuit names from it
    and find a minimum-size set of library sections covering all those names.
  * Otherwise, treat it as one subcircuit name and report every occurrence.

Recognized declarations:

    subckt my_device (...)
    inline subckt my_device (...)
    .subckt my_device ...

List-file format:

    * One subcircuit name per line.
    * Leading/trailing whitespace is ignored.
    * Blank lines and lines beginning with #, ;, *, or // are ignored.
    * On a non-comment line, the first whitespace- or comma-separated token
      is used as the subcircuit name.

Usage:

    python3 find_subckt_sections_v2.py u0_onc18.splib ndio_3
    python3 find_subckt_sections_v2.py u0_onc18.splib required_subckts.txt
    python3 find_subckt_sections_v2.py --case-sensitive u0_onc18.splib ndio_3
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


SECTION_RE = re.compile(r"^\s*section(?:\s+|\s*=\s*)(?P<name>[^\s/]+)", re.IGNORECASE)
ENDSECTION_RE = re.compile(
    r"^\s*endsection(?:\s+|\s*=\s*)?(?P<name>[^\s/]+)?", re.IGNORECASE
)
SUBCKT_RE = re.compile(
    r"^\s*(?:(?:inline)\s+)?\.?subckt\s+(?P<name>[^\s(]+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Match:
    line_number: int
    declared_name: str
    section_path: tuple[str, ...]
    source_line: str

    @property
    def section(self) -> str | None:
        """Return the innermost active section, or None if unsectioned."""
        return self.section_path[-1] if self.section_path else None


@dataclass
class LibraryIndex:
    matches_by_name: dict[str, list[Match]]
    display_name_by_key: dict[str, str]


def canonical(name: str, case_sensitive: bool) -> str:
    return name if case_sensitive else name.casefold()


def names_equal(a: str, b: str, case_sensitive: bool) -> bool:
    return canonical(a, case_sensitive) == canonical(b, case_sensitive)


def strip_spectre_line_comment(line: str) -> str:
    """Remove // comments while preserving // inside quoted strings."""
    out: list[str] = []
    quote: str | None = None
    escaped = False
    i = 0

    while i < len(line):
        ch = line[i]

        if escaped:
            out.append(ch)
            escaped = False
            i += 1
            continue

        if ch == "\\":
            out.append(ch)
            escaped = True
            i += 1
            continue

        if quote is not None:
            out.append(ch)
            if ch == quote:
                quote = None
            i += 1
            continue

        if ch in ('"', "'"):
            quote = ch
            out.append(ch)
            i += 1
            continue

        if ch == "/" and i + 1 < len(line) and line[i + 1] == "/":
            break

        out.append(ch)
        i += 1

    return "".join(out)


def build_library_index(filename: Path, case_sensitive: bool) -> LibraryIndex:
    matches_by_name: dict[str, list[Match]] = defaultdict(list)
    display_name_by_key: dict[str, str] = {}
    section_stack: list[str] = []

    with filename.open("r", encoding="utf-8", errors="replace") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = strip_spectre_line_comment(raw_line).strip()
            if not line:
                continue

            section_match = SECTION_RE.match(line)
            if section_match:
                section_stack.append(section_match.group("name"))
                continue

            endsection_match = ENDSECTION_RE.match(line)
            if endsection_match:
                closing_name = endsection_match.group("name")
                if not section_stack:
                    print(
                        f"warning: line {line_number}: endsection found "
                        "while no section is active",
                        file=sys.stderr,
                    )
                elif closing_name is None:
                    section_stack.pop()
                elif names_equal(section_stack[-1], closing_name, False):
                    section_stack.pop()
                else:
                    print(
                        f"warning: line {line_number}: endsection "
                        f"{closing_name!r} does not match active section "
                        f"{section_stack[-1]!r}; closing the active section",
                        file=sys.stderr,
                    )
                    section_stack.pop()
                continue

            subckt_match = SUBCKT_RE.match(line)
            if not subckt_match:
                continue

            declared_name = subckt_match.group("name")
            key = canonical(declared_name, case_sensitive)
            display_name_by_key.setdefault(key, declared_name)
            matches_by_name[key].append(
                Match(
                    line_number=line_number,
                    declared_name=declared_name,
                    section_path=tuple(section_stack),
                    source_line=raw_line.rstrip("\n"),
                )
            )

    return LibraryIndex(dict(matches_by_name), display_name_by_key)


def read_requested_subckts(filename: Path, case_sensitive: bool) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()

    with filename.open("r", encoding="utf-8", errors="replace") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line or line.startswith(("#", ";", "*", "//")):
                continue

            token = re.split(r"[\s,]+", line, maxsplit=1)[0]
            if not token:
                continue

            key = canonical(token, case_sensitive)
            if key not in seen:
                seen.add(key)
                names.append(token)

    return names


def minimum_section_cover(
    choices_by_name: dict[str, set[str]],
) -> list[str] | None:
    """
    Return an exact minimum-cardinality section cover.

    Each key is a requested subcircuit and each value is the set of sections
    in which that subcircuit is defined. A branch-and-bound search is used,
    with forced-choice propagation. Ties are resolved lexicographically.
    """
    if not choices_by_name:
        return []
    if any(not choices for choices in choices_by_name.values()):
        return None

    best: tuple[str, ...] | None = None

    def search(remaining: dict[str, set[str]], chosen: set[str]) -> None:
        nonlocal best

        # Remove requirements already covered by a chosen section.
        remaining = {
            name: sections
            for name, sections in remaining.items()
            if chosen.isdisjoint(sections)
        }
        if not remaining:
            candidate = tuple(sorted(chosen, key=str.casefold))
            if best is None or len(candidate) < len(best) or (
                len(candidate) == len(best)
                and tuple(s.casefold() for s in candidate)
                < tuple(s.casefold() for s in best)
            ):
                best = candidate
            return

        if best is not None and len(chosen) >= len(best):
            return

        # Repeatedly apply forced choices.
        while True:
            forced = {
                next(iter(sections))
                for sections in remaining.values()
                if len(sections) == 1
            }
            new_forced = forced - chosen
            if not new_forced:
                break
            chosen = chosen | new_forced
            if best is not None and len(chosen) >= len(best):
                return
            remaining = {
                name: sections
                for name, sections in remaining.items()
                if chosen.isdisjoint(sections)
            }
            if not remaining:
                search({}, chosen)
                return

        # Choose the most constrained uncovered subcircuit.
        pivot_name, pivot_sections = min(
            remaining.items(),
            key=lambda item: (len(item[1]), item[0].casefold()),
        )

        # Try sections covering the most remaining names first.
        section_scores = {
            section: sum(section in choices for choices in remaining.values())
            for section in pivot_sections
        }
        ordered_sections = sorted(
            pivot_sections,
            key=lambda section: (-section_scores[section], section.casefold()),
        )

        for section in ordered_sections:
            search(remaining, chosen | {section})

    search(choices_by_name, set())
    return list(best) if best is not None else None


def report_single(
    library: Path,
    requested_name: str,
    index: LibraryIndex,
    case_sensitive: bool,
) -> int:
    matches = index.matches_by_name.get(canonical(requested_name, case_sensitive), [])

    if not matches:
        print(f"Subcircuit {requested_name!r} was not found in {library}")
        return 1

    print(
        f"Subcircuit {requested_name!r} found "
        f"{len(matches)} time(s) in {library}:"
    )

    for match in matches:
        section = (
            " -> ".join(match.section_path)
            if match.section_path
            else "<outside any section>"
        )
        print(f"\n  section: {section}")
        print(f"  line:    {match.line_number}")
        print(f"  decl:    {match.source_line.strip()}")

    return 0


def report_list(
    library: Path,
    list_file: Path,
    requested_names: list[str],
    index: LibraryIndex,
    case_sensitive: bool,
) -> int:
    if not requested_names:
        print(f"error: no subcircuit names found in {list_file}", file=sys.stderr)
        return 2

    missing: list[str] = []
    unsectioned: list[str] = []
    choices_by_name: dict[str, set[str]] = {}
    display_by_key: dict[str, str] = {}

    for requested_name in requested_names:
        key = canonical(requested_name, case_sensitive)
        display_by_key[key] = requested_name
        matches = index.matches_by_name.get(key, [])

        if not matches:
            missing.append(requested_name)
            continue

        if any(match.section is None for match in matches):
            unsectioned.append(requested_name)
            continue

        choices_by_name[key] = {
            match.section for match in matches if match.section is not None
        }

    selected_sections = minimum_section_cover(choices_by_name)

    print(f"Library:       {library}")
    print(f"Subcircuit list: {list_file}")
    print(f"Requested:     {len(requested_names)}")
    print(f"Found:         {len(requested_names) - len(missing)}")
    print(f"Missing:       {len(missing)}")

    if missing:
        print("\nNot found in library:")
        for name in missing:
            print(f"  {name}")

    if unsectioned:
        print("\nDefined outside any section; no section selection is needed:")
        for name in unsectioned:
            print(f"  {name}")

    if selected_sections is None:
        print("\nNo section cover could be found.")
        return 1

    print(f"\nMinimum section count: {len(selected_sections)}")
    if selected_sections:
        for section in selected_sections:
            print(f"  {section}")

        print("\nSpectre include statements:")
        escaped_library = str(library).replace('"', '\\"')
        for section in selected_sections:
            print(f'include "{escaped_library}" section={section}')
    else:
        print("  <none>")

    print("\nCoverage:")
    for requested_name in requested_names:
        key = canonical(requested_name, case_sensitive)
        matches = index.matches_by_name.get(key, [])
        if not matches:
            print(f"  {requested_name}: MISSING")
            continue
        if any(match.section is None for match in matches):
            print(f"  {requested_name}: <outside any section>")
            continue
        covering = sorted(
            {
                match.section
                for match in matches
                if match.section in selected_sections
            },
            key=str.casefold,
        )
        print(f"  {requested_name}: {', '.join(covering)}")

    return 1 if missing else 0


VERSION = "2.1"

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Find the section defining one subcircuit, or compute a minimum "
            "set of sections covering subcircuits listed in a file."
        )
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    parser.add_argument("library", type=Path, help="Spectre/SPICE library file")
    parser.add_argument(
        "subckt_or_file",
        help="A subcircuit name, or an existing regular file listing names",
    )
    parser.add_argument(
        "--list-file",
        action="store_true",
        help=(
            "Require the second argument to be a list file. This avoids any "
            "ambiguity and gives an error if the file cannot be found."
        ),
    )
    parser.add_argument(
        "--case-sensitive",
        action="store_true",
        help="Match subcircuit names case-sensitively",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.library.is_file():
        print(f"error: library is not a regular file: {args.library}", file=sys.stderr)
        return 2

    source = Path(args.subckt_or_file).expanduser()

    if args.list_file and not source.is_file():
        print(
            f"error: list file is not a regular file: {source}",
            file=sys.stderr,
        )
        print(f"       current directory: {Path.cwd()}", file=sys.stderr)
        return 2

    # In automatic mode, a path-looking argument that does not exist is much
    # more likely to be a mistyped/mislocated file than a subcircuit name.
    looks_like_path = (
        source.suffix.lower() in {".txt", ".lst", ".list", ".cir", ".sp", ".spi", ".scs", ".net"}
        or source.parent != Path(".")
    )
    if not args.list_file and looks_like_path and not source.is_file():
        print(
            f"error: second argument looks like a file, but it was not found: {source}",
            file=sys.stderr,
        )
        print(f"       current directory: {Path.cwd()}", file=sys.stderr)
        print(
            "       pass the correct path, or use a bare subcircuit name",
            file=sys.stderr,
        )
        return 2

    try:
        index = build_library_index(args.library, args.case_sensitive)

        if source.is_file():
            requested_names = read_requested_subckts(source, args.case_sensitive)
            return report_list(
                args.library,
                source,
                requested_names,
                index,
                args.case_sensitive,
            )

        return report_single(
            args.library,
            args.subckt_or_file,
            index,
            args.case_sensitive,
        )

    except OSError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
