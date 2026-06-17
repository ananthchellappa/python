#!/usr/bin/env python3
import os
import re
import sys

INST_RE = re.compile(r"\S+\.m_mos\b")

# Default output order (preferred)
DEFAULT_ORDER = ["REGION", "vbs", "vds", "vdsat", "vgt", "vgs", "vth", "id", "gm", "gds"]


def usage(prog: str) -> int:
    print(
        f"Usage: {prog} [-all] <result_file_path_name> <device_name> [-latest]\n"
        f"  <device_name> may use either '.' or '/' as the hierarchy separator.\n"
        f"  Example: XDUT/X1/X2/xMNcdio.m_mos is accepted as XDUT.X1.X2.xMNcdio.m_mos\n"
        f"\n"
        f"  Default prints (order): {', '.join(DEFAULT_ORDER)} (id falls back to ids if missing)\n"
        f"  -all    : print all rows in the mini-table\n"
        f"  -latest : if <result_file_path_name> includes a directory, ignore it and instead\n"
        f"            use the newest subdirectory under the current directory, looking for the same basename\n"
        f"            (if only a basename is provided, -latest has no effect)",
        file=sys.stderr,
    )
    return 2


def device_candidates_from_arg(device_arg: str) -> list[str]:
    """
    Return acceptable device-name spellings.

    Result files commonly use '.' as the hierarchy separator, but users may
    naturally type '/'.

    Examples:
      XDUT.X1.xMN.m_mos      -> XDUT.X1.xMN.m_mos
      XDUT/X1/xMN.m_mos      -> XDUT.X1.xMN.m_mos
      /XDUT/X1/xMN.m_mos/    -> XDUT.X1.xMN.m_mos
    """
    candidates: list[str] = []

    def add(s: str) -> None:
        s = s.strip()
        if s and s not in candidates:
            candidates.append(s)

    add(device_arg)

    if "/" in device_arg:
        slash_as_dot = re.sub(r"/+", ".", device_arg.strip()).strip(".")
        add(slash_as_dot)

    return candidates


def newest_subdir(cwd: str) -> str | None:
    best_path = None
    best_mtime = None
    try:
        for name in os.listdir(cwd):
            p = os.path.join(cwd, name)
            if os.path.isdir(p):
                try:
                    m = os.path.getmtime(p)
                except OSError:
                    continue
                if best_mtime is None or m > best_mtime:
                    best_mtime = m
                    best_path = p
    except OSError:
        return None
    return best_path


def resolve_latest(path_arg: str, latest: bool) -> tuple[str, bool]:
    """
    Returns (resolved_path, was_latest_applied)
    """
    if not latest:
        return path_arg, False

    basename = os.path.basename(path_arg)
    dirpart = os.path.dirname(path_arg)

    # If user gave only "file.ext" (no directory), -latest does not apply.
    if dirpart == "":
        return path_arg, False

    cwd = os.getcwd()
    sub = newest_subdir(cwd)
    if sub is None:
        raise FileNotFoundError("No subdirectories found in current directory for -latest search.")

    candidate = os.path.join(sub, basename)
    if not os.path.isfile(candidate):
        raise FileNotFoundError(
            f"-latest enabled, but '{basename}' was not found in newest subdirectory:\n"
            f"  newest_subdir = {sub}\n"
            f"  expected_file = {candidate}"
        )

    return candidate, True


def parse_table_for_device(lines: list[str], start_model_idx: int, device_candidates: list[str]):
    """
    Given the file lines and an index pointing at a MODEL row, return:
      (matched_device, insts, col, rows_dict, end_idx)

    where rows_dict maps rowname -> value_for_device.
    """
    n = len(lines)

    def prev_nonblank(idx: int) -> int:
        while idx >= 0 and lines[idx].strip() == "":
            idx -= 1
        return idx

    # Gather header lines immediately above MODEL until blank line
    h = prev_nonblank(start_model_idx - 1)
    if h < 0:
        return None

    k = h
    while k >= 0 and lines[k].strip() != "":
        k -= 1

    header_block = " ".join(l.strip() for l in lines[k + 1 : h + 1])
    insts = INST_RE.findall(header_block)
    if not insts:
        return None

    matched_device = None
    for d in device_candidates:
        if d in insts:
            matched_device = d
            break

    if matched_device is None:
        return None

    col = insts.index(matched_device)

    rows = {}
    j = start_model_idx
    while j < n and lines[j].strip() != "":
        row = lines[j].strip()
        parts = row.split()
        if not parts:
            j += 1
            continue
        rowname = parts[0]
        values = parts[1:]
        if col < len(values):
            rows[rowname] = values[col]
        # else: malformed/short row => ignore (fault tolerant)
        j += 1

    return matched_device, insts, col, rows, j


def extract_device_table(path: str, device_arg: str, print_all: bool) -> int:
    device_candidates = device_candidates_from_arg(device_arg)

    try:
        with open(path, "r", errors="replace") as f:
            lines = f.readlines()
    except OSError as e:
        print(f"Error opening '{path}': {e}", file=sys.stderr)
        return 2

    n = len(lines)
    i = 0
    while i < n:
        if lines[i].lstrip().startswith("MODEL"):
            parsed = parse_table_for_device(lines, i, device_candidates)
            if parsed is None:
                i += 1
                continue

            _matched_device, _insts, _col, rows, _end = parsed

            if print_all:
                # Print in file order (MODEL line onward)
                j = i
                while j < n and lines[j].strip() != "":
                    parts = lines[j].split()
                    if parts:
                        rowname = parts[0].strip()
                        if rowname in rows:
                            print(f"{rowname:<12} {rows[rowname]}")
                    j += 1
                return 0

            # Default: print selected keys in desired order, with id->ids fallback
            for key in DEFAULT_ORDER:
                if key == "id":
                    if "id" in rows:
                        print(f"{'id':<12} {rows['id']}")
                    elif "ids" in rows:
                        # fallback: print under label "id" but value from "ids"
                        print(f"{'id':<12} {rows['ids']}")
                    # else: neither exists => skip silently
                else:
                    if key in rows:
                        print(f"{key:<12} {rows[key]}")
            return 0

        i += 1

    if len(device_candidates) == 1:
        print(f"Device not found in any MOS mini-table: {device_arg}", file=sys.stderr)
    else:
        print(
            "Device not found in any MOS mini-table. Tried:\n"
            + "\n".join(f"  {d}" for d in device_candidates),
            file=sys.stderr,
        )
    return 1


def main() -> int:
    args = sys.argv[1:]
    if not args:
        return usage(sys.argv[0])

    print_all = False
    latest = False
    positionals: list[str] = []

    # Allow flags anywhere
    for a in args:
        if a == "-all":
            print_all = True
        elif a == "-latest":
            latest = True
        elif a.startswith("-"):
            print(f"Unknown option: {a}", file=sys.stderr)
            return usage(sys.argv[0])
        else:
            positionals.append(a)

    if len(positionals) != 2:
        return usage(sys.argv[0])

    path_arg, device_arg = positionals

    try:
        path, latest_applied = resolve_latest(path_arg, latest)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 2

    if latest and latest_applied:
        print(f"Using file: {os.path.abspath(path)}\n")

    return extract_device_table(path, device_arg, print_all)


if __name__ == "__main__":
    raise SystemExit(main())
