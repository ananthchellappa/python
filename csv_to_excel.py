import os
import sys
import pandas as pd
import xlsxwriter

#check if the file is correct and exisits
fn = sys.argv[1]
if os.path.exists(fn) and fn[-3:]=='csv':
    print(os.path.basename(fn))
else:
    print("File not found")
    exit()

# Load the CSV file into a DataFrame
df = pd.read_csv(fn)

#Convert csv to excel
writer = pd.ExcelWriter(fn[:-4]+'.xlsx', engine='xlsxwriter')
df.to_excel(
    writer, sheet_name='Testing', startrow=1, startcol=1)

#Load the worksheet object
worksheet = writer.sheets['Testing']

# Get the dimensions of the dataframe.
(max_row, max_col) = df.shape

# Create a list of column headers, to use in add_table().
column_settings = [{'header': column} for column in df.columns]

# Add the Excel table structure. Pandas will add the data.
worksheet.add_table(1, 1, max_row+1, max_col+1, 
        {'columns': column_settings, 
        'style': 'Table Style Light 18'})

writer.close()
