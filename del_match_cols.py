import pandas as pd
import csv
import sys
# python3 ~/python/del_match_cols.py /tmp/file.csv string_to_look_for_in_unwanted_col

# Read the input CSV file
input_file = sys.argv[1]
with open(input_file, 'r', newline='') as file:
    reader = csv.reader(file)
    row_data = next(reader)  # Read the header row
    row_data = next(reader)  # Read the second row
data = pd.read_csv(input_file, dtype=str)

column_names = data.columns

# Filter the columns based on the second command line argument
string_to_exclude = sys.argv[2]
indices_to_keep = [i for i, col in enumerate(row_data) if string_to_exclude not in col]
# remaining_columns = [col for col in column_names if string_to_exclude not in data.iloc[1][col]]
remaining_columns = [col for i,col in enumerate(column_names) if i in indices_to_keep]

# Overwrite the input CSV file with the remaining columns
data = data[remaining_columns]
data.to_csv(input_file, index=False)
