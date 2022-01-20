# usage : python3 add_col_csv.py in_csv.csv col_header col_index value newfile_name
# will generate newfile_name in which col with col_index has specified header and (all same) value

# note that first column is index 0 - so arg on command line should be 0 to operate on column 1 :)

import csv
import sys
import pdb
import re

in_csv = sys.argv[1]            # what the user gives us
header = sys.argv[2]
the_col = int( sys.argv[3] )
value =  sys.argv[4]
out_csv = sys.argv[5]
#pdb.set_trace()

with open(in_csv, 'r') as infile, open( out_csv, 'w') as outfile:
    # output dict needs a list for new column ordering
	csv_reader = csv.reader( infile )
	writer = csv.writer( outfile )

	line = 0
	for row in csv_reader :
		if line > 0 :
			writer.writerow( row[0:the_col] + [str(value )] + row[the_col:] )
		else :
			writer.writerow( row[0:the_col] + [header] + row[the_col:] )
		line = line + 1

