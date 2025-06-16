#!/usr/bin/env python3
import sys
import os
import csv

def main():
    if len(sys.argv) != 2:
        print("Usage: script input_file.csv")
        sys.exit(1)

    input_file = sys.argv[1]
    base, ext = os.path.splitext(input_file)
    output_file = f"{base}_fixed{ext}"

    with open(input_file, newline='') as f:
        reader = list(csv.reader(f))

    top_lines = []
    bottom_lines = []

    for row in reader:
        if len(row) > 1 and ('Type' in row[1] or 'expr' in row[1]):
            top_lines.append(row)
        else:
            bottom_lines.append(row)

    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerows(top_lines + bottom_lines)

    print(f"Reordered CSV written to {output_file}")

if __name__ == "__main__":
    main()
