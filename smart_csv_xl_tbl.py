# Enhanced gen_table_from_csv.py
# you can run on the output of the perl/eng_formatter.pl (to create an _eng.csv) which has unit names as first row
# to get a final table that is more viewer friendly
# all changes done by chatGPT. In the _eng case, the top-most non blank row has the engineering prefixes (m,n, etc)
# python3 script.py whatever.csv # gives you whatever.xlsx

import pandas as pd
import sys
import xlsxwriter as xw
import os

in_csv = sys.argv[1]
basename = os.path.splitext(in_csv)[0]

# Check if it's an "_eng.csv" file
is_eng = basename.endswith('_eng')

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
df = df.apply(pd.to_numeric, errors='coerce')

headers = [{'header': col} for col in df.columns.tolist()]

writer = pd.ExcelWriter(basename + '.xlsx', engine='xlsxwriter')
df.to_excel(writer, sheet_name='EC Table', header=False, index=False, startrow=4, startcol=1)

workbook = writer.book
worksheet = writer.sheets['EC Table']

# If there's a comment row, write it above the table
if comment_row is not None:
    for col_idx, val in enumerate(comment_row):
        worksheet.write(2, 1 + col_idx, str(val) if pd.notna(val) else '')

# Manually write column headers one row above the data
for col_idx, header in enumerate(df.columns):
    worksheet.write(3, 1 + col_idx, header)

# Add the table starting from the manually written header
start_col = 1
end_col = start_col + df.shape[1] - 1
worksheet.add_table(
    3, start_col, 4 + df.shape[0], end_col,
    {
        'columns': headers,
        'header_row': True,
        'autofilter': True,
        'style': 'Table Style Light 18'
    }
)

writer.close()
