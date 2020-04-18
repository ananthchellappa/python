# usage : python3 in_csv.csv col1 col2  newfile_name
# will modify given file and col1,2 exchange places
# note that first col is 0 -- just like list index!!

import csv
import sys
import pdb
from os import  getpid, system

in_csv = sys.argv[1]            # what the user gives us

col1 = int( sys.argv[2] )
col2 = int( sys.argv[3] )

out_csv = "/tmp/" + in_csv.split('/')[-1]
out_csv = out_csv.split('.csv')[0] + str(getpid() ) + '.csv'

#pdb.set_trace()

with open(in_csv, 'r') as infile, open( out_csv, 'w') as outfile:
    # output dict needs a list for new column ordering

	csv_reader = csv.reader( infile )
	fieldnames = next( csv_reader )

	fldn_orig = fieldnames[:]

	fieldnames[col1], fieldnames[col2] = fieldnames[col2], fieldnames[col1]
	writer = csv.DictWriter(outfile, fieldnames=fieldnames)
	# reorder the header first
	writer.writeheader()
	for row in csv.DictReader(infile, fieldnames=fldn_orig):
		# writes the reordered rows to the new file
		writer.writerow(row)
		
system( "mv -f " + out_csv + " " + in_csv ) 	# overwrite
