#!/usr/bin/env python3
"""
delete_cadence_views.py

Safely delete a specified Cadence view directory from cells in the current
directory, but only when the same view exists for that cell in a separately
specified safe copy of the library.

Example:
    python3 delete_cadence_views.py \
        --delete schematic \
        --safe_copy /path/to/safe_copy_dir

By default, the script asks for final confirmation after completing a full
preflight check. Use --yes to skip that prompt.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Delete a view directory from cells in the current directory only "
            "when the corresponding view exists in a safe copy of the library."
        )
    )
    parser.add_argument(
        "--delete",
        required=True,
        metavar="VIEW",
        help="View directory to delete, for example: schematic",
    )
    parser.add_argument(
        "--safe_copy",
        required=True,
        type=Path,
        metavar="DIR",
        help="Path to the safe copy of the Cadence library",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Perform all checks and show what would be deleted, but delete nothing",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Do not ask for final confirmation",
    )
    return parser.parse_args()


def resolved(path: Path) -> Path:
    """Resolve a path without requiring every final component to exist."""
    return path.expanduser().resolve(strict=False)


def is_relative_to(path: Path, possible_parent: Path) -> bool:
    """Compatibility helper equivalent to Path.is_relative_to()."""
    try:
        path.relative_to(possible_parent)
        return True
    except ValueError:
        return False


def validate_view_name(view: str) -> None:
    if not view:
        raise ValueError("The view name cannot be empty.")

    view_path = Path(view)

    # A view must be one immediate directory name, not a path.
    if (
        view in {".", ".."}
        or view_path.name != view
        or "/" in view
        or "\\" in view
        or "\0" in view
    ):
        raise ValueError(
            f"Invalid view name {view!r}. Specify one directory name, "
            "such as 'schematic'."
        )


def find_cell_directories(library_dir: Path) -> list[Path]:
    """
    Return immediate child directories considered to be cells.

    Symlinked cell directories are included when they resolve to directories.
    Hidden directories are ignored.
    """
    cells: list[Path] = []

    try:
        entries = list(library_dir.iterdir())
    except OSError as exc:
        raise RuntimeError(f"Cannot read current directory: {exc}") from exc

    for entry in entries:
        if entry.name.startswith("."):
            continue
        try:
            if entry.is_dir():
                cells.append(entry)
        except OSError as exc:
            raise RuntimeError(f"Cannot inspect {entry}: {exc}") from exc

    return sorted(cells, key=lambda p: p.name.casefold())


def main() -> int:
    args = parse_args()

    try:
        validate_view_name(args.delete)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    view_name = args.delete
    current_library = Path.cwd().resolve()
    safe_library = resolved(args.safe_copy)

    if not safe_library.exists():
        print(
            f"ERROR: Safe-copy directory does not exist:\n  {safe_library}",
            file=sys.stderr,
        )
        return 2

    if not safe_library.is_dir():
        print(
            f"ERROR: Safe-copy path is not a directory:\n  {safe_library}",
            file=sys.stderr,
        )
        return 2

    # Avoid nonsensical or dangerous configurations.
    if safe_library == current_library:
        print(
            "ERROR: The safe-copy directory is the current directory.",
            file=sys.stderr,
        )
        return 2

    if is_relative_to(safe_library, current_library):
        print(
            "ERROR: The safe-copy directory is inside the current library.\n"
            "       Use a separate library copy.",
            file=sys.stderr,
        )
        return 2

    if is_relative_to(current_library, safe_library):
        print(
            "ERROR: The current library is inside the safe-copy directory.\n"
            "       Use two separate library trees.",
            file=sys.stderr,
        )
        return 2

    try:
        cells = find_cell_directories(current_library)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if not cells:
        print("No cell directories were found in the current directory.")
        return 0

    targets: list[tuple[Path, Path]] = []
    skipped_no_local_view: list[Path] = []
    verification_failures: list[tuple[Path, Path, str]] = []

    # Full preflight: collect every target and verify every backup before
    # deleting even one directory.
    for cell_dir in cells:
        local_view = cell_dir / view_name

        try:
            local_exists = local_view.is_dir()
        except OSError as exc:
            verification_failures.append(
                (cell_dir, safe_library / cell_dir.name / view_name,
                 f"cannot inspect local view: {exc}")
            )
            continue

        if not local_exists:
            skipped_no_local_view.append(cell_dir)
            continue

        safe_view = safe_library / cell_dir.name / view_name

        try:
            if not safe_view.exists():
                reason = "safe-copy view does not exist"
            elif not safe_view.is_dir():
                reason = "safe-copy view exists but is not a directory"
            else:
                reason = ""
        except OSError as exc:
            reason = f"cannot inspect safe-copy view: {exc}"

        if reason:
            verification_failures.append((cell_dir, safe_view, reason))
        else:
            targets.append((local_view, safe_view))

    print(f"Current library : {current_library}")
    print(f"Safe copy       : {safe_library}")
    print(f"View            : {view_name}")
    print(f"Cells examined  : {len(cells)}")
    print(f"Views found     : {len(targets) + len(verification_failures)}")
    print()

    if verification_failures:
        print("PRECHECK FAILED — nothing has been deleted.")
        print()
        print(
            "The following local views cannot be deleted because their "
            "safe-copy views were not verified:"
        )
        for cell_dir, safe_view, reason in verification_failures:
            print(f"  Cell: {cell_dir.name}")
            print(f"    Expected: {safe_view}")
            print(f"    Problem : {reason}")
        return 1

    if not targets:
        print(
            f"No '{view_name}' view directories were found in the current library."
        )
        return 0

    print("Verified deletion targets:")
    for local_view, safe_view in targets:
        print(f"  DELETE: {local_view}")
        print(f"  BACKUP: {safe_view}")

    if skipped_no_local_view:
        print()
        print(
            f"Skipped {len(skipped_no_local_view)} cell(s) that do not have a "
            f"local '{view_name}' view."
        )

    if args.preview:
        print()
        print("Preview complete. Nothing was deleted.")
        return 0

    if not args.yes:
        print()
        answer = input(
            f"Delete these {len(targets)} '{view_name}' view director"
            f"{'y' if len(targets) == 1 else 'ies'}? Type DELETE to continue: "
        )
        if answer != "DELETE":
            print("Cancelled. Nothing was deleted.")
            return 0

    deleted = 0
    failures: list[tuple[Path, str]] = []

    for local_view, _safe_view in targets:
        try:
            # shutil.rmtree refuses a directory symlink rather than following it.
            # Handle that case explicitly by unlinking only the symlink itself.
            if local_view.is_symlink():
                local_view.unlink()
            else:
                shutil.rmtree(local_view)
            deleted += 1
            print(f"Deleted: {local_view}")
        except OSError as exc:
            failures.append((local_view, str(exc)))
            print(f"ERROR deleting {local_view}: {exc}", file=sys.stderr)

    print()
    print(f"Deleted successfully: {deleted}")

    if failures:
        print(f"Deletion failures   : {len(failures)}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
