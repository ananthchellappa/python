import csv
import sys

if len(sys.argv) < 4:
    print("Usage: python3 minmax_by_column.py input.csv source_header field1 [field2 ...]")
    sys.exit(1)

csv_file = sys.argv[1]
source = sys.argv[2]
fields = sys.argv[3:]

with open(csv_file, newline='') as f:
    raw_reader = csv.reader(f)
    
    # Find the first non-empty header row
    for row in raw_reader:
        if all(cell.strip() != '' for cell in row):
            header = row
            break
    else:
        print("Error: No valid header row found (a row with all non-empty fields).")
        sys.exit(1)

    # Now treat the rest as data
    reader = csv.DictReader(f, fieldnames=header)
    data = list(reader)

# Validate fields
all_fields = [source] + fields
for field in all_fields:
    if field not in header:
        print(f"Error: Field '{field}' not found in header.")
        sys.exit(1)

# Convert source column to float and filter valid rows
valid_rows = []
for row in data:
    try:
        row[source] = float(row[source])
        valid_rows.append(row)
    except (ValueError, KeyError):
        continue  # Skip rows with non-numeric or missing source

if not valid_rows:
    print(f"No valid numeric data found in column '{source}'")
    sys.exit(1)

min_row = min(valid_rows, key=lambda r: r[source])
max_row = max(valid_rows, key=lambda r: r[source])

# Print output
print(",".join(all_fields))
print(",".join([str(min_row[source])] + [min_row[f] for f in fields]))
print(",".join([str(max_row[source])] + [max_row[f] for f in fields]))
