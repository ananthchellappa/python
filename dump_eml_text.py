import email
from bs4 import BeautifulSoup
import sys
from glob import glob

if not sys.argv[1] :
	dir = "."
else :
	dir = sys.argv[1]

for fil in glob( dir + '/*.eml' ) :
	# print( fil )
	message = email.message_from_file( open(fil) )
	for payload in message.get_payload() :
		html = payload.get_payload( decode=True )
		htm = BeautifulSoup( html )
		print( htm.get_text() )
