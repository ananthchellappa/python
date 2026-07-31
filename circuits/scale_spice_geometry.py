#!/usr/bin/env python3
"""
scale_spice_geometry.py

python3 scale_spice_geometry.py \
    --input /path/to/file.spi \
    --scale 1u #--> file_scaled.spi (default. Can you --output) --help available

Scale selected geometry parameters in a SPICE netlist.

Recognized parameters
---------------------
Length / perimeter:
    lg, lg*, wg, wg*, pd, ps, peri*

Area:
    ad, as, area*

Examples:
    lg=0.34       --scale 1u   -> lg=0.34u
    pd=1.4838     --scale 1u   -> pd=1.4838u
    ad=0.191138   --scale 1u   -> ad=0.191138p
    arealvs=0.2   --scale 10n  -> arealvs=20a

The input file is not overwritten unless --in-place is specified.
"""

from __future__ import annotations

import argparse
import re
import sys
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path


# Engineering suffixes accepted for --scale.
# "meg" is included because SPICE commonly uses it for 1e6.
ENG_SUFFIX_TO_EXP = {
    "a": -18,
    "f": -15,
    "p": -12,
    "n": -9,
    "u": -6,
    "µ": -6,
    "m": -3,
    "": 0,
    "k": 3,
    "meg": 6,
    "g": 9,
    "t": 12,
}

EXP_TO_ENG_SUFFIX = {
    -18: "a",
    -15: "f",
    -12: "p",
    -9: "n",
    -6: "u",
    -3: "m",
    0: "",
    3: "k",
    6: "meg",
    9: "g",
    12: "t",
}

NUMBER_RE = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"

# Match a parameter assignment whose value is a numeric token.
# The optional suffix lets us detect an already-scaled value and leave it alone.
ASSIGNMENT_RE = re.compile(
    rf"""
    (?<![\w$])
    (?P<name>[A-Za-z_][A-Za-z0-9_]*)
    (?P<eq>\s*=\s*)
    (?P<number>{NUMBER_RE})
    (?P<suffix>meg|[afpnuµmkgt])?
    (?=$|\s)
    """,
    re.IGNORECASE | re.VERBOSE,
)

SCALE_RE = re.compile(
    rf"^\s*(?P<number>{NUMBER_RE})\s*(?P<suffix>meg|[afpnuµmkgt])?\s*$",
    re.IGNORECASE,
)


def classify_parameter(name: str) -> str | None:
    """Return 'length', 'area', or None."""
    n = name.lower()

    if n in {"ad", "as"} or n.startswith("area"):
        return "area"

    if (
        n in {"lg", "wg", "pd", "ps"}
        or n.startswith("lg")
        or n.startswith("wg")
        or n.startswith("peri")
    ):
        return "length"

    return None


def parse_scale(text: str) -> Decimal:
    """Parse engineering or scientific notation into a Decimal."""
    match = SCALE_RE.fullmatch(text)
    if not match:
        raise ValueError(
            f"invalid scale {text!r}; examples: 1u, 10n, 1e-6, 2.5e-7"
        )

    try:
        coefficient = Decimal(match.group("number"))
    except InvalidOperation as exc:
        raise ValueError(f"invalid scale {text!r}") from exc

    suffix = (match.group("suffix") or "").lower()
    exponent = ENG_SUFFIX_TO_EXP[suffix]
    scale = coefficient * (Decimal(10) ** exponent)

    if scale <= 0:
        raise ValueError("--scale must be greater than zero")

    return scale


def decimal_to_plain(value: Decimal) -> str:
    """Render Decimal without unnecessary trailing zeros."""
    if value.is_zero():
        return "0"

    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def to_engineering(value: Decimal, preferred_exp: int | None = None) -> str:
    """
    Render a value using a SPICE engineering suffix when possible.

    preferred_exp is used to preserve the user's scale style. For example,
    0.34 * 1e-6 is rendered as 0.34u rather than normalized to 340n.
    """
    if value.is_zero():
        return "0"

    if preferred_exp in EXP_TO_ENG_SUFFIX:
        coefficient = value / (Decimal(10) ** preferred_exp)
        return decimal_to_plain(coefficient) + EXP_TO_ENG_SUFFIX[preferred_exp]

    # Fall back to normalized engineering notation.
    adjusted = value.copy_abs().adjusted()
    eng_exp = (adjusted // 3) * 3

    if eng_exp in EXP_TO_ENG_SUFFIX:
        coefficient = value / (Decimal(10) ** eng_exp)
        return decimal_to_plain(coefficient) + EXP_TO_ENG_SUFFIX[eng_exp]

    # Outside supported engineering-prefix range.
    return f"{value.normalize():E}".replace("E+", "e").replace("E", "e")


def engineering_exponent(value: Decimal) -> int:
    """
    Select an engineering exponent for a scale value.

    Exact powers such as 1e-6 become exponent -6. Values such as 10e-9 retain
    exponent -9, so multiplying 0.34 by 10n becomes 3.4n.
    """
    adjusted = value.copy_abs().adjusted()
    return (adjusted // 3) * 3


def transform_text(text: str, scale: Decimal) -> tuple[str, int, int]:
    """
    Return transformed text, number changed, and number skipped because an
    engineering suffix was already present.
    """
    length_exp = engineering_exponent(scale)
    area_scale = scale * scale
    area_exp = length_exp * 2

    changed = 0
    skipped_existing_units = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal changed, skipped_existing_units

        name = match.group("name")
        kind = classify_parameter(name)
        if kind is None:
            return match.group(0)

        # Avoid silently scaling a file twice.
        if match.group("suffix"):
            skipped_existing_units += 1
            return match.group(0)

        original_number = Decimal(match.group("number"))

        if kind == "length":
            scaled = original_number * scale
            rendered = to_engineering(scaled, preferred_exp=length_exp)
        else:
            scaled = original_number * area_scale
            rendered = to_engineering(scaled, preferred_exp=area_exp)

        changed += 1
        return f"{name}{match.group('eq')}{rendered}"

    output_lines: list[str] = []
    for line in text.splitlines(keepends=True):
        # Full-line SPICE comments are left untouched.
        if line.lstrip().startswith("*"):
            output_lines.append(line)
        else:
            output_lines.append(ASSIGNMENT_RE.sub(replace, line))

    return "".join(output_lines), changed, skipped_existing_units


def default_output_path(input_path: Path) -> Path:
    if input_path.suffix:
        return input_path.with_name(
            f"{input_path.stem}_scaled{input_path.suffix}"
        )
    return input_path.with_name(f"{input_path.name}_scaled")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Apply a physical scale to selected length, perimeter, and area "
            "parameters in a SPICE netlist."
        )
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="input SPICE netlist",
    )
    parser.add_argument(
        "--scale",
        required=True,
        help="scale in engineering or scientific notation, e.g. 1u or 1e-6",
    )

    destination = parser.add_mutually_exclusive_group()
    destination.add_argument(
        "--output",
        type=Path,
        help="output file; default: INPUT_scaled.EXT",
    )
    destination.add_argument(
        "--in-place",
        action="store_true",
        help="replace the input file after creating INPUT.bak",
    )
    destination.add_argument(
        "--stdout",
        action="store_true",
        help="write transformed netlist to standard output",
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        scale = parse_scale(args.scale)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    input_path: Path = args.input
    if not input_path.is_file():
        print(f"ERROR: input file does not exist: {input_path}", file=sys.stderr)
        return 2

    try:
        original = input_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        print(f"ERROR: cannot read {input_path}: {exc}", file=sys.stderr)
        return 2

    with localcontext() as ctx:
        ctx.prec = 50
        transformed, changed, skipped = transform_text(original, scale)

    if args.stdout:
        sys.stdout.write(transformed)
    elif args.in_place:
        backup_path = input_path.with_name(input_path.name + ".bak")
        try:
            backup_path.write_text(original, encoding="utf-8")
            input_path.write_text(transformed, encoding="utf-8")
        except OSError as exc:
            print(f"ERROR: cannot write output: {exc}", file=sys.stderr)
            return 2
        print(f"Wrote:  {input_path}", file=sys.stderr)
        print(f"Backup: {backup_path}", file=sys.stderr)
    else:
        output_path = args.output or default_output_path(input_path)
        try:
            output_path.write_text(transformed, encoding="utf-8")
        except OSError as exc:
            print(f"ERROR: cannot write {output_path}: {exc}", file=sys.stderr)
            return 2
        print(f"Wrote: {output_path}", file=sys.stderr)

    print(f"Scaled parameter assignments: {changed}", file=sys.stderr)
    if skipped:
        print(
            f"WARNING: left {skipped} recognized assignment(s) unchanged "
            "because they already had an engineering suffix",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
