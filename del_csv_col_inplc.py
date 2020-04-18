# usage : python3 in_csv.csv col_index_to_delete  
# will generate in_csv_swapped.csv in which col1,2 exchange places
# note that first col is 0 -- just like list index!!

import csv
import sys
import pdb
from os import  getpid, system

in_csv = sys.argv[1]            # what the user gives us

del_col = int( sys.argv[2] )

out_csv = "/tmp/" + in_csv.split('/')[-1]
out_csv = out_csv.split('.csv')[0] + str(getpid() ) + '.csv'

#pdb.set_trace()

with open(in_csv, 'r') as infile, open( out_csv, 'w') as outfile:
    # output dict needs a list for new column ordering

	csv_reader = csv.reader( infile )

	writer = csv.writer( outfile )
	# reorder the header first
	for row in csv_reader :
		# writes the reordered rows to the new file
		writer.writerow(row[0:del_col] + row[del_col+1:])
		
system( "mv -f " + out_csv + " " + in_csv )     # overwrite
