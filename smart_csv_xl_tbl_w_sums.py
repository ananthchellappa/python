import pandas as pd
import sys
import xlsxwriter as xw
import os

in_csv = sys.argv[1]
basename = os.path.splitext(in_csv)[0]

# Check if it's an "_eng.csv" file
is_eng = basename.endswith("_eng")

# Read the file accordingly
if is_eng:
    raw_df = pd.read_csv(in_csv, header=None)
    comment_row = raw_df.iloc[0]
    raw_header = raw_df.iloc[1].astype(str).tolist()

    def dedup(headers):
        seen = {}
        result = []
        for col in headers:
            if col not in seen:
                seen[col] = 0
                result.append(col)
            else:
                seen[col] += 1
                result.append(f"{col}.{seen[col]}")
        return result

    sanitized_headers = dedup(raw_header)
    df = raw_df[2:].copy()
    df.columns = sanitized_headers
else:
    df = pd.read_csv(in_csv)
    comment_row = None

# Convert to numeric where possible
df = df.apply(pd.to_numeric, errors="coerce")

headers = [{"header": col} for col in df.columns.tolist()]

writer = pd.ExcelWriter(basename + ".xlsx", engine="xlsxwriter")
df.to_excel(
    writer, sheet_name="EC Table", header=False, index=False, startrow=7, startcol=1
)

workbook = writer.book
worksheet = writer.sheets["EC Table"]

# If there's a comment row, write it above the table
if comment_row is not None:
    for col_idx, val in enumerate(comment_row):
        worksheet.write(5, 1 + col_idx, str(val) if pd.notna(val) else "")

# Manually write column headers one row above the data
for col_idx, header in enumerate(df.columns):
    worksheet.write(6, 1 + col_idx, header)

# Add the table starting from the manually written header
start_col = 1
end_col = start_col + df.shape[1] - 1
worksheet.add_table(
    6,
    start_col,
    7 + df.shape[0],
    end_col,
    {
        "columns": headers,
        "header_row": True,
        "autofilter": True,
        "style": "Table Style Light 18",
        "name": "Table1",
    },
)

# Add summary rows at top with SUBTOTAL over visible cells
# Labels in column A
worksheet.write(0, 0, "Max")
worksheet.write(1, 0, "Min")
worksheet.write(2, 0, "Avg")
worksheet.write(3, 0, "Std")

# Define a format with 2 decimal places
num_fmt = workbook.add_format({"num_format": "0.00"})

# Per-column formulas with number format
for col_idx, header in enumerate(df.columns):
    worksheet.write_formula(0, 1 + col_idx, f"=SUBTOTAL(104,Table1[{header}])", num_fmt)
    worksheet.write_formula(1, 1 + col_idx, f"=SUBTOTAL(105,Table1[{header}])", num_fmt)
    worksheet.write_formula(2, 1 + col_idx, f"=SUBTOTAL(101,Table1[{header}])", num_fmt)
    worksheet.write_formula(3, 1 + col_idx, f"=SUBTOTAL(107,Table1[{header}])", num_fmt)

writer.close()
