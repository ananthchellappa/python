#!/usr/bin/env python3

import argparse
import shutil
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Copy local cellname.va files into missing Verilog-A views "
            "in an OpenAccess library."
        )
    )
    parser.add_argument(
        "input_lib_path",
        type=Path,
        help="Path to the OpenAccess library",
    )
    args = parser.parse_args()

    input_lib_path = args.input_lib_path.expanduser().resolve()

    if not input_lib_path.exists():
        print(
            f"ERROR: Library path does not exist: {input_lib_path}",
            file=sys.stderr,
        )
        return 1

    if not input_lib_path.is_dir():
        print(
            f"ERROR: Library path is not a directory: {input_lib_path}",
            file=sys.stderr,
        )
        return 1

    va_files = sorted(Path.cwd().glob("*.va"))

    if not va_files:
        print(f"No .va files found in current directory: {Path.cwd()}")
        return 0

    copied = 0
    skipped_existing = 0
    skipped_missing_cell = 0
    errors = 0

    for source_file in va_files:
        cell_name = source_file.stem
        cell_directory = input_lib_path / cell_name
        destination_directory = cell_directory / "veriloga"
        destination_file = destination_directory / "veriloga.va"

        # Do not accidentally create a new OA cell from a misspelled filename.
        if not cell_directory.is_dir():
            print(
                f"WARNING: {cell_name}: cell directory does not exist; skipped:\n"
                f"         {cell_directory}"
            )
            skipped_missing_cell += 1
            continue

        if destination_directory.exists():
            print(
                f"SKIP:    {cell_name}: veriloga view already exists:\n"
                f"         {destination_directory}"
            )
            skipped_existing += 1
            continue

        try:
            destination_directory.mkdir()

            try:
                shutil.copy2(source_file, destination_file)
            except Exception:
                # Avoid leaving an empty view directory if the copy fails.
                try:
                    destination_directory.rmdir()
                except OSError:
                    pass
                raise

            print(
                f"COPIED:  {source_file.name}\n"
                f"      -> {destination_file}"
            )
            copied += 1

        except OSError as exc:
            print(
                f"ERROR:   {cell_name}: {exc}",
                file=sys.stderr,
            )
            errors += 1

    print()
    print("Summary:")
    print(f"  Copied:                         {copied}")
    print(f"  Existing veriloga views:        {skipped_existing}")
    print(f"  Missing OA cell directories:    {skipped_missing_cell}")
    print(f"  Errors:                         {errors}")

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
    
