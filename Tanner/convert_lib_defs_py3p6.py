#!/usr/bin/env python3

"""
convert_lib_defs.py

Converts Windows paths in DEFINE statements to absolute Linux/WSL paths.

Example input:

    DEFINE lib_name ..\\..\\..\\dir_name\\Layout\\dir2_name\\folder_name
    DEFINE another_lib C:\\projects\\library

Example output:

    DEFINE lib_name /mnt/C/dir_name/Layout/dir2_name/folder_name
    DEFINE another_lib /mnt/C/projects/library

Relative paths are resolved relative to the directory containing the input
file, not relative to the directory from which this script is launched.

Usage:

    python3 convert_lib_defs.py --input /path/to/file --target /output/directory

The output filename is the same as the input filename.

The input file will never be overwritten.
"""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Optional, Tuple


DEFINE_RE = re.compile(
    r"^(?P<prefix>\s*DEFINE\s+\S+\s+)"
    r"(?P<path>.*?)"
    r"(?P<newline>\r?\n)?$",
    re.IGNORECASE
)

DRIVE_ABSOLUTE_RE = re.compile(
    r"^(?P<drive>[A-Za-z]):[\\/](?P<rest>.*)$"
)

DRIVE_RELATIVE_RE = re.compile(
    r"^(?P<drive>[A-Za-z]):(?P<rest>[^\\/].*)$"
)


class ConversionError(Exception):
    """Raised when a Windows path cannot be converted safely."""
    pass


def parse_arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Convert Windows paths in DEFINE lines to absolute Linux paths."
        )
    )

    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Input file containing DEFINE statements."
    )

    parser.add_argument(
        "--target",
        required=True,
        type=Path,
        help=(
            "Output directory. It may be absolute or relative to the "
            "current working directory."
        )
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Overwrite an existing output file. The input file itself "
            "can never be overwritten."
        )
    )

    return parser.parse_args()


def infer_windows_drive_from_linux_path(path):
    # type: (Path) -> Optional[str]
    """
    Infer a Windows drive letter from a WSL path.

    Example:

        /mnt/c/projects/file.def

    returns:

        C
    """

    resolved_path = path.resolve()
    parts = resolved_path.parts

    if (
        len(parts) >= 3
        and parts[0] == os.sep
        and parts[1].lower() == "mnt"
        and len(parts[2]) == 1
        and parts[2].isalpha()
    ):
        return parts[2].upper()

    return None


def strip_matching_quotes(value):
    # type: (str) -> Tuple[str, Optional[str]]
    """
    Remove matching surrounding single or double quotes.

    Returns:

        unquoted text, quote character

    The quote character is None when the path was not quoted.
    """

    stripped = value.strip()

    if (
        len(stripped) >= 2
        and stripped[0] == stripped[-1]
        and stripped[0] in ("'", '"')
    ):
        return stripped[1:-1], stripped[0]

    return stripped, None


def normalize_absolute_path(path):
    # type: (Path) -> str
    """
    Return a normalized absolute path without requiring it to exist.
    """

    return os.path.abspath(os.path.normpath(str(path)))


def convert_windows_path(windows_path, relative_base, inferred_drive):
    # type: (str, Path, Optional[str]) -> str
    """
    Convert a Windows path to an absolute Linux/WSL path.

    Conversions:

        C:\\foo\\bar
            -> /mnt/C/foo/bar

        C:/foo/bar
            -> /mnt/C/foo/bar

        ..\\foo\\bar
            -> resolved relative to the input file's directory

        \\foo\\bar
            -> /mnt/<inferred-drive>/foo/bar

    UNC paths are rejected because their Linux mount point cannot be
    determined automatically.
    """

    path_text, quote = strip_matching_quotes(windows_path)

    if not path_text:
        raise ConversionError("empty path")

    # UNC path, such as \\server\share\folder.
    if path_text.startswith("\\\\") or path_text.startswith("//"):
        raise ConversionError(
            "UNC path has no automatic Linux mapping: {!r}".format(
                path_text
            )
        )

    # Fully qualified Windows drive path, such as C:\folder.
    match = DRIVE_ABSOLUTE_RE.match(path_text)

    if match:
        drive = match.group("drive").upper()
        rest = match.group("rest").replace("\\", "/")

        linux_path = Path("/mnt") / drive / rest
        result = normalize_absolute_path(linux_path)

        if quote:
            return quote + result + quote

        return result

    # Drive-relative Windows path, such as C:folder.
    #
    # This is not equivalent to C:\folder. Its meaning depends on the
    # current directory associated with drive C: in Windows.
    match = DRIVE_RELATIVE_RE.match(path_text)

    if match:
        raise ConversionError(
            "drive-relative path {!r} is ambiguous; use an absolute "
            "path such as {}:\\...".format(
                path_text,
                match.group("drive").upper()
            )
        )

    # Root-relative Windows path, such as \folder\subfolder.
    if path_text.startswith("\\") or path_text.startswith("/"):
        if inferred_drive is None:
            raise ConversionError(
                "cannot determine the Windows drive for root-relative "
                "path {!r}; the input file is not under /mnt/<drive>".format(
                    path_text
                )
            )

        rest = path_text.lstrip("\\/").replace("\\", "/")
        linux_path = Path("/mnt") / inferred_drive / rest
        result = normalize_absolute_path(linux_path)

        if quote:
            return quote + result + quote

        return result

    # Ordinary relative Windows path.
    relative_path = path_text.replace("\\", "/")
    linux_path = relative_base / relative_path
    result = normalize_absolute_path(linux_path)

    if quote:
        return quote + result + quote

    return result


def convert_line(
    line,
    relative_base,
    inferred_drive,
    line_number
):
    # type: (str, Path, Optional[str], int) -> str
    """
    Convert the path in a DEFINE line.

    Lines that do not match:

        DEFINE library_name path

    are copied unchanged.
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
            inferred_drive
        )
    except ConversionError as error:
        raise ConversionError(
            "line {}: {}".format(line_number, error)
        )

    return prefix + converted_path + newline


def paths_refer_to_same_location(first, second):
    # type: (Path, Path) -> bool
    """
    Determine whether two paths refer to the same location.

    This works even when the output file does not yet exist.
    """

    first_absolute = normalize_absolute_path(first)
    second_absolute = normalize_absolute_path(second)

    if first_absolute == second_absolute:
        return True

    if first.exists() and second.exists():
        try:
            return os.path.samefile(
                str(first),
                str(second)
            )
        except OSError:
            pass

    return False


def main():
    args = parse_arguments()

    input_path = Path(
        normalize_absolute_path(args.input.expanduser())
    )

    target_directory = Path(
        normalize_absolute_path(args.target.expanduser())
    )

    if not input_path.exists():
        print(
            "Error: input file does not exist: {}".format(input_path),
            file=sys.stderr
        )
        return 1

    if not input_path.is_file():
        print(
            "Error: --input is not a regular file: {}".format(
                input_path
            ),
            file=sys.stderr
        )
        return 1

    if target_directory.exists() and not target_directory.is_dir():
        print(
            "Error: --target is not a directory: {}".format(
                target_directory
            ),
            file=sys.stderr
        )
        return 1

    output_path = target_directory / input_path.name

    # Prevent the user from selecting the input file's own directory as
    # the output target.
    if paths_refer_to_same_location(input_path, output_path):
        print(
            "Error: the requested output file is the input file itself.",
            file=sys.stderr
        )
        print(
            "Input:  {}".format(input_path),
            file=sys.stderr
        )
        print(
            "Output: {}".format(output_path),
            file=sys.stderr
        )
        print(
            "Choose a different --target directory.",
            file=sys.stderr
        )
        return 1

    if output_path.exists() and not args.force:
        print(
            "Error: output file already exists: {}".format(output_path),
            file=sys.stderr
        )
        print(
            "Use --force to overwrite the existing output copy.",
            file=sys.stderr
        )
        return 1

    relative_base = input_path.parent

    inferred_drive = infer_windows_drive_from_linux_path(
        input_path
    )

    try:
        # newline="" preserves the original Windows or Unix newline style.
        with input_path.open(
            mode="r",
            encoding="utf-8-sig",
            newline=""
        ) as input_file:
            original_lines = input_file.readlines()

        converted_lines = []

        for line_number, line in enumerate(original_lines, start=1):
            converted_line = convert_line(
                line=line,
                relative_base=relative_base,
                inferred_drive=inferred_drive,
                line_number=line_number
            )

            converted_lines.append(converted_line)

    except UnicodeDecodeError as error:
        print(
            "Error: input file is not valid UTF-8: {}".format(error),
            file=sys.stderr
        )
        return 1

    except ConversionError as error:
        print(
            "Error: {}".format(error),
            file=sys.stderr
        )
        return 1

    try:
        target_directory.mkdir(
            parents=True,
            exist_ok=True
        )

        # Check again after creating the target directory. This provides
        # additional protection in case symbolic links are involved.
        if paths_refer_to_same_location(input_path, output_path):
            print(
                "Error: output resolves to the input file. "
                "The input file will not be overwritten.",
                file=sys.stderr
            )
            return 1

        with output_path.open(
            mode="w",
            encoding="utf-8",
            newline=""
        ) as output_file:
            output_file.writelines(converted_lines)

    except OSError as error:
        print(
            "Error writing output file {}: {}".format(
                output_path,
                error
            ),
            file=sys.stderr
        )
        return 1

    define_count = 0

    for line in original_lines:
        if DEFINE_RE.match(line):
            define_count += 1

    print("Input:           {}".format(input_path))
    print("Output:          {}".format(output_path))
    print("Total lines:     {}".format(len(original_lines)))
    print("DEFINE lines:    {}".format(define_count))

    return 0


if __name__ == "__main__":
    sys.exit(main())
