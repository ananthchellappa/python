#!/usr/bin/env python3

"""
convert_lib_defs.py

Convert Windows paths in lines such as:

    DEFINE lib_name ..\\..\\..\\dir_name\\Layout\\dir2_name\\folder_name
    DEFINE other_lib C:\\projects\\example\\layout

to absolute Linux paths:

    DEFINE lib_name /mnt/C/projects/example/layout
    DEFINE other_lib /mnt/C/projects/example/layout

Relative paths are resolved relative to the directory containing the input
file.

The output file has the same filename as the input file and is placed in the
directory specified by --target.

The script will never overwrite the input file.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path


DEFINE_RE = re.compile(
    r"""
    ^
    (?P<prefix>\s*DEFINE\s+\S+\s+)
    (?P<path>.*?)
    (?P<newline>\r?\n)?
    $
    """,
    re.IGNORECASE | re.VERBOSE,
)

DRIVE_ABSOLUTE_RE = re.compile(
    r"^(?P<drive>[A-Za-z]):[\\/](?P<rest>.*)$"
)

DRIVE_RELATIVE_RE = re.compile(
    r"^(?P<drive>[A-Za-z]):(?P<rest>[^\\/].*)$"
)


class ConversionError(Exception):
    """Raised when a Windows path cannot be converted safely."""


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert Windows paths in DEFINE lines to absolute Linux paths."
        )
    )

    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Input file containing DEFINE statements.",
    )

    parser.add_argument(
        "--target",
        required=True,
        type=Path,
        help=(
            "Output directory. It may be absolute or relative to the current "
            "working directory."
        ),
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Overwrite an existing output file. The input file is still "
            "protected and can never be overwritten."
        ),
    )

    return parser.parse_args()


def infer_windows_drive_from_linux_path(path: Path) -> str | None:
    """
    Infer the Windows drive letter from a WSL path such as:

        /mnt/c/projects/file.def

    Returns 'C' in this example.
    """

    parts = path.resolve(strict=False).parts

    if (
        len(parts) >= 3
        and parts[0] == os.sep
        and parts[1].lower() == "mnt"
        and len(parts[2]) == 1
        and parts[2].isalpha()
    ):
        return parts[2].upper()

    return None


def strip_matching_quotes(value: str) -> tuple[str, str | None]:
    """
    Remove matching surrounding single or double quotes.

    Returns:
        (unquoted_value, quote_character_or_None)
    """

    stripped = value.strip()

    if (
        len(stripped) >= 2
        and stripped[0] == stripped[-1]
        and stripped[0] in {"'", '"'}
    ):
        return stripped[1:-1], stripped[0]

    return stripped, None


def convert_windows_path(
    windows_path: str,
    relative_base: Path,
    inferred_drive: str | None,
) -> str:
    """
    Convert a Windows path into an absolute Linux path.

    Rules:
      C:\\foo\\bar       -> /mnt/C/foo/bar
      C:/foo/bar         -> /mnt/C/foo/bar
      ..\\foo\\bar       -> resolved relative to relative_base
      \\foo\\bar         -> /mnt/<inferred-drive>/foo/bar

    UNC paths are rejected because their Linux mount location is
    system-dependent.
    """

    path_text, quote = strip_matching_quotes(windows_path)

    if not path_text:
        raise ConversionError("empty path")

    # UNC path: \\server\share\folder
    if path_text.startswith("\\\\") or path_text.startswith("//"):
        raise ConversionError(
            f"UNC path has no universal Linux mapping: {path_text!r}"
        )

    # Fully qualified drive path: C:\folder or C:/folder
    match = DRIVE_ABSOLUTE_RE.match(path_text)

    if match:
        drive = match.group("drive").upper()
        rest = match.group("rest").replace("\\", "/")

        linux_path = Path(f"/mnt/{drive}") / rest
        result = str(linux_path.resolve(strict=False))

        return f"{quote}{result}{quote}" if quote else result

    # Drive-relative path such as C:folder is not the same as C:\folder.
    match = DRIVE_RELATIVE_RE.match(path_text)

    if match:
        raise ConversionError(
            "drive-relative paths such as "
            f"{path_text!r} are ambiguous; use an absolute path such as "
            f"{match.group('drive').upper()}:\\..."
        )

    # Root-relative Windows path: \folder\subfolder
    if path_text.startswith("\\") or path_text.startswith("/"):
        if inferred_drive is None:
            raise ConversionError(
                f"cannot determine the drive for root-relative path "
                f"{path_text!r}; the input file is not under /mnt/<drive>"
            )

        rest = path_text.lstrip("\\/").replace("\\", "/")
        linux_path = Path(f"/mnt/{inferred_drive}") / rest
        result = str(linux_path.resolve(strict=False))

        return f"{quote}{result}{quote}" if quote else result

    # Ordinary relative Windows path.
    relative_path = path_text.replace("\\", "/")
    linux_path = relative_base / relative_path
    result = str(linux_path.resolve(strict=False))

    return f"{quote}{result}{quote}" if quote else result


def convert_line(
    line: str,
    relative_base: Path,
    inferred_drive: str | None,
    line_number: int,
) -> str:
    """
    Convert the path in a DEFINE line.

    Non-DEFINE lines are returned unchanged.
    """

    match = DEFINE_RE.match(line)

    if not match:
        return line

    prefix = match.group("prefix")
    original_path = match.group("path")
    newline = match.group("newline") or ""

    try:
        converted_path = convert_windows_path(
            original_path,
            relative_base,
            inferred_drive,
        )
    except ConversionError as exc:
        raise ConversionError(f"line {line_number}: {exc}") from exc

    return f"{prefix}{converted_path}{newline}"


def paths_refer_to_same_location(first: Path, second: Path) -> bool:
    """
    Compare two paths safely, including paths that do not yet exist.
    """

    first_resolved = first.resolve(strict=False)
    second_resolved = second.resolve(strict=False)

    if first_resolved == second_resolved:
        return True

    if first.exists() and second.exists():
        try:
            return first.samefile(second)
        except OSError:
            pass

    return False


def main() -> int:
    args = parse_arguments()

    input_path = args.input.expanduser().resolve(strict=False)
    target_directory = args.target.expanduser().resolve(strict=False)

    if not input_path.exists():
        print(
            f"Error: input file does not exist: {input_path}",
            file=sys.stderr,
        )
        return 1

    if not input_path.is_file():
        print(
            f"Error: --input is not a regular file: {input_path}",
            file=sys.stderr,
        )
        return 1

    if target_directory.exists() and not target_directory.is_dir():
        print(
            f"Error: --target is not a directory: {target_directory}",
            file=sys.stderr,
        )
        return 1

    output_path = target_directory / input_path.name

    # This check is performed before creating the target directory.
    if paths_refer_to_same_location(input_path, output_path):
        print(
            "Error: the requested output file is the input file itself.",
            file=sys.stderr,
        )
        print(f"Input:  {input_path}", file=sys.stderr)
        print(f"Output: {output_path}", file=sys.stderr)
        print(
            "Choose a different --target directory.",
            file=sys.stderr,
        )
        return 1

    if output_path.exists() and not args.force:
        print(
            f"Error: output file already exists: {output_path}",
            file=sys.stderr,
        )
        print(
            "Use --force to overwrite it.",
            file=sys.stderr,
        )
        return 1

    relative_base = input_path.parent
    inferred_drive = infer_windows_drive_from_linux_path(input_path)

    try:
        # newline="" preserves the original newline style.
        with input_path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as input_file:
            original_lines = input_file.readlines()

        converted_lines = [
            convert_line(
                line=line,
                relative_base=relative_base,
                inferred_drive=inferred_drive,
                line_number=line_number,
            )
            for line_number, line in enumerate(original_lines, start=1)
        ]

    except UnicodeDecodeError as exc:
        print(
            f"Error: input file is not valid UTF-8: {exc}",
            file=sys.stderr,
        )
        return 1

    except ConversionError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        target_directory.mkdir(parents=True, exist_ok=True)

        # Recheck after creating the directory, guarding against unusual
        # symlink arrangements.
        if paths_refer_to_same_location(input_path, output_path):
            print(
                "Error: output resolves to the input file. "
                "The input will not be overwritten.",
                file=sys.stderr,
            )
            return 1

        with output_path.open(
            "w",
            encoding="utf-8",
            newline="",
        ) as output_file:
            output_file.writelines(converted_lines)

    except OSError as exc:
        print(
            f"Error writing output file {output_path}: {exc}",
            file=sys.stderr,
        )
        return 1

    print(f"Input:  {input_path}")
    print(f"Output: {output_path}")
    print(f"Converted {len(converted_lines)} total lines.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
