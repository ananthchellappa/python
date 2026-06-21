# operate on the output of eng_formatter : $ python3 /path/to/script whatever_eng.csv --> whatever_eng.xlsx
# expect input to look like :
# ,,u,,,,,,,,m,,,m,m,m,m,m,m,,m,m
# Point,Corner,L,Vin,temperature,toplevel_splitR.scs,Pass/Fail,Vo,Iout...
# so that it can use 'Pass/Fail' as the demarcator - it'll put everything to the right in the EC Table, and add everything
# that's in the left to the Min Corner and Max Corner for each EC Table row..
# to generate the vbaProject.bin, use the extract vba from John's github
import pandas as pd
import sys
import os
import pdb
import xlsxwriter as xw
import csv  # only way I know to read just one row :(
import re
from excel_utils import *

in_csv = sys.argv[1]  # what the user gives us
metadata = sys.version + " ".join(sys.argv) + " cwd : " + os.getcwd()

with open(in_csv, mode="r") as f_csv:
    csv_reader = csv.reader(f_csv)
    units = next(csv_reader)

# pdb.set_trace()

df = pd.read_csv(in_csv, skiprows=1)  # captures the corner data
# TEMP and Point are at the and we want to move them..
cols = df.columns.tolist()
cols_w_serial = df.columns.tolist()  # yes, DRY violated :)
cols_w_serial.insert(0, "#")

xl_data_start_row = 6

headers = list(
    map(lambda x: {"header": x}, cols_w_serial)
)  # read the docs for xlsxwriter -- [ { 'header' : whatever} ,..
writer = pd.ExcelWriter(".".join(in_csv.split(".")[:-1]) + ".xlsx", engine="xlsxwriter")
df.to_excel(
    writer,
    sheet_name="Corners",
    header=False,
    index=True,
    startrow=xl_data_start_row,
    startcol=1,
)  # index 10/19/19
workbook = writer.book
workbook.filename = in_csv.split(".")[0] + ".xlsm"
worksheet = writer.sheets[
    "Corners"
]  # the secret sauce that makes the macros ready to go!
workbook.add_vba_project("/home/analog/utils/vbaProject.bin")
workbook.set_vba_name("ThisWorkbook")
worksheet.add_table(
    xl_data_start_row - 1,
    1,
    xl_data_start_row - 1 + df.shape[0],
    df.shape[1] + 1,
    {  # note that shape[0] does not count header.. so have to add 1
        # also, shape[1] for columns doesn't count index (serial number) column... so there.. 10/19/19 eliminated the magic constants here..
        "columns": headers,
        "header_row": True,
        "autofilter": True,
        "style": "Table Style Light 18",
    },
)
# now, insert our min, max and be done..
for i, header in enumerate(cols_w_serial):
    worksheet.write(3, i + 1, header)  # header (yes, again)
    if i > 0:
        worksheet.write(0, i + 1, "=SUBTOTAL(104, Table1[" + header + "])")  # max
        worksheet.write(1, i + 1, "=SUBTOTAL(105, Table1[" + header + "])")  # min
        worksheet.write(
            4, i + 1, units[i - 1]
        )  # unit	-- messed up by the serial # thing :(
    else:
        worksheet.write(0, i + 1, "=SUBTOTAL(104, Table1['#])")  # max
        worksheet.write(1, i + 1, "=SUBTOTAL(105, Table1['#])")  # min


worksheet.write(0, 0, "Max")
worksheet.write(1, 0, "Min")

worksheet.write_comment("A1", metadata)
worksheet.set_vba_name("Sheet1")

# now, let's build an EC Table to make life easier
ind_pf = cols.index("Pass/Fail")
ec_cols = ["Spec", "Units", "Min", "Max", "Min Corner", "Max Corner"]
ec_table = pd.DataFrame(columns=ec_cols)
min_rows = []
max_rows = []  # these are used to insert the hyperlinks..

# pdb.set_trace()

for i, header in enumerate(cols[ind_pf + 1 :]):
    maxv = df[header].max()
    maxc = df[df[header] == maxv].iloc[0, 0:ind_pf].to_string()
    maxc = re.sub("\n", "; ", maxc)
    maxc = re.sub("\s+", "=", maxc)
    maxc = re.sub(";=", ";", maxc)
    max_rows.append(df.loc[df[header] == maxv].index[0])

    minv = df[header].min()
    minc = df[df[header] == minv].iloc[0, 0:ind_pf].to_string()
    minc = re.sub("\n", "; ", minc)
    minc = re.sub("\s+", "=", minc)
    minc = re.sub(";=", ";", minc)
    min_rows.append(df.loc[df[header] == minv].index[0])

    ec_table = ec_table.append(
        {
            "Spec": header,
            "Units": units[i + 1 + ind_pf],
            "Min": minv,
            "Max": maxv,
            "Min Corner": minc,
            "Max Corner": maxc,
        },
        ignore_index=True,
    )

ec_table.to_excel(writer, sheet_name="EC Table", header=False, startrow=3, startcol=1)
worksheet = writer.sheets["EC Table"]
cols = ["#"]
cols.extend(ec_cols)
headers = list(
    map(lambda x: {"header": x}, cols)
)  # read the docs for xlsxwriter -- [ { 'header' : whatever} ,..
worksheet.add_table(
    2,
    1,
    2 + ec_table.shape[0],
    1 + ec_table.shape[1],
    {  # note that shape[0] does not count header.. so have to add 1
        "columns": headers,
        "header_row": True,
        "autofilter": False,
        "style": "Table Style Light 18",
    },
)


ec_table.to_excel(writer, sheet_name="EC w Links", header=False, startrow=3, startcol=1)
worksheet = writer.sheets["EC w Links"]

# so now, when you want to write the links (same text, but hyperlinks added..), it's col 6 for min cor, 7 for max
# xlsxwriter column notation (starting with 0)

for i, min_row in enumerate(min_rows):
    worksheet.write_url(
        3 + i,
        6,
        "internal:Corners!"
        + colnum_string(i + ind_pf + 4)
        + str(1 + xl_data_start_row + min_row),
        string=ec_table["Min Corner"][i],
    )
    worksheet.write_url(
        3 + i,
        7,
        "internal:Corners!"
        + colnum_string(i + ind_pf + 4)
        + str(1 + xl_data_start_row + max_rows[i]),
        string=ec_table["Max Corner"][i],
    )


cols = ["#"]
cols.extend(ec_cols)
headers = list(
    map(lambda x: {"header": x}, cols)
)  # read the docs for xlsxwriter -- [ { 'header' : whatever} ,..
worksheet.add_table(
    2,
    1,
    2 + ec_table.shape[0],
    1 + ec_table.shape[1],
    {  # note that shape[0] does not count header.. so have to add 1
        "columns": headers,
        "header_row": True,
        "autofilter": False,
        "style": "Table Style Light 18",
    },
)
writer.save()
