#!/usr/bin/env python
# coding: utf-8

# this is a hack on Ananth_min_typ_max_xlsV12.py


# operate on the output of eng_formatter : $ python3 /path/to/script whatever_eng.csv --> whatever_eng.xlsx
# expect input to look like :
# ,,u,,,,,,,,m,,,m,m,m,m,m,m,,m,m
# Point,Corner,L,Vin,temperature,toplevel_splitR.scs,Pass/Fail,Vo,Iout...
# so that it can use 'Pass/Fail' as the demarcator - it'll put everything to the right in the EC Table, and add everything
# that's in the left to the Min Corner and Max Corner for each EC Table row..
# to generate the vbaProject.bin, use the extract vba from John's github
import pandas as pd
import ast
import sys
import os
import pdb
import xlsxwriter as xw
import csv  # only way I know to read just one row :(
import re
from math import isnan


def colnum_string(n):
    string = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        string = chr(65 + remainder) + string
    return string


# In[4]:


# process filter condition and apply on dataframe
def apply_filter(df, vname, op, val_list):
    if op == "<":
        try:
            val_list = ast.literal_eval(val_list)
            df = df[df[vname] < val_list]
        except:
            print("invalid filter condition")
    elif op == ">":
        try:
            val_list = ast.literal_eval(val_list)
            df = df[df[vname] > val_list]
        except:
            print("invalid filter condition")
    elif op == "<=":
        try:
            val_list = ast.literal_eval(val_list)
            df = df[df[vname] <= val_list]
        except:
            print("invalid filter condition")

    if op == ">=":
        try:
            val_list = ast.literal_eval(val_list)
            df = df[df[vname] >= val_list]
        except:
            print("invalid filter condition")
    elif op == "=":
        try:
            val_list = "[" + val_list + "]"
            val_list = ast.literal_eval(val_list)
            df = df[df[vname].isin(val_list)]
        except:
            print("invalid filter condition")
    elif op == "!":
        try:
            val_list = "[" + val_list + "]"
            val_list = ast.literal_eval(val_list)
            df = df[~df[vname].isin(val_list)]
        except:
            print("invalid filter condition")

    return df


# In[ ]:


# collect typ command line arguements
def find_typ_args():
    typ_args = []
    for i in range(2, len(sys.argv)):
        a = sys.argv[i]
        if "ignored" in a.lower() or "typical" in a.lower():
            typ_args.append(a)
    return typ_args


# In[ ]:


# get closest value to K in list lst
def closest(lst, K):

    return lst[min(range(len(lst)), key=lambda i: abs(lst[i] - K))]


# In[ ]:


# process typ cmd line arguements
def typ_row(df, bvname):
    # pdb.set_trace()
    global typ_args
    global tempName
    # step 1
    # filter by default variables
    df_typ = df[
        (df["Corner"].str.contains("nom|TT_", case=False))
        & (df[tempName].isin([27, 25]))
    ]
    tval = str(df_typ[tempName].max())
    cond = "Corner : nom" + "\n" + tempName + " : " + tval + "\n"
    # step 2
    # find list of vars for typ criteria in ignored= and typical=
    ignored_lst = []
    typ_lst = []
    ignored = ""
    typ = ""
    for i in range(0, len(typ_args)):
        if "ignored" in typ_args[i].lower():  # process ignored:
            ignored = typ_args[i]
            # ignored = ignored.lower()
            ignored_lst = ignored_lst + ignored.replace("ignored=", "").split(",")
        else:  # typical
            typ = typ_args[i]
            # typ = typ.lower()
            typ_lst = list(typ.replace("typical:", "").split(","))

    # step 3 get rid of ignored vars
    if len(ignored_lst) > 0:
        df_typ = df_typ.drop(columns=ignored_lst)

    # step 4 filtern
    var_lst = df_typ.columns
    var_list = "|".join(var_lst)
    typ_var = []
    new_df_typ = df_typ.copy()
    for typ_con in typ_lst:
        match = re.match(rf"({var_list})([<>!=])(\d+\.\d+|\d+)", typ_con)
        if match:  # filter condition is valid
            vname = match[1]
            typ_var.append(vname)
            op = match[2]
            val = match[3]
            df_typ = apply_filter(df_typ, vname, op, val)
            if df_typ.empty:
                # print("empty dataframe returned for " + typ_con)
                return (
                    pd.DataFrame(columns=df_typ.columns),
                    "No Typ data because no records for "
                    + cond
                    + "\n"
                    + typ_con
                    + " <--",
                )
            else:
                cond = cond + vname + " " + op + " " + val + "\n"
        else:
            # print("invalid typ condition" + typ_con)
            return (
                pd.DataFrame(columns=df_typ.columns),
                "No Typ data because invalid typ condition " + typ_con,
            )

    # step5 check if there are any variables that are not specified in either ignored or typical:
    ind_pf = df_typ.columns.tolist().index(tempName)
    unspecified_lst = []
    for col in var_lst[0:ind_pf]:  # from ind_pf-1
        if col not in ["#", "Point", bvname, "Corner", tempName]:
            if col not in typ_var and pd.api.types.is_numeric_dtype(df[col].dtypes):
                unspecified_lst.append(col)

    # step6 filter on unspecified list of vars
    # new_df_typ = df_typ.copy()

    for col in unspecified_lst:
        # find min max and mid
        min_val = df[col].min()
        max_val = df[col].max()
        mid = (min_val + max_val) / 2
        delta = (max_val - min_val) / 4
        if min_val == max_val:

            return (
                pd.DataFrame(columns=df_typ.columns),
                "No Typ data because " + col + " does not have a mid value",
            )
        else:
            # find mid val
            col_val_lst = df[col].unique().tolist()

            if len(col_val_lst) == 2:
                # print("yes")
                return (
                    pd.DataFrame(columns=df_typ.columns),
                    "No Typ data because " + col + " does not have a mid value",
                )

            # find colsest value to mid
            first_typ = closest(col_val_lst, mid)
            col_val_lst.remove(first_typ)

            second_typ = closest(col_val_lst, mid)
            # check if there is conflict in mid value
            if round(abs(mid - first_typ), 2) == round(abs(mid - second_typ), 2):
                # print("unspecified variable " + col + " has a tie for mid values")
                return pd.DataFrame(
                    columns=df_typ.columns
                ), "No Typ data because " + col + " has a tie for mid values" + str(
                    first_typ
                ) + " and " + str(
                    second_typ
                )

            else:
                mid_val = first_typ

            # check if value is within (max min)/4.0 of either min or max
            if mid_val <= (min_val + delta):
                # print("unspecified variable " + col + " mid value is within (max min)/4.0 of either min or max")
                return (
                    pd.DataFrame(columns=df_typ.columns),
                    "No Typ data because " + col + " mid value is too close to min",
                )
            elif mid_val >= (max_val - delta):
                # print("unspecified variable " + col + " mid value is within (max min)/4.0 of either min or max")
                return (
                    pd.DataFrame(columns=df_typ.columns),
                    "No Typ data because " + col + " mid value is too close to max",
                )
            else:
                cond = cond + col + " : " + str(mid_val) + "\n"
                df_typ = df_typ[df_typ[col] == mid_val]
                if df_typ.empty:
                    return (
                        pd.DataFrame(columns=df_typ.columns),
                        "No Typ data because no records for "
                        + cond
                        + col
                        + " : "
                        + str(mid_val)
                        + " <--",
                    )
                # if df_typ.shape[0] == 1:
                #    return  df_typ

    return df_typ, cond


def EC_tables_w_typ(bvname, df, cols, writer, name1, name2):

    # now, let's build an EC Table to make life easier
    ind_pf = cols.index("Pass/Fail")
    ec_cols = ["Spec", "Units", "Min", "Typ", "Max", "Min Corner", "Max Corner"]
    ec_table = pd.DataFrame(columns=ec_cols)
    min_rows = []
    max_rows = []  # these are used to insert the hyperlinks..

    # pdb.set_trace()
    # typ
    df_typ, cond = typ_row(df, bvname)
    if df_typ.shape[0] > 1:
        cond = "No Typ data because more than 1 row returned"
        df_typ = pd.DataFrame([])
    print(cond)
    # for each min, max, we get the subset of the dataframe with header=max (or min) and then
    # take the first row of this, which gives us a single column and then generate a string
    # like varName1=val1,varName2=val2, etc.. which will eventually go into Min Corner and Max Corner
    for i, header in enumerate(cols[ind_pf + 1 :]):
        maxv = df[header].max()
        if str == type(maxv) or isnan(maxv):
            maxc = "no data"
            max_rows.append(float("NaN"))
        else:
            maxc = df[df[header] == maxv].iloc[0, 0:ind_pf].to_string()
            maxc = re.sub(r"\n", "; ", maxc)
            maxc = re.sub(r"\s+", "=", maxc)
            maxc = re.sub(r";=", ";", maxc)
            max_rows.append(df.loc[df[header] == maxv].index[0])

        minv = df[header].min()
        if str == type(minv) or isnan(minv):
            minc = "no data"
            min_rows.append(float("NaN"))
        else:
            minc = df[df[header] == minv].iloc[0, 0:ind_pf].to_string()
            minc = re.sub(r"\n", "; ", minc)
            minc = re.sub(r"\s+", "=", minc)
            minc = re.sub(r";=", ";", minc)
            min_rows.append(df.loc[df[header] == minv].index[0])

        # typ
        if not df_typ.empty:
            typ = df_typ[header].max()
        else:
            typ = ""
        ec_table = pd.concat(
            [
                ec_table,
                pd.DataFrame.from_records(
                    [
                        {
                            "Spec": header,
                            "Units": units[i + 1 + ind_pf],
                            "Min": minv,
                            "Typ": typ,
                            "Max": maxv,
                            "Min Corner": minc,
                            "Max Corner": maxc,
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
    ec_table.to_excel(writer, sheet_name=name1, header=False, startrow=3, startcol=1)
    worksheet = writer.sheets[name1]
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

    ec_table.to_excel(writer, sheet_name=name2, header=False, startrow=3, startcol=1)
    worksheet.write_comment("F3", cond)
    worksheet = writer.sheets[name2]

    # so now, when you want to write the links (same text, but hyperlinks added..), it's col 7 for min cor, 8 for max
    # xlsxwriter column notation (starting with 0)

    for i, min_row in enumerate(min_rows):
        if not isnan(min_row):  # AC 4/15/21
            worksheet.write_url(
                3 + i,
                7,
                "internal:Corners!"
                + colnum_string(i + ind_pf + 4)
                + str(1 + xl_data_start_row + min_row),
                string=ec_table["Min Corner"][i],
            )
        if not isnan(max_rows[i]):
            worksheet.write_url(
                3 + i,
                8,
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
    worksheet.write_comment("F3", cond)


# add index information to the Index spreadsheet
def update_index_df(originating_spec, val, plain="EC", ec_wl="EC wL"):
    global index_df
    index_df = pd.concat(
        [
            index_df,
            pd.DataFrame.from_records(
                [
                    {
                        "Originating specifier": originating_spec[
                            0
                        ],  # to convert list to string
                        "VAR1": val,
                        "Plain": plain,
                        "w Links": ec_wl,
                    }
                ]
            ),
        ],
        ignore_index=True,
    )


# identify if there is typ related sys arguments
# declare index_table to store index sheet information
index_df = pd.DataFrame(columns=["Originating specifier", "VAR1", "Plain", "w Links"])
typ_args = find_typ_args()
in_csv = sys.argv[1]  # what the user gives us
tempName = "TEMP"
metadata = sys.version + " ".join(sys.argv) + " cwd : " + os.getcwd()

with open(in_csv, mode="r") as f_csv:
    csv_reader = csv.reader(f_csv)
    units = next(csv_reader)

# pdb.set_trace()

df = pd.read_csv(in_csv, skiprows=1)  # captures the corner data
df = df.dropna(how="all")

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
# workbook.filename = in_csv.split('.')[0] + '.xlsx'	# we are not adding macros, so it has to be plain xlsx
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
        worksheet.write(0, i + 1, "=SUBTOTAL(104, Table2[" + header + "])")  # max
        worksheet.write(1, i + 1, "=SUBTOTAL(105, Table2[" + header + "])")  # min
        worksheet.write(
            4, i + 1, units[i - 1]
        )  # unit	-- messed up by the serial # thing :(
    else:
        worksheet.write(0, i + 1, "=SUBTOTAL(104, Table2['#])")  # max
        worksheet.write(1, i + 1, "=SUBTOTAL(105, Table2['#])")  # min


worksheet.write(0, 0, "Max")
worksheet.write(1, 0, "Min")

worksheet.write_comment("A1", metadata)
worksheet.set_vba_name("Sheet1")

# pdb.set_trace() # 4/28/21
EC_tables_w_typ(None, df, cols, writer, "EC Table", "EC w Links")


# get all valid conditions conditions
var_lst = df.columns  # removed Pass/Fail
var_list = "|".join(var_lst)
# c = ['L!5;VDD>778'  'L'] #'L,!5;VDD,!6' ,'L'

if len(typ_args) > 0:
    start_fob_args = 2 + len(typ_args)
else:
    start_fob_args = 2
ec_lst = []
ecl_lst = []
# sheet_number for creating generic names of sheets
sheet_number = 0

# process breakout and filter
for i in range(start_fob_args, len(sys.argv)):
    # check for condition validity
    fob_spec = sys.argv[i].split(";")

    fob = 0
    f = ""
    breakout = 0
    data = df.copy()
    for o in fob_spec:
        match = re.match(rf"({var_list})(,[<>!=])?(.*)", o)
        match1 = re.match(rf"({var_list})([<>!=])(.*)", o)

        if match1:
            f = f + match1.group(0) + ";"

            vname = match1.group(1)
            op = match1.group(2)
            val_list = match1.group(3)
            data = apply_filter(data, vname, op, val_list)

        elif match:

            breakout = 1
            bvname = match.group(1)
            bop = match.group(2)
            bval_list = match.group(3)
        else:
            print("!!!! Please check: " + o + " contains unknown variable!!!")
            sys.exit(1)

    # remove last ;
    f = f[:-1]

    if breakout == 1:
        # process breakout
        if bop:
            # print("process breakout condition")
            bop = bop.replace(",", "")
            data = apply_filter(data, bvname, bop, bval_list)
        try:
            # pdb.set_trace()
            unique_val_list = data[bvname].unique()
            # add header to index table
            update_index_df([""], "", plain="", ec_wl="")
            update_index_df(
                ["Originating specifier"], bvname, plain="Plain", ec_wl="w Links"
            )
            for x in unique_val_list:
                dfx = data[data[bvname] == x]
                name1 = "EC " + bvname + "=" + str(x) + ";" + f
                name2 = "ECL " + bvname + "=" + str(x) + ";" + f
                if name1.endswith(";"):
                    name1 = name1[:-1]
                if name2.endswith(";"):
                    name2 = name2[:-1]
                # collect sheet name for reordering later
                sheet_number = sheet_number + 1
                ec_lst.append("EC " + str(sheet_number))
                ecl_lst.append("ECL " + str(sheet_number))

                EC_tables_w_typ(
                    bvname,
                    dfx,
                    cols,
                    writer,
                    "EC " + str(sheet_number),
                    "ECL " + str(sheet_number),
                )
                # update Index sheet

                update_index_df(
                    [sys.argv[i].replace("'", "")],
                    x,
                    plain="EC " + str(sheet_number),
                    ec_wl="ECL " + str(sheet_number),
                )
        except:
            print("invalid breakout condition")

    elif breakout == 0:
        sheet_number = sheet_number + 1
        ec_lst.append("EC " + str(sheet_number))
        ecl_lst.append("ECL " + str(sheet_number))
        # update headers in index df

        update_index_df([""], "", plain="", ec_wl="")
        update_index_df(["Originating specifier"], "", plain="Plain", ec_wl="w Links")
        EC_tables_w_typ(
            None,
            data,
            cols,
            writer,
            "EC " + str(sheet_number),
            "ECL " + str(sheet_number),
        )
        # update Index sheet
        update_index_df(
            [sys.argv[i].replace("'", "")],
            "",
            plain="EC " + str(sheet_number),
            ec_wl="ECL " + str(sheet_number),
        )


# add data to Index sheet
index_df.to_excel(
    writer, sheet_name="Index", header=False, startrow=2, startcol=2, index=False
)  # first row is empty, therefore starting from 2 insted of 3
worksheet = writer.sheets["Index"]
headers = list(map(lambda x: {"header": x}, index_df.columns))
worksheet.add_table(
    3,
    2,
    3 + index_df.shape[0] - 2,
    1 + index_df.shape[1],
    {
        #'columns' : headers,
        "header_row": False,
        "autofilter": False,
        "style": "Table Style Light 18",
    },
)

# Add link format.
link_format1 = workbook.add_format(
    {
        "font_color": "blue",
        "bold": 1,
        "underline": 0,
        "align": "center",
        #'font_size':  12,
    }
)

link_format2 = workbook.add_format(
    {
        "font_color": "blue",
        "bold": 1,
        "underline": 1,
        "align": "center",
        #'font_size':  12,
    }
)

# header format
header_format = workbook.add_format({"bold": 1, "align": "center"})

# table format
table_format = workbook.add_format(
    {
        "align": "center",
    }
)

# table format
fob_format = workbook.add_format(
    {
        "align": "justify",
    }
)

# spec note format  # -- AC 8/17/2020
ospeci_format = workbook.add_format(
    {
        "align": "left",
        "font_color": "blue",
    }
)

# add links for EC table and EC w Links
worksheet.write_url("E3", "internal:'EC Table'!B3", link_format1, string="EC Table")
worksheet.write_url("F3", "internal:'EC w Links'!B3", link_format2, string="EC w Links")
# Now, iterate through all rows and put the links and format cells
# pdb.set_trace()
for i in range(1, index_df.shape[0]):
    orig_spec_value = index_df.loc[i, "Originating specifier"]
    ec_sheet = index_df.loc[i, "Plain"]
    ecl_sheet = index_df.loc[i, "w Links"]
    if (
        orig_spec_value == "Originating specifier" or orig_spec_value == ""
    ):  # if its a header or empty row, do not add links
        # set bold font
        worksheet.set_row(i + 2, 15, header_format)  # 15 row height
    else:

        worksheet.write_url(
            "E" + str(i + 3),
            "internal:'" + ec_sheet + "'!B3",
            link_format1,
            string=ec_sheet,
        )
        worksheet.write_url(
            "F" + str(i + 3),
            "internal:'" + ecl_sheet + "'!B3",
            link_format2,
            string=ecl_sheet,
        )
        # add originating specifier text to individual sheets
        ws = writer.sheets[ec_sheet]
        ws.write(
            0,
            1,
            orig_spec_value + "   " + "= " + str(index_df["VAR1"][i]),
            ospeci_format,
        )  # -- AC 8/19/2020, 4/15/21
        ws = writer.sheets[ecl_sheet]
        ws.write(
            0,
            1,
            orig_spec_value + "   " + "= " + str(index_df["VAR1"][i]),
            ospeci_format,
        )  # -- AC 8/19/2020

worksheet.set_column("C:F", 10, table_format)
worksheet.set_column("C:C", 30, fob_format)


sheets_lst = ["Index"] + ["Corners"] + ["EC Table"] + ec_lst + ["EC w Links"] + ecl_lst
workbook.worksheets_objs.sort(key=lambda x: sheets_lst.index(x.name))

writer.close()
