#!/usr/bin/env python3
import re
import sys

INST_RE = re.compile(r"\S+\.m_mos\b")

DEFAULT_KEYS = {"REGION", "vbs", "vds", "vdsat", "vgt", "vgs", "vth", "id", "gm", "gds"}

def usage(prog: str) -> int:
    print(
        f"Usage: {prog} [-all] <result_file_path_name> <device_name>\n"
        f"  Default prints: {', '.join(['REGION','vbs','vds','vdsat','vgt','vgs','vth','id','gm','gds'])}\n"
        f"  -all : print all rows in the mini-table",
        file=sys.stderr,
    )
    return 2

def main() -> int:
    args = sys.argv[1:]
    print_all = False

    if not args or len(args) < 2:
        return usage(sys.argv[0])

    if args[0] == "-all":
        print_all = True
        args = args[1:]

    if len(args) != 2:
        return usage(sys.argv[0])

    path, device = args[0], args[1]

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
            # Gather header lines immediately above MODEL until blank line
            h = i - 1
            while h >= 0 and lines[h].strip() == "":
                h -= 1
            if h < 0:
                i += 1
                continue

            # Walk upward to the blank line that separates sections
            k = h
            while k >= 0 and lines[k].strip() != "":
                k -= 1

            header_block = " ".join(l.strip() for l in lines[k+1 : h+1])
            insts = INST_RE.findall(header_block)

            if not insts or device not in insts:
                i += 1
                continue

            col = insts.index(device)

            # Print rows from MODEL down to blank line terminator
            j = i
            while j < n and lines[j].strip() != "":
                row = lines[j].strip()
                parts = row.split()
                if not parts:
                    j += 1
                    continue

                rowname = parts[0]
                if (not print_all) and (rowname not in DEFAULT_KEYS):
                    j += 1
                    continue

                values = parts[1:]

                # Fault tolerant: if row is shorter than expected, skip quietly
                if col >= len(values):
                    j += 1
                    continue

                print(f"{rowname:<12} {values[col]}")
                j += 1

            return 0

        i += 1

    print(f"Device not found in any MOS mini-table: {device}", file=sys.stderr)
    return 1

if __name__ == "__main__":
    raise SystemExit(main())
